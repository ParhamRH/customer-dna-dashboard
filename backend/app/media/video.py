"""Video processing with FFmpeg (probe, frame extraction) and PySceneDetect (scene boundaries),
plus OpenCV optical-flow motion analysis and camera-movement classification."""
from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.config import get_settings


class MediaToolError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as e:
        raise MediaToolError(f"{cmd[0]} not installed") from e
    if p.returncode != 0:
        raise MediaToolError(f"{Path(cmd[0]).name} failed: {p.stderr.decode(errors='ignore')[-800:]}")
    return p


def ffprobe(path: Path) -> dict[str, Any]:
    p = _run(
        [get_settings().ffprobe_binary, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        timeout=120,
    )
    data = json.loads(p.stdout or b"{}")
    fmt = data.get("format", {})
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    out: dict[str, Any] = {
        "container": fmt.get("format_name"),
        "duration_seconds": round(float(fmt.get("duration", 0) or 0), 3),
        "bitrate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        "tags": {k: v for k, v in (fmt.get("tags") or {}).items() if k in ("title", "artist", "comment", "creation_time", "encoder")},
    }
    if v:
        fps = _fraction(v.get("avg_frame_rate") or v.get("r_frame_rate"))
        rotation = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rotation = int(sd["rotation"])
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        if abs(rotation) in (90, 270):
            w, h = h, w
        out.update(
            {
                "width": w,
                "height": h,
                "frame_rate": round(fps, 3) if fps else None,
                "video_codec": v.get("codec_name"),
                "pixel_format": v.get("pix_fmt"),
                "color_space": v.get("color_space"),
                "color_transfer": v.get("color_transfer"),
                "frame_count": int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None,
                "rotation": rotation,
                "aspect_ratio": round(w / h, 4) if h else None,
                "orientation": "landscape" if w > h else "portrait" if h > w else "square",
            }
        )
    if a:
        out["audio"] = {"codec": a.get("codec_name"), "channels": a.get("channels"), "sample_rate": a.get("sample_rate")}
    else:
        out["audio"] = None
    out["has_video"] = v is not None
    return out


def _fraction(s: str | None) -> float | None:
    if not s or s in ("0/0",):
        return None
    if "/" in s:
        n, d = s.split("/")
        return float(n) / float(d) if float(d) else None
    return float(s)


@dataclass
class Scene:
    index: int
    start_s: float
    end_s: float
    keyframe_s: float
    motion: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def detect_scenes(path: Path, duration_s: float, threshold: float = 27.0) -> list[Scene]:
    from scenedetect import ContentDetector, detect

    try:
        raw = detect(str(path), ContentDetector(threshold=threshold, min_scene_len=12))
    except Exception:  # noqa: BLE001
        raw = []
    if not raw:
        raw_pairs = [(0.0, duration_s)]
    else:
        raw_pairs = [(a.get_seconds(), b.get_seconds()) for a, b in raw]
    scenes = []
    for i, (a, b) in enumerate(raw_pairs):
        b = b or duration_s
        scenes.append(Scene(index=i, start_s=round(a, 3), end_s=round(b, 3), keyframe_s=round(a + (b - a) / 2, 3)))
    return scenes


def extract_frame(path: Path, at_s: float, out: Path, max_side: int = 1280) -> Path:
    scale = f"scale='if(gt(iw,ih),min({max_side},iw),-2)':'if(gt(iw,ih),-2,min({max_side},ih))'"
    _run(
        [get_settings().ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, at_s):.3f}",
         "-i", str(path), "-frames:v", "1", "-vf", scale, "-q:v", "3", str(out)],
        timeout=120,
    )
    if not out.exists():
        raise MediaToolError(f"no frame extracted at {at_s}s")
    return out


# --- Motion analysis -----------------------------------------------------------------------------
def analyze_motion(path: Path, scenes: list[Scene], sample_fps: float = 4.0, max_samples: int = 240) -> dict[str, Any]:
    """Dense optical flow on downscaled frames. Per scene: motion intensity, dominant camera move."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"available": False, "reason": "OpenCV could not open the video"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps / sample_fps)))
    if total and total / step > max_samples:
        step = max(1, total // max_samples)
    samples: list[dict[str, float]] = []
    prev = None
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            scale = 240.0 / max(g.shape)
            g = cv2.resize(g, (max(16, int(g.shape[1] * scale)), max(16, int(g.shape[0] * scale))))
            t_now, t_prev = idx / fps, (idx - step) / fps
            crosses_cut = any(t_prev < sc.start_s <= t_now for sc in scenes if sc.start_s > 0)
            if prev is not None and prev.shape == g.shape and not crosses_cut:
                flow = cv2.calcOpticalFlowFarneback(prev, g, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                samples.append({"t": t_now, **_flow_features(flow, step)})
            prev = g
        idx += 1
    cap.release()
    if not samples:
        return {"available": False, "reason": "not enough frames"}
    for sc in scenes:
        ss = [s for s in samples if sc.start_s <= s["t"] < sc.end_s + 1e-6] or [min(samples, key=lambda s: abs(s["t"] - sc.keyframe_s))]
        sc.motion = _classify(ss)
    mags = [s["magnitude"] for s in samples]
    durations = [s.duration_s for s in scenes]
    total_dur = sum(durations) or 1.0
    return {
        "available": True,
        "samples": len(samples),
        "mean_motion": round(float(np.mean(mags)), 4),
        "motion_variability": round(float(np.std(mags)), 4),
        "overall_camera_movement": _classify(samples)["camera_movement"],
        "pace": _pace(len(scenes), total_dur),
        "cuts_per_minute": round(60.0 * max(0, len(scenes) - 1) / total_dur, 2),
        "average_shot_length_s": round(total_dur / max(1, len(scenes)), 2),
    }


def _flow_features(flow: np.ndarray, step: int) -> dict[str, float]:
    h, w = flow.shape[:2]
    fx, fy = flow[..., 0], flow[..., 1]
    norm = max(h, w) * step / 100.0  # % of frame per source frame
    mag = float(np.sqrt(fx**2 + fy**2).mean()) / norm
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = xs - w / 2, ys - h / 2
    r = np.sqrt(cx**2 + cy**2) + 1e-6
    divergence = float(((fx * cx + fy * cy) / r).mean()) / norm  # + zoom in, - zoom out
    curl = float(((fy * cx - fx * cy) / r).mean()) / norm
    return {
        "magnitude": mag,
        "dx": float(fx.mean()) / norm,
        "dy": float(fy.mean()) / norm,
        "divergence": divergence,
        "curl": curl,
        "incoherence": float(np.std(fx) + np.std(fy)) / norm,
    }


def _classify(samples: list[dict[str, float]]) -> dict[str, Any]:
    m = float(np.mean([s["magnitude"] for s in samples]))
    dx = float(np.mean([s["dx"] for s in samples]))
    dy = float(np.mean([s["dy"] for s in samples]))
    div = float(np.mean([s["divergence"] for s in samples]))
    curl = float(np.mean([s["curl"] for s in samples]))
    jitter = float(np.std([s["dx"] for s in samples]) + np.std([s["dy"] for s in samples]))
    speed = "static" if m < 0.08 else "slow" if m < 0.35 else "moderate" if m < 0.9 else "fast"
    moves = []
    if speed != "static":
        if abs(dx) > 0.06 and abs(dx) >= abs(dy):
            moves.append("pan right" if dx < 0 else "pan left")  # scene moves left => camera pans right
        if abs(dy) > 0.06 and abs(dy) > abs(dx) * 0.6:
            moves.append("tilt down" if dy < 0 else "tilt up")
        if abs(div) > 0.05:
            moves.append("push in / zoom in" if div > 0 else "pull out / zoom out")
        if abs(curl) > 0.12:
            moves.append("roll")
        if jitter > 0.25 and not moves:
            moves.append("handheld")
        if not moves:
            moves.append("subject motion (camera largely locked)")
    camera = "locked-off / static" if speed == "static" else f"{speed} " + " + ".join(moves)
    return {
        "speed": speed,
        "camera_movement": camera,
        "mean_magnitude": round(m, 4),
        "pan_x": round(dx, 4),
        "tilt_y": round(dy, 4),
        "zoom": round(div, 4),
        "jitter": round(jitter, 4),
    }


def _pace(n_scenes: int, duration: float) -> str:
    cpm = 60.0 * max(0, n_scenes - 1) / max(duration, 1e-6)
    if cpm < 4:
        return "contemplative (long takes)"
    if cpm < 12:
        return "measured"
    if cpm < 30:
        return "energetic"
    return "rapid-cut"


def contact_sheet(frames: list[Path], out: Path, cols: int = 4, tile: int = 320) -> Path | None:
    from PIL import Image

    imgs = []
    for f in frames:
        try:
            im = Image.open(f).convert("RGB")
            im.thumbnail((tile, tile))
            imgs.append(im)
        except Exception:  # noqa: BLE001
            continue
    if not imgs:
        return None
    rows = math.ceil(len(imgs) / cols)
    th = max(i.height for i in imgs)
    sheet = Image.new("RGB", (cols * tile, rows * th), (18, 18, 18))
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * tile + (tile - im.width) // 2, (i // cols) * th + (th - im.height) // 2))
    sheet.save(out, "JPEG", quality=85)
    return out
