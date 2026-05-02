"""
web/server.py — FastAPI Web Server with WebSocket & MJPEG Streaming
====================================================================
Serves the dashboard UI and provides real‑time data via WebSocket
plus an MJPEG video stream endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from config.settings import WS_BROADCAST_INTERVAL

logger = logging.getLogger(__name__)


class TrafficWebServer:
    """
    Encapsulates the FastAPI app, manages connected WebSocket clients,
    and exposes the MJPEG video stream.
    """

    def __init__(self) -> None:
        self.app = FastAPI(title="Traffic Monitor", version="1.0.0")
        self._clients: list[WebSocket] = []
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_data: dict = {}
        self._frame_lock = threading.Lock()
        self._data_lock = threading.Lock()

        # Mount static files & templates
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(base_dir, "static")
        template_dir = os.path.join(base_dir, "templates")

        # Create dirs if needed
        os.makedirs(static_dir, exist_ok=True)
        os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
        os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)
        os.makedirs(template_dir, exist_ok=True)

        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")
        self.templates = Jinja2Templates(directory=template_dir)

        self._register_routes()

    # ── Route registration ─────────────────────────────────────────────────

    def _register_routes(self) -> None:
        app = self.app

        @app.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            return self.templates.TemplateResponse(request, "index.html")

        @app.get("/api/status")
        async def api_status():
            with self._data_lock:
                return JSONResponse(self._latest_data)

        @app.get("/video_feed")
        async def video_feed():
            return StreamingResponse(
                self._mjpeg_generator(),
                media_type="multipart/x-mixed-replace; boundary=frame",
            )

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()
            self._clients.append(ws)
            logger.info("WebSocket client connected (%d total)", len(self._clients))
            try:
                while True:
                    # Keep alive — also allows client to send messages
                    _ = await ws.receive_text()
            except WebSocketDisconnect:
                self._clients.remove(ws)
                logger.info("WebSocket client disconnected (%d total)", len(self._clients))

    # ── Data update (called from pipeline thread) ──────────────────────────

    def update_frame(self, frame: np.ndarray) -> None:
        """Thread‑safe frame update for the MJPEG stream."""
        with self._frame_lock:
            self._latest_frame = frame.copy()

    def update_data(self, data: dict) -> None:
        """Thread‑safe data update; triggers async broadcast."""
        with self._data_lock:
            self._latest_data = data

    async def broadcast(self) -> None:
        """Send latest data to all connected WebSocket clients."""
        with self._data_lock:
            payload = json.dumps(self._latest_data)
        dead: list[WebSocket] = []
        for ws in self._clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.remove(ws)

    # ── MJPEG generator ───────────────────────────────────────────────────

    async def _mjpeg_generator(self):
        """Yield JPEG frames as multipart chunks."""
        while True:
            with self._frame_lock:
                frame = self._latest_frame
            if frame is not None:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + buf.tobytes()
                    + b"\r\n"
                )
            await asyncio.sleep(0.033)  # ~30 fps cap


# ── Singleton ──────────────────────────────────────────────────────────────

_server: Optional[TrafficWebServer] = None


def get_server() -> TrafficWebServer:
    global _server
    if _server is None:
        _server = TrafficWebServer()
    return _server
