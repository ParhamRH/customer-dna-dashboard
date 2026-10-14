"""Document extraction: PDF (PyMuPDF + Tesseract OCR fallback), DOCX/PPTX (OOXML), text/Markdown.

If Docling is installed (`pip install .[docling]`) it is used first for PDFs/DOCX/PPTX because it
recovers richer structure (reading order, tables). PyMuPDF remains the always-available path.
"""
from __future__ import annotations

import io
import re
import shutil
import statistics
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.config import get_settings


@dataclass
class Page:
    number: int
    text: str
    headings: list[str] = field(default_factory=list)
    ocr: bool = False
    tables: list[str] = field(default_factory=list)  # markdown


@dataclass
class ExtractedDocument:
    engine: str
    metadata: dict[str, Any]
    pages: list[Page]
    headings: list[dict[str, Any]]
    images: list[tuple[int, bytes, str]] = field(default_factory=list)  # (page, bytes, ext)
    renders: list[tuple[int, bytes]] = field(default_factory=list)  # (page, png bytes)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text)


def docling_available() -> bool:
    try:
        import docling  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def tesseract_available() -> bool:
    return shutil.which(get_settings().tesseract_binary) is not None


def ocr_png(png: bytes, lang: str = "eng") -> str:
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "page.png"
        src.write_bytes(png)
        p = subprocess.run(
            [get_settings().tesseract_binary, str(src), "stdout", "-l", lang, "--psm", "3"],
            capture_output=True,
            timeout=180,
            check=False,
        )
        return p.stdout.decode(errors="ignore").strip() if p.returncode == 0 else ""


def extract_pdf(path: Path, render_pages: int | None = None, max_images: int = 24) -> ExtractedDocument:
    import pymupdf

    render_pages = render_pages if render_pages is not None else get_settings().max_document_pages_rendered
    doc = pymupdf.open(str(path))
    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    meta["page_count"] = doc.page_count
    meta["encrypted"] = doc.is_encrypted
    toc = doc.get_toc(simple=True) or []
    headings: list[dict[str, Any]] = [{"level": lvl, "text": t.strip(), "page": pg} for lvl, t, pg in toc if t.strip()]
    pages: list[Page] = []
    renders: list[tuple[int, bytes]] = []
    images: list[tuple[int, bytes, str]] = []
    seen_xrefs: set[int] = set()
    sizes: list[float] = []
    span_cache: list[list[tuple[float, str, bool]]] = []
    for page in doc:
        d = page.get_text("dict")
        spans = []
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                txt = "".join(s["text"] for s in line.get("spans", [])).strip()
                if not txt:
                    continue
                size = max(s["size"] for s in line["spans"])
                bold = any("bold" in s.get("font", "").lower() or (s.get("flags", 0) & 16) for s in line["spans"])
                spans.append((size, txt, bold))
                sizes.append(size)
        span_cache.append(spans)
    body = statistics.median(sizes) if sizes else 11.0
    use_font_headings = not headings
    for page, spans in zip(doc, span_cache, strict=True):
        n = page.number + 1
        text = page.get_text("text").strip()
        ocr = False
        if not text and tesseract_available():
            pix = page.get_pixmap(dpi=200)
            text = ocr_png(pix.tobytes("png"))
            ocr = bool(text)
        page_heads = [t for size, t, bold in spans if (size >= body * 1.25 or (bold and size >= body * 1.1)) and len(t) < 140]
        if use_font_headings:
            for t in page_heads:
                size = next(s for s, tt, _ in spans if tt == t)
                headings.append({"level": 1 if size >= body * 1.6 else 2, "text": t, "page": n})
        tables = []
        try:
            for tab in page.find_tables().tables[:5]:
                md = tab.to_markdown()
                if md and md.count("|") > 4:
                    tables.append(md)
        except Exception:  # noqa: BLE001
            pass
        pages.append(Page(number=n, text=text, headings=page_heads[:20], ocr=ocr, tables=tables))
        if page.number < render_pages:
            renders.append((n, page.get_pixmap(dpi=96).tobytes("png")))
        if len(images) < max_images:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                try:
                    data = doc.extract_image(xref)
                except Exception:  # noqa: BLE001
                    continue
                if data and data.get("width", 0) >= 96 and data.get("height", 0) >= 96:
                    images.append((n, data["image"], data.get("ext", "png")))
                if len(images) >= max_images:
                    break
    meta["ocr_pages"] = [p.number for p in pages if p.ocr]
    meta["table_count"] = sum(len(p.tables) for p in pages)
    meta["word_count"] = sum(len(p.text.split()) for p in pages)
    doc.close()
    return ExtractedDocument("pymupdf", meta, pages, headings, images, renders)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_CP = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dcterms": "http://purl.org/dc/terms/",
}


def _core_props(z: zipfile.ZipFile) -> dict[str, Any]:
    try:
        root = ET.fromstring(z.read("docProps/core.xml"))
    except KeyError:
        return {}
    out = {}
    for key, tag in (("title", "dc:title"), ("author", "dc:creator"), ("subject", "dc:subject"),
                     ("keywords", "cp:keywords"), ("created", "dcterms:created"), ("modified", "dcterms:modified")):
        el = root.find(tag, _CP)
        if el is not None and el.text:
            out[key] = el.text
    return out


def extract_docx(path: Path) -> ExtractedDocument:
    with zipfile.ZipFile(path) as z:
        meta = _core_props(z)
        root = ET.fromstring(z.read("word/document.xml"))
        media = [(1, z.read(n), Path(n).suffix.lstrip(".")) for n in z.namelist() if n.startswith("word/media/")][:24]
    paras, headings = [], []
    for p in root.iter(f"{_W}p"):
        style = p.find(f"{_W}pPr/{_W}pStyle")
        sval = style.get(f"{_W}val", "") if style is not None else ""
        txt = "".join(t.text or "" for t in p.iter(f"{_W}t")).strip()
        if not txt:
            continue
        m = re.match(r"(?i)heading\s*(\d)|title", sval)
        if m:
            headings.append({"level": int(m.group(1)) if m.group(1) else 1, "text": txt, "page": 1})
            paras.append(f"{'#' * (int(m.group(1)) if m.group(1) else 1)} {txt}")
        else:
            paras.append(txt)
    text = "\n\n".join(paras)
    meta.update({"page_count": None, "word_count": len(text.split())})
    return ExtractedDocument("ooxml", meta, [Page(1, text, [h["text"] for h in headings])], headings, media)


def extract_pptx(path: Path) -> ExtractedDocument:
    with zipfile.ZipFile(path) as z:
        meta = _core_props(z)
        slides = sorted(
            (n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
            key=lambda n: int(re.findall(r"\d+", n)[-1]),
        )
        pages, headings = [], []
        for i, name in enumerate(slides, start=1):
            root = ET.fromstring(z.read(name))
            paras = ["".join(t.text or "" for t in p.iter(f"{_A}t")).strip() for p in root.iter(f"{_A}p")]
            paras = [p for p in paras if p]
            if paras:
                headings.append({"level": 1, "text": paras[0][:140], "page": i})
            pages.append(Page(i, "\n".join(paras), paras[:1]))
        media = [(1, z.read(n), Path(n).suffix.lstrip(".")) for n in z.namelist() if n.startswith("ppt/media/")][:24]
    meta.update({"page_count": len(pages), "slide_count": len(pages), "word_count": sum(len(p.text.split()) for p in pages)})
    return ExtractedDocument("ooxml", meta, pages, headings, media)


def extract_text(path: Path, markdown: bool) -> ExtractedDocument:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    headings = []
    if markdown:
        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(.*)", line)
            if m:
                headings.append({"level": len(m.group(1)), "text": m.group(2).strip(), "page": 1})
    meta = {"page_count": 1, "word_count": len(text.split()), "encoding": "utf-8"}
    return ExtractedDocument("text", meta, [Page(1, text.strip(), [h["text"] for h in headings])], headings)


def extract_with_docling(path: Path) -> ExtractedDocument | None:
    if not docling_available():
        return None
    try:
        from docling.document_converter import DocumentConverter

        result = DocumentConverter().convert(str(path))
        md = result.document.export_to_markdown()
        headings = [
            {"level": len(m.group(1)), "text": m.group(2).strip(), "page": None}
            for m in re.finditer(r"^(#{1,6})\s+(.+)$", md, re.M)
        ]
        return ExtractedDocument("docling", {"word_count": len(md.split())}, [Page(1, md)], headings)
    except Exception:  # noqa: BLE001
        return None


def extract(path: Path, mime: str) -> ExtractedDocument:
    if mime == "application/pdf":
        doc = extract_pdf(path)
        dl = extract_with_docling(path)
        if dl:  # keep PyMuPDF renders/images/pages, adopt Docling's structured markdown
            doc.engine = "docling+pymupdf"
            doc.metadata["docling_markdown"] = dl.full_text[:200000]
            if dl.headings:
                doc.headings = dl.headings
        return doc
    if mime.endswith("wordprocessingml.document"):
        return extract_docx(path)
    if mime.endswith("presentationml.presentation"):
        return extract_pptx(path)
    if mime in ("text/plain", "text/markdown", "text/csv", "application/json"):
        return extract_text(path, markdown=mime == "text/markdown")
    raise ValueError(f"unsupported document type {mime}")


def chunk_text(text: str, max_chars: int = 1400, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunking for embeddings."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if len(p) > max_chars:
            for i in range(0, len(p), max_chars - overlap):
                chunks.append(p[i : i + max_chars])
            continue
        if len(cur) + len(p) + 2 > max_chars and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + p if overlap else p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


_ = io
