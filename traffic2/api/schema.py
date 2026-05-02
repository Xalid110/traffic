"""
api/schema.py — Pydantic Models for REST API Responses
=======================================================
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CountsResponse(BaseModel):
    left_turn: int = 0
    right_turn: int = 0
    straight: int = 0
    u_turn: int = 0
    total: int = 0
    active_tracks: int = 0
    timestamp: float = 0.0
    intersection_id: str = ""


class PhaseResponse(BaseModel):
    phase: str
    base_green: float
    adjusted_green: float
    demand_ratio: float
    timestamp: float


class EventResponse(BaseModel):
    track_id: int
    direction: str
    vehicle_class: str
    timestamp: float


class DashboardResponse(BaseModel):
    counts: CountsResponse
    phases: Dict[str, PhaseResponse] = {}
    events: List[EventResponse] = []
    class_counts: Dict[str, int] = {}
    fps: float = 0.0


class HealthResponse(BaseModel):
    status: str = "ok"
    uptime: float = 0.0
    intersection_id: str = ""
    model: str = ""
