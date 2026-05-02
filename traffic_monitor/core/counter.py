"""
core/counter.py — Trajectory Tracking & Turning‑Movement Classification
========================================================================
Handles per‑vehicle trajectory histories, ROI polygon intersection tests,
angular‑displacement direction classification, and aggregated counters.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

from config.settings import (
    ALL_ROI_ZONES,
    ENTRY_ZONE,
    LEFT_TURN_ZONE,
    MOVEMENT_FORWARD_THRESHOLD,
    MOVEMENT_LATERAL_THRESHOLD,
    RIGHT_TURN_ZONE,
    ROIZone,
    STALE_TRACK_FRAMES,
    STRAIGHT_ZONE,
    TRAJECTORY_MAX_LENGTH,
    TRAJECTORY_MIN_POINTS,
)


# ── Direction enum ─────────────────────────────────────────────────────────

class Direction(Enum):
    """Possible turning movements at an intersection."""
    STRAIGHT = auto()
    LEFT = auto()
    RIGHT = auto()
    U_TURN = auto()
    UNKNOWN = auto()


# ── Per‑vehicle state ──────────────────────────────────────────────────────

@dataclass
class VehicleTrack:
    """Rolling trajectory history for a single tracked vehicle."""
    track_id: int
    trajectory: Deque[Tuple[int, int]] = field(
        default_factory=lambda: deque(maxlen=TRAJECTORY_MAX_LENGTH)
    )
    classified: bool = False
    direction: Direction = Direction.UNKNOWN
    last_seen_frame: int = 0
    entry_timestamp: float = field(default_factory=time.time)
    vehicle_class: str = "vehicle"


# ── Counter dataclass (snapshot for the dashboard) ─────────────────────────

@dataclass
class MovementSnapshot:
    """Immutable snapshot of current counts, safe for serialisation."""
    left_turn_count: int = 0
    right_turn_count: int = 0
    straight_count: int = 0
    u_turn_count: int = 0
    total_count: int = 0
    active_tracks: int = 0
    timestamp: float = field(default_factory=time.time)
    intersection_id: str = ""

    def to_dict(self) -> dict:
        return {
            "left_turn": self.left_turn_count,
            "right_turn": self.right_turn_count,
            "straight": self.straight_count,
            "u_turn": self.u_turn_count,
            "total": self.total_count,
            "active_tracks": self.active_tracks,
            "timestamp": self.timestamp,
            "intersection_id": self.intersection_id,
        }


# ── Main counter class ────────────────────────────────────────────────────

class IntersectionCounter:
    """
    Production‑grade turning‑movement counter.

    *   Maintains per‑vehicle trajectory histories (bounded deque).
    *   Classifies movement once enough points are collected,
        using angular displacement **and** ROI polygon tests.
    *   Evicts stale tracks to avoid memory leaks from ID swaps.
    """

    def __init__(
        self,
        left_turn_zone: Optional[List[List[int]]] = None,
        right_turn_zone: Optional[List[List[int]]] = None,
        straight_zone: Optional[List[List[int]]] = None,
        entry_zone: Optional[List[List[int]]] = None,
        intersection_id: str = "",
    ) -> None:
        # Polygon numpy arrays for cv2.pointPolygonTest
        self._left_poly = self._to_np(left_turn_zone or [list(p) for p in LEFT_TURN_ZONE.polygon])
        self._right_poly = self._to_np(right_turn_zone or [list(p) for p in RIGHT_TURN_ZONE.polygon])
        self._straight_poly = self._to_np(straight_zone or [list(p) for p in STRAIGHT_ZONE.polygon])
        self._entry_poly = self._to_np(entry_zone or [list(p) for p in ENTRY_ZONE.polygon])

        self.intersection_id: str = intersection_id

        # Active vehicle tracks  {track_id: VehicleTrack}
        self._tracks: Dict[int, VehicleTrack] = {}

        # Cumulative counters
        self.left_turn_count: int = 0
        self.right_turn_count: int = 0
        self.straight_count: int = 0
        self.u_turn_count: int = 0
        self.total_count: int = 0

        # Time‑series history for charts (last N snapshots)
        self._history: Deque[MovementSnapshot] = deque(maxlen=600)
        self._frame_idx: int = 0

        # Per-class counts
        self.class_counts: Dict[str, int] = defaultdict(int)

        # Recent events list for the dashboard
        self._recent_events: Deque[dict] = deque(maxlen=50)

    # ── helpers ────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all counters and tracks (e.g. when video loops)."""
        self._tracks.clear()
        self.left_turn_count = 0
        self.right_turn_count = 0
        self.straight_count = 0
        self.u_turn_count = 0
        self.total_count = 0
        self._history.clear()
        self.class_counts.clear()
        self._recent_events.clear()
        self._frame_idx = 0

    @staticmethod
    def _to_np(pts: List[List[int]]) -> np.ndarray:
        return np.array(pts, dtype=np.int32)

    @staticmethod
    def _angle_deg(dx: float, dy: float) -> float:
        """Return angle in degrees (0°=right, 90°=down)."""
        return math.degrees(math.atan2(dy, dx))

    @staticmethod
    def _point_in_poly(poly: np.ndarray, x: int, y: int) -> bool:
        return cv2.pointPolygonTest(poly, (float(x), float(y)), False) >= 0

    # ── public API ─────────────────────────────────────────────────────────

    def update_trajectory(
        self,
        track_id: int,
        cx: int,
        cy: int,
        vehicle_class: str = "vehicle",
    ) -> None:
        """Append a centre‑point to the vehicle's trajectory."""
        if track_id not in self._tracks:
            self._tracks[track_id] = VehicleTrack(track_id=track_id, vehicle_class=vehicle_class)
        trk = self._tracks[track_id]
        trk.trajectory.append((cx, cy))
        trk.last_seen_frame = self._frame_idx
        trk.vehicle_class = vehicle_class

    def process_movement(self, track_id: int) -> Optional[Direction]:
        """
        Classify the movement of *track_id*.

        Returns the ``Direction`` if the vehicle was just classified,
        otherwise ``None``.
        """
        trk = self._tracks.get(track_id)
        if trk is None or trk.classified:
            return None

        traj = trk.trajectory
        if len(traj) < TRAJECTORY_MIN_POINTS:
            return None

        direction = self._classify(traj)
        if direction is Direction.UNKNOWN:
            return None

        # Record
        trk.classified = True
        trk.direction = direction
        self._increment(direction, trk.vehicle_class)

        # Log recent event
        self._recent_events.appendleft({
            "track_id": track_id,
            "direction": direction.name,
            "vehicle_class": trk.vehicle_class,
            "timestamp": time.time(),
        })

        return direction

    def tick(self) -> None:
        """Call once per frame to advance internal bookkeeping."""
        self._frame_idx += 1
        self._evict_stale()

    def snapshot(self) -> MovementSnapshot:
        """Return an immutable snapshot of current counts."""
        snap = MovementSnapshot(
            left_turn_count=self.left_turn_count,
            right_turn_count=self.right_turn_count,
            straight_count=self.straight_count,
            u_turn_count=self.u_turn_count,
            total_count=self.total_count,
            active_tracks=len(self._tracks),
            intersection_id=self.intersection_id,
        )
        self._history.append(snap)
        return snap

    def get_history(self, n: int = 60) -> List[dict]:
        """Return the last *n* snapshots as dicts."""
        items = list(self._history)[-n:]
        return [s.to_dict() for s in items]

    def get_recent_events(self, n: int = 20) -> List[dict]:
        """Return the last *n* classification events."""
        return list(self._recent_events)[:n]

    def get_active_tracks(self) -> Dict[int, List[Tuple[int, int]]]:
        """Return active trajectories for overlay drawing."""
        return {
            tid: list(trk.trajectory)
            for tid, trk in self._tracks.items()
            if not trk.classified
        }

    def classify_by_zone(self, track_id: int, cx: int, cy: int,
                         vehicle_class: str = "vehicle") -> Optional[Direction]:
        """
        Classify a vehicle by its current position relative to ROI zones.
        Used for **static image** mode where vehicles don't move across frames
        so trajectory-based classification can never fire.
        Only counts each track_id once.
        """
        # Skip if already classified
        trk = self._tracks.get(track_id)
        if trk is not None and trk.classified:
            return None

        # Create track if needed
        if trk is None:
            self._tracks[track_id] = VehicleTrack(
                track_id=track_id, vehicle_class=vehicle_class
            )
            trk = self._tracks[track_id]

        direction = Direction.UNKNOWN

        if self._point_in_poly(self._left_poly, cx, cy):
            direction = Direction.LEFT
        elif self._point_in_poly(self._right_poly, cx, cy):
            direction = Direction.RIGHT
        elif self._point_in_poly(self._straight_poly, cx, cy):
            direction = Direction.STRAIGHT
        elif self._point_in_poly(self._entry_poly, cx, cy):
            direction = Direction.STRAIGHT  # entry zone = approaching straight

        if direction is Direction.UNKNOWN:
            # Vehicle is outside all zones — still count as total
            self.total_count += 1
            self.class_counts[vehicle_class] += 1
            trk.classified = True
            trk.direction = direction
            self._recent_events.appendleft({
                "track_id": track_id,
                "direction": "DETECTED",
                "vehicle_class": vehicle_class,
                "timestamp": time.time(),
            })
            return None

        # Record
        trk.classified = True
        trk.direction = direction
        self._increment(direction, vehicle_class)
        trk.trajectory.append((cx, cy))
        trk.last_seen_frame = self._frame_idx

        self._recent_events.appendleft({
            "track_id": track_id,
            "direction": direction.name,
            "vehicle_class": vehicle_class,
            "timestamp": time.time(),
        })

        return direction

    # ── internals ──────────────────────────────────────────────────────────

    def _classify(self, traj: Deque[Tuple[int, int]]) -> Direction:
        """
        Two‑stage classifier:
            1. **ROI polygon test** — if the latest point falls inside a
               turn zone, classify immediately.
            2. **Angular displacement** — compute the net heading change
               between the first‑third and last‑third of the trajectory
               to distinguish straight / left / right / U‑turn.
        """
        x_cur, y_cur = traj[-1]

        # Stage 1: ROI polygon test
        if self._point_in_poly(self._left_poly, x_cur, y_cur):
            return Direction.LEFT
        if self._point_in_poly(self._right_poly, x_cur, y_cur):
            return Direction.RIGHT
        if self._point_in_poly(self._straight_poly, x_cur, y_cur):
            return Direction.STRAIGHT

        # Stage 2: Angular displacement
        pts = list(traj)
        n = len(pts)
        third = max(n // 3, 1)

        # Entry vector (first third)
        x0, y0 = pts[0]
        x1, y1 = pts[third]
        entry_angle = self._angle_deg(x1 - x0, y1 - y0)

        # Exit vector (last third)
        x2, y2 = pts[-third]
        x3, y3 = pts[-1]
        exit_angle = self._angle_deg(x3 - x2, y3 - y2)

        # Net heading change (normalised to -180..180)
        delta = (exit_angle - entry_angle + 180) % 360 - 180

        # Net displacement
        dx_total = abs(pts[-1][0] - pts[0][0])
        dy_total = abs(pts[-1][1] - pts[0][1])

        # Only classify if meaningful displacement occurred
        if dx_total < 15 and dy_total < 15:
            return Direction.UNKNOWN

        if abs(delta) < 25 and dy_total > MOVEMENT_FORWARD_THRESHOLD:
            return Direction.STRAIGHT
        elif delta < -25 and dx_total > MOVEMENT_LATERAL_THRESHOLD:
            return Direction.LEFT
        elif delta > 25 and dx_total > MOVEMENT_LATERAL_THRESHOLD:
            return Direction.RIGHT
        elif abs(delta) > 140:
            return Direction.U_TURN

        return Direction.UNKNOWN

    def _increment(self, direction: Direction, vehicle_class: str) -> None:
        self.total_count += 1
        self.class_counts[vehicle_class] += 1
        if direction is Direction.LEFT:
            self.left_turn_count += 1
        elif direction is Direction.RIGHT:
            self.right_turn_count += 1
        elif direction is Direction.STRAIGHT:
            self.straight_count += 1
        elif direction is Direction.U_TURN:
            self.u_turn_count += 1

    def _evict_stale(self) -> None:
        """Remove tracks not seen for ``STALE_TRACK_FRAMES`` frames."""
        stale_ids = [
            tid
            for tid, trk in self._tracks.items()
            if (self._frame_idx - trk.last_seen_frame) > STALE_TRACK_FRAMES
        ]
        for tid in stale_ids:
            del self._tracks[tid]