import { useRef, useState } from "react";
import type { DocStatus } from "../types";

interface Props {
  onUpload: (file: File) => void;
  status: DocStatus;
  error: string | null;
}

export function Uploader({ onUpload, status, error }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const tryUpload = (file: File) => {
    if (file.type !== "application/pdf") { alert("Only PDF files are accepted"); return; }
    onUpload(file);
  };

  if (status === "processing") {
    return (
      <div className="process-stage">
        <div className="process-card">
          <div className="process-spinner" />
          <p className="process-title">Analyzing your document</p>
          <p className="process-detail">
            Extracting content and building a semantic search index.
            <br />This usually takes 30–60 seconds.
          </p>
          <div className="process-bar"><div className="process-bar-fill" /></div>
        </div>
      </div>
    );
  }

  return (
    <div className="upload-stage">
      <div
        className={`upload-zone${drag ? " drag-over" : ""}${status === "error" ? " state-error" : ""}`}
        role="button" tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) tryUpload(f); }}
      >
        <input ref={inputRef} type="file" accept="application/pdf" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) tryUpload(f); }} />

        <div className="upload-icon-wrap">
          {status === "error" ? (
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.8"/>
              <path d="M12 7v5M12 16v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          ) : (
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
                stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M14 2v6h6M12 12v6M9 15l3-3 3 3"
                stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </div>

        {status === "error" ? (
          <>
            <p className="upload-heading">Upload failed</p>
            <p className="upload-error-text">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                <path d="M7 1.5a5.5 5.5 0 1 0 0 11A5.5 5.5 0 0 0 7 1.5ZM7 4v3.5M7 9.5v.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" fill="none"/>
              </svg>
              {error ?? "Something went wrong"}
            </p>
            <p className="upload-sub">Click to try again</p>
          </>
        ) : (
          <>
            <p className="upload-heading">Drop your PDF here</p>
            <p className="upload-sub">or click to browse from your computer</p>
            <span className="upload-pill">
              <svg width="11" height="11" viewBox="0 0 12 12" fill="currentColor" opacity=".6">
                <path d="M6 1a5 5 0 1 0 0 10A5 5 0 0 0 6 1Zm0 1.5a.75.75 0 1 1 0 1.5.75.75 0 0 1 0-1.5ZM5.25 5.5h1.5v3H5.25V5.5Z"/>
              </svg>
              PDF only · max 50 MB
            </span>
          </>
        )}
      </div>
    </div>
  );
}
