/**
 * UDYAM-TWIN Industrial Digital Twin Client
 * Handles real-time telemetry over WebSocket, UI state management,
 * fault injection, calibration tracking, work orders, and MSME economics.
 */

const state = {
  machines: {},
  obs: {},
  twin: {},
  line: null,
  selectedMachineId: "VMC-01",
  autoDemo: true,
  workOrders: [],
  economics: {
    inr_per_part: 450.0,
    downtime_cost_per_hr: 2500.0,
    electricity_tariff_per_kwh: 8.5,
    cea_co2_factor: 0.716,
  },
  metrics: null,
};

let ws = null;
let reconnectTimer = null;

// Determine WebSocket URL
const loc = window.location;
const wsProto = loc.protocol === "https:" ? "wss://" : "ws://";
const wsHost = loc.host || "localhost:8000";
const wsUrl = `${wsProto}${wsHost}/ws/telemetry`;

// Helpers
const fmt = (v, d = 1) => (v === null || v === undefined ? "—" : (typeof v === "number" ? v.toFixed(d) : v));
const esc = s => String(s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function initWebSocket() {
  updateStatus("connecting...", false);
  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    updateStatus("failed, retrying...", false);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    updateStatus("connected", true);
    if (reconnectTimer) clearTimeout(reconnectTimer);
  };

  ws.onclose = () => {
    updateStatus("disconnected, retrying...", false);
    scheduleReconnect();
  };

  ws.onerror = () => {
    updateStatus("connection error", false);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleMessage(msg);
    } catch (err) {
      console.error("Malformed telemetry frame:", err);
    }
  };
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(initWebSocket, 2000);
}

function updateStatus(text, connected) {
  const el = document.getElementById("connectionStatusText");
  const dot = document.getElementById("statusDot");
  if (el) el.textContent = text;
  if (dot) {
    if (connected) dot.classList.add("connected");
    else dot.classList.remove("connected");
  }
}

function handleMessage(msg) {
  if (!msg || !msg.type) return;

  if (msg.type === "registry") {
    state.machines = Object.fromEntries(msg.machines.map(m => [m.machine_id, m]));
    updateMachineDropdowns();
    renderAll();
  } else if (msg.type === "observed") {
    state.obs[msg.machine_id] = msg;
    renderMachineCard(msg.machine_id);
    if (msg.machine_id === state.selectedMachineId) {
      renderDetailPanel();
      if (window.updateMachineVisualization) {
        window.updateMachineVisualization(msg.machine_id, msg, state.twin[msg.machine_id]);
      } else if (window.updateSpindleSpeed && typeof msg.rpm === 'number') {
        window.updateSpindleSpeed(msg.rpm);
      }
    }
  } else if (msg.type === "twin") {
    state.twin[msg.machine_id] = msg;
    renderMachineCard(msg.machine_id);
    if (msg.machine_id === state.selectedMachineId) {
      renderDetailPanel();
      if (window.updateMachineVisualization && state.obs[msg.machine_id]) {
        window.updateMachineVisualization(msg.machine_id, state.obs[msg.machine_id], msg);
      }
    }
  } else if (msg.type === "line") {
    state.line = msg;
    renderLineBanner(msg);
    renderEconomics();
  } else if (msg.type === "event") {
    logEvent(msg);
    if (msg.kind === "MACHINE_ADDED") fetchRegistry();
    if (msg.kind === "WORK_ORDER") fetchWorkOrders();
  }
}

function updateMachineDropdowns() {
  const sel = document.getElementById("faultMachineSelect");
  if (!sel) return;
  const ids = Object.keys(state.machines);
  sel.innerHTML = ids.map(id => `<option value="${esc(id)}">${esc(id)} (${esc(state.machines[id].template)})</option>`).join("");
}

function renderAll() {
  renderMachineGrid();
  if (state.line) renderLineBanner(state.line);
  renderDetailPanel();
}

function renderMachineGrid() {
  const grid = document.getElementById("machineGrid");
  if (!grid) return;

  const sorted = Object.values(state.machines).sort((a, b) =>
    (a.layout.order < 0) - (b.layout.order < 0) || a.layout.order - b.layout.order
  );

  grid.innerHTML = sorted.map(m => {
    const isSelected = m.machine_id === state.selectedMachineId ? "selected" : "";
    return `
      <div class="machine-card ${isSelected}" id="card-${esc(m.machine_id)}" onclick="selectMachine('${esc(m.machine_id)}')">
        <div class="card-header">
          <div class="card-title">
            <h3>${esc(m.name)}</h3>
            ${m.hero ? '<span class="hero-star" title="Detailed Hero Asset">★ Hero</span>' : ''}
          </div>
          <div class="machine-badges" id="badges-${esc(m.machine_id)}">
            <span class="pill OK">RUN</span>
          </div>
        </div>
        <div style="font-size: 11px; color: var(--text-muted);">
          ID: <b>${esc(m.machine_id)}</b> · ${esc(m.template)} · Rated: ${esc(m.nameplate?.rated_kw || 7.5)} kW
        </div>
        <div id="content-${esc(m.machine_id)}">
          <div class="text-muted" style="font-size: 12px;">Waiting for telemetry tick...</div>
        </div>
      </div>
    `;
  }).join("");

  sorted.forEach(m => renderMachineCard(m.machine_id));
}

function renderMachineCard(machineId) {
  const container = document.getElementById(`content-${machineId}`);
  const badgesContainer = document.getElementById(`badges-${machineId}`);
  if (!container) return;

  const m = state.machines[machineId];
  const o = state.obs[machineId] || {};
  const t = state.twin[machineId] || {};

  if (badgesContainer) {
    const risk = t.risk?.rules || "LOW";
    const plc = o.plc_state || "RUN";
    badgesContainer.innerHTML = `
      <span class="pill ${esc(plc)}">${esc(plc)}</span>
      <span class="pill ${esc(risk)}">${esc(risk)} RISK</span>
    `;
  }

  let fields = [];
  if (m.template.startsWith("cnc")) {
    fields = [
      ["Spindle Speed", `${fmt(o.rpm, 0)} RPM`],
      ["Torque", `${fmt(o.torque_nm, 1)} Nm`],
      ["Process Temp", `${fmt(o.process_temp_k, 2)} K`],
      ["Twin Predicted", `${fmt(t.predicted?.process_temp_k, 2)} K`],
      ["Tool Wear", `${fmt(o.tool_wear_min, 1)} min`],
      ["Spindle Vibration", `${fmt(o.vibration_rms_mm_s, 2)} mm/s`],
    ];
  } else if (m.template === "air_compressor") {
    fields = [
      ["Line Pressure", `${fmt(o.pressure_bar, 2)} bar`],
      ["Duty Cycle", `${fmt(o.duty_pct, 1)} %`],
      ["Discharge Temp", `${fmt(o.discharge_temp_c, 1)} °C`],
      ["Vibration", `${fmt(o.vibration_rms_mm_s, 2)} mm/s`],
    ];
  } else {
    fields = [
      ["Blade Speed", `${fmt(o.rpm, 0)} RPM`],
      ["Blade Wear", `${fmt(o.blade_wear_pct, 1)} %`],
      ["Motor Power", `${fmt(o.power_kw, 2)} kW`],
      ["Vibration", `${fmt(o.vibration_rms_mm_s, 2)} mm/s`],
    ];
  }

  const res = t.residual || { signal: "process_temp_k", value: 0.0, state: "IN_BAND" };
  const params = t.params || { version: "v1.0", values: { h_cool: 1.0 }, frozen: false };
  const forecast = t.forecast || { minutes_to_warning: null };

  container.innerHTML = `
    <table class="telemetry-table">
      ${fields.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}
    </table>
    <div class="twin-section">
      <div class="twin-header">
        <span>Residual (${esc(res.signal || "e")})</span>
        <span class="pill ${esc(res.state || 'IN_BAND')}">${fmt(res.value, 2)} (${esc(res.state)})</span>
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span>Params ${esc(params.version || 'v1.0')} ${params.frozen ? '<b style="color:var(--status-crit)">[FROZEN]</b>' : ''}</span>
        <span style="font-family:var(--font-mono); font-size:11px;">
          ${Object.entries(params.values || {}).map(([k, v]) => `${esc(k)}=${fmt(v, 2)}`).join(" ")}
        </span>
      </div>
      ${forecast.warning ? `
        <div style="background:rgba(239,68,68,0.15); color:#f87171; padding:4px 6px; border-radius:4px; font-weight:600; font-size:11px;">
          ⚠ ${esc(forecast.warning)} in ~${fmt(forecast.minutes_to_warning, 0)} min at current rate
        </div>
      ` : ''}
    </div>
  `;
}

function selectMachine(machineId) {
  const prevId = state.selectedMachineId;
  state.selectedMachineId = machineId;
  document.querySelectorAll(".machine-card").forEach(c => c.classList.remove("selected"));
  const card = document.getElementById(`card-${machineId}`);
  if (card) card.classList.add("selected");

  renderDetailPanel();

  if (window.initThreeView) {
    if (prevId !== machineId || !document.getElementById("threeCanvas")) {
      window.initThreeView(machineId);
    }
  }
}

function renderDetailPanel() {
  const panel = document.getElementById("detailView");
  if (!panel) return;

  const mid = state.selectedMachineId;
  const m = state.machines[mid];
  if (!m) {
    panel.innerHTML = "<div class='text-muted'>Select an asset to inspect digital twin.</div>";
    return;
  }

  // Ensure persistent split containers exist: detailMetrics and threeContainer
  let metricsContainer = document.getElementById("detailMetrics");
  let threeContainer = document.getElementById("threeContainer");
  if (!metricsContainer || !threeContainer) {
    panel.innerHTML = `
      <div id="detailMetrics"></div>
      <div id="threeContainer" style="margin-top:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <h3 id="threeTitle" style="font-size:14px; margin:0; font-weight:700;">3D Kinematic Twin</h3>
            <span class="pill OK" id="threeSpindleRpm">— RPM</span>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-sm" onclick="if(window.resetThreeView) window.resetThreeView()">Reset Camera</button>
            <button class="btn btn-sm" id="btnToggleAnim" onclick="if(window.toggleThreeAnimation) window.toggleThreeAnimation()">Pause</button>
          </div>
        </div>
        <div id="threeCanvasWrapper" style="position:relative; width:100%; border:1px solid var(--border-subtle); border-radius:var(--radius-sm); overflow:hidden; background:#0a0e17;"></div>
        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-muted); margin-top:4px;">
          <span>Left-click + drag: Orbit · Scroll: Zoom · Right-click + drag: Pan</span>
          <span>Three.js Procedural Digital Twin</span>
        </div>
      </div>
    `;
    metricsContainer = document.getElementById("detailMetrics");
    threeContainer = document.getElementById("threeContainer");
  }

  const o = state.obs[mid] || {};
  const t = state.twin[mid] || {};
  const r = t.residual || { signal: "process_temp_k", value: 0.0, ewma: 0.0, cusum: 0.0, band: 0.6, state: "IN_BAND" };
  const p = t.params || { version: "v1.0", values: {}, frozen: false, freeze_reason: null };
  const f = t.forecast || {};
  const risk = t.risk || { rules: "LOW", model: 0.01, top_signals: [] };

  // Render asset-specific technical cards
  let specificHtml = "";

  if (m.template.startsWith("cnc")) {
    specificHtml = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:10px;">
        <div class="calc-card">
          <div class="calc-label">Process Temp (Observed / Target)</div>
          <div class="calc-val">${fmt(o.process_temp_k, 2)} / ${fmt(t.predicted?.process_temp_k, 2)} K</div>
          <div class="formula-hint">T_air + 8.0 + 0.7 × P / h_cool (Thermal model)</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Thermal Residual e (Obs - Pred)</div>
          <div class="calc-val ${r.state}">${fmt(r.value, 3)}</div>
          <div class="formula-hint">EWMA: ${fmt(r.ewma, 3)} · CUSUM: ${fmt(r.cusum, 2)} (${esc(r.state)})</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Self-Calibration State</div>
          <div class="calc-val">${esc(p.version)} ${p.frozen ? '<span style="color:var(--status-crit)">(FROZEN)</span>' : '<span style="color:var(--status-ok)">(ACTIVE)</span>'}</div>
          <div class="formula-hint">${p.freeze_reason ? `Frozen: ${esc(p.freeze_reason)} (Safeguard)` : 'Bounded RLS online parameter estimation'}</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">AI4I Failure Risk Model</div>
          <div class="calc-val">${risk.model !== null ? (risk.model * 100).toFixed(1) + '%' : 'N/A'}</div>
          <div class="formula-hint">Rule status: <b>${esc(risk.rules)}</b> · Signals: ${esc(risk.top_signals?.join(", ") || 'nominal')}</div>
        </div>
      </div>

      <div style="background:var(--bg-card); border-radius:var(--radius-sm); padding:12px; margin-top:10px;">
        <h4 style="font-size:13px; margin-bottom:8px; color:var(--text-secondary);">Parameter Coefficients (θ Vector)</h4>
        <div style="display:flex; gap:16px; font-family:var(--font-mono); font-size:13px;">
          <div>h_cool: <b>${fmt(p.values?.h_cool, 3)}</b> (thermal cooling)</div>
          <div>k_heat: <b>${fmt(p.values?.k_heat, 3)}</b> (frictional heat)</div>
          <div>k_wear: <b>${fmt(p.values?.k_wear, 3)}</b> (tool wear rate)</div>
        </div>
      </div>

      <div style="background:var(--bg-card); border-radius:var(--radius-sm); padding:12px; margin-top:10px;">
        <h4 style="font-size:13px; margin-bottom:8px; color:var(--text-secondary);">Spindle Dynamics & Mechanical State</h4>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:10px; font-size:12px;">
          <div>Spindle Speed: <b>${fmt(o.rpm, 0)} RPM</b></div>
          <div>Cutting Torque: <b>${fmt(o.torque_nm, 1)} Nm</b></div>
          <div>Motor Power: <b>${fmt(o.power_kw, 2)} kW</b></div>
          <div>Vibration RMS: <b>${fmt(o.vibration_rms_mm_s, 2)} mm/s</b> (ISO 20816 Zone ${(o.vibration_rms_mm_s || 0) > 4.5 ? 'C/D' : 'A/B'})</div>
          <div>Tool Wear: <b>${fmt(o.tool_wear_min, 1)} min</b></div>
        </div>
      </div>
    `;
  } else if (m.template === "air_compressor") {
    specificHtml = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:10px;">
        <div class="calc-card">
          <div class="calc-label">Header Line Pressure</div>
          <div class="calc-val" style="color:${(o.pressure_bar || 7.0) < 6.0 ? 'var(--status-crit)' : 'var(--status-ok)'}">${fmt(o.pressure_bar, 2)} / 7.00 bar</div>
          <div class="formula-hint">Pneumatic reservoir mass balance</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Pressure Residual e (Obs - 7.0)</div>
          <div class="calc-val ${r.state}">${fmt(r.value, 2)} bar</div>
          <div class="formula-hint">EWMA: ${fmt(r.ewma, 2)} · Threshold: &lt;6.0 bar critical</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Factory Air Supply State</div>
          <div class="calc-val">${(o.pressure_bar || 7.0) >= 6.0 ? '<span style="color:var(--status-ok)">OPTIMAL (≥ 6.0 bar)</span>' : '<span style="color:var(--status-crit)">UNDERPRESSURE (&lt; 6.0 bar)</span>'}</div>
          <div class="formula-hint">Feeds pneumatic clamps on VMC-01 & LATHE-01</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Compressor Duty & Thermal</div>
          <div class="calc-val">${fmt(o.duty_pct, 1)}% Duty</div>
          <div class="formula-hint">Discharge: ${fmt(o.discharge_temp_c, 1)} °C · Vib: ${fmt(o.vibration_rms_mm_s, 2)} mm/s</div>
        </div>
      </div>

      <div style="background:var(--bg-card); border-radius:var(--radius-sm); padding:12px; margin-top:10px;">
        <h4 style="font-size:13px; margin-bottom:6px; color:var(--text-secondary); font-weight:700;">Shared Utility Infrastructure Analysis (Common Cause)</h4>
        <div style="font-size:12px; color:var(--text-secondary); line-height:1.5;">
          This compressor acts as a single-point shared utility node across the floor. When line pressure falls below <b>6.0 bar</b>, pneumatic tool changers and workholding chucks on <b>VMC-01</b> and <b>LATHE-01</b> cannot safely clamp, triggering automatic derating and line bottlenecking.
        </div>
      </div>
    `;
  } else if (m.template === "bar_saw") {
    specificHtml = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:10px;">
        <div class="calc-card">
          <div class="calc-label">Motor Cutting Power</div>
          <div class="calc-val">${fmt(o.power_kw, 2)} / 3.20 kW</div>
          <div class="formula-hint">Specific cutting energy model: P = k_cut × feed × depth</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Power Residual e (Obs - 3.20)</div>
          <div class="calc-val ${r.state}">${fmt(r.value, 2)} kW</div>
          <div class="formula-hint">EWMA: ${fmt(r.ewma, 2)} · Band: ±0.5 kW</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Band Blade Health & Wear</div>
          <div class="calc-val" style="color:${(o.blade_wear_pct || 0) > 75 ? 'var(--status-crit)' : 'var(--status-ok)'}">${fmt(o.blade_wear_pct, 1)}% Wear</div>
          <div class="formula-hint">Blade speed: ${fmt(o.rpm, 0)} RPM · Est: ~${Math.max(0, (100 - (o.blade_wear_pct || 0)) * 4).toFixed(0)} cuts left</div>
        </div>
        <div class="calc-card">
          <div class="calc-label">Vibration & Drive Health</div>
          <div class="calc-val">${fmt(o.vibration_rms_mm_s, 2)} mm/s</div>
          <div class="formula-hint">ISO 20816 Zone ${(o.vibration_rms_mm_s || 0) > 4.5 ? 'C/D (Elevated)' : 'A/B (Normal)'}</div>
        </div>
      </div>

      <div style="background:var(--bg-card); border-radius:var(--radius-sm); padding:12px; margin-top:10px;">
        <h4 style="font-size:13px; margin-bottom:6px; color:var(--text-secondary); font-weight:700;">Upstream Production Line Feed (Station 1)</h4>
        <div style="font-size:12px; color:var(--text-secondary); line-height:1.5;">
          SAW-01 cuts raw cylindrical metal bar stock and feeds the downstream inter-stage buffer for <b>LATHE-01</b>. If SAW-01 experiences accelerated blade wear or stalls, the downstream buffer starves, reducing overall factory line throughput.
        </div>
      </div>
    `;
  }

  metricsContainer.innerHTML = `
    <div class="panel-header">
      <h2>
        <span>${esc(m.name)}</span>
        <span style="font-size:13px; color:var(--text-muted); font-weight:normal;">[${esc(mid)}] · ${esc(m.template)}</span>
      </h2>
      <div style="display:flex; gap:8px;">
        <span class="badge-sim">SIMULATION MODE</span>
        ${m.template.startsWith("cnc") ? `<button class="btn btn-sm" onclick="openToolWearModal('${esc(mid)}')">Enter Tool Wear</button>` : ''}
      </div>
    </div>

    ${specificHtml}

    ${f.warning ? `
      <div style="background:rgba(239, 68, 68, 0.1); border:1px solid rgba(239, 68, 68, 0.3); border-radius:var(--radius-sm); padding:12px; margin-top:10px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <b style="color:var(--status-crit);">Impending Warning: ${esc(f.warning)}</b>
          <div style="font-size:12px; color:var(--text-secondary);">Forecast horizon: ~${fmt(f.minutes_to_warning, 1)} minutes at current load setpoint.</div>
        </div>
        <button class="btn btn-sm btn-primary" onclick="createWorkOrderFromAlert('${esc(mid)}', '${esc(f.warning)}')">Create Work Order</button>
      </div>
    ` : ''}
  `;

  // Update 3D Container title and auto-init
  if (threeContainer) {
    threeContainer.style.display = "block";
    const titleEl = document.getElementById("threeTitle");
    if (titleEl) titleEl.textContent = `3D Kinematic Twin — ${m.name} [${mid}]`;

    if (!document.getElementById("threeCanvas") && window.initThreeView) {
      window.initThreeView(mid);
    }
  }
}

function renderLineBanner(line) {
  const flowEl = document.getElementById("lineStationsFlow");
  const tpEl = document.getElementById("lineThroughput");
  const lossEl = document.getElementById("lineLoss");
  const bnEl = document.getElementById("lineBottleneck");
  const airEl = document.getElementById("lineAirSupply");

  if (flowEl && line.stations) {
    flowEl.innerHTML = line.stations.map((s, idx) => `
      <div class="station-node">
        <span>${esc(s.machine_id)}</span>
        <span class="buffer-pill">buf ${s.buffer_in}/${s.buffer_cap}</span>
        <span class="pill ${esc(s.state)}" style="font-size:10px;">${esc(s.state)}</span>
      </div>
      ${idx < line.stations.length - 1 ? '<span class="flow-arrow">→</span>' : ''}
    `).join("");
  }

  if (tpEl) tpEl.textContent = `${fmt(line.throughput_parts_per_hr, 1)} /h`;
  if (lossEl) lossEl.textContent = `₹${fmt(line.line_loss_inr_per_hr, 0)}/h`;
  if (bnEl) bnEl.textContent = line.bottleneck || "None";
  if (airEl) {
    airEl.textContent = line.air_supply_ok ? "OPTIMAL (7.0 bar)" : "LOW PRESSURE (< 6.0 bar)";
    airEl.style.color = line.air_supply_ok ? "var(--status-ok)" : "var(--status-crit)";
  }
}

function renderEconomics() {
  const econ = state.economics || {};
  const inrPerPart = econ.inr_per_part || 450.0;
  const downtimeCostPerHr = econ.downtime_cost_per_hr || 2500.0;
  const kwhCost = econ.electricity_tariff_per_kwh || 8.5;
  const nodeBOM = econ.sensor_node_cost_inr || 2200.0;
  const ceaFactor = econ.cea_co2_factor || 0.716;
  const baseDowntimeHours = econ.base_breakdown_hours || 12.0;

  // Live line loss
  const lineLoss = state.line?.line_loss_inr_per_hr || 0;

  // Active floor total power
  let totalKw = 0;
  Object.values(state.obs).forEach(o => totalKw += (o.power_kw || 0));
  const hourlyKwhCost = (totalKw * kwhCost).toFixed(1);
  const hourlyCo2 = (totalKw * ceaFactor).toFixed(2);

  // Avoided monthly breakdown losses
  const avoidedHoursPerMonth = baseDowntimeHours * 0.70; // 70% avoided with digital twin
  const monthlyAvoidedLossInr = avoidedHoursPerMonth * downtimeCostPerHr;
  const totalSensorNodes = Object.keys(state.machines).length || 4;
  const totalHardwareCapEx = totalSensorNodes * nodeBOM;
  const paybackMonths = monthlyAvoidedLossInr > 0 ? (totalHardwareCapEx / monthlyAvoidedLossInr).toFixed(2) : "N/A";

  // Tool wear scrap savings
  const monthlyScrapSavings = 6500.0;
  // Energy efficiency savings (~5% waste avoided via timely blade/compressor/coolant maintenance)
  const monthlyHours = 400.0;
  const monthlyEnergyKwh = totalKw * monthlyHours;
  const monthlyEnergySavingsKwh = monthlyEnergyKwh * 0.05;
  const monthlyEnergySavingsInr = monthlyEnergySavingsKwh * kwhCost;
  const monthlyCo2AvoidedKg = monthlyEnergySavingsKwh * ceaFactor;

  const totalMonthlyBenefit = monthlyAvoidedLossInr + monthlyScrapSavings + monthlyEnergySavingsInr;
  const annualNetRoi = totalHardwareCapEx > 0 ? (((totalMonthlyBenefit * 12) - totalHardwareCapEx) / totalHardwareCapEx * 100).toFixed(0) : "0";

  // Update primary KPI cards
  const elLineLoss = document.getElementById("calcLineLoss");
  const elPayback = document.getElementById("calcPayback");
  const elEnergy = document.getElementById("calcEnergy");
  const elCo2 = document.getElementById("calcCo2");

  if (elLineLoss) elLineLoss.textContent = `₹${fmt(lineLoss, 0)} /hr`;
  if (elPayback) elPayback.textContent = `${paybackMonths} Months`;
  if (elEnergy) elEnergy.textContent = `₹${hourlyKwhCost} /hr (${totalKw.toFixed(1)} kW)`;
  if (elCo2) elCo2.textContent = `${hourlyCo2} kg/hr`;

  // Update hints
  const hInr = document.getElementById("econInrPerPartHint");
  const hNode = document.getElementById("econNodeCostHint");
  const hTariff = document.getElementById("econTariffHint");
  const hCea = document.getElementById("econCeaHint");
  if (hInr) hInr.textContent = inrPerPart;
  if (hNode) hNode.textContent = nodeBOM;
  if (hTariff) hTariff.textContent = kwhCost;
  if (hCea) hCea.textContent = ceaFactor;

  // Update Scenario Comparison Table
  const sBaseHours = document.getElementById("scenBaseHours");
  const sTwinHours = document.getElementById("scenTwinHours");
  const sDownSave = document.getElementById("scenDowntimeSave");
  const sEnergySave = document.getElementById("scenEnergySave");
  const sNetMonthly = document.getElementById("scenNetMonthly");
  const sRoi = document.getElementById("scenRoiAnnual");

  if (sBaseHours) sBaseHours.textContent = `${baseDowntimeHours.toFixed(1)} hrs`;
  if (sTwinHours) sTwinHours.textContent = `${(baseDowntimeHours * 0.3).toFixed(1)} hrs (-70%)`;
  if (sDownSave) sDownSave.textContent = `₹${monthlyAvoidedLossInr.toLocaleString('en-IN', {maximumFractionDigits:0})} /mo saved`;
  if (sEnergySave) sEnergySave.textContent = `₹${monthlyEnergySavingsInr.toFixed(0)} /mo · ${monthlyCo2AvoidedKg.toFixed(0)} kg CO₂`;
  if (sNetMonthly) sNetMonthly.textContent = `₹${totalMonthlyBenefit.toLocaleString('en-IN', {maximumFractionDigits:0})} /mo`;
  if (sRoi) sRoi.textContent = `1-Yr Net ROI: ${annualNetRoi}%`;

  // Update Sensitivity Matrix
  const s1500 = document.getElementById("sensPay1500");
  const s2500 = document.getElementById("sensPay2500");
  const s3500 = document.getElementById("sensPay3500");
  if (s1500) s1500.textContent = `${(totalHardwareCapEx / (avoidedHoursPerMonth * 1500)).toFixed(1)} mo`;
  if (s2500) s2500.textContent = `${(totalHardwareCapEx / (avoidedHoursPerMonth * 2500)).toFixed(1)} mo`;
  if (s3500) s3500.textContent = `${(totalHardwareCapEx / (avoidedHoursPerMonth * 3500)).toFixed(1)} mo`;
}

function logEvent(e) {
  const container = document.getElementById("eventLog");
  if (!container) return;

  const card = document.createElement("div");
  card.className = `event-card ${esc(e.severity || 'INFO')}`;

  const tsDisp = (e.ts || "").slice(11, 19);
  let cardBreakdown = "";
  if (e.measured || e.inferred || e.suggested) {
    cardBreakdown = `
      <div class="event-breakdown">
        ${e.measured ? `<div><b>Fact (Measured):</b> ${esc(e.measured)}</div>` : ''}
        ${e.inferred ? `<div><b>Inference:</b> ${esc(e.inferred)}</div>` : ''}
        ${e.suggested ? `<div><b>Suggested Action:</b> ${esc(e.suggested)}</div>` : ''}
      </div>
    `;
  }

  const isActionable = e.severity === "WARN" || e.severity === "CRITICAL";
  const actionButton = isActionable ? `
    <div style="margin-top:6px; display:flex; gap:6px;">
      <button class="btn btn-sm btn-primary" onclick="createWorkOrderFromAlert('${esc(e.machine_id || 'FACTORY')}', '${esc(e.title)}')">Create Work Order</button>
    </div>
  ` : '';

  card.innerHTML = `
    <div class="event-top">
      <span>${esc(tsDisp)} UTC · <b>${esc(e.kind)}</b></span>
      <span>${esc(e.machine_id || 'FACTORY')}</span>
    </div>
    <div class="event-title">${esc(e.title)}</div>
    ${cardBreakdown}
    ${actionButton}
  `;

  container.prepend(card);
  while (container.children.length > 50) container.lastChild.remove();
}

// -----------------------------------------------------------------------------
// Interactive Commands & API Integrations
// -----------------------------------------------------------------------------
function sendCommand(cmd) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(cmd));
  } else {
    // Fallback: send via REST when WebSocket is unavailable
    if (cmd.cmd === "inject_fault") {
      fetch("/api/faults/inject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ machine_id: cmd.machine_id, fault: cmd.fault }),
      }).catch(console.error);
    } else if (cmd.cmd === "clear_faults") {
      fetch("/api/faults/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ machine_id: cmd.machine_id }),
      }).catch(console.error);
    } else if (cmd.cmd === "reset") {
      fetch("/api/reset", { method: "POST" }).catch(console.error);
    } else if (cmd.cmd === "set_derate") {
      fetch("/api/derate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ machine_id: cmd.machine_id, pct: cmd.pct }),
      }).catch(console.error);
    } else if (cmd.cmd === "auto_demo") {
      fetch(`/api/auto_demo?on=${cmd.on}`, { method: "POST" }).catch(console.error);
    }
  }
}

function injectSelectedFault() {
  const mSel = document.getElementById("faultMachineSelect");
  const fSel = document.getElementById("faultTypeSelect");
  if (!mSel || !fSel) return;
  sendCommand({
    cmd: "inject_fault",
    machine_id: mSel.value,
    fault: fSel.value,
  });
}

function clearAllFaults() {
  sendCommand({ cmd: "clear_faults" });
}

function toggleAutoDemo() {
  state.autoDemo = !state.autoDemo;
  const btn = document.getElementById("btnAutoDemo");
  if (btn) btn.textContent = `Auto Demo: ${state.autoDemo ? 'ON' : 'OFF'}`;
  sendCommand({ cmd: "auto_demo", on: state.autoDemo });
}

function resetScenario() {
  sendCommand({ cmd: "reset" });
}

function applyDerate(pct) {
  const mid = state.selectedMachineId;
  sendCommand({ cmd: "set_derate", machine_id: mid, pct: pct });
}

// Onboarding Modal
function openOnboardingModal() {
  document.getElementById("onboardingModal").classList.add("open");
}

function closeOnboardingModal() {
  document.getElementById("onboardingModal").classList.remove("open");
}

function submitOnboardingForm(e) {
  e.preventDefault();
  const template = document.getElementById("onboardTemplate").value;
  const name = document.getElementById("onboardName").value;
  const rated_kw = parseFloat(document.getElementById("onboardKw").value) || 7.5;
  const max_rpm = parseFloat(document.getElementById("onboardRpm").value) || 3000;

  sendCommand({
    cmd: "add_machine",
    template: template,
    name: name,
    nameplate: { rated_kw: rated_kw, max_rpm: max_rpm },
  });

  closeOnboardingModal();
}

// Tool Wear Measurement Feedback Modal
function openToolWearModal(machineId) {
  const midInput = document.getElementById("toolWearMachineId");
  if (midInput) midInput.value = machineId;
  document.getElementById("toolWearModal").classList.add("open");
}

function closeToolWearModal() {
  document.getElementById("toolWearModal").classList.remove("open");
}

function submitToolWearForm(e) {
  e.preventDefault();
  const mid = document.getElementById("toolWearMachineId").value;
  const wear = parseFloat(document.getElementById("toolWearValue").value);

  fetch("/api/tool-wear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ machine_id: mid, measured_wear_min: wear }),
  }).then(r => r.json()).then(data => {
    closeToolWearModal();
  });
}

// Work Orders
function fetchWorkOrders() {
  fetch("/api/work-orders")
    .then(r => r.json())
    .then(data => {
      state.workOrders = data;
      renderWorkOrders();
    })
    .catch(() => {});
}

function renderWorkOrders() {
  const list = document.getElementById("workOrderList");
  if (!list) return;

  if (state.workOrders.length === 0) {
    list.innerHTML = "<div class='text-muted' style='font-size:12px;'>No active work orders.</div>";
    return;
  }

  list.innerHTML = state.workOrders.map(wo => `
    <div style="background:var(--bg-card); border-radius:var(--radius-sm); padding:10px; display:flex; justify-content:space-between; align-items:center; font-size:12px;">
      <div>
        <b>${esc(wo.wo_id)}</b> · ${esc(wo.machine_id)} · <i>${esc(wo.title)}</i>
        <div style="color:var(--text-muted); font-size:11px;">Status: <b style="color:var(--text-primary);">${esc(wo.status)}</b> · Priority: ${esc(wo.priority)}</div>
      </div>
      <div>
        ${wo.status === 'Open' ? `<button class="btn btn-sm btn-primary" onclick="updateWo('${esc(wo.wo_id)}', 'In Progress')">Acknowledge</button>` : ''}
        ${wo.status === 'In Progress' ? `<button class="btn btn-sm btn-primary" onclick="updateWo('${esc(wo.wo_id)}', 'Closed')">Close</button>` : ''}
      </div>
    </div>
  `).join("");
}

function createWorkOrderFromAlert(machineId, warning) {
  fetch("/api/work-orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      machine_id: machineId,
      title: `Corrective maintenance: ${warning}`,
      priority: "High",
      notes: "Auto-generated from digital twin forecast alert",
    }),
  }).then(() => fetchWorkOrders());
}

function updateWo(woId, status) {
  fetch(`/api/work-orders/${woId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: status }),
  }).then(() => fetchWorkOrders());
}

function fetchRegistry() {
  fetch("/api/registry")
    .then(r => r.json())
    .then(data => {
      if (data.machines) {
        state.machines = Object.fromEntries(data.machines.map(m => [m.machine_id, m]));
        updateMachineDropdowns();
        renderAll();
      }
    })
    .catch(() => {});
}

// -----------------------------------------------------------------------------
// Interactive MSME Economics Modal & Calculations
// -----------------------------------------------------------------------------

function openEconomicsModal() {
  const econ = state.economics || {};
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && val !== undefined) el.value = val;
  };
  setVal("inputDowntimeCost", econ.downtime_cost_per_hr || 2500);
  setVal("inputPartMargin", econ.inr_per_part || 450);
  setVal("inputElectricityTariff", econ.electricity_tariff_per_kwh || 8.5);
  setVal("inputSensorCost", econ.sensor_node_cost_inr || 2200);
  setVal("inputBaseHours", econ.base_breakdown_hours || 12);
  setVal("inputCeaFactor", econ.cea_co2_factor || 0.716);

  document.getElementById("economicsModal").classList.add("open");
}

function closeEconomicsModal() {
  document.getElementById("economicsModal").classList.remove("open");
}

function submitEconomicsForm(e) {
  e.preventDefault();
  const updates = {
    downtime_cost_per_hr: parseFloat(document.getElementById("inputDowntimeCost").value) || 2500,
    inr_per_part: parseFloat(document.getElementById("inputPartMargin").value) || 450,
    electricity_tariff_per_kwh: parseFloat(document.getElementById("inputElectricityTariff").value) || 8.5,
    sensor_node_cost_inr: parseFloat(document.getElementById("inputSensorCost").value) || 2200,
    base_breakdown_hours: parseFloat(document.getElementById("inputBaseHours").value) || 12,
    cea_co2_factor: parseFloat(document.getElementById("inputCeaFactor").value) || 0.716,
  };

  Object.assign(state.economics, updates);
  closeEconomicsModal();
  renderEconomics();

  // Persist to SQLite backend
  fetch("/api/economics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  }).catch(() => {});
}

function fetchEconomics() {
  fetch("/api/economics")
    .then(r => r.json())
    .then(data => {
      if (data.assumptions) {
        Object.assign(state.economics, data.assumptions);
        renderEconomics();
      }
    })
    .catch(() => {});
}

// -----------------------------------------------------------------------------
// Competition Demo Scenarios
// -----------------------------------------------------------------------------

function demoScenario(name) {
  if (name === "coolant") {
    selectMachine("VMC-01");
    sendCommand({ cmd: "inject_fault", machine_id: "VMC-01", fault: "coolant_degradation" });
  } else if (name === "bearing") {
    selectMachine("LATHE-01");
    sendCommand({ cmd: "inject_fault", machine_id: "LATHE-01", fault: "bearing_defect" });
  } else if (name === "compressor") {
    selectMachine("COMP-01");
    sendCommand({ cmd: "inject_fault", machine_id: "COMP-01", fault: "pressure_drop" });
  } else if (name === "tool_wear") {
    selectMachine("VMC-01");
    openToolWearModal("VMC-01");
  }
}

// -----------------------------------------------------------------------------
// AI4I Research Intelligence Metrics
// -----------------------------------------------------------------------------

function fetchMetrics() {
  fetch("/api/metrics")
    .then(r => r.json())
    .then(data => {
      state.metrics = data;
      if (data.random_forest) {
        const rf = data.random_forest;
        const rule = data.rule_baseline || {};
        const elRf = document.getElementById("mlRfF1");
        const elRule = document.getElementById("mlRuleF1");
        const elRoc = document.getElementById("mlRocAuc");
        const elPrec = document.getElementById("mlPrec");
        const elFpr = document.getElementById("mlFpr");

        if (elRf) elRf.textContent = `${(rf.f1 * 100).toFixed(1)}%`;
        if (elRule) elRule.textContent = `${(rule.f1 * 100).toFixed(1)}%`;
        if (elRoc) elRoc.textContent = `${rf.roc_auc.toFixed(3)}`;
        if (elPrec) elPrec.textContent = `${(rf.precision * 100).toFixed(1)}%`;
        if (elFpr) elFpr.textContent = `${(rf.false_positive_rate * 100).toFixed(2)}%`;
      }
    })
    .catch(() => {});
}

// -----------------------------------------------------------------------------
// Initial Bootstrap
// -----------------------------------------------------------------------------

window.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  fetchRegistry();
  fetchWorkOrders();
  fetchEconomics();
  fetchMetrics();
});
