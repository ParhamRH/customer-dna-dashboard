"""Synthetic media generator for DEMO / TEST data (clearly fictional, generated on the fly).

Produces real files with distinct, measurable aesthetics so the pipeline has something genuine to
analyse: images, multi-scene videos with real camera moves, PDFs with brand rules, SVG logos and
3D OBJ models.
"""
from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _gradient(w: int, h: int, top: str, bottom: str) -> Image.Image:
    a, b = np.array(_hex(top), float), np.array(_hex(bottom), float)
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (a * (1 - t) + b * t).repeat(w, axis=1)
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def image_organic(path: Path, palette=("#e9e1d4", "#c9b79c", "#8a7a63", "#5b6b4e"), seed: int = 1, size=(1600, 1067)) -> Path:
    """Soft, muted, warm, curvilinear blobs with generous negative space."""
    rng = np.random.default_rng(seed)
    w, h = size
    img = _gradient(w, h, palette[0], palette[1]).convert("RGBA")
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(5):
        cx, cy = rng.uniform(0.45, 0.85) * w, rng.uniform(0.3, 0.8) * h
        r = rng.uniform(0.08, 0.2) * w
        col = _hex(palette[2 + i % 2]) + (int(rng.uniform(120, 200)),)
        pts = []
        for k in range(48):
            ang = 2 * math.pi * k / 48
            rr = r * (1 + 0.18 * math.sin(3 * ang + i) + 0.08 * math.cos(5 * ang))
            pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
        d.polygon(pts, fill=col)
    layer = layer.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, layer).convert("RGB")
    noise = rng.normal(0, 3, (h, w, 1)).repeat(3, 2)
    img = Image.fromarray(np.clip(np.asarray(img, float) + noise, 0, 255).astype(np.uint8))
    img.save(path, "JPEG", quality=90)
    return path


def image_architectural(path: Path, bg="#1f2a33", line="#e8edf0", accent="#7aa6c2", seed: int = 2, size=(1600, 1067)) -> Path:
    """Cool, high-contrast rectilinear structure: grids, columns, hard edges."""
    rng = np.random.default_rng(seed)
    w, h = size
    img = Image.new("RGB", size, _hex(bg))
    d = ImageDraw.Draw(img)
    for x in range(0, w, int(w / 12)):
        d.rectangle([x, int(h * 0.15), x + int(w / 40), h], fill=_hex(line))
    for y in range(int(h * 0.15), h, int(h / 9)):
        d.line([(0, y), (w, y)], fill=_hex(line), width=3)
    for _ in range(4):
        x0, y0 = int(rng.uniform(0, w * 0.7)), int(rng.uniform(h * 0.2, h * 0.7))
        d.rectangle([x0, y0, x0 + int(w * 0.18), y0 + int(h * 0.12)], fill=_hex(accent))
    img.save(path, "JPEG", quality=92)
    return path


def image_dramatic(path: Path, key="#d9a441", seed: int = 3, size=(1600, 1067)) -> Path:
    """Low-key, chiaroscuro: a single warm light pool in darkness."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w * 0.62, h * 0.45
    dist = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    glow = np.clip(1.0 - dist * 2.6, 0, 1) ** 2.2
    col = np.array(_hex(key), float)
    arr = glow[..., None] * col + (1 - glow[..., None]) * np.array([10, 9, 12], float)
    img = Image.fromarray(arr.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    d.ellipse([cx - 120, cy - 160, cx + 120, cy + 160], outline=(240, 200, 120), width=4)
    img.save(path, "JPEG", quality=90)
    return path


def image_vibrant(path: Path, colors=("#ff3366", "#ffcc00", "#00c2a8", "#3d5afe", "#ff7a00"), seed: int = 4, size=(1080, 1350)) -> Path:
    """Saturated, energetic, graphic diagonal bands (portrait / social format)."""
    w, h = size
    img = Image.new("RGB", size, _hex(colors[0]))
    d = ImageDraw.Draw(img)
    band = int(w / 3)
    for i in range(-3, 12):
        c = _hex(colors[i % len(colors)])
        x = i * band // 1.4
        d.polygon([(x, 0), (x + band, 0), (x + band - h * 0.6, h), (x - h * 0.6, h)], fill=c)
    img.save(path, "PNG")
    return path


def image_material(path: Path, base="#8c7b6b", seed: int = 5, size=(1400, 1400)) -> Path:
    """Tactile close-up: stone/linen-like texture with high fine detail."""
    rng = np.random.default_rng(seed)
    w, h = size
    noise = rng.normal(0, 1, (h // 4, w // 4))
    tex = np.array(Image.fromarray(((noise - noise.min()) / (np.ptp(noise) + 1e-9) * 255).astype(np.uint8)).resize(size, Image.BICUBIC), float)
    fine = rng.normal(0, 18, (h, w))
    weave = 10 * np.sin(np.arange(w)[None, :] / 3.0) * np.sin(np.arange(h)[:, None] / 3.0)
    lum = (tex - 128) * 0.35 + fine + weave
    base_c = np.array(_hex(base), float)
    arr = base_c[None, None, :] + lum[..., None]
    Image.fromarray(arr.clip(0, 255).astype(np.uint8)).save(path, "JPEG", quality=92)
    return path


def svg_logo(path: Path, name: str, color: str, accent: str) -> Path:
    initial = name.strip()[0].upper()
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="240" viewBox="0 0 640 240">
  <rect width="640" height="240" fill="#ffffff"/>
  <circle cx="120" cy="120" r="84" fill="{color}"/>
  <path d="M84 160 C 100 60, 150 60, 160 160" stroke="{accent}" stroke-width="14" fill="none" stroke-linecap="round"/>
  <text x="230" y="140" font-family="Helvetica, Arial, sans-serif" font-size="64" font-weight="600" fill="{color}">{name}</text>
  <text x="104" y="135" font-family="Georgia, serif" font-size="40" fill="#ffffff">{initial}</text>
</svg>"""
    )
    return path


def obj_model(path: Path, kind: str = "torus") -> Path:
    lines = ["# demo model generated by Brand DNA platform seed", "o DemoObject"]
    if kind == "torus":
        R, r, nu, nv = 1.0, 0.35, 48, 24
        for i in range(nu):
            for j in range(nv):
                u, v = 2 * math.pi * i / nu, 2 * math.pi * j / nv
                lines.append(f"v {(R + r * math.cos(v)) * math.cos(u):.5f} {r * math.sin(v):.5f} {(R + r * math.cos(v)) * math.sin(u):.5f}")
        for i in range(nu):
            for j in range(nv):
                a = i * nv + j + 1
                b = ((i + 1) % nu) * nv + j + 1
                c = ((i + 1) % nu) * nv + (j + 1) % nv + 1
                dd = i * nv + (j + 1) % nv + 1
                lines.append(f"f {a} {b} {c}")
                lines.append(f"f {a} {c} {dd}")
    else:  # stepped block (architectural)
        verts, faces = [], []
        for k, (sx, sy, sz, oy) in enumerate([(2, 0.4, 2, 0), (1.4, 0.4, 1.4, 0.4), (0.8, 0.6, 0.8, 0.8)]):
            base = len(verts)
            for x in (-sx / 2, sx / 2):
                for y in (oy, oy + sy):
                    for z in (-sz / 2, sz / 2):
                        verts.append((x, y, z))
            q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
            for a, b, c, dd in q:
                faces += [(base + a + 1, base + b + 1, base + c + 1), (base + a + 1, base + c + 1, base + dd + 1)]
            _ = k
        lines += [f"v {x} {y} {z}" for x, y, z in verts] + [f"f {a} {b} {c}" for a, b, c in faces]
    path.write_text("\n".join(lines) + "\n")
    return path


def video_from_images(path: Path, images: list[Path], moves: list[str], seconds: float = 2.5, size=(960, 540), fps: int = 24) -> Path:
    """Concatenate shots built from still images with real camera moves:
    'static', 'pan_right', 'pan_left', 'zoom_in', 'tilt_up'. Cuts between shots are hard cuts."""
    w, h = size
    with tempfile.TemporaryDirectory() as td:
        parts = []
        for i, (img, move) in enumerate(zip(images, moves, strict=True)):
            src = Image.open(img).convert("RGB").resize((int(w * 1.6), int(h * 1.6)))
            src_path = Path(td) / f"src{i}.png"
            src.save(src_path)
            frames = int(seconds * fps)
            W, H = src.size
            if move == "pan_right":
                vf = f"crop={w}:{h}:'(iw-{w})*n/{frames}':'(ih-{h})/2'"
            elif move == "pan_left":
                vf = f"crop={w}:{h}:'(iw-{w})*(1-n/{frames})':'(ih-{h})/2'"
            elif move == "tilt_up":
                vf = f"crop={w}:{h}:'(iw-{w})/2':'(ih-{h})*(1-n/{frames})'"
            elif move == "zoom_in":
                vf = f"zoompan=z='1+0.5*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={fps}"
            else:
                vf = f"crop={w}:{h}:'(iw-{w})/2':'(ih-{h})/2'"
            out = Path(td) / f"part{i}.mp4"
            loop = ["-loop", "1", "-t", f"{seconds}"] if move != "zoom_in" else []
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *loop, "-i", str(src_path), "-vf", vf + ",format=yuv420p",
                   "-r", str(fps), "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", str(out)]
            subprocess.run(cmd, check=True, capture_output=True)
            parts.append(out)
            _ = (W, H)
        lst = Path(td) / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c", "copy", "-movflags", "+faststart", str(path)], check=True, capture_output=True)
    return path


def pdf_guidelines(path: Path, title: str, sections: list[tuple[str, list[str]]], author: str = "Demo Agency") -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    page.insert_text((72, y), title, fontsize=26, fontname="helv")
    y += 46
    for heading, paras in sections:
        if y > 680:
            page = doc.new_page()
            y = 72
        page.insert_text((72, y), heading, fontsize=16, fontname="hebo")
        y += 26
        for para in paras:
            rect = pymupdf.Rect(72, y, 523, y + 120)
            rest = page.insert_textbox(rect, para, fontsize=11, fontname="helv")
            used = 120 - rest if rest >= 0 else 120
            y += max(30, used + 10)
            if y > 720:
                page = doc.new_page()
                y = 72
    doc.set_metadata({"title": title, "author": author, "subject": "Brand guidelines (fictional demo)"})
    doc.save(str(path))
    return path
