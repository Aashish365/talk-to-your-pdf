# Chat-with-PDF — Project Build Instructions

> Agent-facing specification. This document is the single source of truth for building the platform. Read it fully before writing code. Follow the pinned tech choices, data model, and lifecycle rules exactly — they are deliberate, not suggestions.

---

## 1. What we are building

A web platform where a user uploads a PDF and then chats with it. The user asks questions in natural language and gets answers grounded in the document, streamed back **token by token**. Answers carry **citations** that point to the exact page and region of the source PDF.

The entire system runs **locally** — no cloud LLM, no external API calls for inference. It is **session-scoped and ephemeral**: nothing persists beyond the life of a session. When a session ends or goes idle, every trace of it (conversation, vectors, uploaded files) is deleted.

---

## 2. Core principles (do not violate)

1. **Fully local.** PDF parsing, embeddings, and generation all run on the local machine. No third-party inference APIs.
2. **Ephemeral / session-only.** No user accounts, no login, no PII, no long-term storage. A session is an anonymous random token. All data is keyed to it.
3. **Delete everything on session end.** When a session expires (idle timeout) or is explicitly ended, cascade-delete its Redis keys, its Qdrant vectors, and its disk files. No orphans.
4. **Token-by-token streaming.** Responses are streamed incrementally over a WebSocket so the UI renders the answer as it is generated. Never buffer the full answer and send it at once.
5. **Grounded answers with citations.** Every assistant answer is built from retrieved chunks and reports the page + bounding box of its sources.
6. **Prompt-injection aware.** Keep OpenDataLoader's built-in hidden-text / injection filter enabled, since extracted text is fed straight into the LLM.

---

## 3. Goals and non-goals

**Goals**

- Upload a PDF, process it into a searchable form, and chat against it within one session.
- Sub-second perceived latency for the first streamed token where hardware allows.
- Clean, automatic teardown of all session data.

**Non-goals (out of scope for v1)**

- User authentication / accounts / persistent history across sessions.
- Multi-tenant scaling across many backend instances (single instance is fine for v1).
- Cloud deployment, billing, analytics.
- Editing or generating PDFs (read-only ingestion only).

---

## 4. Tech stack (pinned)

| Layer                        | Choice                              | Notes                                                                                           |
| ---------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------- |
| Frontend                     | React + Vite                        | TypeScript. Chat UI, uploader, PDF viewer.                                                      |
| Backend                      | Python + FastAPI (async)            | Native WebSocket + background tasks.                                                            |
| PDF extraction               | OpenDataLoader PDF (Python wrapper) | Requires **Java 11+** runtime on the backend host. Outputs Markdown + JSON with bounding boxes. |
| LLM + embeddings             | Ollama                              | Local. Generation model + dedicated embedding model.                                            |
| Vector store                 | Qdrant                              | Single collection, per-document/session filtering via payload.                                  |
| Conversation + session store | Redis                               | In-memory, native TTL. Holds messages, session metadata, expiry index.                          |
| File storage                 | Local disk                          | Per-session folder.                                                                             |

**Models (Ollama):**

- Generation: `llama3.1` (or `qwen2.5`) — configurable.
- Embeddings: `nomic-embed-text` (or `mxbai-embed-large`) — **fixed once anything is indexed**; changing it invalidates all stored vectors.

There is intentionally **no relational database** (no Postgres). Because nothing outlives the session, Redis + Qdrant + disk is sufficient.

---

## 5. Architecture overview

Two pipelines share the FastAPI backend, Qdrant, and the session.

**Ingestion (on upload):**

```
Browser (React) → FastAPI (store file + create session doc record)
  → OpenDataLoader (PDF → Markdown + JSON w/ bboxes)
  → Chunk + embed (via Ollama embeddings)
  → Upsert into Qdrant (payload: session_id, doc_id, page, bbox, text)
```

Runs as a **background job**; the upload endpoint returns immediately with status `processing`. The UI polls or receives WS `status` events until `ready`.

**Query (on each chat message):**

```
Browser → WebSocket → FastAPI
  → embed question → Qdrant top-k search (filtered by session_id + doc_id)
  → build prompt (retrieved context + chat history)
  → Ollama generate (stream=true)
  → stream tokens back over WS → React renders live
  → on completion: send citations (page + bbox), persist assistant message to Redis
```

---

## 6. Data storage model

Everything hangs off a single anonymous `session_id` (random UUID, held client-side in a cookie or localStorage).

### 6.1 Redis

| Key               | Type           | Contents                                        | TTL                 |
| ----------------- | -------------- | ----------------------------------------------- | ------------------- |
| `session:{sid}`   | hash           | `created_at`, `expires_at`, `status`, `doc_ids` | sliding             |
| `conv:{sid}`      | list (or JSON) | ordered chat messages                           | sliding             |
| `docs:{sid}`      | set            | document ids in this session                    | sliding             |
| `sessions:expiry` | sorted set     | member = `sid`, score = `expires_at` (unix ts)  | n/a (sweeper index) |

**Message shape** (each entry in `conv:{sid}`):

```json
{
  "message_id": "uuid",
  "role": "user | assistant",
  "content": "string",
  "timestamp": 1730000000,
  "citations": [{ "doc_id": "...", "page": 4, "bbox": [x1, y1, x2, y2] }]
}
```

`citations` is present only on assistant messages.

### 6.2 Qdrant

Single collection, e.g. `documents`. One point per chunk.

```json
{
  "id": "chunk-uuid",
  "vector": [ ... embedding ... ],
  "payload": {
    "session_id": "sid",
    "doc_id": "doc-uuid",
    "page": 4,
    "bbox": [x1, y1, x2, y2],
    "text": "chunk text"
  }
}
```

- Retrieval filters by `session_id` **and** `doc_id`.
- Cleanup deletes by filter `session_id == sid` (delete-by-filter).
- (Alternative if hard isolation is later required: one collection per session, dropped on cleanup. Default to the single-collection + filter approach for v1.)

### 6.3 Disk

```
/data/sessions/{sid}/
  ├── {doc_id}.pdf          # original upload
  └── {doc_id}.md           # (optional) extracted markdown cache
```

---

## 7. Session lifecycle and cleanup

### 7.1 Lifecycle

1. **Create** — generate `session_id`; write `session:{sid}` with `expires_at = now + IDLE_TTL`; `ZADD sessions:expiry expires_at sid`; create `/data/sessions/{sid}/`.
2. **Active** — every inbound action (upload, chat message, WS message) refreshes the session: recompute `expires_at`, update the sorted-set score, and refresh TTLs on the Redis keys. This is **sliding expiration** — an active session never dies.
3. **Idle expiry** — when `now > expires_at` and no activity, the session is eligible for cleanup. Detected by the sweeper (below).
4. **Explicit end** — user clicks "end", logs out, or closes the tab (caught via `beforeunload`). Runs cleanup **immediately**.
5. **Socket disconnect** — do **not** delete immediately (refreshes/network blips drop sockets). Treat disconnect as "start the idle clock"; reconnection within the window refreshes and resumes.

Config: `IDLE_TTL` default 30 min. Optional `MAX_SESSION_AGE` hard cap so a session can't be extended forever.

### 7.2 Cleanup — the sweeper is the source of truth

A background task runs every 30–60s:

```
expired = ZRANGEBYSCORE sessions:expiry -inf now
for sid in expired:
    qdrant.delete(filter = session_id == sid)     # vectors
    rm -rf /data/sessions/{sid}/                   # files
    DEL session:{sid} conv:{sid} docs:{sid}        # redis
    ZREM sessions:expiry sid
```

**Do not** rely on Redis key expiry or keyspace notifications to clean Qdrant/disk:

- Expiry events are best-effort and can be missed.
- They only affect Redis keys; they cannot touch Qdrant or the filesystem.
- Use keyspace notifications, if at all, only as an optional fast-path nudge that calls the same cleanup function. The sweeper is the guarantee.

The cleanup function must be **idempotent** (safe to run twice on the same `sid`).

---

## 8. WebSocket protocol

One WebSocket connection per session.

- **Handshake / auth:** client passes `session_id` (query param or first message). Reject if missing, invalid, or expired.
- **Every inbound message refreshes the session TTL.**
- **Heartbeat:** implement ping/pong keepalive; the client owns reconnection (WS does not auto-reconnect like SSE).

**Client → server**

```json
{ "type": "user_message", "doc_id": "...", "content": "user question" }
{ "type": "cancel" }                       // optional: stop current generation
```

**Server → client**

```json
{ "type": "status", "doc_id": "...", "state": "processing | ready | error" }
{ "type": "token", "text": "next token" }  // many of these, in order
{ "type": "done", "message_id": "...", "citations": [ { "doc_id": "...", "page": 4, "bbox": [x1,y1,x2,y2] } ] }
{ "type": "error", "message": "..." }
```

Generation loop: iterate Ollama's streamed chunks (`stream=true`), emit one `token` per chunk, then a single `done` with citations. After `done`, persist the full assistant message to `conv:{sid}`.

> Scaling note (not needed for v1 single instance): if you ever run more than one backend process, add Redis pub/sub as a backplane so the socket process and the generation worker can communicate.

---

## 9. Ingestion pipeline (detailed)

1. **Receive upload** (`POST /documents`, multipart). Validate type/size. Create `doc_id`. Save to `/data/sessions/{sid}/{doc_id}.pdf`. Add to `docs:{sid}`. Set doc status `processing`. Return immediately.
2. **Extract** with OpenDataLoader → Markdown + JSON. Keep the JSON: it carries per-element bounding boxes `[x1,y1,x2,y2]` and page numbers. Keep the **prompt-injection / hidden-text filter enabled**. For scanned PDFs, use hybrid mode (`--force-ocr`, `--ocr-lang` as needed).
3. **Chunk** along document structure (headings/sections) with small overlap — not blind fixed-size splits. Preserve `page` and `bbox` metadata on every chunk.
4. **Embed** each chunk via the Ollama embedding model.
5. **Upsert** points into Qdrant with the payload from §6.2.
6. **Mark ready** — update doc status to `ready`; emit WS `status: ready`.

Run steps 2–6 in a background task. A 200-page PDF parses in seconds, but embedding takes longer — never block the HTTP request on it.

---

## 10. Query / RAG pipeline (detailed)

1. Receive `user_message` over WS. Refresh session TTL. Persist the user message to `conv:{sid}`.
2. Embed the question (Ollama embeddings).
3. Qdrant top-k similarity search, filtered by `session_id` AND `doc_id`.
4. Build the prompt: system instruction + retrieved chunks (as context, with their page refs) + recent chat history from `conv:{sid}`.
5. Call Ollama generation with `stream=true`.
6. Stream each chunk as a WS `token` event.
7. On completion, send `done` with `citations` derived from the retrieved chunks' payloads (page + bbox). Persist the assistant message (with citations) to `conv:{sid}`.

---

## 11. Endpoints

**HTTP (FastAPI)**

- `POST /sessions` → create session, return `session_id`.
- `DELETE /sessions/{sid}` → explicit end → immediate cleanup.
- `POST /documents` → upload PDF (multipart), returns `doc_id` + status.
- `GET /documents/{doc_id}` → processing status (polling fallback for the UI).
- `GET /documents/{doc_id}/file` → serve original PDF for the viewer.

**WebSocket**

- `WS /ws/{sid}` → chat channel (protocol in §8).

---

## 12. Project structure

```
pdf-chat/
├── docker-compose.yml          # backend + ollama + qdrant + redis
├── .env                        # configuration (see §13)
├── frontend/                   # React + Vite (TypeScript)
│   └── src/
│       ├── components/         # ChatWindow, MessageList, Uploader, PdfViewer
│       ├── hooks/              # useSession, useWebSocketChat, useUpload
│       ├── api/                # http + ws clients
│       └── types/              # shared message/citation types
└── backend/
    └── app/
        ├── main.py             # FastAPI app, route + ws registration
        ├── config.py           # env-driven settings
        ├── api/
        │   ├── sessions.py
        │   ├── documents.py
        │   └── ws.py           # WebSocket chat endpoint
        ├── services/
        │   ├── extraction.py   # OpenDataLoader wrapper
        │   ├── chunking.py
        │   ├── embeddings.py   # Ollama embeddings
        │   ├── retrieval.py    # Qdrant search + upsert
        │   └── llm.py          # Ollama streaming generation
        ├── store/
        │   ├── redis_store.py  # sessions, conversations, expiry index
        │   ├── qdrant_store.py # collection mgmt, delete-by-filter
        │   └── files.py        # per-session disk ops
        ├── lifecycle/
        │   ├── sessions.py     # create / refresh / end
        │   └── sweeper.py      # periodic cleanup task
        └── workers/
            └── ingest.py       # background ingestion job
```

---

## 13. Configuration (.env)

```
# Server
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
DATA_DIR=/data/sessions

# Session
IDLE_TTL_SECONDS=1800
MAX_SESSION_AGE_SECONDS=0        # 0 = no hard cap
SWEEPER_INTERVAL_SECONDS=45

# Redis
REDIS_URL=redis://redis:6379/0

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=documents

# Ollama
OLLAMA_URL=http://ollama:11434
OLLAMA_GEN_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text

# Retrieval
TOP_K=5
CHUNK_OVERLAP=80

# Upload limits
MAX_UPLOAD_MB=50
```

---

## 14. Local deployment

**Prerequisites on the backend host/container:** Python 3.11+, **Java 11+** (required by OpenDataLoader's core engine), and Ollama with the two models pulled (`ollama pull llama3.1`, `ollama pull nomic-embed-text`).

`docker-compose.yml` should run four services: `backend`, `ollama`, `qdrant`, `redis`. The `backend` image must include both Python and a JRE. Persist `DATA_DIR`, Qdrant storage, and Ollama models as volumes for dev convenience (note: session data is still wiped by the sweeper — volumes are just so the containers survive restarts).

`pip install opendataloader-pdf` (add the `[hybrid]` extra and configure OCR languages only if scanned-PDF support is needed).

---

## 15. Build plan (phased)

Build and verify in order; each phase should run end-to-end before the next.

1. **Skeleton** — FastAPI app, Vite app, docker-compose with all four services up and healthy.
2. **Sessions** — create/end session endpoints; Redis session record + expiry sorted set; sweeper task (verify it cleans an expired session's Redis keys + disk folder).
3. **Upload + extract** — upload endpoint, disk storage, OpenDataLoader extraction to Markdown/JSON (confirm bounding boxes are captured).
4. **Index** — chunking + Ollama embeddings + Qdrant upsert with payload; background ingestion job; status reporting.
5. **Retrieval** — embed question, Qdrant filtered top-k search; assemble prompt.
6. **WebSocket + streaming** — WS endpoint, Ollama `stream=true`, token events, `done` with citations; React renders tokens live.
7. **Conversation persistence** — store user/assistant messages in `conv:{sid}`; load history into prompts.
8. **Cleanup integration** — confirm cascade deletes Qdrant points + Redis keys + disk files on both idle expiry and explicit end. Verify idempotency.
9. **Citations UI** — PDF viewer highlights cited regions using page + bbox.
10. **Hardening** — heartbeat/reconnect, upload limits, error events, disconnect grace.

---

## 16. Coding conventions and guardrails

- Backend is **async** throughout; never block the event loop on extraction/embedding — use background tasks.
- All session-scoped operations take `session_id` and enforce it in every Qdrant filter — a session must never see another session's data.
- The cleanup function is **idempotent** and is the only place that deletes session data; call it from both the sweeper and the explicit-end path.
- Stream tokens as they arrive; do not accumulate and flush at the end.
- Pin the embedding model in config and treat it as immutable for the life of any index.
- Keep secrets/config in `.env`; no hardcoded URLs or model names.
- Frontend and backend share the WS message/citation type definitions (keep them in sync).

---

## 17. Security and privacy

- **No PII, no accounts.** Sessions are anonymous random tokens.
- **No data leaves the machine** — all inference is local via Ollama.
- **Prompt-injection filter on** during extraction (OpenDataLoader filters hidden text and injection attempts).
- **Guaranteed teardown** — the sweeper plus explicit-end path ensure no session data outlives its session, on disk or in either datastore.
- Validate upload type and size; reject non-PDF and oversized files.

---

## 18. Definition of done (v1)

- A user can open the app (anonymous session created), upload a PDF, watch it reach `ready`, ask questions, and receive answers streamed token by token over a WebSocket.
- Answers include citations that highlight the correct page/region in the PDF viewer.
- Retrieval is correctly scoped to the session and document.
- When the session goes idle past `IDLE_TTL` or is explicitly ended, all of its Qdrant vectors, Redis keys, and disk files are deleted, verified by inspection.
- The whole stack runs locally via `docker-compose up` with no external inference calls.
