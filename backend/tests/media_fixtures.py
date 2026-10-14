"""Generated test media (fictional, created on the fly)."""
from __future__ import annotations

import functools
import tempfile
from pathlib import Path

from app.seed import media as m

_DIR = Path(tempfile.mkdtemp(prefix="bdna-media-"))


@functools.cache
def path(name: str) -> Path:
    p = _DIR / name
    if name == "organic.jpg":
        return m.image_organic(p)
    if name == "organic2.jpg":
        return m.image_organic(p, seed=11)
    if name == "architectural.jpg":
        return m.image_architectural(p)
    if name == "dramatic.jpg":
        return m.image_dramatic(p)
    if name == "vibrant.png":
        return m.image_vibrant(p)
    if name == "material.jpg":
        return m.image_material(p)
    if name == "logo.svg":
        return m.svg_logo(p, "Testbrand", "#22313f", "#c9a227")
    if name == "model.obj":
        return m.obj_model(p)
    if name == "film.mp4":
        return m.video_from_images(p, [path("material.jpg"), path("architectural.jpg"), path("organic.jpg")],
                                   ["zoom_in", "static", "pan_right"])
    if name == "guidelines.pdf":
        return m.pdf_guidelines(p, "Test Brand Guidelines", [
            ("Photography", ["Always use natural, diffused daylight in brand photography.",
                             "Never use harsh on-camera flash or heavy colour filters.",
                             "Compositions should leave generous negative space for typography."]),
            ("Colour", ["The primary palette must appear on every customer touchpoint.", "Avoid neon accent colours."]),
            ("Tone of voice", ["We write in short, warm, confident sentences.", "Do not use exclamation marks in headlines."]),
        ])
    if name == "notes.md":
        p.write_text("# Studio notes\n\n## Materials\nWe prefer raw linen, oak and honed stone.\n")
        return p
    if name == "evil.exe":
        p.write_bytes(b"MZ\x90\x00" + b"\x00" * 200)
        return p
    raise KeyError(name)


def upload(api, brand_id: str, name: str, **data):
    mime = {"jpg": "image/jpeg", "png": "image/png", "svg": "image/svg+xml", "obj": "text/plain", "mp4": "video/mp4",
            "pdf": "application/pdf", "md": "text/markdown", "exe": "application/octet-stream"}[name.rsplit(".", 1)[1]]
    p = path(name)
    return api.post(f"/v1/brands/{brand_id}/assets", files={"file": (name, p.read_bytes(), mime)},
                    data={k: (str(v).lower() if isinstance(v, bool) else v) for k, v in data.items()})
