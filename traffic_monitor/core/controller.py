"""
core/controller.py — Adaptive Traffic‑Light Phase Controller
=============================================================
Uses real‑time turning‑movement ratios to recommend green‑time
adjustments for each signal phase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from config.settings import PhaseTiming, PHASE_TIMING
from core.counter import MovementSnapshot


@dataclass
class PhaseRecommendation:
    """Recommended green‑time for a single phase."""
    phase_name: str
    base_green: float
    adjusted_green: float
    demand_ratio: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase_name,
            "base_green": round(self.base_green, 1),
            "adjusted_green": round(self.adjusted_green, 1),
            "demand_ratio": round(self.demand_ratio, 3),
            "timestamp": self.timestamp,
        }


class AdaptiveController:
    """
    Simple demand‑responsive controller.

    Given a ``MovementSnapshot``, compute the fraction of vehicles
    turning left vs. going straight and scale green times
    proportionally within the configured min/max bounds.
    """

    def __init__(self, timing: PhaseTiming = PHASE_TIMING) -> None:
        self.timing = timing
        self._last_recommendation: Optional[Dict[str, PhaseRecommendation]] = None

    def recommend(self, snap: MovementSnapshot) -> Dict[str, PhaseRecommendation]:
        total = max(snap.total_count, 1)
        base = (self.timing.min_green + self.timing.max_green) / 2

        phases: Dict[str, PhaseRecommendation] = {}

        for name, count in [
            ("straight", snap.straight_count),
            ("left_turn", snap.left_turn_count),
            ("right_turn", snap.right_turn_count),
        ]:
            ratio = count / total
            adjusted = base * (0.5 + ratio)
            adjusted = max(self.timing.min_green, min(self.timing.max_green, adjusted))
            phases[name] = PhaseRecommendation(
                phase_name=name,
                base_green=base,
                adjusted_green=adjusted,
                demand_ratio=ratio,
            )

        self._last_recommendation = phases
        return phases

    @property
    def last(self) -> Optional[Dict[str, PhaseRecommendation]]:
        return self._last_recommendation
