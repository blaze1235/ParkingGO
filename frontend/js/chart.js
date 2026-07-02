/* Hourly occupancy chart: stacked bars (free / occupied / unknown per hour).
   Follows the dataviz spec: thin marks with 2px surface gaps between stacked
   segments, rounded top on the topmost segment, hairline grid, single axis,
   legend + hover tooltip (identity never carried by color alone). */
const OccupancyChart = {
  SERIES: [
    { key: 'free', label: 'Free', color: '#22a862' },
    { key: 'occupied', label: 'Occupied', color: '#d0453f' },
    { key: 'unknown', label: 'Unknown', color: '#8a8f98' },
  ],

  render(container, hourly) {
    container.innerHTML = '';

    const legend = document.createElement('div');
    legend.className = 'chart-legend';
    legend.innerHTML = this.SERIES.map(s =>
      `<span class="chip"><span class="dot" style="background:${s.color}"></span>${s.label}</span>`
    ).join('');
    container.appendChild(legend);

    if (!hourly.length) {
      const empty = document.createElement('p');
      empty.className = 'subtitle';
      empty.textContent = 'No statistics recorded for this day yet. Samples are taken once a minute while cameras run.';
      container.appendChild(empty);
      return;
    }

    const W = 680, H = 240, M = { top: 12, right: 10, bottom: 26, left: 34 };
    const plotW = W - M.left - M.right, plotH = H - M.top - M.bottom;
    const byHour = Object.fromEntries(hourly.map(h => [h.hour, h]));
    const hours = [...Array(24).keys()];
    const maxTotal = Math.max(1, ...hourly.map(h => h.free + h.occupied + h.unknown));
    const yMax = Math.ceil(maxTotal);
    const barW = Math.min(18, plotW / 24 - 4);
    const xFor = hour => M.left + (hour + 0.5) * (plotW / 24) - barW / 2;
    const yFor = v => M.top + plotH * (1 - v / yMax);

    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

    let inner = '';
    // hairline gridlines + y tick labels (integer steps, at most 5)
    const step = Math.max(1, Math.ceil(yMax / 5));
    for (let v = 0; v <= yMax; v += step) {
      const y = yFor(v);
      inner += `<line x1="${M.left}" y1="${y}" x2="${W - M.right}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>`;
      inner += `<text x="${M.left - 7}" y="${y + 4}" fill="#7d838e" font-size="11" text-anchor="end" font-family="system-ui,sans-serif" style="font-variant-numeric:tabular-nums">${v}</text>`;
    }
    // baseline
    inner += `<line x1="${M.left}" y1="${yFor(0)}" x2="${W - M.right}" y2="${yFor(0)}" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>`;

    for (const hour of hours) {
      const d = byHour[hour];
      // x labels every 3 hours
      if (hour % 3 === 0) {
        inner += `<text x="${xFor(hour) + barW / 2}" y="${H - 8}" fill="#7d838e" font-size="11" text-anchor="middle" font-family="system-ui,sans-serif">${String(hour).padStart(2, '0')}</text>`;
      }
      if (!d) continue;
      const segments = this.SERIES
        .map(s => ({ ...s, value: d[s.key] }))
        .filter(s => s.value > 0.01);
      let cumulative = 0;
      segments.forEach((seg, i) => {
        const y0 = yFor(cumulative), y1 = yFor(cumulative + seg.value);
        cumulative += seg.value;
        const gap = i > 0 ? 2 : 0; // 2px surface gap between stacked segments
        const top = y1, bottom = y0 - gap;
        const h = Math.max(1, bottom - top);
        const isTop = i === segments.length - 1;
        const x = xFor(hour);
        if (isTop) { // rounded data-end on the topmost segment only
          const r = Math.min(3, h / 2, barW / 2);
          inner += `<path d="M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${top + h} Z" fill="${seg.color}"/>`;
        } else {
          inner += `<rect x="${x}" y="${top}" width="${barW}" height="${h}" fill="${seg.color}"/>`;
        }
      });
      // full-column invisible hit target for the tooltip
      inner += `<rect class="hit" data-hour="${hour}" x="${xFor(hour) - 3}" y="${M.top}" width="${barW + 6}" height="${plotH}" fill="transparent"/>`;
    }
    svg.innerHTML = inner;

    const box = document.createElement('div');
    box.className = 'chart-box';
    box.appendChild(svg);
    container.appendChild(box);
    this._attachTooltip(svg, byHour);
  },

  _attachTooltip(svg, byHour) {
    let tip = null;
    const hide = () => { if (tip) { tip.remove(); tip = null; } };
    svg.addEventListener('mousemove', e => {
      const hit = e.target.closest('.hit');
      if (!hit) { hide(); return; }
      const d = byHour[hit.dataset.hour];
      if (!tip) { tip = document.createElement('div'); tip.className = 'chart-tooltip'; document.body.appendChild(tip); }
      tip.innerHTML = `<div class="tt-title">${String(d.hour).padStart(2, '0')}:00 – ${String(d.hour).padStart(2, '0')}:59 (avg)</div>` +
        this.SERIES.map(s =>
          `<div class="tt-row"><span class="dot" style="background:${s.color};width:9px;height:9px;border-radius:3px"></span>${s.label}<span class="tt-val">${d[s.key]}</span></div>`
        ).join('');
      tip.style.left = `${Math.min(e.clientX + 14, window.innerWidth - 180)}px`;
      tip.style.top = `${e.clientY + 14}px`;
    });
    svg.addEventListener('mouseleave', hide);
  },
};
