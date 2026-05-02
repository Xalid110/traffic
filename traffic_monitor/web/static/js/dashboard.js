/**
 * Traffic Monitor — Dashboard JS
 * WebSocket real-time updates + Chart.js rendering
 */

// ── State ───────────────────────────────────────────────────────────
let ws = null;
let chart = null;
let donutChart = null;
const MAX_CHART_POINTS = 60;
const chartLabels = [];
const datasets = {
    straight: [],
    left: [],
    right: [],
};

// ── DOM refs ────────────────────────────────────────────────────────
const el = (id) => document.getElementById(id);

// ── Init ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    initDonut();
    connectWebSocket();
    startClock();
    pollStatus();
});

// ── WebSocket ───────────────────────────────────────────────────────
function connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => console.log('[WS] Connected');
    ws.onmessage = (e) => handleData(JSON.parse(e.data));
    ws.onclose = () => {
        console.log('[WS] Disconnected — reconnecting in 2s');
        setTimeout(connectWebSocket, 2000);
    };
    // Keep-alive ping every 15s
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping');
    }, 15000);
}

// ── Fallback HTTP polling ───────────────────────────────────────────
function pollStatus() {
    setInterval(async () => {
        try {
            const res = await fetch('/api/status');
            if (res.ok) handleData(await res.json());
        } catch (_) {}
    }, 2000);
}

// ── Handle incoming data ────────────────────────────────────────────
function handleData(data) {
    if (!data || !data.counts) return;
    const c = data.counts;

    // Stat tiles
    animateValue('stat-total', c.total || 0);
    animateValue('stat-straight', c.straight || 0);
    animateValue('stat-left', c.left_turn || 0);
    animateValue('stat-right', c.right_turn || 0);
    const active = el('stat-active');
    if (active) active.textContent = c.active_tracks || 0;

    // Chart update
    const now = new Date();
    const label = now.toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    chartLabels.push(label);
    datasets.straight.push(c.straight || 0);
    datasets.left.push(c.left_turn || 0);
    datasets.right.push(c.right_turn || 0);
    if (chartLabels.length > MAX_CHART_POINTS) {
        chartLabels.shift();
        datasets.straight.shift();
        datasets.left.shift();
        datasets.right.shift();
    }
    if (chart) chart.update('none');

    // Donut
    updateDonut(c.straight || 0, c.left_turn || 0, c.right_turn || 0);

    // Phases
    if (data.phases) renderPhases(data.phases);

    // Events
    if (data.events) renderEvents(data.events);

    // Vehicle classes
    if (data.class_counts) renderClasses(data.class_counts);
}

// ── Animated counter ────────────────────────────────────────────────
function animateValue(id, newVal) {
    const node = el(id);
    if (!node) return;
    const cur = parseInt(node.textContent) || 0;
    if (cur === newVal) return;
    const diff = newVal - cur;
    const steps = 12;
    let step = 0;
    const inc = diff / steps;
    const timer = setInterval(() => {
        step++;
        node.textContent = Math.round(cur + inc * step);
        if (step >= steps) {
            node.textContent = newVal;
            clearInterval(timer);
        }
    }, 30);
}

// ── Chart.js — Line Chart ───────────────────────────────────────────
function initChart() {
    const ctx = el('flow-chart');
    if (!ctx) return;
    chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [
                { label: 'Straight', data: datasets.straight, borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,.1)', tension: 0.4, pointRadius: 0, borderWidth: 2, fill: true },
                { label: 'Left Turn', data: datasets.left, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,.1)', tension: 0.4, pointRadius: 0, borderWidth: 2, fill: true },
                { label: 'Right Turn', data: datasets.right, borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,.1)', tension: 0.4, pointRadius: 0, borderWidth: 2, fill: true },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: true, position: 'top', labels: { color: '#94a3b8', boxWidth: 10, font: { size: 11, family: 'Inter' } } },
            },
            scales: {
                x: { display: true, ticks: { color: '#64748b', maxTicksLimit: 8, font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.04)' } },
                y: { display: true, beginAtZero: true, ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,.04)' } },
            },
        },
    });
}

// ── Chart.js — Donut Chart ──────────────────────────────────────────
function initDonut() {
    const ctx = el('donut-chart');
    if (!ctx) return;
    donutChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Straight', 'Left Turn', 'Right Turn'],
            datasets: [{ data: [0, 0, 0], backgroundColor: ['#10b981', '#f59e0b', '#8b5cf6'], borderWidth: 0, hoverOffset: 6 }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '65%',
            plugins: { legend: { display: false } },
        },
    });
}

function updateDonut(s, l, r) {
    if (!donutChart) return;
    donutChart.data.datasets[0].data = [s, l, r];
    donutChart.update('none');
    // Legend values
    const lv = el('legend-straight'); if (lv) lv.textContent = s;
    const ll = el('legend-left');     if (ll) ll.textContent = l;
    const lr = el('legend-right');    if (lr) lr.textContent = r;
}

// ── Phase recommendations ───────────────────────────────────────────
function renderPhases(phases) {
    const container = el('phase-list');
    if (!container) return;
    container.innerHTML = '';
    for (const [key, p] of Object.entries(phases)) {
        const pct = Math.round((p.adjusted_green / 60) * 100);
        const cls = key.replace('_turn', '');
        container.innerHTML += `
            <div class="phase-item">
                <span class="phase-dot phase-dot--${cls}"></span>
                <span class="phase-name">${p.phase.replace('_', ' ').toUpperCase()}</span>
                <div class="phase-bar-bg"><div class="phase-bar-fill phase-bar-fill--${cls}" style="width:${pct}%"></div></div>
                <span class="phase-time">${p.adjusted_green}s</span>
            </div>`;
    }
}

// ── Event log ───────────────────────────────────────────────────────
const DIR_ICONS = { STRAIGHT: '⬆️', LEFT: '↩️', RIGHT: '↪️', U_TURN: '🔄', UNKNOWN: '❓' };

function renderEvents(events) {
    const container = el('event-log');
    if (!container) return;
    container.innerHTML = '';
    events.slice(0, 15).forEach((ev) => {
        const t = new Date(ev.timestamp * 1000).toLocaleTimeString('en', { hour12: false });
        container.innerHTML += `
            <div class="event-item">
                <span class="event-icon">${DIR_ICONS[ev.direction] || '🚗'}</span>
                <span class="event-text"><strong>#${ev.track_id}</strong> ${ev.vehicle_class} → ${ev.direction}</span>
                <span class="event-time">${t}</span>
            </div>`;
    });
}

// ── Vehicle class breakdown ─────────────────────────────────────────
const CLASS_ICONS = { car: '🚗', truck: '🚛', bus: '🚌', motorcycle: '🏍️' };

function renderClasses(cc) {
    const container = el('class-breakdown');
    if (!container) return;
    container.innerHTML = '';
    for (const [cls, count] of Object.entries(cc)) {
        container.innerHTML += `
            <div class="class-item">
                <span class="class-icon">${CLASS_ICONS[cls] || '🚙'}</span>
                <div class="class-info">
                    <span class="class-name">${cls}</span>
                    <span class="class-count">${count}</span>
                </div>
            </div>`;
    }
}

// ── Clock ───────────────────────────────────────────────────────────
function startClock() {
    const node = el('clock');
    if (!node) return;
    setInterval(() => {
        node.textContent = new Date().toLocaleTimeString('en', { hour12: false });
    }, 1000);
}
