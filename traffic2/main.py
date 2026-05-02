"""
main.py — Traffic Monitor Pipeline
====================================
Integrates YOLOv8 tracking, turning‑movement counting,
adaptive signal control, and the web dashboard.

Usage:
    python main.py                     # webcam + dashboard
    python main.py --source rtsp://... # RTSP stream
    python main.py --source video.mp4  # video file
    python main.py --no-web            # headless (no dashboard)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import time
from typing import Optional

import cv2
import uvicorn

from config.settings import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    INTERSECTION_ID,
    LEFT_TURN_COORDINATES,
    LOG_FILE,
    LOG_LEVEL,
    RTSP_URL,
    WEB_HOST,
    WEB_PORT,
    WS_BROADCAST_INTERVAL,
    YOLO_MODEL_PATH,
)
from core.controller import AdaptiveController
from core.counter import IntersectionCounter
from core.detector import VehicleDetector
from core.visualizer import annotate_frame

# ── Logging ──────────────────────────────────────────────────────────

def setup_logging() -> None:
    import os
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )

logger = logging.getLogger("traffic_monitor")


# ── Pipeline ─────────────────────────────────────────────────────────

class TrafficPipeline:
    """
    Main processing loop.

    1. Read frames from video source.
    2. Run YOLOv8 detection + tracking.
    3. Update trajectory counter.
    4. Compute adaptive signal timing.
    5. Push annotated frame + data to the web server.
    """

    def __init__(
        self,
        source: str | int,
        enable_web: bool = True,
        show_cv2: bool = False,
    ) -> None:
        self.source = source
        self.enable_web = enable_web
        self.show_cv2 = show_cv2

        # Detect if source is a static image
        self.is_image = (
            isinstance(source, str)
            and source.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))
        )

        self.detector = VehicleDetector(YOLO_MODEL_PATH)
        self.counter = IntersectionCounter(
            left_turn_zone=LEFT_TURN_COORDINATES,
            intersection_id=INTERSECTION_ID,
        )
        self.controller = AdaptiveController()
        self.web_server: Optional[object] = None

        self._running = False
        self._image_counted = False  # ensure we only count once for static images

    def start(self) -> None:
        """Entry point — starts web server (if enabled) and pipeline."""
        setup_logging()
        logger.info("Starting Traffic Monitor pipeline")
        logger.info("  Source     : %s", self.source)
        logger.info("  Model     : %s", YOLO_MODEL_PATH)
        logger.info("  Dashboard : %s", "enabled" if self.enable_web else "disabled")

        if self.enable_web:
            self._start_web_server()

        self._running = True
        try:
            self._run_pipeline()
        except KeyboardInterrupt:
            logger.info("Pipeline interrupted by user")
        finally:
            self._running = False
            logger.info("Pipeline stopped")

    # ── Web server ────────────────────────────────────────────────────

    def _start_web_server(self) -> None:
        from web.server import get_server
        from config.settings import WEB_HOST, WEB_PORT
        self.web_server = get_server()

        # Start broadcast coroutine loop
        broadcast_thread = threading.Thread(
            target=self._broadcast_loop, daemon=True
        )
        broadcast_thread.start()

        # Run uvicorn in a daemon thread
        server_thread = threading.Thread(
            target=lambda: uvicorn.run(
                self.web_server.app,
                host=WEB_HOST,
                port=WEB_PORT,
                log_level="warning",
            ),
            daemon=True,
        )
        server_thread.start()
        logger.info("Web dashboard running at http://%s:%d", WEB_HOST, WEB_PORT)

    def _broadcast_loop(self) -> None:
        """Run an asyncio event loop for WebSocket broadcasting."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self._running or True:
            if self.web_server:
                try:
                    loop.run_until_complete(self.web_server.broadcast())
                except Exception:
                    pass
            time.sleep(WS_BROADCAST_INTERVAL)

    # ── Pipeline loop ─────────────────────────────────────────────────

    def _run_pipeline(self) -> None:
        frame_count = 0
        fps_timer = time.time()
        fps_display = 0.0

        for frame, detections, looped in self.detector.track_stream(
            self.source, FRAME_WIDTH, FRAME_HEIGHT
        ):
            if looped:
                self.counter.reset()
                self._image_counted = False
                logger.info("Video looped. Counters reset.")

            frame_count += 1
            self.counter.tick()

            # Update trajectories / classify
            for det in detections:
                if self.is_image:
                    # Static image: classify by zone position (only once)
                    if not self._image_counted:
                        result = self.counter.classify_by_zone(
                            det.track_id, det.cx, det.cy, det.class_name
                        )
                        if result:
                            logger.info(
                                "Vehicle #%d in zone: %s (%s)",
                                det.track_id, result.name, det.class_name,
                            )
                else:
                    # Video/stream: use trajectory-based classification
                    self.counter.update_trajectory(
                        det.track_id, det.cx, det.cy, det.class_name
                    )
                    result = self.counter.process_movement(det.track_id)
                    if result:
                        logger.info(
                            "Vehicle #%d classified: %s (%s)",
                            det.track_id, result.name, det.class_name,
                        )

            # Mark image as counted after first frame with detections
            if self.is_image and detections and not self._image_counted:
                self._image_counted = True
                logger.info(
                    "Static image counted: %d vehicles detected",
                    len(detections),
                )

            # FPS calculation
            elapsed = time.time() - fps_timer
            if elapsed >= 1.0:
                fps_display = frame_count / elapsed
                frame_count = 0
                fps_timer = time.time()

            # Snapshot + adaptive control
            snap = self.counter.snapshot()
            phases = self.controller.recommend(snap)

            # Annotate frame
            annotated = annotate_frame(frame, detections, self.counter)

            # Console output (throttled)
            if self.counter._frame_idx % 30 == 0:
                print(
                    f"\r[{fps_display:5.1f} FPS] "
                    f"Total: {snap.total_count:4d} | "
                    f"Straight: {snap.straight_count:3d} | "
                    f"Left: {snap.left_turn_count:3d} | "
                    f"Right: {snap.right_turn_count:3d} | "
                    f"Active: {snap.active_tracks:3d}",
                    end="", flush=True,
                )

            # Push to web dashboard
            if self.web_server:
                self.web_server.update_frame(annotated)
                self.web_server.update_data({
                    "counts": snap.to_dict(),
                    "phases": {
                        k: v.to_dict() for k, v in phases.items()
                    },
                    "events": self.counter.get_recent_events(),
                    "class_counts": dict(self.counter.class_counts),
                    "fps": round(fps_display, 1),
                    "history": self.counter.get_history(60),
                })

            # OpenCV preview window
            if self.show_cv2:
                cv2.imshow("Traffic Monitor", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        if self.show_cv2:
            cv2.destroyAllWindows()


# ── CLI ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Traffic Monitor — Real-Time Intersection Intelligence",
    )
    parser.add_argument(
        "--source", type=str, default=RTSP_URL,
        help="Video source: webcam index, RTSP URL, or video file path",
    )
    parser.add_argument(
        "--model", type=str, default=YOLO_MODEL_PATH,
        help="Path to YOLO model weights",
    )
    parser.add_argument(
        "--no-web", action="store_true",
        help="Disable the web dashboard",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Show OpenCV preview window",
    )
    parser.add_argument(
        "--port", type=int, default=WEB_PORT,
        help="Web dashboard port",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Allow CLI to override globals
    import config.settings as cfg
    cfg.YOLO_MODEL_PATH = args.model
    cfg.WEB_PORT = args.port
    
    # Update the module-level reference
    globals()['WEB_PORT'] = args.port

    pipeline = TrafficPipeline(
        source=args.source,
        enable_web=not args.no_web,
        show_cv2=args.show,
    )
    pipeline.start()


if __name__ == "__main__":
    main()