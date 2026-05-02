"""
core/visualizer.py — Annotated Frame Renderer
===============================================
Draws bounding boxes, trajectory trails, ROI overlays, and a
HUD (heads‑up display) panel onto each video frame.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import cv2
import numpy as np

from config.settings import ALL_ROI_ZONES
from core.counter import Direction, IntersectionCounter


# Colour palette per direction
_DIR_COLORS: Dict[Direction, Tuple[int, int, int]] = {
    Direction.STRAIGHT: (0, 255, 100),
    Direction.LEFT: (0, 140, 255),
    Direction.RIGHT: (255, 100, 0),
    Direction.U_TURN: (180, 0, 255),
    Direction.UNKNOWN: (200, 200, 200),
}


def draw_roi_zones(frame: np.ndarray, alpha: float = 0.25) -> np.ndarray:
    """Draw semi‑transparent ROI polygons."""
    overlay = frame.copy()
    for zone in ALL_ROI_ZONES:
        pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(overlay, [pts], zone.color)
        cv2.polylines(frame, [pts], True, zone.color, 2)
        # Label
        cx = int(np.mean([p[0] for p in zone.polygon]))
        cy = int(np.mean([p[1] for p in zone.polygon]))
        cv2.putText(
            frame, zone.name.upper().replace("_", " "),
            (cx - 40, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
        )
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    return frame


def draw_detections(
    frame: np.ndarray,
    detections: list,
    counter: IntersectionCounter,
) -> np.ndarray:
    """Draw bounding boxes and trajectory trails."""
    active = counter.get_active_tracks()

    for det in detections:
        # We no longer draw the green bounding boxes or labels per user request
        
        # Trail (still useful if running on video)
        trail = active.get(det.track_id, [])
        for i in range(1, len(trail)):
            thickness = max(1, int(2 * i / len(trail)))
            cv2.line(frame, trail[i - 1], trail[i], (0, 200, 255), thickness, cv2.LINE_AA)

    return frame


def draw_hud(frame: np.ndarray, counter: IntersectionCounter) -> np.ndarray:
    """Draw a translucent HUD panel with live counts."""
    h, w = frame.shape[:2]
    panel_w, panel_h = 260, 180
    x0, y0 = w - panel_w - 15, 15

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    lines = [
        f"TOTAL       : {counter.total_count}",
        f"STRAIGHT    : {counter.straight_count}",
        f"LEFT TURN   : {counter.left_turn_count}",
        f"RIGHT TURN  : {counter.right_turn_count}",
        f"U-TURN      : {counter.u_turn_count}",
        f"ACTIVE TRKS : {len(counter._tracks)}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(
            frame, line, (x0 + 12, y0 + 28 + i * 24),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA,
        )
    return frame


def annotate_frame(
    frame: np.ndarray,
    detections: list,
    counter: IntersectionCounter,
) -> np.ndarray:
    """Full annotation pipeline: ROIs → detections → HUD."""
    frame = draw_roi_zones(frame)
    frame = draw_detections(frame, detections, counter)
    frame = draw_hud(frame, counter)
    return frame
