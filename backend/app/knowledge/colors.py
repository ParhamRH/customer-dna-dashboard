"""Color conversions (HEX → RGB / HSL / OKLCH / CMYK) and WCAG 2.x contrast."""
from __future__ import annotations

import colorsys
import math
import re
from typing import Any

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$")


def normalize_hex(value: str) -> str:
    m = HEX_RE.match(value.strip())
    if not m:
        short = re.match(r"^#?([0-9a-fA-F]{3})$", value.strip())
        if not short:
            raise ValueError(f"invalid hex color {value!r}")
        return "#" + "".join(c * 2 for c in short.group(1)).lower()
    return "#" + m.group(1).lower() + (m.group(2).lower() if m.group(2) else "")


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = normalize_hex(h)
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def to_oklch(r: int, g: int, b: int) -> dict[str, float]:
    lr, lg, lb = _lin(r), _lin(g), _lin(b)
    l_ = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m_ = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s_ = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb
    l, m, s = (math.copysign(abs(x) ** (1 / 3), x) for x in (l_, m_, s_))
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    C = math.hypot(a, bb)
    H = math.degrees(math.atan2(bb, a)) % 360 if C > 1e-6 else 0.0
    return {"l": round(L, 4), "c": round(C, 4), "h": round(H, 2), "css": f"oklch({L * 100:.2f}% {C:.4f} {H:.2f})"}


def to_hsl(r: int, g: int, b: int) -> dict[str, float]:
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return {"h": round(h * 360, 1), "s": round(s * 100, 1), "l": round(l * 100, 1),
            "css": f"hsl({h * 360:.1f} {s * 100:.1f}% {l * 100:.1f}%)"}


def to_cmyk(r: int, g: int, b: int) -> dict[str, float]:
    """Naive device-independent CMYK. Print work should use the brand's specified (manual) values."""
    if (r, g, b) == (0, 0, 0):
        return {"c": 0, "m": 0, "y": 0, "k": 100, "approximate": True}
    c, m, y = 1 - r / 255, 1 - g / 255, 1 - b / 255
    k = min(c, m, y)
    c, m, y = ((x - k) / (1 - k) for x in (c, m, y))
    return {"c": round(c * 100, 1), "m": round(m * 100, 1), "y": round(y * 100, 1), "k": round(k * 100, 1), "approximate": True}


def describe(hex_value: str) -> dict[str, Any]:
    h = normalize_hex(hex_value)
    r, g, b = hex_to_rgb(h)
    return {
        "hex": h,
        "rgb": {"r": r, "g": g, "b": b, "css": f"rgb({r} {g} {b})"},
        "hsl": to_hsl(r, g, b),
        "oklch": to_oklch(r, g, b),
        "cmyk": to_cmyk(r, g, b),
    }


def relative_luminance(hex_value: str) -> float:
    r, g, b = hex_to_rgb(hex_value)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def wcag(ratio: float) -> dict[str, bool]:
    return {"AA_normal": ratio >= 4.5, "AA_large": ratio >= 3.0, "AAA_normal": ratio >= 7.0, "AAA_large": ratio >= 4.5}


def contrast_matrix(colors: list[dict[str, str]]) -> list[dict[str, Any]]:
    out = []
    for i, fg in enumerate(colors):
        for bg in colors[i + 1 :]:
            ratio = contrast_ratio(fg["hex"], bg["hex"])
            out.append({"a": fg["name"], "a_hex": fg["hex"], "b": bg["name"], "b_hex": bg["hex"], "ratio": ratio, **wcag(ratio)})
    out.sort(key=lambda x: -x["ratio"])
    return out
