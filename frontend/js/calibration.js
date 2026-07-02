/* Parking-zone calibration editor.
   Draws rectangles or free polygons over a camera snapshot; zone coordinates
   are stored in source-frame pixels so detection and display always agree. */
class CalibrationEditor {
  constructor(cameraId, root) {
    this.cameraId = cameraId;
    this.root = root;
    this.mode = 'rect';         // rect | poly
    this.zones = [];
    this.draft = [];            // in-progress polygon points (image px)
    this.dragStart = null;      // rect-mode anchor point
    this.dragCurrent = null;
    this.highlightZoneId = null;
    this.image = new Image();
    this.destroyed = false;
  }

  async init() {
    this.root.innerHTML = `
      <div class="row spread" style="margin-bottom:12px">
        <div class="row">
          <button class="btn btn-sm active" data-mode="rect">▭ Rectangle</button>
          <button class="btn btn-sm" data-mode="poly">⬠ Polygon</button>
          <button class="btn btn-sm" data-act="refresh">↺ Refresh snapshot</button>
        </div>
        <span class="calib-help" id="calib-hint"></span>
      </div>
      <div class="calib-layout">
        <div>
          <div class="calib-canvas-wrap"><canvas id="calib-canvas"></canvas></div>
          <p class="calib-help">
            Rectangle: click and drag over a parking space. Polygon: click each corner,
            then double-click (or press Enter) to close; Esc cancels.
          </p>
        </div>
        <div class="card">
          <h2>Zones</h2>
          <div class="zone-list" id="zone-list"></div>
          <div id="zone-form" class="hidden" style="margin-top:12px; display:flex; flex-direction:column; gap:8px">
            <label class="field">Zone name <input id="zf-name"></label>
            <label class="field">Road side (illustration view)
              <select id="zf-side"><option value="right">Right</option><option value="left">Left</option></select>
            </label>
            <div class="row">
              <button class="btn btn-primary btn-sm" data-act="save-zone">Save zone</button>
              <button class="btn btn-sm" data-act="cancel-zone">Discard</button>
            </div>
          </div>
        </div>
      </div>`;

    this.canvas = this.root.querySelector('#calib-canvas');
    this.ctx = this.canvas.getContext('2d');
    this._bind();
    await this.loadZones();
    await this.loadSnapshot();
    this.updateHint();
  }

  destroy() {
    this.destroyed = true;
    document.removeEventListener('keydown', this._keyHandler);
  }

  _bind() {
    this.root.addEventListener('click', e => {
      const modeBtn = e.target.closest('[data-mode]');
      if (modeBtn) {
        this.mode = modeBtn.dataset.mode;
        this.root.querySelectorAll('[data-mode]').forEach(b =>
          b.classList.toggle('active', b === modeBtn));
        this.cancelDraft();
        return;
      }
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'refresh') this.loadSnapshot();
      if (act === 'save-zone') this.saveDraft();
      if (act === 'cancel-zone') this.cancelDraft();
    });

    const pos = e => {
      const r = this.canvas.getBoundingClientRect();
      return [
        Math.round((e.clientX - r.left) / r.width * this.canvas.width),
        Math.round((e.clientY - r.top) / r.height * this.canvas.height),
      ];
    };

    this.canvas.addEventListener('mousedown', e => {
      if (this.mode !== 'rect' || this.pendingShape()) return;
      this.dragStart = pos(e);
      this.dragCurrent = this.dragStart;
    });
    this.canvas.addEventListener('mousemove', e => {
      if (this.dragStart) { this.dragCurrent = pos(e); this.redraw(); }
      else if (this.mode === 'poly' && this.draft.length && !this.pendingShape()) {
        this.hoverPoint = pos(e); this.redraw();
      }
    });
    this.canvas.addEventListener('mouseup', e => {
      if (!this.dragStart) return;
      const [x1, y1] = this.dragStart, [x2, y2] = pos(e);
      this.dragStart = this.dragCurrent = null;
      if (Math.abs(x2 - x1) > 8 && Math.abs(y2 - y1) > 8) {
        this.draft = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]];
        this.openZoneForm();
      }
      this.redraw();
    });
    this.canvas.addEventListener('click', e => {
      if (this.mode !== 'poly' || this.pendingShape()) return;
      this.draft.push(pos(e));
      this.redraw();
      this.updateHint();
    });
    this.canvas.addEventListener('dblclick', () => {
      if (this.mode === 'poly') this.finishPolygon();
    });

    this._keyHandler = e => {
      if (e.key === 'Enter' && this.mode === 'poly') this.finishPolygon();
      if (e.key === 'Escape') this.cancelDraft();
    };
    document.addEventListener('keydown', this._keyHandler);
  }

  pendingShape() {
    return !this.root.querySelector('#zone-form').classList.contains('hidden');
  }

  finishPolygon() {
    if (this.pendingShape() || this.draft.length < 3) return;
    this.hoverPoint = null;
    this.openZoneForm();
  }

  openZoneForm() {
    const form = this.root.querySelector('#zone-form');
    form.classList.remove('hidden');
    const name = this.root.querySelector('#zf-name');
    name.value = `Spot ${this.zones.length + 1}`;
    name.focus();
    name.select();
    this.redraw();
    this.updateHint();
  }

  async saveDraft() {
    const name = this.root.querySelector('#zf-name').value.trim() || `Spot ${this.zones.length + 1}`;
    const side = this.root.querySelector('#zf-side').value;
    try {
      await API.post(`/api/cameras/${this.cameraId}/zones`, {
        name, side, polygon: this.draft, position: this.zones.length,
      });
      toast(`Zone "${name}" saved`);
      this.cancelDraft();
      await this.loadZones();
    } catch (err) { toast(err.message); }
  }

  cancelDraft() {
    this.draft = [];
    this.hoverPoint = null;
    this.dragStart = this.dragCurrent = null;
    this.root.querySelector('#zone-form').classList.add('hidden');
    this.redraw();
    this.updateHint();
  }

  updateHint() {
    const hint = this.root.querySelector('#calib-hint');
    if (this.pendingShape()) hint.textContent = 'Name the zone, then save or discard.';
    else if (this.mode === 'poly' && this.draft.length) {
      hint.textContent = `${this.draft.length} point(s) — double-click or Enter to close.`;
    } else hint.textContent = 'Draw a zone over each parking space.';
  }

  async loadZones() {
    this.zones = await API.get(`/api/cameras/${this.cameraId}/zones`);
    this.renderZoneList();
    this.redraw();
  }

  async loadSnapshot() {
    await new Promise(resolve => {
      this.image.onload = resolve;
      this.image.onerror = resolve;
      this.image.src = API.snapshotUrl(this.cameraId);
    });
    if (this.destroyed) return;
    this.canvas.width = this.image.naturalWidth || 640;
    this.canvas.height = this.image.naturalHeight || 360;
    this.redraw();
  }

  renderZoneList() {
    const list = this.root.querySelector('#zone-list');
    if (!this.zones.length) {
      list.innerHTML = '<p class="subtitle" style="margin:0">No zones yet — draw the first one on the snapshot.</p>';
      return;
    }
    list.innerHTML = this.zones.map(z => `
      <div class="zone-row" data-zone="${z.id}">
        <span class="zone-name">${esc(z.name)}</span>
        <span class="calib-help">${z.side}</span>
        <span class="spacer"></span>
        <button class="btn btn-ghost btn-sm" data-zact="rename" title="Rename">✎</button>
        <button class="btn btn-ghost btn-sm" data-zact="flip" title="Switch road side">⇄</button>
        <button class="btn btn-ghost btn-sm btn-danger" data-zact="delete" title="Delete">✕</button>
      </div>`).join('');

    list.querySelectorAll('.zone-row').forEach(row => {
      const id = Number(row.dataset.zone);
      row.addEventListener('mouseenter', () => { this.highlightZoneId = id; this.redraw(); });
      row.addEventListener('mouseleave', () => { this.highlightZoneId = null; this.redraw(); });
      row.addEventListener('click', async e => {
        const act = e.target.closest('[data-zact]')?.dataset.zact;
        if (!act) return;
        const zone = this.zones.find(z => z.id === id);
        try {
          if (act === 'delete') {
            if (!confirm(`Delete zone "${zone.name}"?`)) return;
            await API.del(`/api/zones/${id}`);
          } else if (act === 'rename') {
            const name = prompt('Zone name', zone.name);
            if (!name || !name.trim()) return;
            await API.patch(`/api/zones/${id}`, { name: name.trim() });
          } else if (act === 'flip') {
            await API.patch(`/api/zones/${id}`, { side: zone.side === 'left' ? 'right' : 'left' });
          }
          await this.loadZones();
        } catch (err) { toast(err.message); }
      });
    });
  }

  redraw() {
    const { ctx, canvas } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (this.image.naturalWidth) ctx.drawImage(this.image, 0, 0);
    else { ctx.fillStyle = '#262b34'; ctx.fillRect(0, 0, canvas.width, canvas.height); }

    const lw = Math.max(2, canvas.width / 480);
    for (const zone of this.zones) {
      const hot = zone.id === this.highlightZoneId;
      this.drawPoly(zone.polygon, hot ? '#3987e5' : '#22a862', lw, true);
      const [lx, ly] = zone.polygon[0];
      ctx.font = `${Math.max(13, canvas.width / 55)}px system-ui, sans-serif`;
      ctx.fillStyle = '#fff';
      ctx.strokeStyle = 'rgba(0,0,0,0.8)';
      ctx.lineWidth = lw * 1.5;
      ctx.strokeText(zone.name, lx + 6, ly + 20);
      ctx.fillText(zone.name, lx + 6, ly + 20);
    }

    // in-progress shape
    if (this.dragStart && this.dragCurrent) {
      const [x1, y1] = this.dragStart, [x2, y2] = this.dragCurrent;
      this.drawPoly([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], '#f0b429', lw, true, true);
    } else if (this.draft.length) {
      const pts = this.hoverPoint ? [...this.draft, this.hoverPoint] : this.draft;
      this.drawPoly(pts, '#f0b429', lw, this.pendingShape(), true);
      for (const [x, y] of this.draft) {
        ctx.beginPath(); ctx.arc(x, y, lw * 2, 0, Math.PI * 2);
        ctx.fillStyle = '#f0b429'; ctx.fill();
      }
    }
  }

  drawPoly(points, color, lw, close, dashed = false) {
    const { ctx } = this;
    ctx.beginPath();
    ctx.moveTo(points[0][0], points[0][1]);
    for (const [x, y] of points.slice(1)) ctx.lineTo(x, y);
    if (close) ctx.closePath();
    ctx.setLineDash(dashed ? [8, 6] : []);
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.stroke();
    if (close) {
      ctx.fillStyle = color + '2e'; // ~18% alpha fill
      ctx.fill();
    }
    ctx.setLineDash([]);
  }
}
