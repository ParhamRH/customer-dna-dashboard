"""Shot detection and camera-movement classification on synthetic footage with known ground truth.

Regression cases found on demo data:
* hard cuts between tonally similar shots (a palette-disciplined brand film) were missed by a fixed
  ContentDetector threshold;
* fast pans over repetitive structure aliased into the wrong direction when flow was measured
  across several frames;
* encoder "breathing" on a locked-off shot was read as a slow zoom on a one-frame baseline.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from app.media import video
from app.seed import media as m

TMP = Path(tempfile.mkdtemp(prefix="bdna-video-"))


def _analyse(p: Path):
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)]).decode())
    scenes = video.detect_scenes(p, dur)
    summary = video.analyze_motion(p, scenes)
    return scenes, summary


@pytest.fixture(scope="module")
def calm_film() -> Path:
    pal = ("#ece4d7", "#d2c3a8", "#8f7d62", "#5b6b4e")  # three shots in nearly the same muted tones
    a = m.image_organic(TMP / "a.jpg", palette=pal, seed=40)
    b = m.image_organic(TMP / "b.jpg", palette=pal, seed=41)
    c = m.image_material(TMP / "c.jpg", base="#9d968c", seed=9)
    return m.video_from_images(TMP / "calm.mp4", [a, b, c], ["zoom_in", "pan_right", "static"], seconds=3.5)


@pytest.fixture(scope="module")
def fast_film() -> Path:
    shots = [m.image_architectural(TMP / f"arch{i}.jpg", bg=bg, seed=60 + i) for i, bg in enumerate(["#1f2a33", "#26333d", "#18222a"])]
    stripes = m.image_vibrant(TMP / "stripes.png", colors=("#ff6a13", "#1f2a33", "#d4ff3a", "#7aa6c2", "#e8edf0"))
    return m.video_from_images(TMP / "fast.mp4", [shots[0], shots[1], stripes, shots[2]], ["pan_left", "pan_right", "static", "tilt_up"], seconds=1.5)


def test_subtle_cuts_between_similar_shots_are_detected(calm_film):
    scenes, summary = _analyse(calm_film)
    assert [(s.start_s, s.end_s) for s in scenes] == [(0.0, 3.5), (3.5, 7.0), (7.0, 10.5)]
    assert summary["average_shot_length_s"] == pytest.approx(3.5, abs=0.05)


def test_slow_deliberate_moves_are_recognised(calm_film):
    scenes, summary = _analyse(calm_film)
    moves = [s.motion["camera_movement"] for s in scenes]
    assert moves[0].startswith("slow") and "zoom in" in moves[0]
    assert moves[1].startswith("slow") and "pan right" in moves[1] and "zoom" not in moves[1]
    assert moves[2] == "locked-off / static"
    assert len(summary["camera_movements"]) == 3


def test_fast_pans_keep_their_direction_and_static_stays_static(fast_film):
    scenes, _ = _analyse(fast_film)
    assert len(scenes) == 4
    moves = [s.motion["camera_movement"] for s in scenes]
    assert "pan left" in moves[0] and "pan right" in moves[1]
    assert moves[2] == "locked-off / static"
    assert "tilt up" in moves[3]
    assert not any("roll" in mv or "handheld" in mv for mv in moves)
