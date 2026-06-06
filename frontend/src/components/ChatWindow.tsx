import { useState, useRef, useEffect } from "react";
import { MessageList } from "./MessageList";
import type { Message, DocStatus } from "../types";

interface Props {
  messages: Message[];
  connected: boolean;
  docReady: boolean;
  docStatus: DocStatus;
  thinking: boolean;
  onSend: (content: string) => void;
  onCitationClick?: (page: number, docId?: string) => void;
}

export function ChatWindow({
  messages, connected, docReady, docStatus, thinking, onSend, onCitationClick,
}: Props) {
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = messages.some((m) => m.streaming);
  const busy = !connected || !docReady || isStreaming || thinking;

  const submit = () => {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  useEffect(() => {
    if (!isStreaming && !thinking) taRef.current?.focus();
  }, [isStreaming, thinking]);

  const placeholder =
    !connected          ? "Reconnecting…"
    : docStatus === "processing" ? "Analyzing your document…"
    : !docReady         ? "Upload a PDF to start chatting"
    : isStreaming || thinking ? "Generating response…"
    : "Ask anything about your PDF…";

  const statusVisible = docStatus === "processing" || isStreaming || thinking;
  const statusText =
    docStatus === "processing" ? "Analyzing your document…"
    : thinking   ? "Thinking…"
    : isStreaming ? "Generating response…"
    : "";

  const hasMessages = messages.length > 0;

  return (
    <div className="chat-shell">
      {!hasMessages && !thinking ? (
        <div className="chat-welcome">
          <div className="welcome-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10z"
                stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <p className="welcome-title">
            {docStatus === "idle" ? "Start by uploading a PDF" : "Ready to chat"}
          </p>
          <p className="welcome-body">
            {docStatus === "idle"
              ? "Drop a PDF on the left panel. Once processed, ask anything about its contents."
              : "Ask any question — citations will link back to the exact page."}
          </p>
        </div>
      ) : (
        <MessageList messages={messages} thinking={thinking} onCitationClick={onCitationClick} />
      )}

      <div className="chat-foot">
        {statusVisible && (
          <div className="chat-status">
            <span className="status-pulse" />
            <span className="status-label">{statusText}</span>
          </div>
        )}

        <div className="input-row">
          <textarea
            ref={taRef}
            className="chat-ta"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            placeholder={placeholder}
            disabled={busy}
            rows={1}
          />
          <button
            className="btn-send"
            onClick={submit}
            disabled={busy || !text.trim()}
            aria-label="Send message"
          >
            <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
              <path d="M7.5 13V2M2.5 7l5-5 5 5"
                stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
