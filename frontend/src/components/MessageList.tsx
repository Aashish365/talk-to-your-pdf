import { useEffect, useRef } from "react";
import type { Message } from "../types";

interface Props {
  messages: Message[];
  thinking: boolean;
  onCitationClick?: (page: number, docId?: string) => void;
}

export function MessageList({ messages, thinking, onCitationClick }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  return (
    <div className="msg-list">
      {messages.map((m) => (
        <div key={m.message_id} className={`msg ${m.role}`}>
          <div className="msg-row">
            <div className="avatar">{m.role === "user" ? "You" : "AI"}</div>
            <div className="bubble">
              <p style={{ whiteSpace: "pre-wrap" }}>{m.content}</p>
              {m.streaming && <span className="cursor" />}
              {m.citations && m.citations.length > 0 && (
                <div className="citations">
                  {m.citations.map((c, i) => {
                    const label = c.section ? `${c.section} · p.${c.page}` : `p.${c.page}`;
                    return (
                      <button key={i} className="cite-tag"
                        onClick={() => onCitationClick?.(c.page, c.doc_id)}>
                        {label}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}

      {thinking && (
        <div className="msg assistant thinking">
          <div className="msg-row">
            <div className="avatar">AI</div>
            <div className="thinking-inner">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          </div>
        </div>
      )}

      <div ref={endRef} />
    </div>
  );
}
