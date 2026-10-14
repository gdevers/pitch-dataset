// Pitch-to-field: zone picker (catcher's view) + to-scale spray field.
// Works from embedded data (window.P2F_STATIC, GitHub Pages) or the select-web /api/field endpoints.
// Requires zone_map.js (ZONE_META, _zoneColor, _esc).

const P2F = {
  meta: null,
  hitters: [],
  cache: {},
  state: { batterId: null, stand: 'R', pt: 'SL', zone: 'down_away', view: 'hitter', color: 'xwoba', filter: 'all', showBalls: true },
  profile: null,
};

const BB_COLORS = { GB: '#7a4b1e', LD: '#c0392b', FB: '#1f4b99', PU: '#7b7b75' };
const BB_NAMES = { GB: 'Ground ball', LD: 'Line drive', FB: 'Fly ball', PU: 'Popup' };
const BB_KEYS = ['ground_ball', 'line_drive', 'fly_ball', 'popup'];

function p2fIsStatic() { return typeof window.P2F_STATIC === 'object' && window.P2F_STATIC !== null; }

async function p2fJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

async function p2fGetProfile(view, bid, stand, pt) {
  const key = view === 'league' ? `L|${stand}|${pt}` : `H|${bid}|${stand}|${pt}`;
  if (P2F.cache[key]) return P2F.cache[key];
  let prof;
  if (p2fIsStatic()) {
    prof = view === 'league' ? window.P2F_STATIC.league[`${stand}|${pt}`] : window.P2F_STATIC.profiles[`${bid}|${stand}|${pt}`];
    if (!prof) throw new Error('Not precomputed in this demo.');
  } else if (view === 'league') {
    prof = await p2fJSON(`/api/field/league?stand=${stand}&pitch_type=${pt}`);
  } else {
    prof = await p2fJSON(`/api/field?batter_id=${bid}&stand=${stand}&pitch_type=${pt}`);
  }
  if (prof.balls && prof.balls.rows) {
    const f = prof.balls.fields;
    prof.balls = prof.balls.rows.map(r => Object.fromEntries(f.map((k, i) => [k, r[i]])));
  }
  P2F.cache[key] = prof;
  return prof;
}

// ---------------------------------------------------------------- color + format helpers

const DANGER_STOPS = [[0, [255, 247, 224]], [0.3, [253, 208, 138]], [0.55, [240, 138, 75]], [0.78, [215, 48, 39]], [1, [127, 0, 0]]];
function dangerColor(t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < DANGER_STOPS.length; i++) {
    const [t1, c1] = DANGER_STOPS[i];
    const [t0, c0] = DANGER_STOPS[i - 1];
    if (t <= t1) {
      const u = (t - t0) / (t1 - t0);
      return `rgb(${c0.map((v, k) => Math.round(v + (c1[k] - v) * u)).join(',')})`;
    }
  }
  return 'rgb(127,0,0)';
}
const COLOR_DOMAIN = { xwoba: 1.2, hit: 1.0 };
const foldName = s => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const pct = (v, d = 0) => (v == null || isNaN(v) ? '–' : `${(100 * v).toFixed(d)}%`);
const f3 = v => (v == null || isNaN(v) ? '–' : v.toFixed(3).replace(/^0\./, '.'));
const signed = (v, d) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`;

// ---------------------------------------------------------------- geometry

function polar(angleDeg, r) {
  const a = angleDeg * Math.PI / 180;
  return [r * Math.sin(a), -r * Math.cos(a)];
}
function pt2s(p) { return `${p[0].toFixed(1)},${p[1].toFixed(1)}`; }
function sectorPath(a0, a1, r0, r1) {
  const p0 = polar(a0, r1), p1 = polar(a1, r1);
  let d = `M${pt2s(polar(a0, r0))} L${pt2s(p0)} A${r1},${r1} 0 0 1 ${pt2s(p1)}`;
  if (r0 > 0) d += ` L${pt2s(polar(a1, r0))} A${r0},${r0} 0 0 0 ${pt2s(polar(a0, r0))}`;
  return d + ' Z';
}
function sideOfAngle(a, stand) {
  if (Math.abs(a) < 15) return 'center';
  const pull = stand === 'R' ? a < 0 : a > 0;
  return pull ? 'pull side' : 'opposite field';
}

// ---------------------------------------------------------------- field SVG

function fieldCells(profile, entry, stand, filter) {
  const g = P2F.meta.geometry;
  const nCell = g.n_ang * g.n_ring;
  const vec = entry.cells.map(v => v / (profile.cell_scale || 1000));
  const cx = P2F.meta.cell_xwoba[stand], ch = P2F.meta.cell_hit[stand];
  const groups = filter === 'ground' ? [0] : filter === 'air' ? [1] : [0, 1];
  let total = 0;
  groups.forEach(gi => { for (let i = 0; i < nCell; i++) total += vec[gi * nCell + i]; });
  const cells = [];
  for (let i = 0; i < nCell; i++) {
    let s = 0, xw = 0, hit = 0, wDanger = 0, gShare = 0;
    groups.forEach(gi => {
      const k = gi * nCell + i;
      s += vec[k];
      if (gi === 0) gShare += vec[k];
      if (cx[k] != null) { xw += vec[k] * cx[k]; hit += vec[k] * ch[k]; wDanger += vec[k]; }
    });
    const ring = Math.floor(i / g.n_ang), ang = i % g.n_ang;
    cells.push({
      i, ring, ang,
      a0: g.angle_edges[ang], a1: g.angle_edges[ang + 1],
      r0: g.dist_edges[ring], r1: g.dist_edges[ring + 1],
      share: total > 0 ? s / total : 0,
      xwoba: wDanger > 0 ? xw / wDanger : null,
      hit: wDanger > 0 ? hit / wDanger : null,
      gbShare: s > 0 ? gShare / s : 0,
    });
  }
  return { cells, total };
}

function fieldSVG(profile, entry, opts) {
  const g = P2F.meta.geometry;
  const stand = profile.stand;
  const { cells } = fieldCells(profile, entry, stand, opts.filter);
  const maxShare = Math.max(1e-6, ...cells.map(c => c.share));
  const wall = g.wall.map(([a, d]) => polar(a, d));
  const fair = `M0,0 L${wall.map(pt2s).join(' L')} Z`;
  const diamond = [[0, 0], polar(45, 90), [0, -127.28], polar(-45, 90)];
  const ctr = [0, -63.64];
  const grass = diamond.map(([x, y]) => [ctr[0] + (x - ctr[0]) * 0.8, ctr[1] + (y - ctr[1]) * 0.8]);
  let o = `<svg viewBox="-335 -478 670 512" role="img" aria-label="Spray field, view from behind home plate" style="width:100%;height:auto;display:block">`;
  o += `<defs><clipPath id="p2f-fair"><path d="${fair}"/></clipPath></defs>`;
  o += `<rect x="-335" y="-478" width="670" height="512" fill="#eef0e8"/>`;
  o += `<path d="${fair}" fill="#dcead0" stroke="none"/>`;
  o += `<g clip-path="url(#p2f-fair)"><circle cx="0" cy="-60.5" r="95" fill="#ecdcc0"/></g>`;
  o += `<polygon points="${grass.map(pt2s).join(' ')}" fill="#d3e5c3"/>`;
  o += `<circle cx="0" cy="-60.5" r="9" fill="#e6d0aa" stroke="#cbb48c" stroke-width="0.6"/>`;
  o += `<circle cx="0" cy="0" r="13" fill="#ecdcc0"/>`;
  // distance guides
  [100, 200, 300].forEach(r => {
    o += `<path d="M${pt2s(polar(-45, r))} A${r},${r} 0 0 1 ${pt2s(polar(45, r))}" fill="none" stroke="#9aa58f" stroke-width="0.8" stroke-dasharray="4 5"/>`;
  });
  // landing-spot bins
  const colorBy = opts.color;
  cells.forEach(c => {
    if (c.share < 0.002) return;
    const alpha = 0.14 + 0.82 * Math.sqrt(c.share / maxShare);
    let fill = '#1f4b99';
    if (colorBy !== 'density') {
      const v = colorBy === 'hit' ? c.hit : c.xwoba;
      fill = v == null ? '#bbb' : dangerColor(v / COLOR_DOMAIN[colorBy]);
    }
    const mid = (c.a0 + c.a1) / 2;
    const tip = [
      `Spray ${c.a0.toFixed(1)}° to ${c.a1.toFixed(1)}° (${sideOfAngle(mid, stand)}), ${c.r0}–${c.r1} ft from home`,
      `Share of ${opts.filter === 'all' ? 'contact' : opts.filter === 'ground' ? 'ground balls' : 'air balls'}: ${pct(c.share, 1)}`,
      opts.filter === 'all' ? `Ground balls in this spot: ${pct(c.gbShare)}` : null,
      `Danger of balls here (league ${stand}HH): xwOBA ${f3(c.xwoba)} · hit ${pct(c.hit)}`,
    ].filter(Boolean).join('\n');
    o += `<path d="${sectorPath(c.a0, c.a1, c.r0, c.r1)}" fill="${fill}" fill-opacity="${alpha.toFixed(2)}" stroke="#fff" stroke-width="0.6"><title>${_esc(tip)}</title></path>`;
  });
  // foul lines, bases, wall
  o += `<line x1="0" y1="0" x2="${wall[0][0]}" y2="${wall[0][1]}" stroke="#fff" stroke-width="2"/>`;
  o += `<line x1="0" y1="0" x2="${wall[wall.length - 1][0]}" y2="${wall[wall.length - 1][1]}" stroke="#fff" stroke-width="2"/>`;
  o += `<polygon points="${diamond.map(pt2s).join(' ')}" fill="none" stroke="#fff" stroke-width="1.2"/>`;
  diamond.slice(1).forEach(([x, y]) => { o += `<rect x="${x - 2}" y="${y - 2}" width="4" height="4" fill="#fff" stroke="#999" stroke-width="0.4" transform="rotate(45 ${x} ${y})"/>`; });
  o += `<polygon points="-1.4,0.3 1.4,0.3 1.4,-1 0,-2.4 -1.4,-1" fill="#fff" stroke="#888" stroke-width="0.4"/>`;
  o += `<polyline points="${wall.map(pt2s).join(' ')}" fill="none" stroke="#2f4a35" stroke-width="4" stroke-linejoin="round"/>`;
  g.wall_labels.forEach(([a, d]) => {
    const [x, y] = polar(a, d + 16);
    o += `<text x="${x}" y="${y}" text-anchor="middle" font-size="13" font-weight="600" fill="#2f4a35">${d}</text>`;
  });
  [100, 200, 300].forEach(r => {
    const [x, y] = polar(43, r);
    o += `<text x="${x + 6}" y="${y + 4}" font-size="11" fill="#6f7a64">${r} ft</text>`;
  });
  // share labels
  cells.forEach(c => {
    const mid = (c.a0 + c.a1) / 2, rm = (c.r0 + c.r1) / 2;
    if (c.share < 0.035 || rm * (c.a1 - c.a0) * Math.PI / 180 < 26) return;
    const [x, y] = polar(mid, rm);
    o += `<text x="${x}" y="${y + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="#111" pointer-events="none" style="paint-order:stroke;stroke:#fff;stroke-width:2.5px">${Math.round(100 * c.share)}</text>`;
  });
  // actual batted balls
  if (opts.showBalls && opts.balls && opts.balls.length) {
    opts.balls.forEach(b => {
      if (opts.filter === 'ground' && b.bb !== 'GB') return;
      if (opts.filter === 'air' && b.bb === 'GB') return;
      const tip = `${b.d} · ${b.ev_name || 'in play'} · ${BB_NAMES[b.bb]}\nEV ${b.ev ?? '–'} mph, LA ${b.la ?? '–'}° · xwOBA ${b.xw == null ? '–' : f3(b.xw)}\n(${b.x.toFixed(0)}, ${b.y.toFixed(0)}) ft from home`;
      o += `<circle cx="${b.x}" cy="${-b.y}" r="4.2" fill="${BB_COLORS[b.bb]}" stroke="#fff" stroke-width="1.2"><title>${_esc(tip)}</title></circle>`;
    });
  }
  // orientation labels
  const leftLbl = stand === 'R' ? 'pull side' : 'opposite field';
  const rightLbl = stand === 'R' ? 'opposite field' : 'pull side';
  o += `<text x="-325" y="22" font-size="12" fill="#5c5c5c">← LF · ${leftLbl}</text>`;
  o += `<text x="325" y="22" text-anchor="end" font-size="12" fill="#5c5c5c">${rightLbl} · RF →</text>`;
  o += `<text x="0" y="24" text-anchor="middle" font-size="11" fill="#5c5c5c">home plate · view from behind the plate</text>`;
  o += `</svg>`;
  return o;
}

function fieldLegend(opts) {
  let colorPart;
  if (opts.color === 'density') {
    colorPart = `<span>Darker blue = larger share of his contact</span>`;
  } else {
    const max = COLOR_DOMAIN[opts.color];
    const lbl = opts.color === 'hit' ? 'Hit probability of balls there' : 'xwOBA of balls there';
    const ticks = opts.color === 'hit' ? ['0%', '50%', '100%'] : ['.000', (max / 2).toFixed(1).replace(/^0/, ''), `${max.toFixed(1)}+`];
    colorPart = `<span>${lbl}: ${ticks[0]}<span class="ramp" style="background:linear-gradient(90deg,${[0, 0.25, 0.5, 0.75, 1].map(dangerColor).join(',')})"></span>${ticks[2]}</span>` +
      `<span>Opacity &amp; number = % of his contact landing there</span>`;
  }
  const dots = opts.showBalls ? Object.keys(BB_COLORS).map(k => `<span><span class="dot" style="background:${BB_COLORS[k]}"></span>${BB_NAMES[k]}</span>`).join('') : '';
  return `<div class="legend">${colorPart}</div>` +
    (dots ? `<div class="legend"><span>His actual batted balls (hover for details):</span>${dots}</div>` : '') +
    `<div class="legend"><span>Generic park, drawn to scale: 330 ft lines · 380 ft gaps · 400 ft center. Bins are 7.5° wide; distance is where the ball was caught, fielded, or landed (bins past the wall are home runs).</span></div>`;
}

// ---------------------------------------------------------------- zone picker

function zonePickerSVG(profile, selected) {
  const stand = profile.stand;
  const ppf = 74, zScale = 1.8;
  const xMin = -1.6, xMax = 1.6, zMin = -0.62, zMax = 1.52;
  const padTop = 24, padBottom = 46;
  const W = (xMax - xMin) * ppf;
  const H = (zMax - zMin) * zScale * ppf + padTop + padBottom;
  const sx = xa => ((stand === 'R' ? xa : -xa) - xMin) * ppf;
  const sz = zn => padTop + (zMax - zn) * zScale * ppf;
  const rect = id => {
    const m = ZONE_META[id];
    const xa = sx(m.x[0]), xb = sx(m.x[1]);
    return { x: Math.min(xa, xb), y: sz(m.z[1]), w: Math.abs(xb - xa), h: sz(m.z[0]) - sz(m.z[1]) };
  };
  const isLeague = profile.batter_id == null;
  const cellFor = (id, cx, cy, small) => {
    const e = profile.zones[id];
    if (!e) return '';
    const n = isLeague ? Math.round(e.n_league_bip) : e.n_own_bip;
    return `<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="${small ? 12 : 14}" font-weight="700" fill="#1a1a1a" pointer-events="none">${f3(e.xwoba_con)}</text>` +
      `<text x="${cx}" y="${cy + 12}" text-anchor="middle" font-size="10" fill="#333" pointer-events="none">n ${n}</text>`;
  };
  const colorFor = id => {
    const e = profile.zones[id];
    if (!e || e.xwoba_con == null) return '#eee';
    return _zoneColor(Math.max(0, Math.min(1, (0.5 - e.xwoba_con) / 0.25)));
  };
  const tip = id => {
    const e = profile.zones[id];
    if (!e) return '';
    return _esc([
      e.label,
      `xwOBA on contact ${f3(e.xwoba_con)} (league ${f3(e.league_xwoba_con)})`,
      `GB ${pct(e.bb.ground_ball)} · whiff/swing ${pct(e.swing.whiff_per_swing)}`,
      isLeague ? `League balls in play: ${Math.round(e.n_league_bip)}` : `His balls in play here: ${e.n_own_bip} (blend weight ${pct(e.blend_weight)})`,
    ].join('\n'));
  };
  let o = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Strike zone picker, catcher's view" style="width:100%;max-width:${W}px;height:auto;display:block;margin:0 auto">`;
  o += `<text x="${W / 2}" y="15" text-anchor="middle" font-size="12" fill="#5c5c5c">Catcher's view · ${stand}HH · ${_esc(profile.pitch_name)}</text>`;
  ZONE_CHASE_IDS.forEach(id => {
    const r = rect(id);
    o += `<g class="zone-cell" data-zone="${id}"><title>${tip(id)}</title><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${colorFor(id)}" fill-opacity="0.8" stroke="#fff" stroke-width="1.5"/></g>`;
  });
  ZONE_CHASE_IDS.forEach(id => { const m = ZONE_META[id]; o += cellFor(id, sx(m.lx), sz(m.lz), true); });
  Object.keys(ZONE_META).filter(id => !ZONE_CHASE_IDS.includes(id)).forEach(id => {
    const r = rect(id);
    o += `<g class="zone-cell" data-zone="${id}"><title>${tip(id)}</title><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${colorFor(id)}" stroke="#fff" stroke-width="1"/>${cellFor(id, r.x + r.w / 2, r.y + r.h / 2 + 2, false)}</g>`;
  });
  const zx = Math.min(sx(-0.83), sx(0.83));
  o += `<rect x="${zx}" y="${sz(1)}" width="${Math.abs(sx(0.83) - sx(-0.83))}" height="${sz(0) - sz(1)}" fill="none" stroke="#1a1a1a" stroke-width="2" pointer-events="none"/>`;
  if (selected && ZONE_META[selected]) {
    const r = rect(selected);
    o += `<rect x="${r.x + 2}" y="${r.y + 2}" width="${r.w - 4}" height="${r.h - 4}" fill="none" stroke="#111" stroke-width="4" pointer-events="none"/>`;
  }
  const py = sz(zMin) + 6;
  const pl = sx(-0.708), pr = sx(0.708), a = Math.min(pl, pr), b = Math.max(pl, pr), m = (a + b) / 2;
  o += `<polygon points="${a},${py} ${b},${py} ${b},${py + 7} ${m},${py + 15} ${a},${py + 7}" fill="#fff" stroke="#8a8a84"/>`;
  const inLeft = stand === 'R';
  o += `<text x="4" y="${py + 34}" font-size="11" fill="#5c5c5c">← ${inLeft ? 'inside' : 'away'}</text>`;
  o += `<text x="${W - 4}" y="${py + 34}" text-anchor="end" font-size="11" fill="#5c5c5c">${inLeft ? 'away' : 'inside'} →</text>`;
  o += `</svg>`;
  return o;
}

function zoneLegend() {
  return `<div class="legend"><span>xwOBA on contact: .250</span><span class="ramp" style="background:linear-gradient(90deg,${_zoneColor(1)},${_zoneColor(0.5)},${_zoneColor(0)})"></span><span>.500+</span></div>`;
}

// ---------------------------------------------------------------- summary

function mixRow(label, v, lg) {
  return `<div class="mix-row"><div>${label}</div><div class="mix-track"><div class="mix-fill" style="width:${(100 * v).toFixed(1)}%"></div>` +
    `<div class="mix-tick" style="left:calc(${(100 * lg).toFixed(1)}% - 1px)" title="League ${pct(lg)}"></div></div><div>${pct(v)}</div></div>`;
}
function stackBar(d) {
  const segs = [['pull', '#1f4b99'], ['center', '#6b8fc7'], ['oppo', '#b9c8e2']];
  return `<div class="stack">${segs.map(([k, c]) => `<div style="width:${(100 * d[k]).toFixed(1)}%;background:${c};color:${k === 'oppo' ? '#1a1a1a' : '#fff'}">${k} ${pct(d[k])}</div>`).join('')}</div>`;
}
function tile(label, val, lgVal, fmt, higherIsBad, deltaFmt) {
  let cmp = '';
  if (lgVal != null && !isNaN(lgVal)) {
    const d = val - lgVal;
    const cls = Math.abs(d) < 1e-9 ? '' : ((d > 0) === higherIsBad ? 'up' : 'down');
    cmp = `<div class="c ${cls}">${deltaFmt(d)} vs league (${fmt(lgVal)})</div>`;
  }
  return `<div class="tile"><div class="v">${fmt(val)}</div><div class="l">${label}</div>${cmp}</div>`;
}

function summaryHTML(profile, entry) {
  const isLeague = profile.batter_id == null;
  const lgBB = entry.league_bb;
  const mix = BB_KEYS.map((k, i) => mixRow(['Ground ball', 'Line drive', 'Fly ball', 'Popup'][i], entry.bb[k], lgBB[k])).join('');
  const sw = entry.swing;
  const tiles = [
    tile('Avg exit velo (mph)', entry.ev, isLeague ? null : entry.league_ev, v => v.toFixed(1), true, d => `${signed(d, 1)} mph`),
    tile('xwOBA on contact', entry.xwoba_con, isLeague ? null : entry.league_xwoba_con, f3, true, d => signed(d, 3).replace('0.', '.')),
    tile('Swing rate', sw.swing_rate, isLeague ? null : sw.league_swing_rate, v => pct(v), false, d => `${signed(100 * d, 0)} pts`),
    tile('Whiff per swing', sw.whiff_per_swing, isLeague ? null : sw.league_whiff_per_swing, v => pct(v), false, d => `${signed(100 * d, 0)} pts`),
    tile('Foul per swing', sw.foul_per_swing, null, v => pct(v), false, null),
    tile('Hit prob. from landing spots', entry.hit_rate_from_spots, null, v => pct(v), true, null),
  ].join('');
  let blend;
  if (isLeague) {
    blend = `<p>League average for ${profile.stand}HH vs ${_esc(profile.pitch_name.toLowerCase())}s in this zone: <strong>${Math.round(entry.n_league_bip).toLocaleString()}</strong> season-weighted balls in play.</p>`;
  } else {
    const w = entry.blend_weight;
    const k = P2F.meta.constants.spray_k;
    blend = `<div class="blend-bar"><div class="own" style="width:${(100 * w).toFixed(1)}%"></div><div class="prior" style="width:${(100 * (1 - w)).toFixed(1)}%"></div></div>` +
      `<p><strong>${pct(w)} hitter-specific.</strong> ${entry.n_own_bip} of his own balls in play on ${_esc(profile.pitch_name.toLowerCase())}s here ` +
      `(season-weighted n = ${entry.n_own_weighted}; weight = n / (n + ${k})).</p>` +
      `<p>The other ${pct(1 - w)} is the league ${profile.stand}HH distribution for this pitch and zone (${Math.round(entry.n_league_bip).toLocaleString()} balls), ` +
      `re-weighted by his overall direction and ground-ball tendencies (${profile.n_all_bip} of his batted balls, all pitches).</p>` +
      `<p class="tag">${sw.own_pitches} of his pitches seen in this cell. Swing / whiff rates are shrunk the same way (K = ${P2F.meta.constants.swing_k} pitches).</p>`;
  }
  return `<div class="sum-grid">
    <div><h3>Contact mix</h3>${mix}<div class="tag">Bar = ${isLeague ? 'league' : 'blended hitter'} estimate · black tick = league average</div>
      <div class="stack-label">Direction (${isLeague ? 'league' : 'him'})</div>${stackBar(entry.direction)}
      ${isLeague ? '' : `<div class="stack-label">Direction (league ${profile.stand}HH, same pitch &amp; zone)</div>${stackBar(entry.league_direction)}`}
    </div>
    <div><h3>Quality of contact &amp; swing context</h3><div class="tiles">${tiles}</div></div>
    <div><h3>Sample size &amp; blend</h3>${blend}</div>
  </div>`;
}

function methodHTML() {
  const m = P2F.meta;
  const c = m.constants;
  return `<ul>
    <li><strong>Data:</strong> MLB Statcast ${m.seasons.join(' + ')} (${m.date_range[0]} → ${m.date_range[1]}, includes postseason), ${m.n_bip.toLocaleString()} batted balls with hit coordinates. Season weights: ${Object.entries(c.season_weights).map(([s, w]) => `${s} × ${w}`).join(', ')}.</li>
    <li><strong>Zones:</strong> the 13 batter-relative zones of the location model (3×3 in-zone grid, 4 chase quadrants, waste). Horizontal is flipped for left-handed hitters so "in" / "away" read the same; height is scaled to each batter's strike zone.</li>
    <li><strong>Coordinates:</strong> Statcast <code>hc_x</code>/<code>hc_y</code> → feet with home plate at (${m.geometry.hc_home.join(', ')}) and ${m.geometry.ft_per_hc_unit} ft per unit (checked against <code>hit_distance_sc</code>: median ratio 2.48 on home runs, 2.49 on fly outs). For ground balls the point is where the ball was <em>fielded</em>, so it reflects defensive positioning as well as the hitter.</li>
    <li><strong>Shrinkage:</strong> his spray for this pitch and zone is blended with a prior: <code>(own + ${c.spray_k}·prior) / (n + ${c.spray_k})</code>. The prior is the league distribution for the same batter side × pitch type × zone, re-weighted by his overall pull/center/oppo and ground/air tendencies (each shrunk toward league with K = ${c.tendency_k}). Exit velo and xwOBA on contact are shrunk the same way toward the league value plus his overall offset.</li>
    <li><strong>Danger colors</strong> are league averages for balls ending in that spot (same batter side), so they describe the landing spot. The hitter's own quality of contact is in the xwOBA on contact tile.</li>
    <li><strong>Not modeled:</strong> pitcher handedness, count, velocity or movement within a pitch type, park, and fielder positions. This Statcast extract has alignment labels but no fielder coordinates, so positioning hints are directional only.</li>
  </ul>`;
}

// ---------------------------------------------------------------- app

function p2fUpdateURL() {
  const s = P2F.state;
  const q = new URLSearchParams({ batter_id: s.batterId, stand: s.stand, pitch_type: s.pt, zone: s.zone });
  history.replaceState(null, '', `${location.pathname}?${q}`);
}

function p2fFillBatters(list) {
  const sel = document.getElementById('p2f-batter');
  sel.innerHTML = '';
  list.forEach(h => {
    const o = document.createElement('option');
    o.value = String(h.id);
    o.textContent = `${h.name} (${h.stands.join('/')})`;
    sel.appendChild(o);
  });
  if (list.some(h => String(h.id) === String(P2F.state.batterId))) sel.value = String(P2F.state.batterId);
}

function p2fFillStands() {
  const h = P2F.hitters.find(x => String(x.id) === String(P2F.state.batterId));
  const sel = document.getElementById('p2f-stand');
  const stands = h ? h.stands : ['R'];
  sel.innerHTML = stands.map(s => `<option value="${s}">${s === 'L' ? 'Left (LHH)' : 'Right (RHH)'}</option>`).join('');
  if (!stands.includes(P2F.state.stand)) P2F.state.stand = stands[0];
  sel.value = P2F.state.stand;
}

function p2fRenderTabs(profile) {
  const counts = profile.pt_counts || {};
  document.getElementById('p2f-pts').innerHTML = P2F.meta.pitch_types.map(p =>
    `<button type="button" class="pt-tab${p.id === P2F.state.pt ? ' active' : ''}" data-pt="${p.id}" title="${_esc(p.name)}">${p.id}` +
    (profile.batter_id != null ? `<span class="n">${counts[p.id] || 0} BIP</span>` : '') + `</button>`).join('');
  document.querySelectorAll('#p2f-pts .pt-tab').forEach(b => b.addEventListener('click', () => { P2F.state.pt = b.dataset.pt; p2fLoad(); }));
}

function p2fRender() {
  const s = P2F.state;
  const prof = P2F.profile;
  if (!prof) return;
  const entry = prof.zones[s.zone];
  p2fRenderTabs(prof);
  document.getElementById('p2f-zone').innerHTML = zonePickerSVG(prof, s.zone);
  document.getElementById('p2f-zone-legend').innerHTML = zoneLegend();
  document.querySelectorAll('#p2f-zone .zone-cell').forEach(g => g.addEventListener('click', () => { s.zone = g.dataset.zone; p2fRender(); }));
  const waste = document.getElementById('p2f-waste');
  waste.classList.toggle('active', s.zone === 'waste');
  const isLeague = prof.batter_id == null;
  const balls = isLeague ? [] : (prof.balls || []).filter(b => b.z === s.zone);
  document.getElementById('p2f-field-title').textContent =
    `2 · Where the contact goes: ${prof.pitch_name.toLowerCase()}s, ${entry.label.toLowerCase()}`;
  const opts = { color: s.color, filter: s.filter, showBalls: s.showBalls && !isLeague, balls };
  document.getElementById('p2f-field').innerHTML = fieldSVG(prof, entry, opts);
  document.getElementById('p2f-field-legend').innerHTML = fieldLegend(opts);
  const nBalls = isLeague ? `${Math.round(entry.n_league_bip).toLocaleString()} league balls in play` :
    `${entry.n_own_bip} of his balls in play here · ${pct(entry.blend_weight)} hitter-specific`;
  document.getElementById('p2f-takeaway').innerHTML = `<span class="k">Takeaway · ${_esc(prof.batter_name)} · ${nBalls}</span>${_esc(entry.takeaway)}`;
  document.getElementById('p2f-summary').innerHTML = summaryHTML(prof, entry);
  p2fUpdateURL();
}

async function p2fLoad() {
  const s = P2F.state;
  try {
    P2F.profile = await p2fGetProfile(s.view, s.batterId, s.stand, s.pt);
    p2fRender();
  } catch (e) {
    document.getElementById('p2f-takeaway').innerHTML = `<span class="empty">${_esc(e.message || 'Request failed')}</span>`;
  }
}

async function p2fInit() {
  try {
    if (p2fIsStatic()) {
      P2F.meta = window.P2F_STATIC.meta;
      P2F.hitters = window.P2F_STATIC.hitters;
    } else {
      [P2F.meta, P2F.hitters] = await Promise.all([p2fJSON('/api/field/meta'), p2fJSON('/api/field/batters')]);
    }
    const m = P2F.meta;
    document.getElementById('p2f-note').textContent =
      `MLB ${m.seasons.join(' + ')} Statcast (${m.date_range[0]} → ${m.date_range[1]}), ${m.n_bip.toLocaleString()} batted balls. ` +
      `${P2F.hitters.length.toLocaleString()} hitters available.`;
    document.getElementById('p2f-method').innerHTML = methodHTML();

    const q = new URLSearchParams(location.search);
    const s = P2F.state;
    const byName = q.get('batter') && P2F.hitters.find(h => foldName(h.name).includes(foldName(q.get('batter'))));
    const byId = q.get('batter_id') && P2F.hitters.find(h => String(h.id) === q.get('batter_id'));
    const def = byId || byName || P2F.hitters.find(h => /devers/i.test(h.name)) || P2F.hitters[0];
    s.batterId = def.id;
    s.stand = (q.get('stand') || def.stands[0]).toUpperCase();
    const qpt = (q.get('pitch_type') || '').toUpperCase();
    if (m.pitch_types.some(p => p.id === qpt)) s.pt = qpt;
    if (q.get('zone') && m.zones.some(z => z.id === q.get('zone'))) s.zone = q.get('zone');

    p2fFillBatters(P2F.hitters);
    p2fFillStands();
    document.getElementById('p2f-search').addEventListener('input', e => {
      const needle = foldName(e.target.value.trim());
      const list = needle ? P2F.hitters.filter(h => foldName(h.name).includes(needle) || String(h.id).includes(needle)) : P2F.hitters;
      p2fFillBatters(list.slice(0, 500));
      if (list.length && !list.some(h => String(h.id) === String(s.batterId))) {
        s.batterId = list[0].id; p2fFillStands(); p2fLoad();
      }
    });
    document.getElementById('p2f-batter').addEventListener('change', e => { s.batterId = Number(e.target.value); p2fFillStands(); p2fLoad(); });
    document.getElementById('p2f-stand').addEventListener('change', e => { s.stand = e.target.value; p2fLoad(); });
    document.getElementById('p2f-view').addEventListener('change', e => { s.view = e.target.value; p2fLoad(); });
    document.getElementById('p2f-color').addEventListener('change', e => { s.color = e.target.value; p2fRender(); });
    document.getElementById('p2f-filter').addEventListener('change', e => { s.filter = e.target.value; p2fRender(); });
    document.getElementById('p2f-balls').addEventListener('change', e => { s.showBalls = e.target.checked; p2fRender(); });
    document.getElementById('p2f-waste').addEventListener('click', () => { s.zone = 'waste'; p2fRender(); });
    await p2fLoad();
  } catch (e) {
    document.getElementById('p2f-takeaway').innerHTML = `<span class="empty">${_esc(e.message || 'Initialization failed')}</span>`;
  }
}

p2fInit();
