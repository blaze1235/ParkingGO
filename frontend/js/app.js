/* ParkingGo SPA: hash router + views.
   Routes: #/login, #/ (dashboard), #/cameras, #/camera/{id}, #/camera/{id}/calibrate */

const view = document.getElementById('view');
const topbar = document.getElementById('topbar');
let cleanup = [];   // per-view timers/objects torn down on navigation

function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add('hidden'), 3500);
}

function every(ms, fn) {
  fn();
  const id = setInterval(fn, ms);
  cleanup.push(() => clearInterval(id));
}

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function fmtDateTime(ts) {
  return new Date(ts * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function countChips(s) {
  return `
    <span class="chip"><span class="dot dot-free"></span>${s.free} free</span>
    <span class="chip"><span class="dot dot-occupied"></span>${s.occupied} occupied</span>
    <span class="chip"><span class="dot dot-unknown"></span>${s.unknown} unknown</span>`;
}

/* ------------------------------------------------------------------ router */

const routes = [
  { re: /^#\/login$/, fn: renderLogin, public: true },
  { re: /^#\/?$/, fn: renderDashboard, nav: 'dashboard' },
  { re: /^#\/cameras$/, fn: renderCameras, nav: 'cameras' },
  { re: /^#\/camera\/(\d+)$/, fn: renderCameraDetail },
  { re: /^#\/camera\/(\d+)\/calibrate$/, fn: renderCalibrate },
];

async function route() {
  cleanup.forEach(fn => fn());
  cleanup = [];
  document.querySelectorAll('.chart-tooltip').forEach(t => t.remove());
  const hash = location.hash || '#/';
  const match = routes.find(r => r.re.test(hash));
  if (!match) { location.hash = '#/'; return; }
  if (!match.public && !API.token()) { location.hash = '#/login'; return; }

  topbar.classList.toggle('hidden', !!match.public);
  document.querySelectorAll('[data-nav]').forEach(a =>
    a.classList.toggle('active', a.dataset.nav === match.nav));

  view.innerHTML = '';
  try {
    await match.fn(...(hash.match(match.re).slice(1)));
  } catch (err) {
    if (err.message !== 'Session expired') {
      view.innerHTML = `<div class="card"><p class="error-text">${esc(err.message)}</p></div>`;
    }
  }
}

window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', () => {
  document.getElementById('logout-btn').addEventListener('click', async () => {
    try { await API.post('/api/auth/logout'); } catch (_) { /* token already dead */ }
    API.setToken(null);
    location.hash = '#/login';
  });
  route();
});

/* ------------------------------------------------------------------- login */

function renderLogin() {
  view.innerHTML = `
    <div class="login-wrap">
      <form class="card login-card" id="login-form">
        <div class="brand"><span class="brand-badge">P</span> ParkingGo</div>
        <p class="subtitle" style="text-align:center;margin:0">Street parking monitor — admin sign in</p>
        <label class="field">Username <input id="login-user" autocomplete="username" value="admin"></label>
        <label class="field">Password <input id="login-pass" type="password" autocomplete="current-password"></label>
        <div class="error-text" id="login-error"></div>
        <button class="btn btn-primary" type="submit">Sign in</button>
      </form>
    </div>`;
  document.getElementById('login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const errEl = document.getElementById('login-error');
    errEl.textContent = '';
    try {
      const res = await API.post('/api/auth/login', {
        username: document.getElementById('login-user').value,
        password: document.getElementById('login-pass').value,
      });
      API.setToken(res.token);
      loadDetectorBadge();
      location.hash = '#/';
    } catch (err) { errEl.textContent = err.message; }
  });
}

async function loadDetectorBadge() {
  try {
    const info = await API.get('/api/info');
    const el = document.getElementById('detector-badge');
    el.textContent = `detector: ${info.detector}`;
    el.title = info.detector === 'mock'
      ? 'Mock detector active — install requirements-yolo.txt for real car detection'
      : 'YOLO vehicle detection active';
  } catch (_) { /* not logged in yet */ }
}

/* --------------------------------------------------------------- dashboard */

async function renderDashboard() {
  loadDetectorBadge();
  view.innerHTML = `
    <h1>Dashboard</h1>
    <p class="subtitle">Live availability of monitored street parking</p>
    <div class="kpi-row" id="kpis"></div>
    <div class="camera-grid" id="cam-grid"></div>`;

  every(3000, async () => {
    let statuses;
    try { statuses = await API.get('/api/status'); } catch (_) { return; }
    const total = { total: 0, free: 0, occupied: 0, unknown: 0 };
    statuses.forEach(s => { for (const k in total) total[k] += s[k]; });

    document.getElementById('kpis').innerHTML = `
      <div class="card stat-tile"><div class="stat-label">Total spaces</div><div class="stat-value">${total.total}</div></div>
      <div class="card stat-tile"><div class="stat-label"><span class="dot dot-free"></span>Free</div><div class="stat-value" style="color:var(--free)">${total.free}</div></div>
      <div class="card stat-tile"><div class="stat-label"><span class="dot dot-occupied"></span>Occupied</div><div class="stat-value" style="color:var(--occupied)">${total.occupied}</div></div>
      <div class="card stat-tile"><div class="stat-label"><span class="dot dot-unknown"></span>Unknown</div><div class="stat-value" style="color:var(--unknown)">${total.unknown}</div></div>`;

    const grid = document.getElementById('cam-grid');
    if (!statuses.length) {
      grid.innerHTML = `<div class="card"><h2>No cameras yet</h2>
        <p class="subtitle">Add your first camera to start monitoring.</p>
        <a class="btn btn-primary" href="#/cameras">Add a camera</a></div>`;
      return;
    }
    grid.innerHTML = statuses.map(s => `
      <div class="card camera-card">
        <div class="row spread">
          <h2>${esc(s.camera_name)}</h2>
          <span class="conn ${s.connected ? 'on' : 'off'}">${s.connected ? '● live' : '○ offline'}</span>
        </div>
        <div class="counts">${countChips(s)}</div>
        <div class="row">
          <a class="btn btn-sm" href="#/camera/${s.camera_id}">Open</a>
          <a class="btn btn-sm btn-ghost" href="#/camera/${s.camera_id}/calibrate">Edit zones</a>
        </div>
      </div>`).join('');
  });
}

/* ----------------------------------------------------------------- cameras */

async function renderCameras() {
  view.innerHTML = `
    <h1>Cameras</h1>
    <p class="subtitle">Connect RTSP / IP streams, a webcam, or upload a test video</p>
    <div class="card" style="margin-bottom:16px">
      <h2>Add camera</h2>
      <form id="cam-form" class="row" style="align-items:flex-end">
        <label class="field">Name <input id="cf-name" required placeholder="Front street cam"></label>
        <label class="field">Source type
          <select id="cf-type">
            <option value="url">RTSP / IP camera URL</option>
            <option value="webcam">Local webcam</option>
            <option value="file">Upload test video</option>
          </select>
        </label>
        <label class="field" id="cf-source-wrap">Stream URL
          <input id="cf-source" placeholder="rtsp://user:pass@192.168.1.10:554/stream" style="min-width:320px">
        </label>
        <label class="field hidden" id="cf-file-wrap">Video file
          <input id="cf-file" type="file" accept=".mp4,.avi,.mov,.mkv,.webm">
        </label>
        <button class="btn btn-primary" type="submit" id="cf-submit">Add camera</button>
      </form>
      <div class="error-text" id="cf-error"></div>
    </div>
    <div class="card">
      <h2>Configured cameras</h2>
      <table class="list"><thead>
        <tr><th>Name</th><th>Source</th><th>Status</th><th></th></tr>
      </thead><tbody id="cam-rows"></tbody></table>
    </div>`;

  const typeSel = document.getElementById('cf-type');
  typeSel.addEventListener('change', () => {
    const t = typeSel.value;
    document.getElementById('cf-file-wrap').classList.toggle('hidden', t !== 'file');
    document.getElementById('cf-source-wrap').classList.toggle('hidden', t === 'file');
    const src = document.getElementById('cf-source');
    document.getElementById('cf-source-wrap').firstChild.textContent =
      t === 'webcam' ? 'Device index ' : 'Stream URL ';
    src.placeholder = t === 'webcam' ? '0' : 'rtsp://user:pass@192.168.1.10:554/stream';
  });

  document.getElementById('cam-form').addEventListener('submit', async e => {
    e.preventDefault();
    const errEl = document.getElementById('cf-error');
    const btn = document.getElementById('cf-submit');
    errEl.textContent = '';
    const name = document.getElementById('cf-name').value.trim();
    const type = typeSel.value;
    btn.disabled = true;
    try {
      if (type === 'file') {
        const file = document.getElementById('cf-file').files[0];
        if (!file) throw new Error('Choose a video file first');
        btn.textContent = 'Uploading…';
        const fd = new FormData();
        fd.append('name', name);
        fd.append('file', file);
        await API.postForm('/api/cameras/upload', fd);
      } else {
        const source = document.getElementById('cf-source').value.trim();
        if (!source) throw new Error('Source is required');
        await API.post('/api/cameras', { name, source_type: type, source });
      }
      toast(`Camera "${name}" added`);
      e.target.reset();
      typeSel.dispatchEvent(new Event('change'));
      refreshRows();
    } catch (err) { errEl.textContent = err.message; }
    btn.disabled = false;
    btn.textContent = 'Add camera';
  });

  async function refreshRows() {
    const cams = await API.get('/api/cameras');
    const rows = document.getElementById('cam-rows');
    rows.innerHTML = cams.length ? cams.map(c => `
      <tr>
        <td><a href="#/camera/${c.id}">${esc(c.name)}</a></td>
        <td class="calib-help">${esc(c.source_type)}: ${esc(String(c.source).slice(0, 60))}</td>
        <td><span class="conn ${c.connected ? 'on' : 'off'}">${
          c.enabled ? (c.connected ? '● live' : '○ connecting / offline') : '⏸ disabled'}</span>
          ${c.runtime_error ? `<div class="error-text">${esc(c.runtime_error)}</div>` : ''}</td>
        <td class="row" style="justify-content:flex-end">
          <a class="btn btn-sm" href="#/camera/${c.id}/calibrate">Zones</a>
          <button class="btn btn-sm" data-toggle="${c.id}" data-enabled="${c.enabled}">${c.enabled ? 'Disable' : 'Enable'}</button>
          <button class="btn btn-sm btn-danger" data-del="${c.id}" data-name="${esc(c.name)}">Delete</button>
        </td>
      </tr>`).join('')
      : '<tr><td colspan="4" class="subtitle">No cameras configured yet.</td></tr>';

    rows.querySelectorAll('[data-toggle]').forEach(btn =>
      btn.addEventListener('click', async () => {
        await API.patch(`/api/cameras/${btn.dataset.toggle}`, { enabled: btn.dataset.enabled !== '1' });
        refreshRows();
      }));
    rows.querySelectorAll('[data-del]').forEach(btn =>
      btn.addEventListener('click', async () => {
        if (!confirm(`Delete camera "${btn.dataset.name}" and its zones/history?`)) return;
        await API.del(`/api/cameras/${btn.dataset.del}`);
        toast('Camera deleted');
        refreshRows();
      }));
  }
  await refreshRows();
  every(5000, refreshRows);
}

/* ----------------------------------------------------------- camera detail */

async function renderCameraDetail(idStr) {
  const cameraId = Number(idStr);
  const camera = await API.get(`/api/cameras/${cameraId}`);
  view.innerHTML = `
    <div class="row spread">
      <div>
        <h1>${esc(camera.name)}</h1>
        <p class="subtitle" style="margin:0">${esc(camera.source_type)} · <span class="conn ${camera.connected ? 'on' : 'off'}">${camera.connected ? '● live' : '○ offline'}</span></p>
      </div>
      <div class="row" id="detail-chips"></div>
    </div>
    <div class="tabs">
      <button data-tab="live" class="active">Live camera</button>
      <button data-tab="road">Road view</button>
      <button data-tab="history">History</button>
      <span style="margin-left:auto"><a class="btn btn-sm" href="#/camera/${cameraId}/calibrate">Edit zones</a></span>
    </div>
    <div id="tab-content"></div>`;

  every(2000, async () => {
    try {
      const s = await API.get(`/api/cameras/${cameraId}/status`);
      document.getElementById('detail-chips').innerHTML = countChips(s);
      const road = document.getElementById('road-svg');
      if (road) road.innerHTML = Illustration.render(s.zones);
      const ztab = document.getElementById('zone-status-rows');
      if (ztab) ztab.innerHTML = s.zones.map(z => `
        <tr><td>${esc(z.name)}</td>
          <td><span class="status-pill ${z.status}">${z.status}</span></td>
          <td class="calib-help">${z.since ? 'since ' + fmtTime(z.since) : ''}</td></tr>`).join('');
    } catch (_) { /* transient */ }
  });

  const tabs = view.querySelectorAll('[data-tab]');
  tabs.forEach(btn => btn.addEventListener('click', () => {
    tabs.forEach(b => b.classList.toggle('active', b === btn));
    showTab(btn.dataset.tab);
  }));

  function showTab(tab) {
    const el = document.getElementById('tab-content');
    if (tab === 'live') {
      el.innerHTML = `
        <div class="card stream-box">
          <div class="row spread" style="margin-bottom:10px">
            <span class="calib-help">Live stream with detection overlays</span>
            <label class="row" style="gap:6px;font-size:13px;color:var(--text-2)">
              <input type="checkbox" id="overlay-toggle" checked> overlays
            </label>
          </div>
          <img id="live-img" src="${API.streamUrl(cameraId, true)}" alt="Live camera stream">
        </div>`;
      document.getElementById('overlay-toggle').addEventListener('change', e => {
        document.getElementById('live-img').src = API.streamUrl(cameraId, e.target.checked);
      });
      cleanup.push(() => { const img = document.getElementById('live-img'); if (img) img.src = ''; });
    } else if (tab === 'road') {
      el.innerHTML = `
        <div class="card">
          <div class="road-wrap" id="road-svg"></div>
          <table class="list" style="margin-top:14px"><thead>
            <tr><th>Zone</th><th>Status</th><th></th></tr>
          </thead><tbody id="zone-status-rows"></tbody></table>
        </div>`;
    } else if (tab === 'history') {
      el.innerHTML = `
        <div class="history-layout">
          <div class="card">
            <div class="row spread" style="margin-bottom:8px">
              <h2 style="margin:0">Daily occupancy</h2>
              <input type="date" id="stats-date" value="${new Date().toISOString().slice(0, 10)}">
            </div>
            <div id="stats-chart"></div>
          </div>
          <div class="card">
            <h2>Recent changes</h2>
            <div class="event-feed" id="event-feed"></div>
          </div>
        </div>`;
      const loadStats = async () => {
        const date = document.getElementById('stats-date').value;
        const stats = await API.get(`/api/cameras/${cameraId}/stats?date=${date}`);
        OccupancyChart.render(document.getElementById('stats-chart'), stats.hourly);
      };
      document.getElementById('stats-date').addEventListener('change', loadStats);
      loadStats();
      every(10000, async () => {
        const events = await API.get(`/api/cameras/${cameraId}/history?limit=60`);
        document.getElementById('event-feed').innerHTML = events.length ? events.map(ev => `
          <div class="event-item">
            <span class="status-pill ${ev.status}">${ev.status}</span>
            <span>${esc(ev.zone_name)}</span>
            <time>${fmtDateTime(ev.changed_at)}</time>
          </div>`).join('')
          : '<p class="subtitle">No status changes recorded yet.</p>';
      });
    }
  }
  showTab('live');
}

/* -------------------------------------------------------------- calibrate */

async function renderCalibrate(idStr) {
  const cameraId = Number(idStr);
  const camera = await API.get(`/api/cameras/${cameraId}`);
  view.innerHTML = `
    <div class="row spread" style="margin-bottom:14px">
      <div>
        <h1>Zone calibration — ${esc(camera.name)}</h1>
        <p class="subtitle" style="margin:0">Mark each parking space on the camera snapshot</p>
      </div>
      <a class="btn" href="#/camera/${cameraId}">Done — back to camera</a>
    </div>
    <div id="calib-root"></div>`;
  const editor = new CalibrationEditor(cameraId, document.getElementById('calib-root'));
  cleanup.push(() => editor.destroy());
  await editor.init();
}
