import re
import uuid
from app.config import settings

_MAX_CHARS = 800

_KNOWN_HEADINGS = {
    "abstract", "introduction", "background", "related work", "literature review",
    "methodology", "methods", "approach", "experiments", "results", "evaluation",
    "discussion", "conclusion", "conclusions", "future work", "acknowledgements",
    "acknowledgments", "references", "bibliography", "appendix", "summary",
    "overview", "motivation", "problem statement", "contributions",
    "table of contents", "preface", "foreword",
}


def _is_heading(text: str, etype: str) -> bool:
    if etype == "heading":
        return True
    stripped = text.strip()
    if len(stripped) > 80 or stripped.endswith((".", "?", "!", ",", ";")):
        return False
    lower = stripped.lower()
    if lower in _KNOWN_HEADINGS:
        return True
    if re.match(r"^\d[\d.]*\s+\w", stripped):   # "1. Introduction", "2.1 Methods"
        return True
    if stripped.isupper() and 1 <= len(stripped.split()) <= 6:  # "ABSTRACT"
        return True
    return False


def chunk_elements(elements: list[dict], doc_id: str, session_id: str) -> list[dict]:
    """
    Semantic section-based chunking.

    Each chunk tracks TWO location anchors:
      - buf_page / buf_bbox  : where the chunk starts (heading position)
      - anchor_page / anchor_bbox : first NON-heading content element in the chunk

    Citations use the content anchor so they point to the actual answer text,
    not just the section heading line.
    """
    overlap = settings.chunk_overlap
    chunks: list[dict] = []

    current_heading: str = ""
    buf_text: str = ""
    buf_page: int = 1
    buf_bbox: list = [0, 0, 0, 0]

    # anchor = page/bbox of the first body-content element in the current buffer
    anchor_page: int = 1
    anchor_bbox: list = [0, 0, 0, 0]
    anchor_set: bool = False

    def flush():
        nonlocal buf_text, buf_page, buf_bbox, anchor_page, anchor_bbox, anchor_set
        t = buf_text.strip()
        if t:
            cite_page = anchor_page if anchor_set else buf_page
            cite_bbox = anchor_bbox if anchor_set else buf_bbox
            chunks.append(
                _make_chunk(t, cite_page, cite_bbox, doc_id, session_id, current_heading)
            )
        buf_text = ""
        buf_page = 1
        buf_bbox = [0, 0, 0, 0]
        anchor_page = 1
        anchor_bbox = [0, 0, 0, 0]
        anchor_set = False

    def append_buf(text: str, page: int, bbox: list, is_heading_seed: bool = False):
        nonlocal buf_text, buf_page, buf_bbox, anchor_page, anchor_bbox, anchor_set
        if not buf_text:
            buf_page = page
            buf_bbox = list(bbox)
        else:
            buf_text += "\n\n"
            if page == buf_page:
                buf_bbox = _union(buf_bbox, bbox)
        buf_text += text
        # Record the first body content (non-heading) element as the citation anchor
        if not is_heading_seed and not anchor_set and _bbox_valid(bbox):
            anchor_page = page
            anchor_bbox = list(bbox)
            anchor_set = True

    for elem in elements:
        text = elem.get("text", "").strip()
        etype = elem.get("type", "paragraph")
        page = elem.get("page", 1)
        bbox = elem.get("bbox") or [0, 0, 0, 0]

        if not text:
            continue

        if _is_heading(text, etype):
            flush()
            current_heading = text
            append_buf(text, page, bbox, is_heading_seed=True)
            continue

        projected = len(buf_text) + 2 + len(text) if buf_text else len(text)

        if projected > _MAX_CHARS and buf_text:
            tail = buf_text[-overlap:].strip() if overlap else ""
            flush()
            seed_parts = [p for p in [current_heading, tail, text] if p]
            # Seed inherits the heading position; anchor will be set on first body append
            if current_heading:
                append_buf(current_heading, page, [0, 0, 0, 0], is_heading_seed=True)
                if tail:
                    append_buf(tail, page, [0, 0, 0, 0], is_heading_seed=True)
                append_buf(text, page, bbox)
            else:
                seed = "\n\n".join(seed_parts)
                append_buf(seed, page, bbox)
        else:
            append_buf(text, page, bbox)

    flush()
    return chunks


def _bbox_valid(bbox: list) -> bool:
    return bool(bbox) and any(v != 0 for v in bbox)


def _union(a: list, b: list) -> list:
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _make_chunk(
    text: str, page: int, bbox: list,
    doc_id: str, session_id: str, section: str,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "text": text,
        "payload": {
            "session_id": session_id,
            "doc_id": doc_id,
            "page": page,
            "bbox": bbox,
            "section": section,
            "text": text,
        },
    }
