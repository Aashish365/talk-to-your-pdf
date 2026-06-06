const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function createSession(): Promise<string> {
  const res = await fetch(`${BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to create session");
  const data = await res.json();
  return data.session_id;
}

export async function endSession(sessionId: string): Promise<void> {
  await fetch(`${BASE}/sessions/${sessionId}`, { method: "DELETE" });
}

export async function uploadDocument(
  sessionId: string,
  file: File
): Promise<{ doc_id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/documents`, {
    method: "POST",
    headers: { "x-session-id": sessionId },
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function getDocumentStatus(
  sessionId: string,
  docId: string
): Promise<{ doc_id: string; status: string }> {
  const res = await fetch(`${BASE}/documents/${docId}`, {
    headers: { "x-session-id": sessionId },
  });
  if (!res.ok) throw new Error("Failed to get document status");
  return res.json();
}

export function documentFileUrl(sessionId: string, docId: string): string {
  return `${BASE}/documents/${docId}/file?session_id=${sessionId}`;
}
