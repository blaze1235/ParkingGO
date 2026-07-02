/* Simplified road illustration: a vertical two-lane road with parking bays
   drawn beside it, colored by live status. Pure SVG string building. */
const Illustration = {
  STATUS_FILL: { free: '#22a862', occupied: '#d0453f', unknown: '#8a8f98' },

  render(zones) {
    const left = zones.filter(z => z.side === 'left');
    const right = zones.filter(z => z.side !== 'left');
    const rows = Math.max(left.length, right.length, 1);

    const BAY_W = 150, BAY_H = 62, GAP = 12, ROAD_W = 130, PAD = 16;
    const width = PAD * 2 + BAY_W * 2 + ROAD_W + GAP * 2;
    const height = PAD * 2 + rows * (BAY_H + GAP) - GAP + 40;
    const roadX = PAD + BAY_W + GAP;

    let svg = `<svg viewBox="0 0 ${width} ${height}" width="${width}" role="img" aria-label="Parking availability illustration" xmlns="http://www.w3.org/2000/svg">`;

    // road body + dashed center divider + edge lines
    svg += `<rect x="${roadX}" y="0" width="${ROAD_W}" height="${height}" fill="#262b34"/>`;
    svg += `<line x1="${roadX + 4}" y1="0" x2="${roadX + 4}" y2="${height}" stroke="#4a5160" stroke-width="2"/>`;
    svg += `<line x1="${roadX + ROAD_W - 4}" y1="0" x2="${roadX + ROAD_W - 4}" y2="${height}" stroke="#4a5160" stroke-width="2"/>`;
    svg += `<line x1="${roadX + ROAD_W / 2}" y1="0" x2="${roadX + ROAD_W / 2}" y2="${height}" stroke="#a7adb8" stroke-width="3" stroke-dasharray="18 14"/>`;

    const bay = (zone, x, y) => {
      const color = this.STATUS_FILL[zone.status] || this.STATUS_FILL.unknown;
      let s = `<g>`;
      s += `<rect x="${x}" y="${y}" width="${BAY_W}" height="${BAY_H}" rx="8" fill="${color}" fill-opacity="0.22" stroke="${color}" stroke-width="2"/>`;
      if (zone.status === 'occupied') s += this.car(x + BAY_W - 52, y + BAY_H / 2 - 14, color);
      s += `<text x="${x + 12}" y="${y + 26}" fill="#e8eaed" font-size="15" font-weight="600" font-family="system-ui, sans-serif">${esc(zone.name)}</text>`;
      s += `<text x="${x + 12}" y="${y + 46}" fill="#a7adb8" font-size="12" font-family="system-ui, sans-serif">${zone.status.toUpperCase()}</text>`;
      s += `</g>`;
      return s;
    };

    left.forEach((z, i) => { svg += bay(z, PAD, PAD + i * (BAY_H + GAP)); });
    right.forEach((z, i) => { svg += bay(z, roadX + ROAD_W + GAP, PAD + i * (BAY_H + GAP)); });

    if (!zones.length) {
      svg += `<text x="${width / 2}" y="${height / 2}" fill="#7d838e" font-size="14" text-anchor="middle" font-family="system-ui, sans-serif">No parking zones defined yet</text>`;
    }
    svg += `</svg>`;
    return svg;
  },

  /* small top-view car glyph for occupied bays */
  car(x, y, color) {
    return `<g transform="translate(${x},${y})">
      <rect x="0" y="4" width="40" height="20" rx="7" fill="${color}"/>
      <rect x="6" y="0" width="7" height="28" rx="2" fill="${color}" opacity="0.6"/>
      <rect x="27" y="0" width="7" height="28" rx="2" fill="${color}" opacity="0.6"/>
      <rect x="14" y="7" width="9" height="14" rx="2" fill="#171a20" opacity="0.45"/>
    </g>`;
  },
};

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
