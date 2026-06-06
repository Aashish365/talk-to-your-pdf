import json
import uuid
import time
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.store import redis_store
from app.lifecycle import sessions as sess_lifecycle
from app.services.retrieval import retrieve_chunks, build_prompt, filter_citations
from app.services.llm import stream_chat

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/{sid}")
async def websocket_chat(websocket: WebSocket, sid: str):
    await websocket.accept()

    session = await redis_store.get_session(sid)
    if not session:
        await websocket.send_json({"type": "error", "message": "Invalid or expired session"})
        await websocket.close(code=4001)
        return

    await sess_lifecycle.refresh(sid)

    async def send(msg: dict):
        await websocket.send_json(msg)

    # Ping/pong keepalive task
    async def keepalive():
        while True:
            await asyncio.sleep(30)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    keepalive_task = asyncio.create_task(keepalive())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send({"type": "error", "message": "Invalid JSON"})
                continue

            await sess_lifecycle.refresh(sid)

            msg_type = msg.get("type")

            if msg_type == "pong":
                continue

            if msg_type == "user_message":
                content = msg.get("content", "").strip()
                if not content:
                    await send({"type": "error", "message": "content required"})
                    continue

                # Ensure at least one document is ready in this session
                session_data = await redis_store.get_session(sid)
                doc_ids = session_data.get("doc_ids", []) if session_data else []
                has_ready = False
                for did in doc_ids:
                    if await redis_store.get_doc_status(sid, did) == "ready":
                        has_ready = True
                        break
                if not has_ready:
                    await send({"type": "error", "message": "No documents are ready yet"})
                    continue

                # Persist user message
                user_msg = {
                    "message_id": str(uuid.uuid4()),
                    "role": "user",
                    "content": content,
                    "timestamp": int(time.time()),
                }
                await redis_store.append_message(sid, user_msg)

                try:
                    # Step 1: analyze + multi-step retrieval
                    await send({"type": "step", "text": "Analyzing question…"})
                    chunks = await retrieve_chunks(sid, content)

                    # Step 2: build prompt and stream answer
                    await send({"type": "step", "text": "Generating answer…"})
                    history = await redis_store.get_messages(sid)
                    messages = build_prompt(content, chunks, history[:-1])  # exclude the user msg we just added

                    # Stream tokens
                    full_response = ""
                    async for token in stream_chat(messages):
                        full_response += token
                        await send({"type": "token", "text": token})

                    # Only include citations the LLM actually referenced ([1], [2], …)
                    citations = filter_citations(full_response, chunks)

                    message_id = str(uuid.uuid4())
                    await send({"type": "done", "message_id": message_id, "citations": citations})

                    # Persist assistant message
                    assistant_msg = {
                        "message_id": message_id,
                        "role": "assistant",
                        "content": full_response,
                        "timestamp": int(time.time()),
                        "citations": citations,
                    }
                    await redis_store.append_message(sid, assistant_msg)

                except Exception as e:
                    logger.error("Chat error for session %s: %s", sid, e)
                    await send({"type": "error", "message": str(e)})

            elif msg_type == "cancel":
                # Generation cancellation not yet implemented
                pass

            else:
                await send({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", sid)
    except Exception as e:
        logger.error("WebSocket error for session %s: %s", sid, e)
    finally:
        keepalive_task.cancel()
