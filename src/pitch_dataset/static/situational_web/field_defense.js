// Pitch-to-field defense mode: draggable fielders, a deliberately simple reach model, live
// out-conversion on the hitter's actual balls in play, presets and a greedy optimizer that
// respects the 2023 shift rules. Requires field_map.js.

// Speeds / delays were tuned so the standard alignment reproduces the actual out rate on the
// demo hitters' balls in play (ground balls ~73%, air balls ~60%).
const DEF = {
  gbSpeed: 0.85, // average ground-ball speed to the infield as a share of exit velo
  reaction: 0.3, // s before an infielder moves on a grounder
  ifRun: 17, // ft/s effective lateral range speed
  glove: 4, // ft reach without moving
  transfer: 0.8, // s glove-to-release
  throwSpeed: 110, // ft/s (~75 mph average infield throw)
  runner: { R: 4.3, L: 4.2 }, // s home to first
  maxInfieldDepth: 175, // ft — grounders are hits if not fielded before this
  airReaction: 0.5,
  ofRun: 23, // ft/s effective outfielder range speed (sprint speed less route inefficiency)
  ifAirRun: 20,
  batteryRun: 16,
  defaultEV: 85,
  hangDefault: { LD: 1.5, FB: 4.2, PU: 5.5 },
};
const FIRST_BASE = [63.64, 63.64];
const DIRT_CENTER = [0, 60.5];
const DIRT_RADIUS = 95;

const STANDARD_POLAR = {
  '1B': [112, 33], '2B': [150, 12], SS: [148, -12], '3B': [116, -32],
  LF: [292, -27], CF: [322, 0], RF: [292, 27],
};
const FIELDER_ORDER = ['P', 'C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF'];
const MOVABLE = ['1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF'];
const INFIELD = ['1B', '2B', 'SS', '3B'];
const OUTFIELD = ['LF', 'CF', 'RF'];
const FIELDER_NAMES = { P: 'Pitcher', C: 'Catcher', '1B': 'First base', '2B': 'Second base', SS: 'Shortstop', '3B': 'Third base', LF: 'Left field', CF: 'Center field', RF: 'Right field' };

const toXY = (r, a) => [r * Math.sin(a * Math.PI / 180), r * Math.cos(a * Math.PI / 180)];
const toPolar = (x, y) => [Math.hypot(x, y), sprayAngle(x, y)];
const dist2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);

const DEFENSE = { pos: null, key: null, rules: true, standardOuts: null, lastOpt: null, balls: [], feats: null };

function standardPositions() {
  const pos = { P: [0, 60.5], C: [0, -4] };
  Object.entries(STANDARD_POLAR).forEach(([k, [r, a]]) => { pos[k] = toXY(r, a); });
  return pos;
}

// Statcast gives only an alignment label; these are labeled approximations.
function alignmentPositions(ifLabel, ofLabel, stand) {
  const pullSign = stand === 'R' ? -1 : 1;
  const pos = standardPositions();
  const rot = (k, deg, dr = 0) => { const [r, a] = toPolar(...pos[k]); pos[k] = toXY(r + dr, a + pullSign * deg); };
  if (ifLabel === 'Infield shade') INFIELD.forEach(k => rot(k, 5));
  if (ifLabel === 'Strategic') { rot('1B', 6); rot('3B', 7); rot('2B', 9, 10); rot('SS', 9, 10); }
  if (ofLabel === 'Strategic') OUTFIELD.forEach(k => rot(k, 8));
  MOVABLE.forEach(k => { pos[k] = clampFielder(k, pos[k], true); });
  return pos;
}

function clampFielder(k, p, rules) {
  let [x, y] = p;
  let [r, a] = toPolar(x, y);
  a = Math.max(-46, Math.min(46, a));
  if (INFIELD.includes(k)) {
    r = Math.max(55, Math.min(rules ? 200 : 230, r));
    [x, y] = toXY(r, a);
    if (rules) {
      const right = k === '1B' || k === '2B';
      if (right && x < 1) x = 1;
      if (!right && x > -1) x = -1;
      const dx = x - DIRT_CENTER[0], dy = y - DIRT_CENTER[1];
      const d = Math.hypot(dx, dy);
      if (d > DIRT_RADIUS) { x = DIRT_CENTER[0] + dx * DIRT_RADIUS / d; y = DIRT_CENTER[1] + dy * DIRT_RADIUS / d; }
    }
    const dm = dist2([x, y], DIRT_CENTER);
    if (dm < 18) { const ux = (x - DIRT_CENTER[0]) / (dm || 1), uy = (y - DIRT_CENTER[1]) / (dm || 1); x = DIRT_CENTER[0] + ux * 18; y = DIRT_CENTER[1] + uy * 18; }
    return [x, y];
  }
  r = Math.max(170, Math.min(wallDist(a) - 6, r));
  return toXY(r, a);
}

// Per-ball features computed once per ball set.
function defenseFeatures(balls, stand) {
  return balls.map(b => {
    const ang = sprayAngle(b.x, b.y);
    const u = [Math.sin(ang * Math.PI / 180), Math.cos(ang * Math.PI / 180)];
    const rec = Math.hypot(b.x, b.y);
    if (b.bb === 'GB') {
      const ev = b.ev || DEF.defaultEV;
      return { gb: true, u, vg: Math.max(25, ev * 1.467 * DEF.gbSpeed), stop: rec < 70 ? rec : Infinity, runner: DEF.runner[stand] || 4.3, w: b.w };
    }
    let d = b.dist != null ? b.dist : rec;
    if (!b.hr) d = Math.min(d, wallDist(ang) - 3);
    let hang = DEF.hangDefault[b.bb] || 3;
    if (b.ev != null && b.la != null && b.la > 0) hang = Math.max(0.4, 2 * b.ev * 1.467 * Math.sin(b.la * Math.PI / 180) / 32.17);
    return { gb: false, land: [u[0] * d, u[1] * d], hang, hr: b.hr, w: b.w, popup: b.bb === 'PU' };
  });
}

// Returns a score in [0, 1) (lower = easier) if fielder k turns the ball into an out, else null.
function fielderPlay(k, p, f) {
  if (f.gb) {
    if (OUTFIELD.includes(k) || k === 'C') return null;
    const d = p[0] * f.u[0] + p[1] * f.u[1];
    const hi = Math.min(f.stop, d + 35, DEF.maxInfieldDepth);
    const lo = Math.max(4, Math.min(d - 25, hi));
    let best = null;
    for (let t = lo; t <= hi + 0.01; t += 5) {
      const q = [f.u[0] * t, f.u[1] * t];
      const tb = t / f.vg;
      const tf = DEF.reaction + Math.max(0, dist2(q, p) - DEF.glove) / DEF.ifRun;
      const atStop = Math.abs(t - f.stop) < 5.01;
      if (tf > tb && !atStop) continue;
      const field = Math.max(tb, tf);
      let total = field + DEF.transfer + dist2(q, FIRST_BASE) / DEF.throwSpeed;
      if (k === '1B') total = Math.min(total, field + dist2(q, FIRST_BASE) / DEF.ifRun);
      if (total <= f.runner && (best === null || total < best)) best = total;
    }
    return best === null ? null : best / f.runner;
  }
  if (f.hr) return null;
  const speed = OUTFIELD.includes(k) ? DEF.ofRun : (k === 'P' || k === 'C') ? DEF.batteryRun : DEF.ifAirRun;
  if (k === 'C' && !f.popup) return null;
  const reach = DEF.glove + Math.max(0, f.hang - DEF.airReaction) * speed;
  const d = dist2(f.land, p);
  return d <= reach ? d / reach : null;
}

function evaluateDefense(pos, feats) {
  let tot = 0, outs = 0;
  const credit = Object.fromEntries(FIELDER_ORDER.map(k => [k, { outs: 0, gb: 0, air: 0 }]));
  const isOut = new Array(feats.length).fill(false);
  feats.forEach((f, i) => {
    tot += f.w;
    let bestK = null, bestS = Infinity;
    FIELDER_ORDER.forEach(k => {
      const s = fielderPlay(k, pos[k], f);
      if (s !== null && s < bestS) { bestS = s; bestK = k; }
    });
    if (bestK) {
      outs += f.w;
      isOut[i] = true;
      credit[bestK].outs += f.w;
      credit[bestK][f.gb ? 'gb' : 'air'] += f.w;
    }
  });
  return { rate: tot ? outs / tot : 0, outs, tot, credit, isOut };
}

function optimizeDefense(startPos, feats, rules) {
  const pos = JSON.parse(JSON.stringify(startPos));
  const col = (k, p) => feats.map(f => fielderPlay(k, p, f) !== null);
  const cols = Object.fromEntries(FIELDER_ORDER.map(k => [k, col(k, pos[k])]));
  const cover = feats.map((_, i) => FIELDER_ORDER.reduce((n, k) => n + (cols[k][i] ? 1 : 0), 0));
  const step = { IF: 12, OF: 30 };
  let rounds = 0;
  while (rounds++ < 250 && step.IF >= 1.5) {
    let improved = false;
    for (const k of MOVABLE) {
      const s = INFIELD.includes(k) ? step.IF : step.OF;
      let best = null, bestGain = 1e-9;
      for (const [dx, dy] of [[s, 0], [-s, 0], [0, s], [0, -s], [s, s], [s, -s], [-s, s], [-s, -s]]) {
        const cand = clampFielder(k, [pos[k][0] + dx, pos[k][1] + dy], rules);
        if (dist2(cand, pos[k]) < 0.5) continue;
        const c = col(k, cand);
        let gain = 0;
        for (let i = 0; i < feats.length; i++) {
          if (c[i] === cols[k][i]) continue;
          const others = cover[i] - (cols[k][i] ? 1 : 0);
          if (others > 0) continue;
          gain += c[i] ? feats[i].w : -feats[i].w;
        }
        if (gain > bestGain) { bestGain = gain; best = { cand, c }; }
      }
      if (best) {
        for (let i = 0; i < feats.length; i++) cover[i] += (best.c[i] ? 1 : 0) - (cols[k][i] ? 1 : 0);
        cols[k] = best.c;
        pos[k] = best.cand;
        improved = true;
      }
    }
    if (!improved) { step.IF /= 2; step.OF /= 2; }
  }
  return pos;
}

function defenseBallSet() {
  const s = P2F.state;
  if (s.defScope === 'pt') return p2fBalls({ stand: s.stand, pt: s.pt });
  if (s.defScope === 'zone') return p2fBalls({ stand: s.stand, pt: s.pt, zone: s.zone });
  return p2fBalls({ stand: s.stand });
}

function fieldersOverlay(pos, evalRes) {
  let o = '<g id="p2f-fielders">';
  // Reach guides: outfielders on a 4.0 s fly; infielders on a 90 mph grounder at their depth.
  OUTFIELD.forEach(k => {
    const r = DEF.glove + (4.0 - DEF.airReaction) * DEF.ofRun;
    o += `<circle cx="${pos[k][0]}" cy="${-pos[k][1]}" r="${r}" fill="#1f4b99" fill-opacity="0.05" stroke="#1f4b99" stroke-opacity="0.45" stroke-dasharray="5 4" pointer-events="none"/>`;
  });
  INFIELD.forEach(k => {
    const [r, a] = toPolar(...pos[k]);
    const t = r / (90 * 1.467 * DEF.gbSpeed);
    const reach = DEF.glove + Math.max(0, t - DEF.reaction) * DEF.ifRun;
    const ux = Math.cos(a * Math.PI / 180), uy = -Math.sin(a * Math.PI / 180);
    const [x, y] = pos[k];
    o += `<line x1="${x - ux * reach}" y1="${-(y - uy * reach)}" x2="${x + ux * reach}" y2="${-(y + uy * reach)}" stroke="#1f4b99" stroke-opacity="0.45" stroke-width="7" stroke-linecap="round" pointer-events="none"/>`;
  });
  FIELDER_ORDER.forEach(k => {
    const [x, y] = pos[k];
    const movable = MOVABLE.includes(k);
    const c = evalRes.credit[k];
    const share = evalRes.tot ? c.outs / evalRes.tot : 0;
    o += `<g class="fielder${movable ? ' movable' : ''}" data-f="${k}" transform="translate(${x.toFixed(1)},${(-y).toFixed(1)})">` +
      `<title>${_esc(`${FIELDER_NAMES[k]}${movable ? ' — drag to move' : ' (fixed)'}\n${Math.round(Math.hypot(x, y))} ft from home, ${sprayAngle(x, y).toFixed(0)}° spray\nOuts credited: ${pct(share, 1)} of balls in play`)}</title>` +
      `<circle r="${movable ? 10 : 8}" fill="${movable ? '#1f4b99' : '#6b7280'}" stroke="#fff" stroke-width="2"/>` +
      `<text y="3.5" text-anchor="middle" font-size="${k.length > 1 ? 8.5 : 10}" font-weight="700" fill="#fff" pointer-events="none">${k}</text></g>`;
  });
  return o + '</g>';
}

function defenseStatsHTML(res) {
  const std = DEFENSE.standardOuts;
  const delta = std ? res.rate - std.rate : 0;
  const balls = DEFENSE.balls;
  const totW = sum(balls.map(b => b.w));
  const actual = totW ? sum(balls.map(b => (b.out ? b.w : 0))) / totW : 0;
  const rows = FIELDER_ORDER.map(k => {
    const c = res.credit[k], sc = std ? std.credit[k] : null;
    const d = sc ? (c.outs - sc.outs) / res.tot : 0;
    return `<tr><td>${k}</td><td>${pct(c.outs / Math.max(res.tot, 1e-9), 1)}</td><td>${pct(c.gb / Math.max(res.tot, 1e-9), 1)}</td><td>${pct(c.air / Math.max(res.tot, 1e-9), 1)}</td>` +
      `<td class="${Math.abs(d) < 0.0005 ? '' : d > 0 ? 'down' : 'up'}">${Math.abs(d) < 0.0005 ? '—' : signed(100 * d, 1)}</td></tr>`;
  }).join('');
  return `<div class="def-big"><div><div class="v">${pct(res.rate, 1)}</div><div class="l">of his balls in play turned into outs (model)</div></div>` +
    `<div><div class="v ${Math.abs(delta) < 0.0005 ? '' : delta > 0 ? 'down' : 'up'}">${std ? signed(100 * delta, 1) : '—'}</div><div class="l">pts vs standard alignment (${std ? pct(std.rate, 1) : '–'})</div></div></div>` +
    `<p class="tag">${balls.length} balls in play (season-weighted n = ${totW.toFixed(0)}). Actual Statcast out rate on these balls: <strong>${pct(actual, 1)}</strong> — real outcomes include true positioning, errors, parks and runner speed, so compare the model to itself (deltas), not to that number.</p>` +
    `<table class="def-table"><thead><tr><th>Fielder</th><th>Outs</th><th>on GB</th><th>on air</th><th>Δ vs std</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<div class="tag">Outs credited as % of all his balls in play; Δ in percentage points vs standard positions.</div>`;
}

function defenseAssumptionsHTML() {
  return `<details class="def-assume"><summary>Model assumptions (simplified)</summary><ul>
    <li><strong>Ground balls</strong> roll along their spray angle at ${DEF.gbSpeed} × exit velo (default ${DEF.defaultEV} mph if missing). An infielder can field it at a point on that path if he gets there first: ${DEF.reaction} s reaction, then ${DEF.ifRun} ft/s, plus ${DEF.glove} ft of reach. It's an out only if fielding time + ${DEF.transfer} s transfer + throw to first at ${DEF.throwSpeed} ft/s beats the runner (${DEF.runner.R} s RHH / ${DEF.runner.L} s LHH). The first baseman can also take it to the bag himself. Grounders not fielded within ${DEF.maxInfieldDepth} ft are hits.</li>
    <li><strong>Air balls</strong> (line drives, flies, popups) are caught only where they come down (distance = <code>hit_distance_sc</code>, direction from hit coordinates). Hang time = vacuum estimate 2·v·sin(LA)/g (backspin lift and drag roughly offset); fixed ${DEF.hangDefault.LD}/${DEF.hangDefault.FB}/${DEF.hangDefault.PU} s for LD/FB/PU when exit velo or launch angle is missing. Reach = ${DEF.glove} ft + (hang − ${DEF.airReaction} s) × speed: ${DEF.ofRun} ft/s outfielders, ${DEF.ifAirRun} ft/s infielders, ${DEF.batteryRun} ft/s pitcher / catcher (catcher on popups only). Home runs are never outs.</li>
    <li><strong>Shift rules</strong> (when enforced): two infielders on each side of second base and all four on the infield dirt (within ${DIRT_RADIUS} ft of the mound). Pitcher and catcher are fixed.</li>
    <li><strong>Optimize</strong> = greedy coordinate search: each fielder tries 8 moves (12 ft infield / 30 ft outfield, halving when nothing helps) and keeps any that add outs. It finds a good local optimum for <em>these</em> balls; it ignores runners on base, double plays, hit value (a single and a double count the same) and the fact that hitters adjust.</li>
    <li><strong>Calibration:</strong> speeds and delays were tuned so the standard alignment reproduces the actual out rate on the 12 demo hitters' balls in play (ground balls ≈ 73%, air balls ≈ 60%). Individual hitters still differ from their actual rate (speed, parks, real positioning), so read the <em>deltas</em>.</li>
    <li>Ground-ball coordinates are where the ball was fielded under the real defense, so only their direction and exit velo are used.</li>
  </ul></details>`;
}

P2F.modes.defense = {
  label: 'Defense (fielders)',
  help: '<strong>Drag the blue fielders.</strong> Every one of his balls in play is re-scored as an out or a hit under your alignment with a simple reach model. Presets: standard, his most common Statcast alignment label, or Optimize.',
  render(prof) {
    const s = P2F.state;
    const isLeague = prof.batter_id == null;
    if (isLeague || !P2F.detail) {
      p2fTakeaway2('Defense', 'Defense mode needs a hitter (not the league view).');
      return;
    }
    const key = `${s.batterId}|${s.stand}|${s.defScope}|${s.pt}|${s.zone}|${s.count}|${s.hand}`;
    const posKey = `${s.batterId}|${s.stand}`;
    if (DEFENSE.posKey !== posKey || !DEFENSE.pos) { DEFENSE.pos = standardPositions(); DEFENSE.posKey = posKey; DEFENSE.lastOpt = null; }
    if (DEFENSE.key !== key) {
      DEFENSE.balls = defenseBallSet();
      DEFENSE.feats = defenseFeatures(DEFENSE.balls, s.stand);
      DEFENSE.standardOuts = evaluateDefense(standardPositions(), DEFENSE.feats);
      DEFENSE.key = key;
    }
    const al = (P2F.detail.align || {})[s.stand] || { if: {}, of: {} };
    const topIf = Object.entries(al.if || {}).filter(([k]) => k !== 'Unknown').sort((a, b) => b[1] - a[1])[0] || ['Standard', 1];
    const topOf = Object.entries(al.of || {}).filter(([k]) => k !== 'Unknown').sort((a, b) => b[1] - a[1])[0] || ['Standard', 1];
    document.getElementById('p2f-left-title').textContent = '1 · Alignment & outs';
    document.getElementById('p2f-left-tag').innerHTML = `Balls: ${prof.batter_name}'s actual balls in play as a ${s.stand}HH${isFiltered() ? ` (${_esc(filterSets(s.count, s.hand).label)})` : ''}.`;
    document.getElementById('p2f-waste').style.display = 'none';
    document.getElementById('p2f-zone').innerHTML =
      `<div class="def-controls"><label class="tag">Balls in play <select id="p2f-def-scope"><option value="all">All pitch types</option><option value="pt">Current pitch type (${s.pt})</option><option value="zone">Current pitch type &amp; zone</option></select></label>` +
      `<div class="btn-row"><button type="button" class="btn" data-preset="standard">Standard</button>` +
      `<button type="button" class="btn" data-preset="common" title="Statcast labels only; positions approximated">His most common: IF ${_esc(topIf[0])} (${pct(topIf[1])}) / OF ${_esc(topOf[0])}</button>` +
      `<button type="button" class="btn primary" data-preset="optimize">Optimize</button></div>` +
      `<label class="tag check"><input type="checkbox" id="p2f-def-rules" ${DEFENSE.rules ? 'checked' : ''}/> Enforce shift rules (2 infielders each side of 2B, on the dirt)</label></div>` +
      `<div id="p2f-def-stats"></div>`;
    document.getElementById('p2f-zone-legend').innerHTML = defenseAssumptionsHTML();
    const scopeSel = document.getElementById('p2f-def-scope');
    scopeSel.value = s.defScope;
    scopeSel.addEventListener('change', e => { s.defScope = e.target.value; p2fRender(); });
    document.getElementById('p2f-def-rules').addEventListener('change', e => {
      DEFENSE.rules = e.target.checked;
      MOVABLE.forEach(k => { DEFENSE.pos[k] = clampFielder(k, DEFENSE.pos[k], DEFENSE.rules); });
      p2fRender();
    });
    document.querySelectorAll('[data-preset]').forEach(b => b.addEventListener('click', () => {
      const p = b.dataset.preset;
      if (p === 'standard') { DEFENSE.pos = standardPositions(); DEFENSE.lastOpt = null; }
      if (p === 'common') { DEFENSE.pos = alignmentPositions(topIf[0], topOf[0], s.stand); DEFENSE.lastOpt = null; }
      if (p === 'optimize') {
        b.textContent = 'Optimizing…';
        b.disabled = true;
        setTimeout(() => {
          const starts = [standardPositions(), alignmentPositions('Infield shade', 'Standard', s.stand), alignmentPositions('Strategic', 'Strategic', s.stand)];
          let best = null;
          starts.forEach(st => {
            const p2 = optimizeDefense(st, DEFENSE.feats, DEFENSE.rules);
            const r = evaluateDefense(p2, DEFENSE.feats);
            if (!best || r.rate > best.r.rate) best = { p2, r };
          });
          DEFENSE.pos = best.p2;
          DEFENSE.lastOpt = { rate: best.r.rate, std: DEFENSE.standardOuts.rate };
          p2fRender();
        }, 30);
        return;
      }
      p2fRender();
    }));
    this.draw(prof);
  },
  draw(prof) {
    const s = P2F.state;
    const res = evaluateDefense(DEFENSE.pos, DEFENSE.feats);
    const outSet = new Set(DEFENSE.balls.filter((b, i) => res.isOut[i]).map(b => b.i));
    const ballColor = b => (b.hr ? '#7f0000' : outSet.has(b.i) ? '#9a9a94' : '#d7301f');
    document.getElementById('p2f-field-title').textContent = `2 · ${prof.batter_name}'s balls in play under this alignment (${s.defScope === 'all' ? 'all pitch types' : s.defScope === 'pt' ? ptName(s.pt).toLowerCase() + 's' : `${ptName(s.pt).toLowerCase()}s, ${zoneLabel(s.zone).toLowerCase()}`})`;
    const opts = { noCells: true, showBalls: true, balls: DEFENSE.balls, ballColor, overlay: fieldersOverlay(DEFENSE.pos, res), filter: 'all' };
    document.getElementById('p2f-field').innerHTML = fieldSVG(prof, null, opts);
    document.getElementById('p2f-field-legend').innerHTML = fieldLegend({
      ...opts, color: 'density', noPark: false,
      ballLegendTitle: 'Each dot = one of his balls in play, re-scored:',
      ballLegend: `<span><span class="dot" style="background:#9a9a94"></span>Out under this alignment</span><span><span class="dot" style="background:#d7301f"></span>Hit</span><span><span class="dot" style="background:#7f0000"></span>Home run</span>` +
        `<span>Blue bars = infielder range on a 90 mph grounder · dashed circles = outfielder range on a 4.0 s fly</span>`,
    }).replace(/<div class="legend"><span>Darker blue[^<]*<\/span><\/div>/, '');
    document.getElementById('p2f-field-extra').innerHTML = '';
    document.getElementById('p2f-def-stats').innerHTML = defenseStatsHTML(res);
    document.getElementById('p2f-summary').style.display = 'none';
    // Takeaway.
    const std = DEFENSE.standardOuts;
    const moves = MOVABLE.map(k => {
      const sp = standardPositions()[k];
      const [r0, a0] = toPolar(...sp), [r1, a1] = toPolar(...DEFENSE.pos[k]);
      const pullDeg = (a1 - a0) * (s.stand === 'R' ? -1 : 1);
      return { k, d: dist2(sp, DEFENSE.pos[k]), dr: r1 - r0, pullDeg };
    }).filter(m => m.d > 6).sort((a, b) => b.d - a.d).slice(0, 3);
    const moveTxt = moves.map(m => `${m.k} ${Math.abs(m.pullDeg).toFixed(0)}° toward ${m.pullDeg >= 0 ? 'pull' : 'opposite'} side${Math.abs(m.dr) >= 5 ? `, ${Math.abs(m.dr).toFixed(0)} ft ${m.dr > 0 ? 'deeper' : 'shallower'}` : ''}`).join('; ');
    const gain = 100 * (res.rate - std.rate);
    let txt = `${prof.batter_name}: this alignment turns ${pct(res.rate, 1)} of his ${DEFENSE.balls.length} balls in play into outs in the model (standard: ${pct(std.rate, 1)}, ${signed(gain, 1)} pts = ${signed(gain, 1)} outs per 100 balls in play).`;
    if (moves.length) txt += ` Biggest moves from standard: ${moveTxt}.`;
    if (DEFENSE.lastOpt) txt += ' Optimized with a greedy search under the selected rules; treat it as a direction, not a precise spot.';
    p2fTakeaway2(`Defense · ${prof.batter_name} · ${s.stand}HH`, txt);
    this.attachDrag(prof);
  },
  attachDrag(prof) {
    const svg = document.getElementById('p2f-svg-main');
    let drag = null;
    svg.querySelectorAll('.fielder.movable').forEach(g => {
      g.addEventListener('pointerdown', e => {
        drag = g.dataset.f;
        svg.setPointerCapture(e.pointerId);
        e.preventDefault();
      });
    });
    svg.addEventListener('pointermove', e => {
      if (!drag) return;
      const p = svgFeet(svg, e);
      DEFENSE.pos[drag] = clampFielder(drag, [p.x, p.y], DEFENSE.rules);
      const g = svg.querySelector(`.fielder[data-f="${drag}"]`);
      g.setAttribute('transform', `translate(${DEFENSE.pos[drag][0].toFixed(1)},${(-DEFENSE.pos[drag][1]).toFixed(1)})`);
      const res = evaluateDefense(DEFENSE.pos, DEFENSE.feats);
      document.getElementById('p2f-def-stats').innerHTML = defenseStatsHTML(res);
    });
    const end = () => {
      if (!drag) return;
      drag = null;
      DEFENSE.lastOpt = null;
      this.draw(prof);
    };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
  },
};
