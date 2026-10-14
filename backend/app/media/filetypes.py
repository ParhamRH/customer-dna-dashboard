"""Content-based file type detection and upload validation (allow-list)."""
from __future__ import annotations

import mimetypes
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileKind:
    mime: str
    asset_type: str  # default asset_type for this kind
    family: str  # image | video | audio | document | presentation | text | model_3d | archive | design


_ZIP_OFFICE = {
    "word/": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "document", "document"),
    "ppt/": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "presentation", "presentation"),
    "xl/": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "document", "document"),
}

ALLOWED_FAMILIES = {"image", "video", "audio", "document", "presentation", "text", "model_3d", "design"}


def _head(path: Path, n: int = 4096) -> bytes:
    with path.open("rb") as f:
        return f.read(n)


def sniff(path: Path, filename: str | None = None) -> FileKind | None:
    """Identify a file from its bytes (extension only as a tie-breaker). None = unknown."""
    h = _head(path)
    ext = Path(filename or path.name).suffix.lower()

    if h.startswith(b"MZ") or h.startswith(b"\x7fELF") or h.startswith(b"#!"):
        return None  # executables / scripts are never accepted
    if h.startswith(b"\xff\xd8\xff"):
        return FileKind("image/jpeg", "image", "image")
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileKind("image/png", "image", "image")
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return FileKind("image/gif", "animation", "image")
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return FileKind("image/webp", "image", "image")
    if h[:4] == b"RIFF" and h[8:12] == b"WAVE":
        return FileKind("audio/wav", "audio", "audio")
    if h[:4] == b"RIFF" and h[8:12] == b"AVI ":
        return FileKind("video/x-msvideo", "video", "video")
    if h[:4] in (b"II*\x00", b"MM\x00*"):
        return FileKind("image/tiff", "image", "image")
    if h[:2] == b"BM":
        return FileKind("image/bmp", "image", "image")
    if h[:4] == b"8BPS":
        return FileKind("image/vnd.adobe.photoshop", "graphic_design", "design")
    if h[4:8] == b"ftyp":
        brand = h[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
            return FileKind("image/heic", "image", "image")
        if brand in (b"avif", b"avis"):
            return FileKind("image/avif", "image", "image")
        if brand == b"qt  ":
            return FileKind("video/quicktime", "video", "video")
        if brand in (b"M4A ", b"M4B "):
            return FileKind("audio/mp4", "audio", "audio")
        return FileKind("video/mp4", "video", "video")
    if h[:4] == b"\x1aE\xdf\xa3":
        return FileKind("video/webm" if ext == ".webm" else "video/x-matroska", "video", "video")
    if h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return FileKind("audio/mpeg", "audio", "audio")
    if h[:4] == b"OggS":
        return FileKind("audio/ogg", "audio", "audio")
    if h[:4] == b"fLaC":
        return FileKind("audio/flac", "audio", "audio")
    if h[:5] == b"%PDF-":
        if ext == ".ai":
            return FileKind("application/pdf", "graphic_design", "design")
        return FileKind("application/pdf", "document", "document")
    if h[:4] == b"%!PS":
        return FileKind("application/postscript", "graphic_design", "design")
    if h[:4] == b"glTF":
        return FileKind("model/gltf-binary", "model_3d", "model_3d")
    if h[:18] == b"Kaydara FBX Binary":
        return FileKind("application/octet-stream+fbx", "model_3d", "model_3d")
    if h[:3] == b"ply":
        return FileKind("model/ply", "model_3d", "model_3d")
    if h[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            return None
        for prefix, (mime, atype, fam) in _ZIP_OFFICE.items():
            if any(n.startswith(prefix) for n in names):
                return FileKind(mime, atype, fam)
        if ext == ".usdz":
            return FileKind("model/vnd.usdz+zip", "model_3d", "model_3d")
        if ext == ".sketch" or "document.json" in names:
            return FileKind("application/vnd.sketch", "graphic_design", "design")
        return None  # generic archives are not assets
    if ext == ".stl" and (h[:5] == b"solid" or len(h) >= 84):
        return FileKind("model/stl", "model_3d", "model_3d")

    # Text-like formats
    try:
        text = h.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = h.decode("latin-1") if ext in (".txt", ".md", ".csv") else ""
        except UnicodeDecodeError:
            text = ""
    if text:
        stripped = text.lstrip("﻿ \t\r\n")
        if "<svg" in stripped[:2000] and (stripped.startswith("<") or stripped.startswith("<?xml")):
            return FileKind("image/svg+xml", "graphic_design", "image")
        if ext == ".gltf" and stripped.startswith("{"):
            return FileKind("model/gltf+json", "model_3d", "model_3d")
        if ext == ".obj" and re.search(r"^(v|vn|vt|f|o|g|mtllib)\s", stripped, re.M):
            return FileKind("model/obj", "model_3d", "model_3d")
        if ext in (".md", ".markdown"):
            return FileKind("text/markdown", "text", "text")
        if ext == ".csv":
            return FileKind("text/csv", "text", "text")
        if ext in (".txt", ".text", "") or not ext:
            return FileKind("text/plain", "text", "text")
        if ext in (".json",):
            return FileKind("application/json", "text", "text")
    guessed, _ = mimetypes.guess_type(filename or "")
    if guessed == "text/plain" and text:
        return FileKind("text/plain", "text", "text")
    return None


def safe_filename(name: str, max_len: int = 180) -> str:
    name = unicodedata.normalize("NFKC", Path(name or "file").name)
    name = re.sub(r"[^\w.\- ]+", "_", name).strip(" .") or "file"
    stem, dot, ext = name.rpartition(".")
    if not dot:
        return name[:max_len]
    return f"{stem[: max_len - len(ext) - 1]}.{ext[:16]}"
