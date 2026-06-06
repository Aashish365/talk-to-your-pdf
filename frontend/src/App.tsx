import { useRef, useState, useEffect } from "react";
import { useSession } from "./hooks/useSession";
import { useUpload } from "./hooks/useUpload";
import { useWebSocketChat } from "./hooks/useWebSocketChat";
import { Uploader } from "./components/Uploader";
import { ChatWindow } from "./components/ChatWindow";
import { PdfViewer } from "./components/PdfViewer";
import { documentFileUrl } from "./api/http";
import type { DocEntry, DocStatus } from "./types";
import "./App.css";

export default function App() {
  const { sessionId, loading, clearSession, resetSession } = useSession();
  const { docs, anyReady, anyProcessing, error, upload, setDocStatus } = useUpload(sessionId);

  const [activePdfDocId, setActivePdfDocId] = useState<string | null>(null);
  const [citationPage, setCitationPage] = useState<number | undefined>();

  // Auto-select the first PDF that becomes ready
  useEffect(() => {
    if (!activePdfDocId) {
      const first = docs.find((d) => d.status === "ready");
      if (first) setActivePdfDocId(first.docId);
    }
  }, [docs, activePdfDocId]);

  // Reset viewer state on new session
  useEffect(() => {
    setActivePdfDocId(null);
    setCitationPage(undefined);
  }, [sessionId]);

  const handleDocStatus = (docId: string, state: DocStatus) => {
    setDocStatus(docId, state);
  };

  const { messages, connected, thinking, thinkingStep, sendMessage } = useWebSocketChat(
    sessionId,
    handleDocStatus,
    resetSession,
  );

  const handleSend = (content: string) => {
    if (anyReady) sendMessage(content);
  };

  const handleCitationClick = (page: number, docId?: string) => {
    if (docId) setActivePdfDocId(docId);
    setCitationPage(page);
  };

  if (loading || !sessionId) {
    return (
      <div className="app-boot">
        <div className="spin" />
        <span>Starting session…</span>
      </div>
    );
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-brand">
          <img src="/logo.png" alt="TalkToPDF logo" className="brand-logo" />
          <span className="brand-name">
            <span className="brand-talk">Talk</span> to your{" "}
            <span className="brand-pdf">PDF</span>
          </span>
        </div>
        <div className="header-actions">
          <span className={`conn-badge ${connected ? "online" : "offline"}`}>
            <span className="conn-dot" />
            {connected ? "Connected" : "Disconnected"}
          </span>
          <button className="btn-session" onClick={clearSession}>New session</button>
        </div>
      </header>

      {/* Workspace */}
      <div className="workspace">
        {/* Left pane – PDF viewer */}
        <div className="pane pane-left">
          {anyReady && activePdfDocId ? (
            <>
              <PdfViewer
                url={documentFileUrl(sessionId, activePdfDocId)}
                page={citationPage}
              />
              <PdfDock
                docs={docs}
                activePdfDocId={activePdfDocId}
                onSwitch={(docId) => { setActivePdfDocId(docId); setCitationPage(undefined); }}
                onAdd={upload}
              />
            </>
          ) : anyProcessing ? (
            <Uploader onUpload={upload} status="processing" error={null} />
          ) : (
            <Uploader onUpload={upload} status={docs[0]?.status ?? "idle"} error={error} />
          )}
        </div>

        {/* Right pane – Chat */}
        <div className="pane pane-right">
          <ChatWindow
            messages={messages}
            connected={connected}
            docReady={anyReady}
            docStatus={anyProcessing ? "processing" : anyReady ? "ready" : "idle"}
            thinking={thinking}
            thinkingStep={thinkingStep}
            onSend={handleSend}
            onCitationClick={(page, docId) => handleCitationClick(page, docId)}
          />
        </div>
      </div>
    </div>
  );
}

/* ── PDF Dock ─────────────────────────────────────────────────── */
function PdfDock({
  docs, activePdfDocId, onSwitch, onAdd,
}: {
  docs: DocEntry[];
  activePdfDocId: string | null;
  onSwitch: (docId: string) => void;
  onAdd: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const statusIcon = (status: DocEntry["status"]) => {
    if (status === "processing") return "⟳";
    if (status === "error") return "✕";
    return null;
  };

  return (
    <div className="pdf-dock">
      {docs.map((doc) => (
        <button
          key={doc.docId}
          className={`pdf-tab ${doc.docId === activePdfDocId ? "active" : ""} ${doc.status}`}
          onClick={() => doc.status === "ready" && onSwitch(doc.docId)}
          title={doc.name}
        >
          <span>{doc.name}</span>
          {statusIcon(doc.status) && <em style={{ fontStyle: "normal" }}>{statusIcon(doc.status)}</em>}
        </button>
      ))}
      <button className="pdf-add-btn" onClick={() => inputRef.current?.click()}>
        + Add PDF
      </button>
      <input
        ref={inputRef} type="file" accept="application/pdf" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) { onAdd(f); e.target.value = ""; } }}
      />
    </div>
  );
}
