"""
Traffic Monitor — Global Configuration
========================================
All tuneable knobs live here.  Override any value through environment
variables prefixed with ``TM_`` (e.g. ``TM_RTSP_URL``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _env(key: str, default: str) -> str:
    """Read from env with a ``TM_`` prefix."""
    return os.getenv(f"TM_{key}", default)


# ---------------------------------------------------------------------------
# Camera & Stream
# ---------------------------------------------------------------------------

RTSP_URL: str = _env("RTSP_URL", "0")  # "0" → local webcam
CAMERA_FPS: int = int(_env("CAMERA_FPS", "30"))
FRAME_WIDTH: int = int(_env("FRAME_WIDTH", "1280"))
FRAME_HEIGHT: int = int(_env("FRAME_HEIGHT", "720"))

# ---------------------------------------------------------------------------
# YOLO Model
# ---------------------------------------------------------------------------

YOLO_MODEL_PATH: str = _env("YOLO_MODEL_PATH", "yolov8n.pt")
CONFIDENCE_THRESHOLD: float = float(_env("CONFIDENCE_THRESHOLD", "0.40"))
IOU_THRESHOLD: float = float(_env("IOU_THRESHOLD", "0.45"))
TRACK_PERSIST: bool = True

# COCO class IDs: 2=car, 3=motorcycle, 5=bus, 7=truck
VEHICLE_CLASSES: List[int] = [2, 3, 5, 7]

# ---------------------------------------------------------------------------
# Intersection Metadata
# ---------------------------------------------------------------------------

INTERSECTION_ID: str = _env("INTERSECTION_ID", "yusif_safarov_28may")
INTERSECTION_NAME: str = _env("INTERSECTION_NAME", "Yusif Safarov × 28 May")


@dataclass(frozen=True)
class ROIZone:
    """A polygon Region‑of‑Interest defined by its vertex list."""
    name: str
    polygon: List[Tuple[int, int]]
    color: Tuple[int, int, int] = (0, 255, 0)


# Default ROI zones — calibrated for the 1920×944 aerial intersection image.
# Polygon vertices are in (x, y) pixel coordinates.
ENTRY_ZONE = ROIZone(
    name="entry",
    polygon=[(0, 0), (1, 0), (1, 1), (0, 1)],
    color=(0, 0, 0),       # hidden
)

STRAIGHT_ZONE = ROIZone(
    name="straight",
    polygon=[(165, 20), (220, 20), (350, 85), (240, 90)],
    color=(0, 255, 255),       # yellow BGR — right lane
)

LEFT_TURN_ZONE = ROIZone(
    name="left_turn",
    polygon=[(140, 20), (165, 20), (240, 90), (150, 90)],
    color=(0, 0, 255),      # red BGR — left lane
)

RIGHT_TURN_ZONE = ROIZone(
    name="right_turn",
    polygon=[(0, 0), (1, 0), (1, 1), (0, 1)],
    color=(0, 0, 0),       # hidden
)

# Convenience list of all ROIs
ALL_ROI_ZONES: List[ROIZone] = [LEFT_TURN_ZONE, RIGHT_TURN_ZONE, STRAIGHT_ZONE, ENTRY_ZONE]

# Polygon for legacy compat (flat list of [x,y] pairs)
LEFT_TURN_COORDINATES: List[List[int]] = [list(p) for p in LEFT_TURN_ZONE.polygon]

# ---------------------------------------------------------------------------
# Trajectory / Counting
# ---------------------------------------------------------------------------

TRAJECTORY_MAX_LENGTH: int = int(_env("TRAJECTORY_MAX_LEN", "40"))
TRAJECTORY_MIN_POINTS: int = int(_env("TRAJECTORY_MIN_PTS", "8"))
MOVEMENT_LATERAL_THRESHOLD: int = int(_env("MOVEMENT_LATERAL_THRESH", "60"))
MOVEMENT_FORWARD_THRESHOLD: int = int(_env("MOVEMENT_FORWARD_THRESH", "50"))
STALE_TRACK_FRAMES: int = int(_env("STALE_TRACK_FRAMES", "30"))

# ---------------------------------------------------------------------------
# Traffic‑Light Controller
# ---------------------------------------------------------------------------

@dataclass
class PhaseTiming:
    """Minimum / maximum green‑time for a single phase (seconds)."""
    min_green: float = 15.0
    max_green: float = 60.0
    yellow: float = 4.0
    all_red: float = 2.0


PHASE_TIMING: PhaseTiming = PhaseTiming()

# ---------------------------------------------------------------------------
# Web Dashboard
# ---------------------------------------------------------------------------

WEB_HOST: str = _env("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(_env("WEB_PORT", "8000"))
WS_BROADCAST_INTERVAL: float = float(_env("WS_INTERVAL", "0.5"))   # seconds

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
LOG_FILE: str = _env("LOG_FILE", "logs/traffic_monitor.log")