"""Objective image measurements (no AI): metadata, palette, tonal and compositional statistics."""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import ExifTags, Image, ImageColor, ImageOps

Image.MAX_IMAGE_PIXELS = 300_000_000  # allow large print files, still guards against bombs

_EXIF_KEEP = {
    "Make", "Model", "LensModel", "FNumber", "ExposureTime", "ISOSpeedRatings", "FocalLength",
    "DateTimeOriginal", "Software", "Artist", "Copyright", "WhiteBalance", "Flash",
}


def open_image(path: Path) -> Image.Image:
    img = Image.open(path)
    try:
        img.seek(0)
    except EOFError:
        pass
    return img


def probe(path: Path) -> dict[str, Any]:
    img = open_image(path)
    info: dict[str, Any] = {
        "format": img.format,
        "width": img.width,
        "height": img.height,
        "mode": img.mode,
        "has_alpha": img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info,
        "animated": bool(getattr(img, "is_animated", False)),
        "frame_count": int(getattr(img, "n_frames", 1)),
        "aspect_ratio": round(img.width / img.height, 4) if img.height else None,
        "orientation": "landscape" if img.width > img.height else "portrait" if img.height > img.width else "square",
        "megapixels": round(img.width * img.height / 1e6, 2),
    }
    if dpi := img.info.get("dpi"):
        info["dpi"] = [round(float(d), 1) for d in dpi]
    icc = img.info.get("icc_profile")
    if icc:
        info["color_profile"] = _icc_description(icc)
    else:
        info["color_profile"] = "sRGB (assumed, no embedded profile)" if img.mode in ("RGB", "RGBA", "P") else img.mode
    try:
        exif = img.getexif()
        merged = dict(exif)
        try:
            merged.update(exif.get_ifd(0x8769))
        except Exception:  # noqa: BLE001
            pass
        tags = {ExifTags.TAGS.get(k, str(k)): v for k, v in merged.items()}
        kept = {k: _exif_value(v) for k, v in tags.items() if k in _EXIF_KEEP}
        if kept:
            info["exif"] = kept
    except Exception:  # noqa: BLE001
        pass
    return info


def _icc_description(icc: bytes) -> str:
    try:
        from PIL import ImageCms

        prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        return ImageCms.getProfileDescription(prof).strip() or "embedded ICC profile"
    except Exception:  # noqa: BLE001
        return "embedded ICC profile"


def _exif_value(v: Any) -> Any:
    if isinstance(v, bytes):
        return v.decode(errors="ignore")[:200]
    if hasattr(v, "numerator") and hasattr(v, "denominator"):
        return round(float(v), 4) if v.denominator else None
    if isinstance(v, tuple):
        return [_exif_value(x) for x in v]
    return v if isinstance(v, int | float | str) else str(v)[:200]


def to_rgb(img: Image.Image, max_side: int | None = None) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "PA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if max_side and max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return img


# --- Color ---------------------------------------------------------------------------------------
def _srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    arr = (rgb.reshape(-1, 1, 3).astype(np.float32) / 255.0)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    return lab.reshape(-1, 3)


_NAMED: list[tuple[str, np.ndarray]] | None = None


def _named_colors() -> list[tuple[str, np.ndarray]]:
    global _NAMED
    if _NAMED is None:
        names = list(ImageColor.colormap.keys())
        rgbs = np.array([ImageColor.getrgb(n)[:3] for n in names], dtype=np.uint8)
        labs = _srgb_to_lab(rgbs)
        _NAMED = list(zip(names, labs, strict=True))
    return _NAMED


def nearest_color_name(lab: np.ndarray) -> str:
    return min(_named_colors(), key=lambda nl: float(np.sum((nl[1] - lab) ** 2)))[0]


def extract_palette(img: Image.Image, k: int = 6) -> list[dict[str, Any]]:
    small = to_rgb(img, 200)
    px = np.asarray(small).reshape(-1, 3)
    lab = _srgb_to_lab(px).astype(np.float32)
    k = min(k, max(1, len(np.unique(px, axis=0))))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(7)
    _, labels, centers = cv2.kmeans(lab, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=k)
    out = []
    for idx in np.argsort(-counts):
        c_lab = centers[idx].reshape(1, 1, 3).astype(np.float32)
        rgb = np.clip(cv2.cvtColor(c_lab, cv2.COLOR_LAB2RGB).reshape(3) * 255, 0, 255).round().astype(int)
        hexv = "#{:02x}{:02x}{:02x}".format(*rgb)
        L, a, b = (float(x) for x in centers[idx])
        out.append(
            {
                "hex": hexv,
                "rgb": [int(x) for x in rgb],
                "lab": [round(L, 1), round(a, 1), round(b, 1)],
                "proportion": round(float(counts[idx]) / float(counts.sum()), 4),
                "name": nearest_color_name(centers[idx]),
                "chroma": round(math.hypot(a, b), 1),
            }
        )
    return out


# --- Tonal / compositional statistics ------------------------------------------------------------
def image_stats(img: Image.Image) -> dict[str, Any]:
    rgb = np.asarray(to_rgb(img, 768))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    brightness = float(L.mean()) / 100.0
    contrast = float(L.std()) / 50.0
    saturation = float(hsv[..., 1].mean()) / 255.0
    # Hasler & Süsstrunk colorfulness
    R, G, Bc = (rgb[..., i].astype(np.float32) for i in range(3))
    rg, yb = R - G, 0.5 * (R + G) - Bc
    colorfulness = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)) / 109.0
    warmth = float(B.mean() + 0.5 * A.mean()) / 40.0
    p5, p95 = np.percentile(L, [5, 95])
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float((edges > 0).mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    h, w = gray.shape
    flipped = cv2.flip(gray, 1)
    symmetry = 1.0 - float(np.abs(gray.astype(np.float32) - flipped.astype(np.float32)).mean()) / 128.0

    # Visual weight / centre of interest from spectral-residual saliency
    focus = _focus_point(bgr)
    thirds = [(1 / 3, 1 / 3), (2 / 3, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 2 / 3)]
    near_thirds = min(math.dist(focus, t) for t in thirds)
    centered = math.dist(focus, (0.5, 0.5))

    # Shape structure uses adaptive thresholds (soft, low-contrast forms still have contours)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    gmag = cv2.magnitude(cv2.Sobel(blur, cv2.CV_32F, 1, 0), cv2.Sobel(blur, cv2.CV_32F, 0, 1))
    nz = gmag[gmag > 4]
    hi = float(np.clip(np.percentile(nz, 90) if nz.size else 100, 25, 400))
    shape_edges = cv2.Canny(blur, int(hi * 0.4), int(hi))
    # Straight-line structure (architectural / geometric composition)
    lines = cv2.HoughLinesP(shape_edges, 1, np.pi / 180, threshold=60, minLineLength=min(h, w) // 8, maxLineGap=6)
    lines = np.zeros((0, 4), dtype=np.int32) if lines is None else np.asarray(lines).reshape(-1, 4)
    line_count = int(len(lines))
    orient = {"horizontal": 0, "vertical": 0, "diagonal": 0}
    for x1, y1, x2, y2 in lines:
        ang = abs(math.degrees(math.atan2(y2 - y1, x2 - x1))) % 180
        orient["horizontal" if ang < 12 or ang > 168 else "vertical" if 78 < ang < 102 else "diagonal"] += 1
    contours, _ = cv2.findContours(shape_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    curvy = 0
    for c in contours:
        length = cv2.arcLength(c, False)
        if length > 60:
            approx = cv2.approxPolyDP(c, 0.01 * length, False)
            if len(approx) > 10:
                curvy += 1
    # Share of an 8x8 grid with (almost) no edges: a proxy for negative / empty space.
    hh, ww = (h // 8) * 8, (w // 8) * 8
    negative_space = 0.0
    if hh and ww:
        blocks = (edges[:hh, :ww] > 0).reshape(8, hh // 8, 8, ww // 8).mean(axis=(1, 3))
        negative_space = float((blocks < 0.01).mean())

    # Where the light comes from (brightness gradient across halves of the frame)
    lr = float(L[:, w // 2 :].mean() - L[:, : w // 2].mean()) / 100.0
    tb = float(L[: h // 2, :].mean() - L[h // 2 :, :].mean()) / 100.0
    if max(abs(lr), abs(tb)) < 0.06:
        light_dir = "even / frontal"
    elif abs(lr) >= abs(tb):
        light_dir = "from the right" if lr > 0 else "from the left"
    else:
        light_dir = "from above" if tb > 0 else "from below"

    return {
        "light_direction": light_dir,
        "light_gradient": [round(lr, 3), round(tb, 3)],
        "brightness": round(brightness, 3),
        "contrast": round(contrast, 3),
        "saturation": round(saturation, 3),
        "colorfulness": round(min(colorfulness, 1.5), 3),
        "warmth": round(warmth, 3),
        "tonal_range": [round(float(p5), 1), round(float(p95), 1)],
        "key": "high-key" if p5 > 40 and brightness > 0.62 else "low-key" if p95 < 70 and brightness < 0.38 else "mid-key",
        "edge_density": round(edge_density, 4),
        "sharpness": round(sharpness, 1),
        "symmetry": round(symmetry, 3),
        "focus_point": [round(focus[0], 3), round(focus[1], 3)],
        "focus_near_thirds": near_thirds < 0.12,
        "focus_centered": centered < 0.12,
        "straight_lines": line_count,
        "line_orientation": orient,
        "curved_contours": curvy,
        "negative_space_ratio": round(negative_space, 3),
        "dimensions_analyzed": [w, h],
    }


def _focus_point(bgr: np.ndarray) -> tuple[float, float]:
    h, w = bgr.shape[:2]
    try:
        sal = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok, smap = sal.computeSaliency(bgr)
        if not ok:
            raise RuntimeError
        smap = (smap * 255).astype(np.float32)
    except Exception:  # noqa: BLE001  (opencv without contrib)
        smap = cv2.GaussianBlur(cv2.Laplacian(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), cv2.CV_32F), (0, 0), 9)
        smap = np.abs(smap)
    m = cv2.moments(smap)
    if m["m00"] <= 1e-6:
        return 0.5, 0.5
    return float(m["m10"] / m["m00"]) / w, float(m["m01"] / m["m00"]) / h


# --- Derivatives ----------------------------------------------------------------------------------
def render_derivative(img: Image.Image, max_side: int, fmt: str = "WEBP", quality: int = 82) -> tuple[bytes, int, int]:
    out = to_rgb(img, max_side)
    buf = io.BytesIO()
    out.save(buf, fmt, quality=quality, method=4) if fmt == "WEBP" else out.save(buf, fmt, quality=quality, optimize=True)
    return buf.getvalue(), out.width, out.height


def ahash(img: Image.Image, size: int = 16) -> str:
    """Perceptual average hash (near-duplicate detection)."""
    g = to_rgb(img).convert("L").resize((size, size), Image.Resampling.LANCZOS)
    arr = np.asarray(g, dtype=np.float32)
    bits = (arr > arr.mean()).flatten()
    return "".join("1" if b else "0" for b in bits)
