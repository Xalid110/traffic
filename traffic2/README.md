# 🚦 Traffic Monitor — Real-Time Intersection Intelligence

AI-powered traffic monitoring system using **YOLOv8** for vehicle detection/tracking, trajectory-based turning-movement classification, adaptive signal timing, and a real-time web dashboard.

## Architecture

```
traffic_monitor/
├── config/
│   └── settings.py          # All configuration (ROI zones, model paths, thresholds)
├── core/
│   ├── counter.py            # Trajectory tracking & turning-movement classification
│   ├── detector.py           # YOLOv8/v11 detection wrapper
│   ├── controller.py         # Adaptive traffic-light phase controller
│   └── visualizer.py         # Frame annotation (ROIs, boxes, HUD)
├── api/
│   ├── schema.py             # Pydantic response models
│   └── client.py             # HTTP client for external systems
├── web/
│   ├── server.py             # FastAPI + WebSocket + MJPEG streaming
│   ├── templates/index.html  # Dashboard UI
│   └── static/               # CSS + JS assets
├── main.py                   # Entry point — pipeline orchestrator
└── requirements.txt
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run with webcam (default) + web dashboard
python main.py

# 3. Run with RTSP stream
python main.py --source "rtsp://user:pass@camera-ip:554/stream"

# 4. Run with video file
python main.py --source intersection_video.mp4

# 5. Headless mode (no dashboard)
python main.py --no-web --show
```

Open **http://localhost:8000** for the real-time dashboard.

## CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `--source` | Video source (webcam index, RTSP URL, or file) | `0` (webcam) |
| `--model` | Path to YOLO weights | `yolov8n.pt` |
| `--port` | Dashboard port | `8000` |
| `--no-web` | Disable web dashboard | `False` |
| `--show` | Show OpenCV preview window | `False` |

## Environment Variables

All settings can be overridden with `TM_` prefixed env vars:

```bash
TM_RTSP_URL=rtsp://...
TM_YOLO_MODEL_PATH=yolov8m.pt
TM_CONFIDENCE_THRESHOLD=0.5
TM_WEB_PORT=9000
```

## Features

- **YOLOv8 Vehicle Detection** — cars, trucks, buses, motorcycles
- **ByteTrack Tracking** — persistent IDs across frames
- **Turning Movement Classification** — straight / left / right / U-turn
- **Adaptive Signal Control** — green-time recommendations
- **Web Dashboard** — real-time stats, charts, MJPEG video stream
- **WebSocket Updates** — sub-second latency data push
- **Stale Track Eviction** — handles ID swaps gracefully
