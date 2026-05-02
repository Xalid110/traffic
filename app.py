"""
Traffic Map Controller
======================
Flask app that serves an interactive map with two traffic monitor points.
Clicking a marker starts the corresponding traffic monitor pipeline.
"""

import subprocess
import os
import signal
import sys
import time
import requests
from flask import Flask, render_template, jsonify, request

app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Store running processes and their log file handles
processes = {
    "traffic_monitor": None,
    "traffic2": None,
}

log_files = {
    "traffic_monitor": None,
    "traffic2": None,
}

# Configuration for each monitor
MONITORS = {
    "traffic_monitor": {
        "name": "Polis Camera 1",
        "lat": 40.37534450550863,
        "lng": 49.85410697518418,
        "command": [sys.executable, "main.py", "--source", "polis.mp4", "--port", "8001"],
        "cwd": os.path.join(BASE_DIR, "traffic_monitor"),
        "dashboard_port": 8001,
        "description": "Yusif Safarov × 28 May — Camera 1",
    },
    "traffic2": {
        "name": "Polis Camera 2",
        "lat": 40.37599085456807,
        "lng": 49.856587875415904,
        "command": [sys.executable, "main.py", "--source", "polis2.mp4", "--port", "8002"],
        "cwd": os.path.join(BASE_DIR, "traffic2"),
        "dashboard_port": 8002,
        "description": "Yusif Safarov × 28 May — Camera 2",
    },
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/.well-known/appspecific/com.chrome.devtools.json")
def chrome_devtools():
    """Silence the Chrome DevTools 404 error."""
    return jsonify({})


@app.route("/api/monitors")
def get_monitors():
    """Return monitor configs with their running status."""
    result = {}
    for key, cfg in MONITORS.items():
        proc = processes[key]
        running = proc is not None and proc.poll() is None
        # Clean up dead processes
        if proc is not None and proc.poll() is not None:
            processes[key] = None
            if log_files[key]:
                try:
                    log_files[key].close()
                except:
                    pass
                log_files[key] = None

        result[key] = {
            "name": cfg["name"],
            "lat": cfg["lat"],
            "lng": cfg["lng"],
            "description": cfg["description"],
            "dashboard_port": cfg["dashboard_port"],
            "running": running,
        }
    return jsonify(result)


@app.route("/api/start/<monitor_id>", methods=["POST"])
def start_monitor(monitor_id):
    """Start a traffic monitor process."""
    if monitor_id not in MONITORS:
        return jsonify({"error": "Unknown monitor"}), 404

    # Check if already running
    proc = processes[monitor_id]
    if proc is not None and proc.poll() is None:
        return jsonify({
            "status": "already_running",
            "message": f"{MONITORS[monitor_id]['name']} is already running",
            "dashboard_url": f"http://localhost:{MONITORS[monitor_id]['dashboard_port']}",
        })

    cfg = MONITORS[monitor_id]
    try:
        # Redirect output to log files instead of PIPE to avoid blocking
        log_path = os.path.join(LOGS_DIR, f"{monitor_id}.log")
        log_file = open(log_path, "w", encoding="utf-8")
        log_files[monitor_id] = log_file

        proc = subprocess.Popen(
            cfg["command"],
            cwd=cfg["cwd"],
            stdout=log_file,
            stderr=log_file,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        processes[monitor_id] = proc

        # Give it a moment to start and check if it crashed immediately
        time.sleep(1)
        if proc.poll() is not None:
            # Process crashed
            log_file.flush()
            log_file.close()
            log_files[monitor_id] = None
            processes[monitor_id] = None
            # Read error log
            with open(log_path, "r", encoding="utf-8") as f:
                error_output = f.read()[-500:]
            return jsonify({
                "status": "error",
                "message": f"Process crashed immediately. Check logs.",
                "log": error_output,
            }), 500

        # Wait for the web server to be ready (max 60 seconds)
        port = cfg["dashboard_port"]
        health_url = f"http://localhost:{port}/api/status"
        max_retries = 60
        for attempt in range(max_retries):
            try:
                response = requests.get(health_url, timeout=2)
                if response.status_code == 200:
                    # Server is ready!
                    return jsonify({
                        "status": "started",
                        "message": f"{cfg['name']} started successfully (PID: {proc.pid})",
                        "pid": proc.pid,
                        "dashboard_url": f"http://localhost:{cfg['dashboard_port']}",
                    })
            except (requests.ConnectionError, requests.Timeout):
                pass
            
            # Check if process died while waiting
            if proc.poll() is not None:
                log_file.flush()
                log_file.close()
                log_files[monitor_id] = None
                processes[monitor_id] = None
                with open(log_path, "r", encoding="utf-8") as f:
                    error_output = f.read()[-500:]
                return jsonify({
                    "status": "error",
                    "message": f"Process crashed during startup. Check logs.",
                    "log": error_output,
                }), 500
            
            time.sleep(1)
        
        # Timeout waiting for server
        return jsonify({
            "status": "started",
            "message": f"{cfg['name']} started but server took too long to respond. Try again in a moment.",
            "pid": proc.pid,
            "dashboard_url": f"http://localhost:{cfg['dashboard_port']}",
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/stop/<monitor_id>", methods=["POST"])
def stop_monitor(monitor_id):
    """Stop a running traffic monitor process."""
    if monitor_id not in MONITORS:
        return jsonify({"error": "Unknown monitor"}), 404

    proc = processes[monitor_id]
    if proc is None or proc.poll() is not None:
        processes[monitor_id] = None
        if log_files[monitor_id]:
            try:
                log_files[monitor_id].close()
            except:
                pass
            log_files[monitor_id] = None
        return jsonify({
            "status": "not_running",
            "message": f"{MONITORS[monitor_id]['name']} is not running",
        })

    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            os.kill(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    finally:
        processes[monitor_id] = None
        if log_files[monitor_id]:
            try:
                log_files[monitor_id].close()
            except:
                pass
            log_files[monitor_id] = None

    return jsonify({
        "status": "stopped",
        "message": f"{MONITORS[monitor_id]['name']} stopped",
    })


@app.route("/api/status/<monitor_id>")
def monitor_status(monitor_id):
    """Get status of a specific monitor with log output."""
    if monitor_id not in MONITORS:
        return jsonify({"error": "Unknown monitor"}), 404

    proc = processes[monitor_id]
    running = proc is not None and proc.poll() is None

    # Read last part of log file
    log_path = os.path.join(LOGS_DIR, f"{monitor_id}.log")
    log_tail = ""
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                log_tail = content[-1000:]
        except:
            pass

    return jsonify({
        "monitor_id": monitor_id,
        "running": running,
        "pid": proc.pid if running else None,
        "return_code": proc.poll() if proc else None,
        "dashboard_url": f"http://localhost:{MONITORS[monitor_id]['dashboard_port']}" if running else None,
        "log": log_tail,
    })


@app.route("/api/logs/<monitor_id>")
def get_logs(monitor_id):
    """Get full logs for a monitor."""
    log_path = os.path.join(LOGS_DIR, f"{monitor_id}.log")
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), 200, {"Content-Type": "text/plain"}
    return "No logs found", 404


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Traffic Map Controller")
    print("  Open http://localhost:5000 in your browser")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
