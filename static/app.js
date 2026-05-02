/**
 * Traffic Monitor — Map Control Panel
 * ====================================
 * Interactive Leaflet map with markers for each traffic camera.
 * Communicates with the Flask backend to start/stop monitor processes.
 */

// ── State ──────────────────────────────────────────────────────────

const state = {
    monitors: {},
    markers: {},
    map: null,
    pollInterval: null,
};

// ── Initialization ─────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    initMap();
    loadMonitors();
    // Poll status every 3 seconds
    state.pollInterval = setInterval(refreshStatus, 3000);
});

function initMap() {
    // Center between the two points
    const centerLat = (40.37534450550863 + 40.37599085456807) / 2;
    const centerLng = (49.85410697518418 + 49.856587875415904) / 2;

    state.map = L.map("map", {
        center: [centerLat, centerLng],
        zoom: 17,
        zoomControl: true,
        attributionControl: true,
    });

    // Use CartoDB Dark Matter tiles for dark theme
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 20,
    }).addTo(state.map);

    // Remove default tile filter since we're using dark tiles
    document.querySelector(".leaflet-tile-pane").style.filter = "none";
}


// ── Load Monitors ──────────────────────────────────────────────────

async function loadMonitors() {
    try {
        const res = await fetch("/api/monitors");
        const data = await res.json();
        state.monitors = data;

        for (const [id, monitor] of Object.entries(data)) {
            createMarker(id, monitor);
            createCard(id, monitor);
        }
    } catch (err) {
        showToast("error", "Failed to load monitor data");
        console.error(err);
    }
}


// ── Map Markers ────────────────────────────────────────────────────

function createMarker(id, monitor) {
    const markerState = monitor.running ? "running" : "idle";
    const cameraIcon = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>`;

    const icon = L.divIcon({
        className: "custom-marker",
        html: `
            <div class="marker-pin ${markerState}" data-id="${id}">
                <div class="marker-pulse"></div>
                <span class="marker-icon">${cameraIcon}</span>
            </div>
            <div class="marker-label">${monitor.name}</div>
        `,
        iconSize: [44, 70],
        iconAnchor: [22, 22],
        popupAnchor: [0, -30],
    });

    const marker = L.marker([monitor.lat, monitor.lng], { icon })
        .addTo(state.map)
        .bindPopup(() => buildPopupContent(id), {
            maxWidth: 280,
            minWidth: 220,
            closeButton: true,
        });

    marker.on("click", () => {
        // Just open popup, don't auto-start
    });

    state.markers[id] = marker;
}

function updateMarkerState(id, running) {
    const marker = state.markers[id];
    if (!marker) return;

    const pin = marker.getElement()?.querySelector(".marker-pin");
    if (pin) {
        pin.classList.remove("idle", "running", "loading");
        pin.classList.add(running ? "running" : "idle");
    }
}

function setMarkerLoading(id) {
    const marker = state.markers[id];
    if (!marker) return;

    const pin = marker.getElement()?.querySelector(".marker-pin");
    if (pin) {
        pin.classList.remove("idle", "running");
        pin.classList.add("loading");
    }
}

function buildPopupContent(id) {
    const m = state.monitors[id];
    if (!m) return "<p>Unknown</p>";

    const statusClass = m.running ? "running" : "stopped";
    const statusText = m.running ? "● Running" : "○ Stopped";
    const btnClass = m.running ? "stop" : "start";
    const btnText = m.running ? "⏹ Stop Monitor" : "▶ Start Monitor";

    let html = `
        <div class="popup-content">
            <div class="popup-title">${m.name}</div>
            <div class="popup-description">${m.description}</div>
            <div class="popup-status ${statusClass}">${statusText}</div>
            <button class="popup-btn ${btnClass}" id="popup-btn-${id}"
                onclick="${m.running ? `stopMonitor('${id}')` : `startMonitor('${id}')`}">
                ${btnText}
            </button>
    `;

    if (m.running) {
        html += `<a class="popup-dashboard-link" href="http://localhost:${m.dashboard_port}" target="_blank">
            Open Live Dashboard →
        </a>`;
    }

    html += `</div>`;
    return html;
}


// ── Side Panel Cards ───────────────────────────────────────────────

function createCard(id, monitor) {
    const container = document.getElementById("monitors-list");

    const card = document.createElement("div");
    card.className = `monitor-card ${monitor.running ? "running" : ""}`;
    card.id = `card-${id}`;

    card.innerHTML = buildCardContent(id, monitor);
    container.appendChild(card);
}

function buildCardContent(id, monitor) {
    const statusBadge = monitor.running
        ? `<span class="card-status-badge running">Live</span>`
        : `<span class="card-status-badge stopped">Offline</span>`;

    let actions = "";
    if (monitor.running) {
        actions = `
            <button class="card-btn dashboard-btn" onclick="window.open('http://localhost:${monitor.dashboard_port}', '_blank')">
                📊 Dashboard
            </button>
            <button class="card-btn stop-btn" onclick="stopMonitor('${id}')" id="card-btn-stop-${id}">
                ⏹ Stop
            </button>
        `;
    } else {
        actions = `
            <button class="card-btn start-btn" onclick="startMonitor('${id}')" id="card-btn-start-${id}">
                ▶ Start Monitor
            </button>
        `;
    }

    return `
        <div class="card-header">
            <div class="card-title-area">
                <div class="card-title">${monitor.name}</div>
                <div class="card-description">${monitor.description}</div>
            </div>
            ${statusBadge}
        </div>
        <div class="card-coords">📍 ${monitor.lat.toFixed(6)}, ${monitor.lng.toFixed(6)}</div>
        <div class="card-actions">${actions}</div>
    `;
}

function updateCard(id) {
    const card = document.getElementById(`card-${id}`);
    const monitor = state.monitors[id];
    if (!card || !monitor) return;

    card.className = `monitor-card ${monitor.running ? "running" : ""}`;
    card.innerHTML = buildCardContent(id, monitor);
}


// ── API Calls ──────────────────────────────────────────────────────

async function startMonitor(id) {
    const monitor = state.monitors[id];
    if (!monitor) return;

    // Disable buttons
    setButtonsLoading(id, true);
    setMarkerLoading(id);
    showToast("info", `Starting ${monitor.name}...`);

    try {
        const res = await fetch(`/api/start/${id}`, { method: "POST" });
        const data = await res.json();

        if (data.status === "started" || data.status === "already_running") {
            state.monitors[id].running = true;
            updateMarkerState(id, true);
            updateCard(id);
            refreshPopup(id);
            showToast("success", data.message);

            // Open dashboard after a short delay
            if (data.dashboard_url) {
                setTimeout(() => {
                    window.open(data.dashboard_url, `_dashboard_${id}`);
                }, 2000);
            }
        } else {
            showToast("error", data.message || "Failed to start");
            setButtonsLoading(id, false);
            updateMarkerState(id, false);
        }
    } catch (err) {
        showToast("error", `Error starting ${monitor.name}`);
        console.error(err);
        setButtonsLoading(id, false);
        updateMarkerState(id, false);
    }
}

async function stopMonitor(id) {
    const monitor = state.monitors[id];
    if (!monitor) return;

    setButtonsLoading(id, true);
    showToast("warning", `Stopping ${monitor.name}...`);

    try {
        const res = await fetch(`/api/stop/${id}`, { method: "POST" });
        const data = await res.json();

        state.monitors[id].running = false;
        updateMarkerState(id, false);
        updateCard(id);
        refreshPopup(id);
        showToast("success", data.message);
    } catch (err) {
        showToast("error", `Error stopping ${monitor.name}`);
        console.error(err);
        setButtonsLoading(id, false);
    }
}


// ── Status Polling ─────────────────────────────────────────────────

async function refreshStatus() {
    try {
        const res = await fetch("/api/monitors");
        const data = await res.json();

        for (const [id, monitor] of Object.entries(data)) {
            const prev = state.monitors[id];
            const changed = prev && prev.running !== monitor.running;

            state.monitors[id] = monitor;

            if (changed) {
                updateMarkerState(id, monitor.running);
                updateCard(id);

                if (!monitor.running && prev.running) {
                    showToast("warning", `${monitor.name} has stopped`);
                }
            }
        }
    } catch {
        // Silent fail on poll
    }
}


// ── Helpers ────────────────────────────────────────────────────────

function setButtonsLoading(id, loading) {
    const btns = document.querySelectorAll(
        `#card-btn-start-${id}, #card-btn-stop-${id}, #popup-btn-${id}`
    );
    btns.forEach((btn) => {
        if (btn) {
            btn.disabled = loading;
            if (loading) {
                btn.dataset.originalText = btn.innerHTML;
                btn.innerHTML = `<span class="spinner"></span> Please wait...`;
            }
        }
    });
}

function refreshPopup(id) {
    const marker = state.markers[id];
    if (marker && marker.isPopupOpen()) {
        marker.getPopup().setContent(buildPopupContent(id));
    }
}


// ── Toast System ───────────────────────────────────────────────────

const toastIcons = {
    success: "✅",
    error: "❌",
    info: "ℹ️",
    warning: "⚠️",
};

function showToast(type, message) {
    const container = document.getElementById("toast-container");

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${toastIcons[type] || "ℹ️"}</span>
        <span>${message}</span>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add("leaving");
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
