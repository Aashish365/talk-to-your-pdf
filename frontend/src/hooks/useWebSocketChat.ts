import { useState, useEffect, useRef, useCallback } from "react";
import { ChatSocket } from "../api/ws";
import type { Message, WsIncoming, DocStatus } from "../types";

export function useWebSocketChat(
  sessionId: string | null,
  onDocStatus: (docId: string, state: DocStatus) => void,
  onSessionExpired: () => void,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [connected, setConnected] = useState(false);
  const [thinking, setThinking] = useState(false);
  const socketRef = useRef<ChatSocket | null>(null);

  // Reset state whenever the session changes
  useEffect(() => {
    setMessages([]);
    setThinking(false);
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;

    const socket = new ChatSocket(
      sessionId,
      (msg: WsIncoming) => {
        if (msg.type === "status") {
          onDocStatus(msg.doc_id, msg.state as DocStatus);
          return;
        }
        if (msg.type === "token") {
          setThinking(false);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.streaming) {
              return [...prev.slice(0, -1), { ...last, content: last.content + msg.text }];
            }
            return [...prev, {
              message_id: `streaming-${Date.now()}`,
              role: "assistant",
              content: msg.text,
              timestamp: Date.now() / 1000,
              streaming: true,
            }];
          });
          return;
        }
        if (msg.type === "done") {
          setThinking(false);
          setMessages((prev) =>
            prev.map((m) =>
              m.streaming
                ? { ...m, streaming: false, message_id: msg.message_id, citations: msg.citations }
                : m
            )
          );
          return;
        }
        if (msg.type === "error") {
          setThinking(false);
          // Session expired on the server — silently recreate it
          if (msg.message?.toLowerCase().includes("invalid or expired session")) {
            onSessionExpired();
            return;
          }
          setMessages((prev) => [...prev, {
            message_id: `error-${Date.now()}`,
            role: "assistant",
            content: `Error: ${msg.message}`,
            timestamp: Date.now() / 1000,
          }]);
        }
      },
      () => setConnected(true),
      () => setConnected(false),
    );

    socket.connect();
    socketRef.current = socket;
    return () => { socket.disconnect(); };
  }, [sessionId]);

  const sendMessage = useCallback((content: string) => {
    socketRef.current?.send({ type: "user_message", content });
    setThinking(true);
    setMessages((prev) => [...prev, {
      message_id: `user-${Date.now()}`,
      role: "user",
      content,
      timestamp: Date.now() / 1000,
    }]);
  }, []);

  return { messages, connected, thinking, sendMessage };
}
