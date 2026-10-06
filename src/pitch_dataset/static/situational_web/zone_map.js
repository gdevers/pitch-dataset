// Strike-zone location heatmap (catcher's view). Shared by select-web and the static demo.
// Zones are batter-relative (in/away); screen side depends on batter stand.

const ZONE_META = {
  up_in: { label: 'Up & in', x: [-0.83, -0.277], z: [2 / 3, 1] },
  up_mid: { label: 'Up, middle', x: [-0.277, 0.277], z: [2 / 3, 1] },
  up_away: { label: 'Up & away', x: [0.277, 0.83], z: [2 / 3, 1] },
  mid_in: { label: 'Middle in', x: [-0.83, -0.277], z: [1 / 3, 2 / 3] },
  heart: { label: 'Heart', x: [-0.277, 0.277], z: [1 / 3, 2 / 3] },
  mid_away: { label: 'Middle away', x: [0.277, 0.83], z: [1 / 3, 2 / 3] },
  down_in: { label: 'Down & in', x: [-0.83, -0.277], z: [0, 1 / 3] },
  down_mid: { label: 'Down, middle', x: [-0.277, 0.277], z: [0, 1 / 3] },
  down_away: { label: 'Down & away', x: [0.277, 0.83], z: [0, 1 / 3] },
  chase_up_in: { label: 'Chase up & in', x: [-1.45, 0], z: [0.5, 1.5], lx: -1.14, lz: 1.27 },
  chase_up_away: { label: 'Chase up & away', x: [0, 1.45], z: [0.5, 1.5], lx: 1.14, lz: 1.27 },
  chase_down_in: { label: 'Chase down & in', x: [-1.45, 0], z: [-0.6, 0.5], lx: -1.14, lz: -0.32 },
  chase_down_away: { label: 'Chase down & away', x: [0, 1.45], z: [-0.6, 0.5], lx: 1.14, lz: -0.32 },
};
const ZONE_CHASE_IDS = ['chase_up_in', 'chase_up_away', 'chase_down_in', 'chase_down_away'];

function zoneLabel(id) {
  return (ZONE_META[id] && ZONE_META[id].label) || id;
}

function _zoneColor(t) {
  // t in [0,1]: 0 = worst (red), 0.5 = neutral, 1 = best (green)
  const lerp = (a, b, u) => Math.round(a + (b - a) * u);
  const bad = [192, 57, 43], mid = [244, 241, 234], good = [31, 107, 58];
  const [a, b, u] = t < 0.5 ? [bad, mid, t / 0.5] : [mid, good, (t - 0.5) / 0.5];
  return `rgb(${lerp(a[0], b[0], u)},${lerp(a[1], b[1], u)},${lerp(a[2], b[2], u)})`;
}

function _esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

/**
 * cells: [{zone, rank, value, whiff?, xwoba?, n?}] — value = runs saved / 100 pitches (higher = better).
 * opts: {stand: 'L'|'R', gloveSide: 'in'|'away', pitchType}
 */
function zoneMapSVG(cells, opts) {
  const stand = (opts && opts.stand) || 'R';
  const glove = (opts && opts.gloveSide) || 'away';
  const ppf = 78;
  const zScale = 1.8;
  const xMin = -1.6, xMax = 1.6, zMin = -0.62, zMax = 1.52;
  const padTop = 30, padBottom = 58;
  const W = (xMax - xMin) * ppf;
  const H = (zMax - zMin) * zScale * ppf + padTop + padBottom;
  const sx = xAway => ((stand === 'R' ? xAway : -xAway) - xMin) * ppf;
  const sz = zn => padTop + (zMax - zn) * zScale * ppf;
  const byZone = {};
  cells.forEach(c => { byZone[c.zone] = c; });
  const vals = cells.map(c => c.value);
  const vMin = Math.min(...vals), vMax = Math.max(...vals);
  const span = Math.max(1e-6, vMax - vMin);
  const best = cells.reduce((a, c) => (a === null || c.rank < a.rank ? c : a), null);

  const rectFor = (id) => {
    const m = ZONE_META[id];
    const xa = sx(m.x[0]), xb = sx(m.x[1]);
    return { x: Math.min(xa, xb), y: sz(m.z[1]), w: Math.abs(xb - xa), h: sz(m.z[0]) - sz(m.z[1]) };
  };
  const tip = c => {
    const parts = [`#${c.rank} ${zoneLabel(c.zone)}`, `runs saved/100: ${c.value >= 0 ? '+' : ''}${c.value.toFixed(2)}`];
    if (c.whiff != null) parts.push(`whiff: ${c.whiff.toFixed(1)}%`);
    if (c.xwoba != null) parts.push(`pred xwOBA: ${c.xwoba.toFixed(3)}`);
    if (c.n != null) parts.push(`league n (pitch×hand×zone×count): ${c.n}`);
    return _esc(parts.join('\n'));
  };
  const cellText = (c, cx, cy, small) => {
    const isBest = best && c.zone === best.zone;
    return `<text x="${cx}" y="${cy - 3}" text-anchor="middle" font-size="${small ? 13 : 15}" font-weight="700" fill="#1a1a1a">${isBest ? '★ ' : ''}${c.rank}</text>` +
      `<text x="${cx}" y="${cy + 13}" text-anchor="middle" font-size="11" fill="#333">${c.value >= 0 ? '+' : ''}${c.value.toFixed(1)}</text>`;
  };

  let out = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Location heatmap, catcher's view" style="max-width:100%;height:auto;font-family:inherit">`;
  out += `<text x="${W / 2}" y="18" text-anchor="middle" font-size="12" fill="#5c5c5c">Catcher's view · ${stand === 'R' ? 'RHH' : 'LHH'} · ${_esc(opts.pitchType || '')}</text>`;

  ZONE_CHASE_IDS.forEach(id => {
    const c = byZone[id];
    if (!c) return;
    const r = rectFor(id);
    const isBest = best && id === best.zone;
    out += `<g><title>${tip(c)}</title><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${_zoneColor((c.value - vMin) / span)}" fill-opacity="0.85" stroke="${isBest ? '#111' : '#fff'}" stroke-width="${isBest ? 3 : 1.5}"/></g>`;
  });
  ZONE_CHASE_IDS.forEach(id => {
    const c = byZone[id];
    if (!c) return;
    const m = ZONE_META[id];
    out += `<g pointer-events="none">${cellText(c, sx(m.lx), sz(m.lz), true)}</g>`;
  });

  const zr = { x: sx(-0.83) < sx(0.83) ? sx(-0.83) : sx(0.83), y: sz(1), w: Math.abs(sx(0.83) - sx(-0.83)), h: sz(0) - sz(1) };
  Object.keys(ZONE_META).filter(id => !ZONE_CHASE_IDS.includes(id)).forEach(id => {
    const c = byZone[id];
    if (!c) return;
    const r = rectFor(id);
    out += `<g><title>${tip(c)}</title><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${_zoneColor((c.value - vMin) / span)}" stroke="#fff" stroke-width="1"/>${cellText(c, r.x + r.w / 2, r.y + r.h / 2 + 2, false)}</g>`;
  });
  out += `<rect x="${zr.x}" y="${zr.y}" width="${zr.w}" height="${zr.h}" fill="none" stroke="#1a1a1a" stroke-width="2" pointer-events="none"/>`;
  if (best && !ZONE_CHASE_IDS.includes(best.zone)) {
    const r = rectFor(best.zone);
    out += `<rect x="${r.x + 1.5}" y="${r.y + 1.5}" width="${r.w - 3}" height="${r.h - 3}" fill="none" stroke="#111" stroke-width="3" pointer-events="none"/>`;
  }

  // Home plate (catcher's view: point toward the catcher, i.e. down).
  const py = sz(zMin) + 8;
  const pl = sx(-0.708), pr = sx(0.708), pxl = Math.min(pl, pr), pxr = Math.max(pl, pr), pm = (pxl + pxr) / 2;
  out += `<polygon points="${pxl},${py} ${pxr},${py} ${pxr},${py + 8} ${pm},${py + 18} ${pxl},${py + 8}" fill="#fff" stroke="#8a8a84"/>`;
  const inLeft = stand === 'R';
  const inText = `in${glove === 'in' ? ' (glove side)' : ' (arm side)'}`;
  const awayText = `away${glove === 'away' ? ' (glove side)' : ' (arm side)'}`;
  out += `<text x="6" y="${py + 40}" font-size="11" fill="#5c5c5c">← ${inLeft ? inText : awayText}</text>`;
  out += `<text x="${W - 6}" y="${py + 40}" text-anchor="end" font-size="11" fill="#5c5c5c">${inLeft ? awayText : inText} →</text>`;
  out += `</svg>`;
  return out;
}

function zoneMapLegend() {
  return `<div style="display:flex;align-items:center;gap:8px;font-size:11px;color:#5c5c5c;margin-top:6px">` +
    `<span>worse</span><span style="display:inline-block;width:120px;height:10px;border-radius:2px;` +
    `background:linear-gradient(90deg,${_zoneColor(0)},${_zoneColor(0.5)},${_zoneColor(1)})"></span><span>better</span>` +
    `<span style="margin-left:8px">Cell: rank (★ = best) and runs saved per 100 pitches</span></div>`;
}

function zoneTopList(cells, n) {
  return cells.slice().sort((a, b) => a.rank - b.rank).slice(0, n).map(c =>
    `<li><strong>${zoneLabel(c.zone)}</strong> — ${c.value >= 0 ? '+' : ''}${c.value.toFixed(2)} runs saved/100` +
    (c.whiff != null ? `, whiff ${c.whiff.toFixed(0)}%` : '') +
    (c.xwoba != null ? `, xwOBA ${c.xwoba.toFixed(3)}` : '') + `</li>`
  ).join('');
}
