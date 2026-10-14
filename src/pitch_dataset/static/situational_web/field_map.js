// Pitch-to-field: zone picker (catcher's view) + to-scale spray field, with count / pitcher-hand
// filters and a brush (drag a box on the field). Other modes live in field_defense.js and
// field_modes.js. Works from embedded data (window.P2F_STATIC, GitHub Pages) or the select-web
// /api/field endpoints. Requires zone_map.js (ZONE_META, _zoneColor, _esc).

const P2F = {
  meta: null,
  hitters: [],
  pitchers: [],
  cache: {},
  details: {},
  pitcherDists: {},
  state: {
    batterId: null, stand: 'R', pt: 'SL', zone: 'down_away', view: 'hitter', color: 'xwoba', filter: 'all',
    showBalls: true, count: 'all', hand: 'all', mode: 'explore', brush: null, brushScope: 'all',
    compare: 'league', compareId: null, pitcherId: null, mixSource: 'actual', sitCount: '1-2',
    defScope: 'all',
  },
  profile: null,
  detail: null,
  modes: {},
};

const BB_COLORS = { GB: '#7a4b1e', LD: '#c0392b', FB: '#1f4b99', PU: '#7b7b75' };
const BB_NAMES = { GB: 'Ground ball', LD: 'Line drive', FB: 'Fly ball', PU: 'Popup' };
const BB_KEYS = ['ground_ball', 'line_drive', 'fly_ball', 'popup'];
const BB_IDX = { GB: 0, LD: 1, FB: 2, PU: 3 };
const ATOM_LABELS = ['pitcher ahead, 2 strikes', 'pitcher ahead', 'even, 2 strikes', 'even', 'full count', 'pitcher behind'];

function p2fIsStatic() { return typeof window.P2F_STATIC === 'object' && window.P2F_STATIC !== null; }

async function p2fJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

async function p2fGetBase(view, bid, stand, pt) {
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
  delete prof.balls;
  P2F.cache[key] = prof;
  return prof;
}

async function p2fGetDetail(bid) {
  if (P2F.details[bid]) return P2F.details[bid];
  const raw = p2fIsStatic() ? window.P2F_STATIC.details[String(bid)] : await p2fJSON(`/api/field/detail?batter_id=${bid}`);
  if (!raw) throw new Error('No batted-ball detail for this hitter in the demo.');
  const outs = new Set(P2F.meta.out_events);
  const f = raw.balls.fields;
  const balls = raw.balls.rows.map((r, i) => {
    const b = Object.fromEntries(f.map((k, j) => [k, r[j]]));
    b.i = i;
    b.out = outs.has(b.res);
    b.hr = b.res === 'home_run';
    b.pname = raw.pitchers[String(b.pid)] || String(b.pid);
    return b;
  });
  const sf = raw.swings.fields;
  const swings = raw.swings.rows.map(r => Object.fromEntries(sf.map((k, j) => [k, r[j]])));
  const d = { ...raw, balls, swings };
  P2F.details[bid] = d;
  return d;
}

// ---------------------------------------------------------------- color + format helpers

const DANGER_STOPS = [[0, [255, 247, 224]], [0.3, [253, 208, 138]], [0.55, [240, 138, 75]], [0.78, [215, 48, 39]], [1, [127, 0, 0]]];
function rampColor(stops, t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    const [t1, c1] = stops[i];
    const [t0, c0] = stops[i - 1];
    if (t <= t1) {
      const u = (t - t0) / (t1 - t0);
      return `rgb(${c0.map((v, k) => Math.round(v + (c1[k] - v) * u)).join(',')})`;
    }
  }
  return `rgb(${stops[stops.length - 1][1].join(',')})`;
}
const dangerColor = t => rampColor(DANGER_STOPS, t);
const BLUE_STOPS = [[0, [242, 245, 251]], [0.5, [122, 156, 210]], [1, [20, 52, 115]]];
const blueColor = t => rampColor(BLUE_STOPS, t);
const DIV_STOPS = [[0, [33, 102, 172]], [0.25, [103, 169, 207]], [0.5, [247, 247, 247]], [0.75, [239, 138, 98]], [1, [178, 24, 43]]];
const divColor = t => rampColor(DIV_STOPS, (t + 1) / 2);
const COLOR_DOMAIN = { xwoba: 1.2, hit: 1.0 };
const foldName = s => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const pct = (v, d = 0) => (v == null || isNaN(v) ? '–' : `${(100 * v).toFixed(d)}%`);
const f3 = v => (v == null || isNaN(v) ? '–' : v.toFixed(3).replace(/^(-?)0\./, '$1.'));
const signed = (v, d) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`;
const sum = a => a.reduce((x, y) => x + y, 0);
const norm = a => { const s = sum(a); return s > 0 ? a.map(v => v / s) : a.map(() => 1 / a.length); };
const argmax = a => a.reduce((bi, v, i) => (v > a[bi] ? i : bi), 0);
const ptName = pt => ((P2F.meta.pitch_types.find(p => p.id === pt) || {}).name || pt);
const ptIdx = pt => P2F.meta.pitch_types.findIndex(p => p.id === pt);
const zoneIdx = z => P2F.meta.zones.findIndex(x => x.id === z);
const hitterName = id => ((P2F.hitters.find(h => String(h.id) === String(id)) || {}).name || String(id));

function shortName(name) {
  if (name.includes(',')) return name.split(',')[0].trim();
  const parts = name.split(/\s+/);
  if (parts.length > 1 && ['jr', 'sr', 'ii', 'iii'].includes(parts[parts.length - 1].replace('.', '').toLowerCase())) return parts[parts.length - 2];
  return parts[parts.length - 1] || name;
}

// ---------------------------------------------------------------- count / pitcher-hand filters

function filterSets(count, hand) {
  const F = P2F.meta.filters;
  const c = F.count.find(x => x.id === count) || F.count[0];
  const h = F.hand.find(x => x.id === hand) || F.hand[0];
  return { atoms: c.atoms, hands: h.hands, label: `${c.label}, ${h.label}`, countLabel: c.label, handLabel: h.label };
}
const isFiltered = () => P2F.state.count !== 'all' || P2F.state.hand !== 'all';
const handIdx = ph => (ph === 'L' ? 0 : 1);

function nsum(a, b) { return Array.isArray(a) ? a.map((v, i) => nsum(v, b[i])) : a + b; }
function nzero(a) { return Array.isArray(a) ? a.map(nzero) : 0; }

// Mirrors spray.league_filter_adjustment: how the league's spray / contact / swing profile shifts
// in this count / pitcher-hand slice for the same batter side and pitch type.
function leagueAdjust(stand, pt, count, hand) {
  const T = P2F.meta.filter_tables;
  const K = P2F.meta.filters.league_k;
  const s = stand === 'L' ? 0 : 1;
  const p = ptIdx(pt);
  const { atoms, hands } = filterSets(count, hand);
  const split = arr => {
    const base = arr[s][p];
    let all = nzero(base[0][0]);
    let f = nzero(base[0][0]);
    for (let a = 0; a < base.length; a++) {
      for (let h = 0; h < 2; h++) {
        all = nsum(all, base[a][h]);
        if (atoms.includes(a) && hands.includes(h)) f = nsum(f, base[a][h]);
      }
    }
    return [[all].flat(3), [f].flat(3)];
  };
  const shareRatio = (all, f) => {
    const tot = sum(all), nf = sum(f);
    return all.map((v, i) => {
      const lg = tot > 0 ? v / tot : 0;
      return lg > 0 ? ((f[i] + K * lg) / (nf + K)) / lg : 1;
    });
  };
  const meanShift = (all, f) => {
    const base = all[1] ? all[0] / all[1] : 0;
    return (f[0] + K * base) / (f[1] + K) - base;
  };
  const [angA, angF] = split(T.ang);
  const [bbA, bbF] = split(T.bb);
  const [evA, evF] = split(T.ev);
  const [xwA, xwF] = split(T.xw);
  const [swA, swF] = split(T.sw);
  const num = a => [a[1], a[2], a[3], a[4]];
  const den = a => [a[0], a[1], a[1], a[1]];
  const rA = num(swA).map((v, i) => v / Math.max(den(swA)[i], 1e-9));
  const rF = num(swF).map((v, i) => (v + K * rA[i]) / (den(swF)[i] + K));
  return {
    ang: shareRatio(angA, angF), bb: shareRatio(bbA, bbF), ev: meanShift(evA, evF), xw: meanShift(xwA, xwF),
    sw: rA.map((v, i) => (v > 0 ? rF[i] / v : 1)), nSlice: sum(angF),
  };
}

function lanesOf(cells01, group) {
  const g = P2F.meta.geometry;
  const nA = g.n_ang, nC = nA * g.n_ring, per = nA / 6;
  const out = [0, 0, 0, 0, 0, 0];
  for (let i = 0; i < nC; i++) out[Math.floor((i % nA) / per)] += cells01[group * nC + i];
  return out;
}

function directionOf(cells01, stand) {
  const g = P2F.meta.geometry;
  const nA = g.n_ang, third = nA / 3;
  const ang = new Array(nA).fill(0);
  cells01.forEach((v, i) => { ang[i % nA] += v; });
  const a = norm(ang);
  const left = sum(a.slice(0, third)), mid = sum(a.slice(third, 2 * third)), right = sum(a.slice(2 * third));
  const [pull, oppo] = stand === 'R' ? [left, right] : [right, left];
  return { pull, center: mid, oppo };
}

// Mirrors spray._filtered_entry (same shrinkage, K = spray_k).
function filterEntry(e, ctx) {
  const g = P2F.meta.geometry;
  const nA = g.n_ang, nC = nA * g.n_ring;
  const K = P2F.meta.constants.spray_k, SK = P2F.meta.constants.swing_k;
  const scale = ctx.scale;
  const prior = norm(e.cells.map((v, i) => (v / scale) * ctx.adj.ang[Math.floor(i / nC) * nA + (i % nA)]));
  const own = new Array(2 * nC).fill(0);
  const ownBB = [0, 0, 0, 0];
  let evS = 0, evN = 0, xwS = 0, xwN = 0;
  ctx.own.forEach(b => {
    own[b.c] += b.w;
    ownBB[BB_IDX[b.bb]] += b.w;
    if (b.ev != null) { evS += b.ev * b.w; evN += b.w; }
    if (b.xw != null) { xwS += b.xw * b.w; xwN += b.w; }
  });
  const n = sum(own);
  const post = own.map((v, i) => (v + K * prior[i]) / (n + K));
  const bbPrior = norm(BB_KEYS.map((k, i) => e.bb[k] * ctx.adj.bb[i]));
  const nbb = sum(ownBB);
  const bbPost = ownBB.map((v, i) => (v + K * bbPrior[i]) / (nbb + K));
  const lgBB = norm(BB_KEYS.map((k, i) => e.league_bb[k] * ctx.adj.bb[i]));
  const sw = e.swing, r = ctx.adj.sw;
  const base = [sw.swing_rate * r[0], sw.whiff_per_swing * r[1], sw.foul_per_swing * r[2], sw.in_play_per_swing * r[3]].map(v => Math.min(v, 0.99));
  const o = [0, 0, 0, 0, 0];
  let cnt = 0;
  ctx.ownSw.forEach(x => { o[0] += x.n; o[1] += x.swing; o[2] += x.whiff; o[3] += x.foul; o[4] += x.in_play; cnt += x.cnt || 0; });
  const s = ctx.stand;
  const cx = P2F.meta.cell_xwoba[s], ch = P2F.meta.cell_hit[s];
  const out = {
    ...e,
    cells: post.map(v => v * scale),
    bb: Object.fromEntries(BB_KEYS.map((k, i) => [k, bbPost[i]])),
    league_bb: Object.fromEntries(BB_KEYS.map((k, i) => [k, lgBB[i]])),
    ev: (evS + K * (e.ev + ctx.adj.ev)) / (evN + K),
    league_ev: e.league_ev + ctx.adj.ev,
    xwoba_con: (xwS + K * (e.xwoba_con + ctx.adj.xw)) / (xwN + K),
    league_xwoba_con: e.league_xwoba_con + ctx.adj.xw,
    hit_rate_from_spots: sum(post.map((v, i) => v * (ch[i] || 0))),
    landing_xwoba: sum(post.map((v, i) => v * (cx[i] || 0))),
    direction: directionOf(post, s),
    lanes_ground: lanesOf(post, 0),
    lanes_air: lanesOf(post, 1),
    swing: {
      swing_rate: (o[1] + SK * base[0]) / (o[0] + SK),
      whiff_per_swing: (o[2] + SK * base[1]) / (o[1] + SK),
      foul_per_swing: (o[3] + SK * base[2]) / (o[1] + SK),
      in_play_per_swing: (o[4] + SK * base[3]) / (o[1] + SK),
      league_swing_rate: Math.min(sw.league_swing_rate * r[0], 0.99),
      league_whiff_per_swing: Math.min(sw.league_whiff_per_swing * r[1], 0.99),
      own_pitches: cnt,
    },
    n_own_bip: ctx.own.length,
    n_own_weighted: Math.round(n * 10) / 10,
    blend_weight: ctx.name ? n / (n + K) : 0,
  };
  out.takeaway = p2fTakeaway(out, s, ctx.pt, ctx.name);
  return out;
}

// Profile for (view, hitter, side, pitch type) under the current count / pitcher-hand filters.
async function p2fEffective(view, bid, stand, pt, count, hand) {
  const s = P2F.state;
  count = count || s.count;
  hand = hand || s.hand;
  const base = await p2fGetBase(view, bid, stand, pt);
  if (count === 'all' && hand === 'all') return base;
  const key = `F|${view}|${bid}|${stand}|${pt}|${count}|${hand}`;
  if (P2F.cache[key]) return P2F.cache[key];
  const adj = leagueAdjust(stand, pt, count, hand);
  const { atoms, hands, label } = filterSets(count, hand);
  let own = [], ownSw = [];
  if (view !== 'league') {
    const d = await p2fGetDetail(bid);
    const p = ptIdx(pt), si = stand === 'L' ? 0 : 1;
    own = d.balls.filter(b => b.s === stand && b.pt === pt && atoms.includes(b.k) && hands.includes(handIdx(b.ph)));
    ownSw = d.swings.filter(x => x.s === si && x.p === p && atoms.includes(x.k) && hands.includes(x.ph));
  }
  const name = view === 'league' ? null : base.batter_name;
  const zones = {};
  Object.entries(base.zones).forEach(([zid, e]) => {
    const zi = zoneIdx(zid);
    zones[zid] = filterEntry(e, {
      stand, pt, name, adj, scale: base.cell_scale || 1000,
      own: own.filter(b => b.z === zid), ownSw: ownSw.filter(x => x.z === zi),
    });
  });
  const prof = { ...base, zones, filter: { count, hand, label, n_slice_bip: own.length } };
  P2F.cache[key] = prof;
  return prof;
}

// Hitter's actual balls in play (current filters), optionally restricted to a pitch type / zone.
function p2fBalls({ stand, pt = null, zone = null, count = null, hand = null } = {}) {
  const d = P2F.detail;
  if (!d) return [];
  const { atoms, hands } = filterSets(count || P2F.state.count, hand || P2F.state.hand);
  return d.balls.filter(b => (!stand || b.s === stand) && (!pt || b.pt === pt) && (!zone || b.z === zone) &&
    atoms.includes(b.k) && hands.includes(handIdx(b.ph)));
}

// Mirrors spray.spray_takeaway.
function p2fTakeaway(e, stand, pt, name) {
  const g = P2F.meta.geometry;
  const who = name ? shortName(name) : `league ${stand}HH`;
  const what = `${e.label.toLowerCase()} ${ptName(pt).toLowerCase()}s`;
  const gb = e.bb.ground_ball, air = e.bb.line_drive + e.bb.fly_ball;
  const d = e.direction, lgD = e.league_direction;
  const parts = [`${what[0].toUpperCase()}${what.slice(1)} vs ${who}: ${pct(gb)} grounders${name ? ` (league ${pct(e.league_bb.ground_ball)})` : ''}`];
  parts.push(`${pct(d.pull)} pulled${name ? ` (league ${pct(lgD.pull)})` : ''}`);
  const useG = gb >= 0.4;
  const lanes = useG ? e.lanes_ground : e.lanes_air;
  const top = argmax(lanes);
  const share = lanes[top] / Math.max(sum(lanes), 1e-9);
  parts.push(`most common: ${useG ? 'grounders' : 'air balls'} ${(useG ? g.lanes_ground : g.lanes_air)[top]} (${pct(share)} of those)`);
  let text = `${parts.join('; ')}. xwOBA on contact ${e.xwoba_con.toFixed(3)}${name ? ` vs league ${e.league_xwoba_con.toFixed(3)}` : ''}.`;
  if (e.n_league_bip < 30) return `Rare contact: only ${Math.round(e.n_league_bip)} league balls in play on ${what} — treat the map as noise. ${text}`;
  if (name && e.blend_weight < 0.25) {
    text += ' Mostly prior: few of his own balls in play here.';
  } else if (name) {
    const lgLanes = useG ? e.league_lanes_ground : e.league_lanes_air;
    const lgShare = lgLanes[top] / Math.max(sum(lgLanes), 1e-9);
    const pullSide = (top < 3) === (stand === 'R');
    if (gb >= 0.45 && share - lgShare >= 0.05) {
      text += ` Grounders lean ${pullSide ? 'pull side' : 'opposite field'} more than league — supports shading the infield that way (try the Defense mode).`;
    } else if (air >= 0.45 && d.pull - lgD.pull >= 0.08) {
      text += ' Air contact is pull-heavy relative to league — outfield shift candidate.';
    }
  }
  return text;
}

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
const wallDist = a => 330 + 70 * Math.cos(2 * Math.max(-45, Math.min(45, a)) * Math.PI / 180);
const sprayAngle = (x, y) => Math.atan2(x, y) * 180 / Math.PI;

// SVG user units are feet: (x, -y). Returns field feet for a pointer event.
function svgFeet(svg, evt) {
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX;
  pt.y = evt.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  return { x: p.x, y: -p.y };
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

function ballTip(b) {
  return `${b.d} · ${b.pname ? `vs ${b.pname} · ` : ''}${b.pt ? `${ptName(b.pt)}, ${zoneLabel(b.z).toLowerCase()} · ` : ''}${(b.res || b.ev_name || 'in play').replace(/_/g, ' ')}\n` +
    `${BB_NAMES[b.bb]} · EV ${b.ev ?? '–'} mph, LA ${b.la ?? '–'}°${b.dist != null ? ` · ${b.dist} ft` : ''}` +
    `${b.xw != null ? ` · xwOBA ${f3(b.xw)}` : ''}\n(${Math.round(b.x)}, ${Math.round(b.y)}) ft from home`;
}

// opts: {color, filter, showBalls, balls, uid, noCells, diff, brush, inBox, ballColor, overlay, compact}
function fieldSVG(profile, entry, opts) {
  const g = P2F.meta.geometry;
  const stand = profile.stand;
  const uid = opts.uid || 'main';
  const cells = entry && !opts.noCells ? fieldCells(profile, entry, stand, opts.filter).cells : [];
  const maxShare = Math.max(1e-6, ...cells.map(c => c.share));
  const wall = g.wall.map(([a, d]) => polar(a, d));
  const fair = `M0,0 L${wall.map(pt2s).join(' L')} Z`;
  const diamond = [[0, 0], polar(45, 90), [0, -127.28], polar(-45, 90)];
  const ctr = [0, -63.64];
  const grass = diamond.map(([x, y]) => [ctr[0] + (x - ctr[0]) * 0.8, ctr[1] + (y - ctr[1]) * 0.8]);
  let o = `<svg id="p2f-svg-${uid}" viewBox="-335 -478 670 512" role="img" aria-label="Spray field, view from behind home plate" style="width:100%;height:auto;display:block;touch-action:none">`;
  o += `<defs><clipPath id="p2f-fair-${uid}"><path d="${fair}"/></clipPath></defs>`;
  o += `<rect x="-335" y="-478" width="670" height="512" fill="#eef0e8"/>`;
  o += `<path d="${fair}" fill="#dcead0" stroke="none"/>`;
  o += `<g clip-path="url(#p2f-fair-${uid})"><circle cx="0" cy="-60.5" r="95" fill="#ecdcc0"/></g>`;
  o += `<polygon points="${grass.map(pt2s).join(' ')}" fill="#d3e5c3"/>`;
  o += `<circle cx="0" cy="-60.5" r="9" fill="#e6d0aa" stroke="#cbb48c" stroke-width="0.6"/>`;
  o += `<circle cx="0" cy="0" r="13" fill="#ecdcc0"/>`;
  [100, 200, 300].forEach(r => {
    o += `<path d="M${pt2s(polar(-45, r))} A${r},${r} 0 0 1 ${pt2s(polar(45, r))}" fill="none" stroke="#9aa58f" stroke-width="0.8" stroke-dasharray="4 5"/>`;
  });
  const colorBy = opts.color;
  const maxDiff = opts.diff ? Math.max(0.01, ...opts.diff.map(Math.abs)) : 1;
  cells.forEach(c => {
    let fill = '#1f4b99', alpha;
    let tip;
    const mid = (c.a0 + c.a1) / 2;
    const where = `Spray ${c.a0.toFixed(1)}° to ${c.a1.toFixed(1)}° (${sideOfAngle(mid, stand)}), ${c.r0}–${c.r1} ft from home`;
    if (opts.diff) {
      const dv = opts.diff[c.i];
      if (Math.abs(dv) < 0.001 && c.share < 0.002) return;
      fill = divColor(dv / maxDiff);
      alpha = 0.9;
      tip = `${where}\n${opts.diffLabel || 'Difference'}: ${signed(100 * dv, 1)} pts of contact`;
    } else {
      if (c.share < 0.002) return;
      alpha = 0.14 + 0.82 * Math.sqrt(c.share / maxShare);
      if (colorBy !== 'density') {
        const v = colorBy === 'hit' ? c.hit : c.xwoba;
        fill = v == null ? '#bbb' : dangerColor(v / COLOR_DOMAIN[colorBy]);
      }
      tip = [
        where,
        `Share of ${opts.filter === 'all' ? 'contact' : opts.filter === 'ground' ? 'ground balls' : 'air balls'}: ${pct(c.share, 1)}`,
        opts.filter === 'all' ? `Ground balls in this spot: ${pct(c.gbShare)}` : null,
        `Danger of balls here (league ${stand}HH): xwOBA ${f3(c.xwoba)} · hit ${pct(c.hit)}`,
      ].filter(Boolean).join('\n');
    }
    if (opts.dimCells) alpha *= 0.35;
    o += `<path d="${sectorPath(c.a0, c.a1, c.r0, c.r1)}" fill="${fill}" fill-opacity="${alpha.toFixed(2)}" stroke="#fff" stroke-width="0.6"><title>${_esc(tip)}</title></path>`;
  });
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
  if (!opts.compact) {
    const labelMin = Math.min(0.035, 0.6 * maxShare);
    cells.forEach(c => {
      const mid = (c.a0 + c.a1) / 2, rm = (c.r0 + c.r1) / 2;
      if (rm * (c.a1 - c.a0) * Math.PI / 180 < 26) return;
      let label;
      if (opts.diff) {
        const dv = opts.diff[c.i];
        if (Math.abs(dv) < 0.015) return;
        label = signed(100 * dv, 0);
      } else {
        if (c.share < labelMin) return;
        label = Math.round(100 * c.share);
      }
      const [x, y] = polar(mid, rm);
      o += `<text x="${x}" y="${y + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="#111" pointer-events="none" style="paint-order:stroke;stroke:#fff;stroke-width:2.5px">${label}</text>`;
    });
  }
  if (opts.showBalls && opts.balls && opts.balls.length) {
    const box = opts.inBox;
    opts.balls.forEach(b => {
      if (opts.filter === 'ground' && b.bb !== 'GB') return;
      if (opts.filter === 'air' && b.bb === 'GB') return;
      const dim = box && !box.has(b.i);
      const fill = opts.ballColor ? opts.ballColor(b) : BB_COLORS[b.bb];
      o += `<circle class="p2f-ball" data-i="${b.i}" cx="${b.x}" cy="${-b.y}" r="${dim ? 2.6 : 4.2}" fill="${fill}" fill-opacity="${dim ? 0.25 : 1}" stroke="#fff" stroke-width="${dim ? 0.5 : 1.2}"><title>${_esc(ballTip(b))}</title></circle>`;
    });
  }
  if (opts.brush) {
    const b = opts.brush;
    o += `<rect x="${Math.min(b.x0, b.x1)}" y="${-Math.max(b.y0, b.y1)}" width="${Math.abs(b.x1 - b.x0)}" height="${Math.abs(b.y1 - b.y0)}" fill="#1f4b99" fill-opacity="0.08" stroke="#1f4b99" stroke-width="2" stroke-dasharray="6 4" pointer-events="none"/>`;
  }
  o += `<g id="p2f-brush-live-${uid}"></g>`;
  if (opts.overlay) o += opts.overlay;
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
  if (opts.diff) {
    colorPart = `<span>${_esc(opts.diffLabel || 'Difference')}: less<span class="ramp" style="background:linear-gradient(90deg,${[-1, -0.5, 0, 0.5, 1].map(divColor).join(',')})"></span>more</span>` +
      `<span>Number = difference in percentage points of contact landing there</span>`;
  } else if (opts.color === 'density') {
    colorPart = `<span>Darker blue = larger share of his contact</span>`;
  } else {
    const max = COLOR_DOMAIN[opts.color];
    const lbl = opts.color === 'hit' ? 'Hit probability of balls there' : 'xwOBA of balls there';
    const ticks = opts.color === 'hit' ? ['0%', '50%', '100%'] : ['.000', (max / 2).toFixed(1).replace(/^0/, ''), `${max.toFixed(1)}+`];
    colorPart = `<span>${lbl}: ${ticks[0]}<span class="ramp" style="background:linear-gradient(90deg,${[0, 0.25, 0.5, 0.75, 1].map(dangerColor).join(',')})"></span>${ticks[2]}</span>` +
      `<span>Opacity &amp; number = % of ${opts.who || 'his'} contact landing there</span>`;
  }
  const dots = opts.showBalls && !opts.ballLegend ? Object.keys(BB_COLORS).map(k => `<span><span class="dot" style="background:${BB_COLORS[k]}"></span>${BB_NAMES[k]}</span>`).join('') : (opts.ballLegend || '');
  return `<div class="legend">${colorPart}</div>` +
    (dots ? `<div class="legend"><span>${opts.ballLegendTitle || 'His actual batted balls (hover for details):'}</span>${dots}</div>` : '') +
    (opts.noPark ? '' : `<div class="legend"><span>Generic park, drawn to scale: 330 ft lines · 380 ft gaps · 400 ft center. Bins are 7.5° wide; distance is where the ball was caught, fielded, or landed (bins past the wall are home runs).</span></div>`);
}

// ---------------------------------------------------------------- zone grid (catcher's view)

// info(id) -> {fill, opacity, l1, l2, tip}
function zoneGridSVG(stand, title, info, selected) {
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
  const text = (id, cx, cy, small) => {
    const c = info(id);
    if (!c) return '';
    const dark = !!c.dark;
    return `<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="${small ? 12 : 14}" font-weight="700" fill="${dark ? '#fff' : '#1a1a1a'}" pointer-events="none"${dark ? '' : ' style="paint-order:stroke;stroke:rgba(255,255,255,.7);stroke-width:2px"'}>${c.l1}</text>` +
      `<text x="${cx}" y="${cy + 12}" text-anchor="middle" font-size="10" fill="${dark ? '#e8eefa' : '#333'}" pointer-events="none">${c.l2 || ''}</text>`;
  };
  const cellRect = (id, chase) => {
    const c = info(id) || { fill: '#eee', tip: zoneLabel(id) };
    const r = rect(id);
    return `<g class="zone-cell" data-zone="${id}"><title>${_esc(c.tip || '')}</title><rect x="${r.x}" y="${r.y}" width="${r.w}" height="${r.h}" fill="${c.fill}" fill-opacity="${c.opacity ?? (chase ? 0.8 : 1)}" stroke="#fff" stroke-width="${chase ? 1.5 : 1}"/></g>`;
  };
  let o = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Strike zone, catcher's view" style="width:100%;max-width:${W}px;height:auto;display:block;margin:0 auto">`;
  o += `<text x="${W / 2}" y="15" text-anchor="middle" font-size="12" fill="#5c5c5c">${_esc(title)}</text>`;
  ZONE_CHASE_IDS.forEach(id => { o += cellRect(id, true); });
  ZONE_CHASE_IDS.forEach(id => { const m = ZONE_META[id]; o += text(id, sx(m.lx), sz(m.lz), true); });
  Object.keys(ZONE_META).filter(id => !ZONE_CHASE_IDS.includes(id)).forEach(id => {
    const r = rect(id);
    o += cellRect(id, false) + text(id, r.x + r.w / 2, r.y + r.h / 2 + 2, false);
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

function zonePickerSVG(profile, selected) {
  const isLeague = profile.batter_id == null;
  const info = id => {
    const e = profile.zones[id];
    if (!e) return null;
    const n = isLeague ? Math.round(e.n_league_bip) : e.n_own_bip;
    return {
      fill: e.xwoba_con == null ? '#eee' : _zoneColor(Math.max(0, Math.min(1, (0.5 - e.xwoba_con) / 0.25))),
      l1: f3(e.xwoba_con),
      l2: `n ${n}`,
      tip: [
        e.label,
        `xwOBA on contact ${f3(e.xwoba_con)} (league ${f3(e.league_xwoba_con)})`,
        `GB ${pct(e.bb.ground_ball)} · whiff/swing ${pct(e.swing.whiff_per_swing)}`,
        isLeague ? `League balls in play: ${Math.round(e.n_league_bip)}` : `His balls in play here: ${e.n_own_bip} (blend weight ${pct(e.blend_weight)})`,
      ].join('\n'),
    };
  };
  return zoneGridSVG(profile.stand, `Catcher's view · ${profile.stand}HH · ${profile.pitch_name}`, info, selected);
}

function zoneLegend() {
  return `<div class="legend"><span>xwOBA on contact: .250</span><span class="ramp" style="background:linear-gradient(90deg,${_zoneColor(1)},${_zoneColor(0.5)},${_zoneColor(0)})"></span><span>.500+</span></div>`;
}

// ---------------------------------------------------------------- summary

function mixRow(label, v, lg, tickTitle) {
  return `<div class="mix-row"><div>${label}</div><div class="mix-track"><div class="mix-fill" style="width:${(100 * v).toFixed(1)}%"></div>` +
    (lg == null ? '' : `<div class="mix-tick" style="left:calc(${(100 * lg).toFixed(1)}% - 1px)" title="${_esc(tickTitle || `League ${pct(lg)}`)}"></div>`) + `</div><div>${pct(v)}</div></div>`;
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
  const flt = profile.filter;
  const k = P2F.meta.constants.spray_k;
  let blend;
  if (isLeague) {
    blend = `<p>League average for ${profile.stand}HH vs ${_esc(profile.pitch_name.toLowerCase())}s in this zone: <strong>${Math.round(entry.n_league_bip).toLocaleString()}</strong> season-weighted balls in play (all counts).</p>` +
      (flt ? `<p>Shown for <strong>${_esc(flt.label)}</strong>: the all-count league map re-weighted by how league direction and contact mix shift in that slice.</p>` : '');
  } else if (flt) {
    const w = entry.blend_weight;
    blend = `<div class="blend-bar"><div class="own" style="width:${(100 * w).toFixed(1)}%"></div><div class="prior" style="width:${(100 * (1 - w)).toFixed(1)}%"></div></div>` +
      `<p><strong>${pct(w)} from his balls in this slice</strong> (${_esc(flt.label)}): ${entry.n_own_bip} balls in play on ${_esc(profile.pitch_name.toLowerCase())}s here (weighted n = ${entry.n_own_weighted}; weight = n / (n + ${k})).</p>` +
      `<p>The other ${pct(1 - w)} is his all-count profile for this pitch and zone, re-weighted by how league ${profile.stand}HH direction and contact mix shift in this slice. Thin slices lean on that prior.</p>` +
      `<p class="tag">${sw.own_pitches} of his pitches seen in this cell and slice. Swing / whiff rates shrink the same way (K = ${P2F.meta.constants.swing_k}).</p>`;
  } else {
    const w = entry.blend_weight;
    blend = `<div class="blend-bar"><div class="own" style="width:${(100 * w).toFixed(1)}%"></div><div class="prior" style="width:${(100 * (1 - w)).toFixed(1)}%"></div></div>` +
      `<p><strong>${pct(w)} hitter-specific.</strong> ${entry.n_own_bip} of his own balls in play on ${_esc(profile.pitch_name.toLowerCase())}s here ` +
      `(season-weighted n = ${entry.n_own_weighted}; weight = n / (n + ${k})).</p>` +
      `<p>The other ${pct(1 - w)} is the league ${profile.stand}HH distribution for this pitch and zone (${Math.round(entry.n_league_bip).toLocaleString()} balls), ` +
      `re-weighted by his overall direction and ground-ball tendencies (${profile.n_all_bip} of his batted balls, all pitches).</p>` +
      `<p class="tag">${sw.own_pitches} of his pitches seen in this cell. Swing / whiff rates are shrunk the same way (K = ${P2F.meta.constants.swing_k} pitches).</p>`;
  }
  return `<div class="sum-grid">
    <div><h3>Contact mix</h3>${mix}<div class="tag">Bar = ${isLeague ? 'league' : 'blended hitter'} estimate · black tick = league average${flt ? ' (same slice)' : ''}</div>
      <div class="stack-label">Direction (${isLeague ? 'league' : 'him'})</div>${stackBar(entry.direction)}
      ${isLeague ? '' : `<div class="stack-label">Direction (league ${profile.stand}HH, same pitch &amp; zone${flt ? ', all counts' : ''})</div>${stackBar(entry.league_direction)}`}
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
    <li><strong>Count / pitcher-hand filters:</strong> the same formula one level down: his balls in the slice are blended (K = ${c.spray_k}) with his all-count profile for that pitch × zone, re-weighted by how the league's direction, contact mix, exit velo and swing rates shift in that slice (league shift smoothed with K = ${m.filters.league_k}). Thin slices therefore show more prior in the blend bar.</li>
    <li><strong>Danger colors</strong> are league averages for balls ending in that spot (same batter side), so they describe the landing spot. The hitter's own quality of contact is in the xwOBA on contact tile.</li>
    <li><strong>Brush, replay and defense</strong> use his actual batted balls (season-weighted where rates are shown); the zone / pitch-type split of a brushed area is descriptive, not shrunk.</li>
    <li><strong>Not modeled:</strong> velocity or movement within a pitch type, park, and real fielder coordinates (Statcast only labels the alignment). The defense mode is a deliberately simple reach model; see its assumptions panel.</li>
  </ul>`;
}

// ---------------------------------------------------------------- explore mode (+ brush)

function brushStats() {
  const s = P2F.state, b = s.brush;
  const pool = p2fBalls({ stand: s.stand, pt: s.brushScope === 'pt' ? s.pt : null });
  const [x0, x1] = [Math.min(b.x0, b.x1), Math.max(b.x0, b.x1)];
  const [y0, y1] = [Math.min(b.y0, b.y1), Math.max(b.y0, b.y1)];
  const inBox = pool.filter(x => x.x >= x0 && x.x <= x1 && x.y >= y0 && x.y <= y1);
  const count = (arr, key) => arr.reduce((acc, x) => { acc[x[key]] = (acc[x[key]] || 0) + 1; return acc; }, {});
  return { pool, inBox, zIn: count(inBox, 'z'), zAll: count(pool, 'z'), pIn: count(inBox, 'pt'), pAll: count(pool, 'pt') };
}

function renderBrushPanel() {
  const s = P2F.state;
  const st = brushStats();
  const n = st.inBox.length, N = st.pool.length;
  const maxShare = Math.max(1e-9, ...Object.values(st.zIn).map(v => v / Math.max(n, 1)));
  const info = id => {
    const k = st.zIn[id] || 0, all = st.zAll[id] || 0;
    const share = n ? k / n : 0, base = N ? all / N : 0;
    const lift = base > 0 ? share / base : 0;
    return {
      fill: k ? blueColor(share / maxShare) : '#f4f4f1',
      dark: share / maxShare > 0.55,
      l1: k ? pct(share) : '–',
      l2: k ? `${lift.toFixed(1)}×` : '',
      tip: `${zoneLabel(id)}\n${k} of the ${n} balls in the box (${pct(share)})\n${all} of his ${N} balls overall came from here (${pct(base)}); lift ${lift.toFixed(2)}×\n${all ? pct(k / all) : '–'} of his balls from this zone land in the box`,
    };
  };
  const scope = s.brushScope === 'pt' ? `${ptName(s.pt).toLowerCase()}s only` : 'all pitch types';
  document.getElementById('p2f-left-title').textContent = '1 · Which pitches send his contact into the box';
  document.getElementById('p2f-left-tag').innerHTML = `Each cell = share of his balls landing in the dashed box that came on pitches in that zone (${scope}); × = lift vs his overall zone mix (hover for counts). Darker = bigger share.`;
  document.getElementById('p2f-zone').innerHTML = zoneGridSVG(s.stand, `Catcher's view · ${s.stand}HH · ${n} balls in box`, info, null);
  document.getElementById('p2f-waste').style.display = 'none';
  const pts = P2F.meta.pitch_types.filter(p => st.pAll[p.id]);
  const rows = pts.sort((a, b) => (st.pIn[b.id] || 0) - (st.pIn[a.id] || 0)).map(p =>
    mixRow(p.id, n ? (st.pIn[p.id] || 0) / n : 0, N ? st.pAll[p.id] / N : 0, `Share of all his balls: ${pct(st.pAll[p.id] / N)}`)).join('');
  document.getElementById('p2f-zone-legend').innerHTML =
    `<div class="legend"><span>Share of box: 0</span><span class="ramp" style="background:linear-gradient(90deg,${[0, 0.5, 1].map(blueColor).join(',')})"></span><span>max</span></div>` +
    `<h3 style="margin-top:10px">By pitch type</h3>${rows || '<p class="tag">No balls in the box.</p>'}<div class="tag">Bar = share of balls in the box · tick = share of all his balls</div>` +
    `<div class="brush-actions"><label class="tag">Scope <select id="p2f-brush-scope"><option value="all">All pitch types</option><option value="pt">Current pitch type</option></select></label>` +
    `<button type="button" class="btn" id="p2f-brush-clear">Clear box</button></div>`;
  const sel = document.getElementById('p2f-brush-scope');
  sel.value = s.brushScope;
  sel.addEventListener('change', e => { s.brushScope = e.target.value; p2fRender(); });
  document.getElementById('p2f-brush-clear').addEventListener('click', () => { s.brush = null; p2fRender(); });
  // Takeaway: top zone by lift with a meaningful count.
  let txt;
  if (!n) {
    txt = 'None of his balls (with the current filters) landed in this box. Drag a larger area.';
  } else {
    const ranked = Object.keys(st.zIn).map(z => ({ z, k: st.zIn[z], share: st.zIn[z] / n, base: (st.zAll[z] || 0) / N }))
      .sort((a, b) => b.k - a.k);
    const top = ranked[0];
    const lifted = ranked.filter(r => r.k >= 3).sort((a, b) => b.share / b.base - a.share / a.base)[0];
    const topPt = Object.keys(st.pIn).sort((a, b) => st.pIn[b] - st.pIn[a])[0];
    txt = `${n} of his ${N} balls in play (${pct(n / N)}) landed in this box. Most came on pitches ${zoneLabel(top.z).toLowerCase()} (${pct(top.share)}, vs ${pct(top.base)} of all his contact)` +
      (lifted && lifted.z !== top.z ? `; the biggest over-representation is ${zoneLabel(lifted.z).toLowerCase()} (${(lifted.share / lifted.base).toFixed(1)}× his usual share, n = ${lifted.k})` : '') +
      `. Leading pitch type: ${ptName(topPt).toLowerCase()} (${pct(st.pIn[topPt] / n)}).` + (n < 25 ? ' Small sample — read as directional.' : '');
  }
  return { txt, inBox: new Set(st.inBox.map(x => x.i)), n };
}

function attachBrush(svg) {
  const s = P2F.state;
  const live = svg.querySelector('[id^="p2f-brush-live"]');
  let start = null;
  svg.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    start = svgFeet(svg, e);
    svg.setPointerCapture(e.pointerId);
  });
  svg.addEventListener('pointermove', e => {
    if (!start) return;
    const p = svgFeet(svg, e);
    live.innerHTML = `<rect x="${Math.min(start.x, p.x)}" y="${-Math.max(start.y, p.y)}" width="${Math.abs(p.x - start.x)}" height="${Math.abs(p.y - start.y)}" fill="#1f4b99" fill-opacity="0.1" stroke="#1f4b99" stroke-width="2" stroke-dasharray="6 4"/>`;
  });
  const finish = e => {
    if (!start) return;
    const p = svgFeet(svg, e);
    const a = start;
    start = null;
    live.innerHTML = '';
    if (Math.abs(p.x - a.x) < 8 && Math.abs(p.y - a.y) < 8) return;
    s.brush = { x0: a.x, y0: a.y, x1: p.x, y1: p.y };
    p2fRender();
  };
  svg.addEventListener('pointerup', finish);
  svg.addEventListener('pointercancel', () => { start = null; live.innerHTML = ''; });
}

P2F.modes.explore = {
  label: 'Explore & brush',
  help: 'Pick a pitch type and a zone to see where his contact goes. <strong>Drag a box on the field</strong> to reverse it: which zones and pitch types send his balls there.',
  render(prof, entry) {
    const s = P2F.state;
    const isLeague = prof.batter_id == null;
    let brush = null;
    if (s.brush && !isLeague) {
      brush = renderBrushPanel();
    } else {
      document.getElementById('p2f-left-title').textContent = '1 · Pick a location';
      document.getElementById('p2f-left-tag').innerHTML = `Catcher's view. Cell color = ${isLeague ? 'league' : 'his'} xwOBA on contact for this pitch there (green = weak contact, red = damage); <em>n</em> = ${isLeague ? 'league' : 'his own'} balls in play${isFiltered() ? ' in this slice' : ''}. Click a cell.`;
      document.getElementById('p2f-zone').innerHTML = zonePickerSVG(prof, s.zone);
      document.getElementById('p2f-zone-legend').innerHTML = zoneLegend();
      const waste = document.getElementById('p2f-waste');
      waste.style.display = '';
      waste.classList.toggle('active', s.zone === 'waste');
      document.querySelectorAll('#p2f-zone .zone-cell').forEach(g => g.addEventListener('click', () => { s.zone = g.dataset.zone; p2fRender(); }));
    }
    const balls = isLeague ? [] : (brush ? p2fBalls({ stand: s.stand, pt: s.brushScope === 'pt' ? s.pt : null }) : p2fBalls({ stand: s.stand, pt: s.pt, zone: s.zone }));
    document.getElementById('p2f-field-title').textContent = brush
      ? `2 · His batted balls (${s.brushScope === 'pt' ? ptName(s.pt).toLowerCase() + 's' : 'all pitch types'}) — box selection`
      : `2 · Where the contact goes: ${prof.pitch_name.toLowerCase()}s, ${entry.label.toLowerCase()}`;
    const opts = {
      color: s.color, filter: s.filter, showBalls: (s.showBalls || !!brush) && !isLeague, balls,
      brush: s.brush && !isLeague ? s.brush : null, inBox: brush ? brush.inBox : null, dimCells: !!brush,
    };
    document.getElementById('p2f-field').innerHTML = fieldSVG(prof, entry, opts);
    document.getElementById('p2f-field-legend').innerHTML = fieldLegend(opts) +
      (isLeague ? '' : `<div class="legend"><span><strong>Brush:</strong> drag a box on the field to see which zones / pitch types produce the balls inside it${s.brush ? ' · drag again to replace it' : ''}.</span></div>`);
    document.getElementById('p2f-field-extra').innerHTML = '';
    if (!isLeague) attachBrush(document.getElementById('p2f-svg-main'));
    const nBalls = isLeague ? `${Math.round(entry.n_league_bip).toLocaleString()} league balls in play` :
      `${entry.n_own_bip} of his balls in play here · ${pct(entry.blend_weight)} hitter-specific`;
    p2fTakeaway2(brush ? `Box selection · ${prof.batter_name} · ${s.stand}HH${isFiltered() ? ` · ${filterSets(s.count, s.hand).label}` : ''}` :
      `Takeaway · ${prof.batter_name} · ${nBalls}${isFiltered() ? ` · ${prof.filter.label}` : ''}`, brush ? brush.txt : entry.takeaway);
    document.getElementById('p2f-summary').style.display = '';
    document.getElementById('p2f-summary').innerHTML = summaryHTML(prof, entry);
  },
};

function p2fTakeaway2(k, text) {
  document.getElementById('p2f-takeaway').innerHTML = `<span class="k">${_esc(k)}</span>${_esc(text)}`;
}

// ---------------------------------------------------------------- app shell

function p2fUpdateURL() {
  const s = P2F.state;
  const q = new URLSearchParams({ batter_id: s.batterId, stand: s.stand, pitch_type: s.pt, zone: s.zone });
  if (s.mode !== 'explore') q.set('mode', s.mode);
  if (s.count !== 'all') q.set('count', s.count);
  if (s.hand !== 'all') q.set('p_throws', s.hand);
  if (s.mode === 'matchup' && s.pitcherId) q.set('pitcher_id', s.pitcherId);
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
  const counts = {};
  if (P2F.detail && profile.batter_id != null) p2fBalls({ stand: P2F.state.stand }).forEach(b => { counts[b.pt] = (counts[b.pt] || 0) + 1; });
  document.getElementById('p2f-pts').innerHTML = P2F.meta.pitch_types.map(p =>
    `<button type="button" class="pt-tab${p.id === P2F.state.pt ? ' active' : ''}" data-pt="${p.id}" title="${_esc(p.name)}">${p.id}` +
    (profile.batter_id != null ? `<span class="n">${counts[p.id] || 0} BIP</span>` : '') + `</button>`).join('');
  document.querySelectorAll('#p2f-pts .pt-tab').forEach(b => b.addEventListener('click', () => { P2F.state.pt = b.dataset.pt; p2fLoad(); }));
}

function p2fRenderModes() {
  const s = P2F.state;
  document.getElementById('p2f-modes').innerHTML = Object.entries(P2F.modes).map(([id, m]) =>
    `<button type="button" class="mode-tab${id === s.mode ? ' active' : ''}" data-mode="${id}">${m.label}</button>`).join('');
  document.getElementById('p2f-mode-help').innerHTML = P2F.modes[s.mode].help;
  document.querySelectorAll('#p2f-modes .mode-tab').forEach(b => b.addEventListener('click', () => {
    if (P2F.modes[s.mode].leave) P2F.modes[s.mode].leave();
    s.mode = b.dataset.mode;
    p2fLoad();
  }));
}

function p2fRender() {
  const s = P2F.state;
  const prof = P2F.profile;
  if (!prof) return;
  const entry = prof.zones[s.zone];
  p2fRenderModes();
  p2fRenderTabs(prof);
  const handSel = document.getElementById('p2f-hand');
  handSel.value = s.hand;
  handSel.disabled = s.mode === 'matchup';
  document.getElementById('p2f-count').value = s.count;
  document.getElementById('p2f-filter-note').textContent = isFiltered()
    ? `Filtered: ${filterSets(s.count, s.hand).label}. Maps re-estimated with the same shrinkage (thinner samples lean more on the prior).`
    : '';
  P2F.modes[s.mode].render(prof, entry);
  p2fUpdateURL();
}

async function p2fLoad() {
  const s = P2F.state;
  try {
    const view = s.mode === 'explore' ? s.view : 'hitter';
    P2F.detail = await p2fGetDetail(s.batterId).catch(() => null);
    if (P2F.modes[s.mode].load) await P2F.modes[s.mode].load();
    P2F.profile = await p2fEffective(view, s.batterId, s.stand, s.pt);
    p2fRender();
  } catch (e) {
    console.warn(e);
    document.getElementById('p2f-takeaway').innerHTML = `<span class="empty">${_esc(e.message || 'Request failed')}</span>`;
  }
}

async function p2fInit() {
  try {
    if (p2fIsStatic()) {
      P2F.meta = window.P2F_STATIC.meta;
      P2F.hitters = window.P2F_STATIC.hitters;
      P2F.pitchers = window.P2F_STATIC.pitchers || [];
    } else {
      [P2F.meta, P2F.hitters, P2F.pitchers] = await Promise.all([
        p2fJSON('/api/field/meta'), p2fJSON('/api/field/batters'), p2fJSON('/api/field/pitchers?limit=600'),
      ]);
    }
    const m = P2F.meta;
    document.getElementById('p2f-note').textContent =
      `MLB ${m.seasons.join(' + ')} Statcast (${m.date_range[0]} → ${m.date_range[1]}), ${m.n_bip.toLocaleString()} batted balls. ` +
      `${P2F.hitters.length.toLocaleString()} hitters` + (p2fIsStatic() ? ` and ${P2F.pitchers.length} matchup pitchers in this demo.` : ' available.');
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
    if (q.get('mode') && P2F.modes[q.get('mode')]) s.mode = q.get('mode');
    if (q.get('count') && m.filters.count.some(c => c.id === q.get('count'))) s.count = q.get('count');
    if (['L', 'R'].includes(q.get('p_throws'))) s.hand = q.get('p_throws');
    if (q.get('pitcher_id')) s.pitcherId = Number(q.get('pitcher_id'));

    document.getElementById('p2f-count').innerHTML = m.filters.count.map(c => `<option value="${c.id}">${_esc(c.label[0].toUpperCase() + c.label.slice(1))}</option>`).join('');
    document.getElementById('p2f-hand').innerHTML = m.filters.hand.map(h => `<option value="${h.id}">${h.id === 'all' ? 'Both' : _esc(h.label)}</option>`).join('');

    p2fFillBatters(P2F.hitters);
    p2fFillStands();
    document.getElementById('p2f-search').addEventListener('input', e => {
      const needle = foldName(e.target.value.trim());
      const list = needle ? P2F.hitters.filter(h => foldName(h.name).includes(needle) || String(h.id).includes(needle)) : P2F.hitters;
      p2fFillBatters(list.slice(0, 500));
      if (list.length && !list.some(h => String(h.id) === String(s.batterId))) {
        s.batterId = list[0].id; s.brush = null; p2fFillStands(); p2fLoad();
      }
    });
    document.getElementById('p2f-batter').addEventListener('change', e => { s.batterId = Number(e.target.value); s.brush = null; p2fFillStands(); p2fLoad(); });
    document.getElementById('p2f-stand').addEventListener('change', e => { s.stand = e.target.value; s.brush = null; p2fLoad(); });
    document.getElementById('p2f-view').addEventListener('change', e => { s.view = e.target.value; p2fLoad(); });
    document.getElementById('p2f-color').addEventListener('change', e => { s.color = e.target.value; p2fRender(); });
    document.getElementById('p2f-filter').addEventListener('change', e => { s.filter = e.target.value; p2fRender(); });
    document.getElementById('p2f-balls').addEventListener('change', e => { s.showBalls = e.target.checked; p2fRender(); });
    document.getElementById('p2f-count').addEventListener('change', e => { s.count = e.target.value; p2fLoad(); });
    document.getElementById('p2f-hand').addEventListener('change', e => { s.hand = e.target.value; p2fLoad(); });
    document.getElementById('p2f-waste').addEventListener('click', () => { s.zone = 'waste'; p2fRender(); });
    await p2fLoad();
  } catch (e) {
    console.warn(e);
    document.getElementById('p2f-takeaway').innerHTML = `<span class="empty">${_esc(e.message || 'Initialization failed')}</span>`;
  }
}
