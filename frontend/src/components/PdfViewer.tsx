import { useState, useRef, useEffect } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

interface Props { url: string; page?: number; }

export function PdfViewer({ url, page: targetPage }: Props) {
  const [numPages, setNumPages]   = useState(0);
  const [page, setPage]           = useState(1);
  const [loadError, setLoadError] = useState<string | null>(null);
  const containerRef              = useRef<HTMLDivElement>(null);
  const [width, setWidth]         = useState(620);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width || 620));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => { if (targetPage) setPage(targetPage); }, [targetPage]);

  const pageW = Math.min(width - 48, 800);

  return (
    <div className="pdf-shell">
      <div className="pdf-bar">
        <span className="pdf-bar-title">Document</span>
        <div className="pdf-nav">
          <button className="btn-nav" onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1} aria-label="Previous page">‹</button>
          <span className="pdf-page-count">{page} / {numPages || "—"}</span>
          <button className="btn-nav" onClick={() => setPage((p) => Math.min(numPages, p + 1))}
            disabled={page >= numPages} aria-label="Next page">›</button>
        </div>
      </div>

      <div className="pdf-canvas" ref={containerRef}>
        {loadError ? (
          <div className="pdf-state">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" color="var(--red)">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.6"/>
              <path d="M12 8v4M12 16v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <p className="pdf-err">Failed to load PDF<br /><small>{loadError}</small></p>
          </div>
        ) : (
          <Document
            file={url}
            onLoadSuccess={({ numPages: n }) => { setNumPages(n); setLoadError(null); }}
            onLoadError={(err) => setLoadError(err.message || "Unknown error")}
            loading={
              <div className="pdf-state">
                <div className="spin" />
                <span style={{ color: "var(--text-3)", fontSize: 13 }}>Loading PDF…</span>
              </div>
            }
          >
            <div className="pdf-page-shadow">
              <Page pageNumber={page} width={pageW} renderAnnotationLayer renderTextLayer />
            </div>
          </Document>
        )}
      </div>
    </div>
  );
}
