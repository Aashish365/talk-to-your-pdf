import { useState, useEffect, useCallback } from "react";
import { createSession, endSession } from "../api/http";

const SESSION_KEY = "pdf_chat_session_id";

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem(SESSION_KEY)
  );
  const [loading, setLoading] = useState(!localStorage.getItem(SESSION_KEY));

  // Create a new session whenever sessionId is null
  useEffect(() => {
    if (sessionId) return;
    setLoading(true);
    createSession().then((sid) => {
      localStorage.setItem(SESSION_KEY, sid);
      setSessionId(sid);
      setLoading(false);
    });
  }, [sessionId]);

  // Manual "New session" — ends the current one on the server first
  const clearSession = useCallback(async () => {
    if (sessionId) {
      await endSession(sessionId).catch(() => {});
    }
    localStorage.removeItem(SESSION_KEY);
    setSessionId(null);
  }, [sessionId]);

  // Silent reset — used when the server already expired the session.
  // No DELETE call; just forget the ID and let the useEffect above create a new one.
  const resetSession = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    setSessionId(null);
  }, []);

  // Best-effort cleanup on tab close
  useEffect(() => {
    const handler = () => {
      if (sessionId)
        navigator.sendBeacon(`/sessions/${sessionId}`, JSON.stringify({ _method: "DELETE" }));
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [sessionId]);

  return { sessionId, loading, clearSession, resetSession };
}
