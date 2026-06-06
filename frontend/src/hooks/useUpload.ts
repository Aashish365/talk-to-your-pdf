import { useState, useEffect, useCallback } from "react";
import { uploadDocument, getDocumentStatus } from "../api/http";
import type { DocEntry, DocStatus } from "../types";

export function useUpload(sessionId: string | null) {
  const [docs, setDocs] = useState<DocEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Reset when session changes
  useEffect(() => {
    setDocs([]);
    setError(null);
  }, [sessionId]);

  const upload = useCallback(async (file: File) => {
    if (!sessionId) return;
    setError(null);

    const tempId = `tmp-${Date.now()}`;
    setDocs((prev) => [...prev, { docId: tempId, name: file.name, status: "processing" }]);

    try {
      const result = await uploadDocument(sessionId, file);

      setDocs((prev) =>
        prev.map((d) =>
          d.docId === tempId
            ? { docId: result.doc_id, name: file.name, status: "processing" }
            : d
        )
      );

      const poll = setInterval(async () => {
        const s = await getDocumentStatus(sessionId, result.doc_id).catch(() => null);
        if (!s) return;
        if (s.status === "ready" || s.status === "error") {
          setDocs((prev) =>
            prev.map((d) =>
              d.docId === result.doc_id ? { ...d, status: s.status as DocStatus } : d
            )
          );
          if (s.status === "error") setError("Processing failed");
          clearInterval(poll);
        }
      }, 2000);
    } catch (e) {
      setDocs((prev) => prev.filter((d) => d.docId !== tempId));
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  }, [sessionId]);

  // Allow WebSocket status events to override polling
  const setDocStatus = useCallback((docId: string, state: DocStatus) => {
    setDocs((prev) =>
      prev.map((d) => (d.docId === docId ? { ...d, status: state } : d))
    );
  }, []);

  const anyReady = docs.some((d) => d.status === "ready");
  const anyProcessing = docs.some((d) => d.status === "processing");

  return { docs, anyReady, anyProcessing, error, upload, setDocStatus };
}
