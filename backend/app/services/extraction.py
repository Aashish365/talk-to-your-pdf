import os
import re
import json
import logging
import asyncio
from app.store.files import pdf_path, session_dir

logger = logging.getLogger(__name__)

# Headings that may be run together with their body text in some extractors.
# e.g. "Abstract\n\nThis paper presents..."
_HEADING_PREFIX_RE = re.compile(
    r"^(abstract|introduction|background|related work|literature review|"
    r"methodology|methods|approach|experiments|results|evaluation|"
    r"discussion|conclusion|conclusions|future work|acknowledgements|"
    r"acknowledgments|references|bibliography|appendix|summary|overview)"
    r"\s*[\n:]\s+",
    re.IGNORECASE,
)


async def extract_pdf(sid: str, doc_id: str) -> list[dict]:
    """
    Extract structured elements from a PDF.
    Returns list of {"text", "type", "page", "bbox"}.
    """
    src = pdf_path(sid, doc_id)
    out_dir = session_dir(sid)

    try:
        import opendataloader_pdf
        logger.info("extraction: using opendataloader_pdf for %s", doc_id)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: opendataloader_pdf.convert(
                input_path=[src],
                output_dir=out_dir,
                format="markdown,json",
            ),
        )

        base = os.path.splitext(os.path.basename(src))[0]
        json_path = os.path.join(out_dir, f"{base}.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"ODL JSON not found at {json_path}")

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        elements = _parse_odl_json(data)
        logger.info(
            "extraction: odl produced %d elements; first bbox sample: %s",
            len(elements),
            elements[0]["bbox"] if elements else "n/a",
        )
        return _split_embedded_headings(elements)

    except Exception as exc:
        logger.warning("extraction: opendataloader failed (%s) — falling back to PyMuPDF", exc)
        elements = await _pymupdf_extract(src)
        logger.info("extraction: pymupdf produced %d elements", len(elements))
        return _split_embedded_headings(elements)


# ── opendataloader JSON parsing ────────────────────────────────────────────────

def _parse_odl_json(data) -> list[dict]:
    elements: list[dict] = []

    if isinstance(data, dict):
        for elem in data.get("kids", []):
            _collect_tree(elem, elements)
        return elements

    if isinstance(data, list):
        for elem in data:
            text = (elem.get("content") or elem.get("text", "")).strip()
            if not text:
                continue
            elem_type = _normalise_type(elem.get("type", "paragraph"))
            bbox = (
                elem.get("bounding box")
                or elem.get("bbox")
                or elem.get("coordinates")
                or [0, 0, 0, 0]
            )
            # Normalise bbox: some versions store as {"x1":..} dict or nested list
            bbox = _normalise_bbox(bbox)
            elements.append({
                "text": text,
                "type": elem_type,
                "page": elem.get("page number") or elem.get("page") or 1,
                "bbox": bbox,
            })

    return elements


def _collect_tree(elem: dict, out: list) -> None:
    elem_type = _normalise_type(elem.get("type", "paragraph"))
    content = (elem.get("content") or "").strip()
    if content:
        out.append({
            "text": content,
            "type": elem_type,
            "page": elem.get("page number") or elem.get("page") or 1,
            "bbox": _normalise_bbox(
                elem.get("bounding box") or elem.get("bbox") or [0, 0, 0, 0]
            ),
        })
    for child in elem.get("kids", []):
        _collect_tree(child, out)


def _normalise_bbox(raw) -> list:
    """Accept multiple bbox formats and return [x1, y1, x2, y2]."""
    if isinstance(raw, (list, tuple)):
        flat = list(raw)
        if len(flat) == 4 and all(isinstance(v, (int, float)) for v in flat):
            return [float(v) for v in flat]
        # Nested list of points [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        if len(flat) == 4 and isinstance(flat[0], (list, tuple)):
            xs = [p[0] for p in flat]
            ys = [p[1] for p in flat]
            return [min(xs), min(ys), max(xs), max(ys)]
    if isinstance(raw, dict):
        # {"x1":…, "y1":…, "x2":…, "y2":…}
        if "x1" in raw:
            return [float(raw["x1"]), float(raw["y1"]), float(raw["x2"]), float(raw["y2"])]
        if "left" in raw:
            l, t = float(raw["left"]), float(raw["top"])
            r = l + float(raw.get("width", 0))
            b = t + float(raw.get("height", 0))
            return [l, t, r, b]
    return [0.0, 0.0, 0.0, 0.0]


def _normalise_type(raw: str) -> str:
    t = str(raw).lower()
    if "head" in t or t in ("h1", "h2", "h3", "h4", "title", "subtitle"):
        return "heading"
    if "list" in t or "item" in t or t in ("ul", "ol", "li"):
        return "list"
    return "paragraph"


# ── PyMuPDF fallback ───────────────────────────────────────────────────────────

async def _pymupdf_extract(src: str) -> list[dict]:
    try:
        import fitz
    except ImportError:
        raise RuntimeError("No extraction library available — install opendataloader-pdf or pymupdf")

    loop = asyncio.get_event_loop()

    def _read():
        doc = fitz.open(src)
        out = []
        for page_num, page in enumerate(doc, start=1):
            raw = page.get_text("dict")
            for block in raw.get("blocks", []):
                if block.get("type") != 0:  # 0 = text block
                    continue
                lines = block.get("lines", [])
                if not lines:
                    continue

                block_text = ""
                max_size = 0.0
                has_bold = False

                for line in lines:
                    for span in line.get("spans", []):
                        t = span.get("text", "")
                        block_text += t
                        sz = float(span.get("size", 12))
                        if sz > max_size:
                            max_size = sz
                        font = span.get("font", "").lower()
                        if "bold" in font or "heavy" in font or "black" in font:
                            has_bold = True
                    block_text += " "

                block_text = block_text.strip()
                if not block_text:
                    continue

                # Heuristic: large font or bold + short = heading
                is_heading = (
                    max_size >= 14
                    or (has_bold and len(block_text) < 120)
                )
                elem_type = "heading" if is_heading else "paragraph"

                bbox = list(block.get("bbox", [0, 0, 0, 0]))
                out.append({
                    "text": block_text,
                    "type": elem_type,
                    "page": page_num,
                    "bbox": bbox,
                })
        return out

    return await loop.run_in_executor(None, _read)


# ── Post-processing ────────────────────────────────────────────────────────────

def _split_embedded_headings(elements: list[dict]) -> list[dict]:
    """
    Some extractors return heading + body as one element, e.g.:
      "Abstract\n\nThis paper studies..."
    Split those into a proper heading element + body element.
    """
    result = []
    for elem in elements:
        text = elem["text"]
        m = _HEADING_PREFIX_RE.match(text)
        if m and elem["type"] != "heading":
            heading_text = text[: m.start(1) + len(m.group(1))].strip()
            body_text = text[m.end():].strip()
            result.append({**elem, "text": heading_text, "type": "heading"})
            if body_text:
                result.append({**elem, "text": body_text, "type": "paragraph"})
        else:
            result.append(elem)
    return result
