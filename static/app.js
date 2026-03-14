/**
 * VitalGuard — Frontend Application Logic
 * WebSocket connection, real-time updates, and dashboard interactivity.
 */

// State
const state = {
    ws: null,
    connected: false,
    reconnectAttempts: 0,
    maxReconnectAttempts: 20,
    reconnectDelay: 2000,
    currentMode: 'normal',
    logEntries: [],
    actionEntries: [],
    twilioStatus: null,
    location: null,
};

// DOM Elements
const DOM = {
    connectionStatus: document.getElementById('connection-status'),
    statusDot: null,
    statusText: null,
    headerTime: document.getElementById('header-time'),

    valHR:   document.getElementById('val-hr'),
    valSpO2: document.getElementById('val-spo2'),
    valTemp: document.getElementById('val-temp'),
    valHRV:  document.getElementById('val-hrv'),

    barHR:   document.getElementById('bar-hr'),
    barSpO2: document.getElementById('bar-spo2'),
    barTemp: document.getElementById('bar-temp'),
    barHRV:  document.getElementById('bar-hrv'),

    cardHR:   document.getElementById('card-hr'),
    cardSpO2: document.getElementById('card-spo2'),
    cardTemp: document.getElementById('card-temp'),
    cardHRV:  document.getElementById('card-hrv'),

    gaugeFill:  document.getElementById('gauge-fill'),
    gaugeValue: document.getElementById('gauge-value'),
    gaugeLabel: document.getElementById('gauge-label'),

    riskFactors: document.getElementById('risk-factors'),
    actionsList: document.getElementById('actions-list'),
    decisionLog: document.getElementById('decision-log'),
    logCount:    document.getElementById('log-count'),
};

// Initialize
function init() {
    DOM.statusDot  = DOM.connectionStatus.querySelector('.status-dot');
    DOM.statusText = DOM.connectionStatus.querySelector('.status-text');
    DOM.twilioBadge = document.getElementById('twilio-badge');

    initCharts();
    setupScenarioButtons();
    startClock();
    connectWebSocket();
    fetchTwilioStatus();
}

// Twilio Status
async function fetchTwilioStatus() {
    try {
        const res  = await fetch('/api/twilio-status');
        const data = await res.json();
        state.twilioStatus = data;

        const badge = DOM.twilioBadge;
        const label = badge.querySelector('.twilio-label');

        if (data.enabled && data.configured) {
            badge.className    = 'twilio-badge live';
            label.textContent  = 'SMS: Live';
            badge.title        = `Twilio SMS active — Patient: ${data.patient_name}, Contact: ${data.emergency_contact_name}`;
        } else {
            badge.className    = 'twilio-badge mock';
            label.textContent  = 'SMS: Mock';
            badge.title        = 'Twilio not configured — SMS actions are simulated';
        }
    } catch (e) {
        console.error('[VitalGuard] Failed to fetch Twilio status:', e);
    }
}

// Clock
function startClock() {
    function updateTime() {
        const now = new Date();
        DOM.headerTime.textContent = now.toLocaleTimeString('en-IN', {
            hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
        });
    }
    updateTime();
    setInterval(updateTime, 1000);
}

// Scenario Buttons
function setupScenarioButtons() {
    document.querySelectorAll('.scenario-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const mode = btn.dataset.mode;
            state.currentMode = mode;

            document.querySelectorAll('.scenario-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send(JSON.stringify({ type: 'set_mode', mode }));
            }
        });
    });
}

// WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl    = `${protocol}//${window.location.host}/ws`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        state.connected        = true;
        state.reconnectAttempts = 0;
        updateConnectionStatus(true);
        console.log('[VitalGuard] WebSocket connected');

        // Re-send location immediately on reconnect
        if (state.location && state.location.lat) {
            state.ws.send(JSON.stringify({ type: 'location_update', location: state.location }));
        }
        // If no location yet, request it fresh
        if (!state.location || !state.location.lat) {
            requestLocationOnce();
        }

        // Refill chart buffers with baseline on reconnect
        for (const key of Object.keys(CHART_CONFIG)) fillBuffer(key);
    };

    state.ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        } catch (e) {
            console.error('[VitalGuard] Failed to parse message:', e);
        }
    };

    state.ws.onclose = () => {
        state.connected = false;
        updateConnectionStatus(false);
        console.log('[VitalGuard] WebSocket disconnected');
        attemptReconnect();
    };

    state.ws.onerror = (error) => {
        console.error('[VitalGuard] WebSocket error:', error);
    };
}

function attemptReconnect() {
    if (state.reconnectAttempts < state.maxReconnectAttempts) {
        state.reconnectAttempts++;
        DOM.statusText.textContent = `Reconnecting (${state.reconnectAttempts})...`;
        setTimeout(connectWebSocket, state.reconnectDelay);
    } else {
        DOM.statusText.textContent = 'Connection failed';
    }
}

function updateConnectionStatus(connected) {
    if (connected) {
        DOM.statusDot.className    = 'status-dot connected';
        DOM.statusText.textContent = 'Live';
    } else {
        DOM.statusDot.className    = 'status-dot disconnected';
        DOM.statusText.textContent = 'Disconnected';
    }
}

// Message Handler
function handleMessage(msg) {
    switch (msg.type) {
        case 'vitals':   updateVitals(msg.data);    break;
        case 'risk':     updateRiskGauge(msg.data); break;
        case 'decision': addDecisionLog(msg.data);  break;
        case 'action':   addActionItem(msg.data);   break;
        case 'system':   console.log('[System]', msg.message); break;
        case 'error':    console.error('[Agent Error]', msg.message); break;
    }
}

// Vitals Config
const VITAL_CONFIG = {
    heart_rate: {
        el: 'val-hr', bar: 'bar-hr', card: 'card-hr',
        min: 30, max: 200, normalLow: 60, normalHigh: 100,
        warnHigh: 120, critHigh: 140, warnLow: 50, critLow: 40,
    },
    spo2: {
        el: 'val-spo2', bar: 'bar-spo2', card: 'card-spo2',
        min: 70, max: 100, normalLow: 95, normalHigh: 100,
        warnLow: 92, critLow: 88,
    },
    temperature: {
        el: 'val-temp', bar: 'bar-temp', card: 'card-temp',
        min: 33, max: 42, normalLow: 36.1, normalHigh: 37.2,
        warnHigh: 38, critHigh: 39.5, warnLow: 35.5, critLow: 34.5,
    },
    hrv: {
        el: 'val-hrv', bar: 'bar-hrv', card: 'card-hrv',
        min: 0, max: 100, normalLow: 20, normalHigh: 70,
        warnLow: 15, critLow: 10,
    },
};

// Stock-style Scrolling Charts
const CHART_CONFIG = {
    hr:   { color: '#10b981', fill: 'rgba(16,185,129,0.15)',  range: [40,  180] },
    spo2: { color: '#3b82f6', fill: 'rgba(59,130,246,0.15)',  range: [82,  102] },
    temp: { color: '#f97316', fill: 'rgba(249,115,22,0.15)',  range: [33,  42]  },
    hrv:  { color: '#8b5cf6', fill: 'rgba(139,92,246,0.15)',  range: [0,   100] },
};

const CHART_POINTS  = 60;
const chartBuffers  = {};
const chartCanvases = {};

for (const key of Object.keys(CHART_CONFIG)) {
    chartBuffers[key] = [];
}

function fillBuffer(key) {
    const cfg   = CHART_CONFIG[key];
    const mid   = (cfg.range[0] + cfg.range[1]) / 2;
    const noise = (cfg.range[1] - cfg.range[0]) * 0.04;
    chartBuffers[key] = Array.from({ length: CHART_POINTS },
        () => mid + (Math.random() - 0.5) * noise
    );
}

function sizeCanvas(canvas) {
    const dpr  = window.devicePixelRatio || 1;
    const card = canvas.closest('.vital-card') || canvas.parentElement.parentElement;
    const w    = card.clientWidth - 48;
    if (w <= 0) return false;
    const h    = 64;
    canvas.width  = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width  = w + 'px';
    canvas.style.height = h + 'px';
    return true;
}

function initCharts() {
    for (const key of Object.keys(CHART_CONFIG)) {
        const canvasId = `chart-${key}`;
        const canvas   = document.getElementById(canvasId);
        if (!canvas) continue;
        chartCanvases[key] = canvas;
        fillBuffer(key);
        sizeCanvas(canvas);
    }

    // Retry sizing at multiple points to catch late layout
    [0, 50, 150, 400, 800].forEach(ms => {
        setTimeout(() => {
            for (const key of Object.keys(chartCanvases)) {
                sizeCanvas(chartCanvases[key]);
            }
        }, ms);
    });

    window.addEventListener('resize', () => {
        for (const key of Object.keys(chartCanvases)) sizeCanvas(chartCanvases[key]);
    });

    requestAnimationFrame(chartLoop);
}

function pushChartValue(key, value) {
    const buf = chartBuffers[key];
    if (!buf) return;
    buf.push(value);
    if (buf.length > CHART_POINTS) buf.shift();
}

function drawChart(key) {
    const cfg    = CHART_CONFIG[key];
    const canvas = chartCanvases[key];
    if (!canvas) return;

    const buf = chartBuffers[key];
    if (buf.length < 2) return;

    if (canvas.width <= 1) sizeCanvas(canvas);
    if (canvas.width <= 1) return;

    const ctx = canvas.getContext('2d');
    const W   = canvas.width;
    const H   = canvas.height;
    const dpr = window.devicePixelRatio || 1;

    const [yMin, yMax] = cfg.range;
    const padding      = (yMax - yMin) * 0.08;
    const lo = yMin - padding;
    const hi = yMax + padding;

    function toY(v) {
        return H - ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * H * 0.9 - H * 0.05;
    }

    ctx.clearRect(0, 0, W, H);

    const stepX  = W / (CHART_POINTS - 1);
    const startX = (CHART_POINTS - buf.length) * stepX;

    // Filled area under line
    ctx.beginPath();
    ctx.moveTo(startX, toY(buf[0]));
    for (let i = 1; i < buf.length; i++) {
        ctx.lineTo(startX + i * stepX, toY(buf[i]));
    }
    ctx.lineTo(startX + (buf.length - 1) * stepX, H);
    ctx.lineTo(startX, H);
    ctx.closePath();

    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, cfg.fill);
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.fill();

    // Main line
    ctx.beginPath();
    ctx.moveTo(startX, toY(buf[0]));
    for (let i = 1; i < buf.length; i++) {
        ctx.lineTo(startX + i * stepX, toY(buf[i]));
    }
    ctx.strokeStyle = cfg.color;
    ctx.lineWidth   = 1.5 * dpr;
    ctx.lineJoin    = 'round';
    ctx.lineCap     = 'round';
    ctx.stroke();

    // Live dot at leading edge
    const lx = startX + (buf.length - 1) * stepX;
    const ly = toY(buf[buf.length - 1]);
    ctx.beginPath();
    ctx.arc(lx, ly, 3 * dpr, 0, Math.PI * 2);
    ctx.fillStyle = cfg.color;
    ctx.fill();
}

let chartLastFrame = 0;
function chartLoop(ts) {
    if (ts - chartLastFrame >= 33) {
        for (const key of Object.keys(chartCanvases)) drawChart(key);
        chartLastFrame = ts;
    }
    requestAnimationFrame(chartLoop);
}

// Vitals Update
function updateVitals(data) {
    for (const [key, config] of Object.entries(VITAL_CONFIG)) {
        const value = data[key];
        if (value == null) continue;

        const chartKey = { heart_rate: 'hr', spo2: 'spo2', temperature: 'temp', hrv: 'hrv' }[key];
        if (chartKey) pushChartValue(chartKey, value);

        const el   = document.getElementById(config.el);
        const bar  = document.getElementById(config.bar);
        const card = document.getElementById(config.card);

        const displayVal = key === 'spo2' || key === 'temperature'
            ? value.toFixed(1)
            : Math.round(value);
        el.textContent = displayVal;
        el.classList.add('value-flash');
        setTimeout(() => el.classList.remove('value-flash'), 500);

        const pct = Math.max(0, Math.min(100,
            ((value - config.min) / (config.max - config.min)) * 100
        ));
        bar.style.width = pct + '%';

        let severity = 'normal';
        if (config.critHigh  && value >= config.critHigh)        severity = 'critical';
        else if (config.critLow  != null && value <= config.critLow)  severity = 'critical';
        else if (config.warnHigh && value >= config.warnHigh)    severity = 'warning';
        else if (config.warnLow  != null && value <= config.warnLow)  severity = 'warning';

        card.classList.remove('warning', 'critical');
        if (severity !== 'normal') card.classList.add(severity);

        const barColors = {
            normal:   'var(--color-low)',
            warning:  'var(--color-moderate)',
            critical: 'var(--color-critical)',
        };
        bar.style.background = barColors[severity];

        const valueColors = {
            normal:   'var(--text-primary)',
            warning:  'var(--color-moderate)',
            critical: 'var(--color-critical)',
        };
        el.style.color = valueColors[severity];

        const chartKey2 = { heart_rate: 'hr', spo2: 'spo2', temperature: 'temp', hrv: 'hrv' }[key];
        if (chartKey2 && CHART_CONFIG[chartKey2]) {
            const defaults = {
                hr:   { color: '#10b981', fill: 'rgba(16,185,129,0.15)'  },
                spo2: { color: '#3b82f6', fill: 'rgba(59,130,246,0.15)'  },
                temp: { color: '#f97316', fill: 'rgba(249,115,22,0.15)'  },
                hrv:  { color: '#8b5cf6', fill: 'rgba(139,92,246,0.15)' },
            };
            if (severity === 'critical') {
                CHART_CONFIG[chartKey2].color = '#ef4444';
                CHART_CONFIG[chartKey2].fill  = 'rgba(239,68,68,0.15)';
            } else if (severity === 'warning') {
                CHART_CONFIG[chartKey2].color = '#f59e0b';
                CHART_CONFIG[chartKey2].fill  = 'rgba(245,158,11,0.15)';
            } else {
                CHART_CONFIG[chartKey2].color = defaults[chartKey2].color;
                CHART_CONFIG[chartKey2].fill  = defaults[chartKey2].fill;
            }
        }
    }
}

// Risk Gauge
const GAUGE_CIRCUMFERENCE = 2 * Math.PI * 85;

function updateRiskGauge(data) {
    const score   = data.score || 0;
    const level   = data.level || 'LOW';
    const factors = data.contributing_factors || [];

    const offset = GAUGE_CIRCUMFERENCE - (score / 100) * GAUGE_CIRCUMFERENCE;
    DOM.gaugeFill.style.strokeDashoffset = offset;

    const levelColors = {
        LOW:      'var(--color-low)',
        MODERATE: 'var(--color-moderate)',
        HIGH:     'var(--color-high)',
        CRITICAL: 'var(--color-critical)',
    };
    const levelGlows = {
        LOW:      'var(--color-low-glow)',
        MODERATE: 'var(--color-moderate-glow)',
        HIGH:     'var(--color-high-glow)',
        CRITICAL: 'var(--color-critical-glow)',
    };

    const color = levelColors[level] || levelColors.LOW;
    const glow  = levelGlows[level]  || levelGlows.LOW;

    DOM.gaugeFill.style.stroke = color;
    DOM.gaugeFill.style.filter = `drop-shadow(0 0 12px ${glow})`;
    DOM.gaugeValue.textContent = score;
    DOM.gaugeValue.style.color = color;
    DOM.gaugeLabel.textContent = level;

    if (factors.length === 0) {
        DOM.riskFactors.innerHTML = '<p class="no-factors">All vitals normal</p>';
    } else {
        DOM.riskFactors.innerHTML = factors
            .map(f => `<div class="factor-item">\u2022 ${escapeHtml(f)}</div>`)
            .join('');
    }
}

// Decision Log
function addDecisionLog(data) {

    const placeholder = DOM.decisionLog.querySelector('.log-placeholder');
    if (placeholder) placeholder.remove();

    const entry = document.createElement('div');

    const level = (data.risk_level || 'LOW').toLowerCase();
    const action = data.decided_action || 'log';
    const reasoning = data.action_reasoning || data.clinical_analysis || 'Monitoring vitals...';

    const timestamp = new Date().toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });

    const triggers = data.trigger_vitals || [];

    entry.className = `log-entry level-${level}`;

    entry.innerHTML = `
        <div class="log-time">${timestamp}</div>

        <div class="log-body">

            <span class="log-action-badge badge-${action}">
                ${formatAction(action)}
            </span>

            <div class="log-reasoning">
                ${escapeHtml(reasoning)}
            </div>

            <div class="log-details">

                <b>Risk Score:</b> ${data.risk_score ?? 0}/100<br>
                <b>Risk Level:</b> ${data.risk_level ?? "LOW"}<br>

                ${
                    triggers.length > 0
                    ? `<b>Triggered By:</b>
                       <ul class="trigger-list">
                       ${triggers.map(t => `<li>${escapeHtml(t)}</li>`).join('')}
                       </ul>`
                    : '<b>Triggered By:</b> None'
                }

            </div>

        </div>
    `;

    entry.addEventListener('click', () => entry.classList.toggle('expanded'));

    DOM.decisionLog.insertBefore(entry, DOM.decisionLog.firstChild);

    state.logEntries.push(data);

    if (state.logEntries.length > 50) {

        state.logEntries.shift();

        const children = DOM.decisionLog.children;

        if (children.length > 50) {
            DOM.decisionLog.removeChild(children[children.length - 1]);
        }
    }

    DOM.logCount.textContent = `${state.logEntries.length} entries`;
}
function formatAction(action) {
    const labels = {
        log:              '\uD83D\uDCCB Logged',
        alert_user:       '\u26A0\uFE0F Alert',
        schedule_doctor:  '\uD83E\uDE7A Doctor',
        call_emergency:   '\uD83D\uDEA8 Emergency',
        notify_contact:   '\uD83D\uDCF1 Contact',
    };
    return labels[action] || action;
}

// Action Items
function addActionItem(data) {
    const placeholder = DOM.actionsList.querySelector('.action-placeholder');
    if (placeholder) placeholder.remove();

    const actionType = data.action_type || 'log';
    if (actionType === 'log') return;

    const time = new Date().toLocaleTimeString('en-IN', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });

    const icons = {
        alert_user:      '\u26A0\uFE0F',
        schedule_doctor: '\uD83E\uDE7A',
        call_emergency:  '\uD83D\uDEA8',
        notify_contact:  '\uD83D\uDCF1',
    };
    const classes = {
        alert_user:      'warning',
        schedule_doctor: 'doctor',
        call_emergency:  'emergency',
        notify_contact:  'contact',
    };

    const item = document.createElement('div');
    item.className = `action-item ${classes[actionType] || ''}`;
    item.innerHTML = `
        <span class="action-type-icon">${icons[actionType] || '\uD83E\uDD16'}</span>
        <div class="action-content">
            <div class="action-message">${escapeHtml(data.message || 'Action taken')}</div>
            <div class="action-detail">${getActionDetail(data)}</div>
        </div>
        <div class="action-time">${time}</div>
    `;

    DOM.actionsList.insertBefore(item, DOM.actionsList.firstChild);

    if (data.contact_notification) addActionItem(data.contact_notification);

    state.actionEntries.push(data);
    if (state.actionEntries.length > 20) {
        state.actionEntries.shift();
        const children = DOM.actionsList.children;
        if (children.length > 20) DOM.actionsList.removeChild(children[children.length - 1]);
    }
}

function getActionDetail(data) {
    const details = data.details || {};
    const parts   = [];

    if (details.trigger_vitals?.length > 0) {
        parts.push(`Triggered By: ${details.trigger_vitals.join(' | ')}`);
    } else if (details.contributing_factors?.length > 0) {
        parts.push(`Triggers: ${details.contributing_factors.join(' | ')}`);
    }
    if (details.eta)                  parts.push(`ETA: ${details.eta}`);
    if (details.case_id)              parts.push(`Case: ${details.case_id}`);
    if (details.appointment_id)       parts.push(`Apt: ${details.appointment_id}`);
    if (details.doctor)               parts.push(details.doctor);
    if (details.scheduled_within)     parts.push(`Within: ${details.scheduled_within}`);
    if (details.recommendation)       parts.push(details.recommendation);
    if (details.notification_channels) parts.push(`Via: ${details.notification_channels.join(', ')}`);

    const sms = details.sms_delivery;
    if (sms?.mode === 'live') {
        parts.push(`\uD83D\uDCE8 SMS sent (${sms.status})`);
        if (sms.sid) parts.push(`SID: ${sms.sid}`);
    } else if (sms?.mode === 'mock') {
        parts.push('\uD83D\uDCE8 SMS (mock)');
    }

    return parts.length > 0 ? escapeHtml(parts.join(' \u00B7 ')) : '';
}

// Utilities
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Location Tracking
let locationWatchId = null;

function onLocationSuccess(position) {
    const newLocation = {
        lat: position.coords.latitude,
        lng: position.coords.longitude,
    };
    state.location = newLocation;
    console.log('[VitalGuard] Location acquired:', newLocation);
    if (state.connected && state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'location_update', location: newLocation }));
    }
}

function onLocationError(error) {
    console.warn('[VitalGuard] Geolocation error:', error.message);
}

function requestLocationOnce() {
    if ('geolocation' in navigator) {
        navigator.geolocation.getCurrentPosition(
            onLocationSuccess,
            onLocationError,
            { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
        );
    }
}

function initLocationTracking() {
    if (!('geolocation' in navigator)) {
        console.warn('[VitalGuard] Geolocation not supported');
        return;
    }
    requestLocationOnce();
    locationWatchId = navigator.geolocation.watchPosition(
        onLocationSuccess,
        onLocationError,
        { enableHighAccuracy: true, maximumAge: 10000, timeout: 10000 }
    );
}

function stopLocationTracking() {
    if (locationWatchId !== null && 'geolocation' in navigator) {
        navigator.geolocation.clearWatch(locationWatchId);
        locationWatchId = null;
    }
}

// Start
document.addEventListener('DOMContentLoaded', () => {
    init();
    initLocationTracking();
});