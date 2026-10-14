"""3D model inspection (trimesh) and a dependency-free flat-shaded preview render."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


def _load(path: Path, mime: str):
    import trimesh

    ftype = {
        "model/gltf-binary": "glb",
        "model/gltf+json": "gltf",
        "model/obj": "obj",
        "model/stl": "stl",
        "model/ply": "ply",
    }.get(mime) or path.suffix.lstrip(".").lower()
    return trimesh.load(str(path), file_type=ftype, force="scene", process=False)


def inspect(path: Path, mime: str) -> dict[str, Any]:
    scene = _load(path, mime)
    geoms = list(scene.geometry.values())
    verts = sum(len(getattr(g, "vertices", [])) for g in geoms)
    faces = sum(len(getattr(g, "faces", [])) for g in geoms)
    bounds = scene.bounds if scene.bounds is not None else np.zeros((2, 3))
    extents = (bounds[1] - bounds[0]).tolist() if bounds is not None else [0, 0, 0]
    materials, textures = [], 0
    for g in geoms:
        vis = getattr(g, "visual", None)
        mat = getattr(vis, "material", None)
        if mat is not None:
            name = getattr(mat, "name", None) or type(mat).__name__
            entry: dict[str, Any] = {"name": name}
            for attr in ("baseColorFactor", "metallicFactor", "roughnessFactor", "diffuse"):
                val = getattr(mat, attr, None)
                if val is not None:
                    entry[attr] = np.asarray(val).round(3).tolist() if hasattr(val, "__len__") else round(float(val), 3)
            if getattr(mat, "baseColorTexture", None) is not None or getattr(mat, "image", None) is not None:
                textures += 1
                entry["has_texture"] = True
            if entry not in materials:
                materials.append(entry)
    watertight = all(getattr(g, "is_watertight", False) for g in geoms) if geoms else False
    return {
        "format": path.suffix.lstrip(".").lower() or mime,
        "mesh_count": len(geoms),
        "vertex_count": int(verts),
        "face_count": int(faces),
        "bounds_min": np.asarray(bounds[0]).round(4).tolist(),
        "bounds_max": np.asarray(bounds[1]).round(4).tolist(),
        "dimensions": [round(float(x), 4) for x in extents],
        "units": getattr(scene, "units", None),
        "watertight": bool(watertight),
        "materials": materials[:20],
        "texture_count": textures,
        "node_count": len(scene.graph.nodes) if hasattr(scene, "graph") else None,
    }


def render_preview(path: Path, mime: str, size: int = 640, max_faces: int = 60000) -> bytes | None:
    """Three-quarter view, painter's algorithm, lambert shading. Good enough for a thumbnail."""
    try:
        scene = _load(path, mime)
        mesh = scene.to_geometry() if hasattr(scene, "to_geometry") else scene.dump(concatenate=True)
    except Exception:  # noqa: BLE001
        return None
    v = np.asarray(getattr(mesh, "vertices", []), dtype=np.float64)
    f = np.asarray(getattr(mesh, "faces", []), dtype=np.int64)
    if len(v) == 0 or len(f) == 0:
        return None
    if len(f) > max_faces:
        f = f[np.linspace(0, len(f) - 1, max_faces).astype(int)]
    v = v - v.mean(axis=0)
    scale = np.abs(v).max() or 1.0
    v = v / scale
    ay, ax = np.radians(35), np.radians(-25)
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    v = v @ ry.T @ rx.T
    tri = v[f]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    norms = np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12
    normals = normals / norms
    light = np.array([0.3, 0.5, 0.8])
    light /= np.linalg.norm(light)
    shade = np.clip(np.abs(normals @ light), 0.12, 1.0)
    depth = tri[:, :, 2].mean(axis=1)
    order = np.argsort(depth)
    img = Image.new("RGB", (size, size), (243, 241, 237))
    draw = ImageDraw.Draw(img)
    pad = size * 0.08
    pts2 = (tri[:, :, :2] * np.array([1, -1]) + 1) / 2 * (size - 2 * pad) + pad
    for i in order:
        c = int(60 + 170 * shade[i])
        draw.polygon([tuple(p) for p in pts2[i]], fill=(c, c - 4, c - 10))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
