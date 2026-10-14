// Pitch-to-field modes: pitcher matchup, compare (vs league / two hitters) and replay.
// Requires field_map.js. Calls p2fInit() at the end.

async function p2fGetPitcher(pid) {
  if (P2F.pitcherDists[pid]) return P2F.pitcherDists[pid];
  const d = p2fIsStatic() ? (window.P2F_STATIC.pitcher_dists || {})[String(pid)] : await p2fJSON(`/api/field/pitcher?pitcher_id=${pid}`);
  if (!d) throw new Error('Pitcher not in this demo.');
  P2F.pitcherDists[pid] = d;
  return d;
}

// rows: [stand, atom, pt, zone, weight] -> mix over pitch types + zone distribution per pitch type.
function mixFromRows(rows, stand, count) {
  const si = stand === 'L' ? 0 : 1;
  const { atoms } = filterSets(count, 'all');
  const nP = P2F.meta.pitch_types.length, nZ = P2F.meta.zones.length;
  const m = Array.from({ length: nP }, () => new Array(nZ).fill(0));
  rows.forEach(([s, k, p, z, w]) => { if (s === si && atoms.includes(k)) m[p][z] += w; });
  const tot = sum(m.map(sum));
  return { mix: m.map(r => (tot ? sum(r) / tot : 0)), loc: m.map(r => norm(r)), n: tot };
}

function leagueMixRows(stand, hand) {
  const L = P2F.meta.league_mix;
  const si = stand === 'L' ? 0 : 1, hi = hand === 'L' ? 0 : 1;
  const rows = [];
  L[si][hi].forEach((byP, k) => byP.forEach((byZ, p) => byZ.forEach((w, z) => { if (w) rows.push([si, k, p, z, w]); })));
  return rows;
}

// Expected contact for a pitch mix: weight = P(pitch type) × P(zone | type) × P(ball in play | pitch).
function matchupCombine(profiles, mixInfo) {
  const g = P2F.meta.geometry;
  const nV = 2 * g.n_ang * g.n_ring;
  const cells = new Array(nV).fill(0);
  let W = 0, xw = 0, ev = 0;
  const bb = [0, 0, 0, 0];
  const perPt = [];
  P2F.meta.pitch_types.forEach((p, pi) => {
    const prof = profiles[p.id];
    if (!prof || mixInfo.mix[pi] < 0.003) return;
    let wPt = 0, xwPt = 0, top = null;
    P2F.meta.zones.forEach((z, zi) => {
      const e = prof.zones[z.id];
      if (!e) return;
      const pc = e.swing.swing_rate * e.swing.in_play_per_swing;
      const w = mixInfo.mix[pi] * mixInfo.loc[pi][zi] * pc;
      if (!(w > 0)) return;
      const sc = prof.cell_scale || 1000;
      e.cells.forEach((v, i) => { cells[i] += w * v / sc; });
      W += w; xw += w * e.xwoba_con; ev += w * e.ev;
      BB_KEYS.forEach((k, j) => { bb[j] += w * e.bb[k]; });
      wPt += w; xwPt += w * e.xwoba_con;
      if (!top || w > top.w) top = { z: z.id, w, xw: e.xwoba_con };
    });
    perPt.push({ pt: p.id, mix: mixInfo.mix[pi], contact: wPt, xw: wPt ? xwPt / wPt : null, top });
  });
  const cs = sum(cells);
  return {
    cells01: cells.map(v => (cs ? v / cs : 0)),
    W, xw: W ? xw / W : null, ev: W ? ev / W : null, bb: bb.map(v => (W ? v / W : 0)),
    perPt: perPt.map(r => ({ ...r, share: W ? r.contact / W : 0 })),
  };
}

const MATCHUP = { dist: null, profiles: {}, rec: null, recErr: null };

function fillPitchers(list) {
  const sel = document.getElementById('p2f-pitcher');
  if (!sel) return;
  sel.innerHTML = list.map(p => `<option value="${p.id}">${_esc(p.name)} (${p.p_throws}HP)</option>`).join('');
  if (list.some(p => String(p.id) === String(P2F.state.pitcherId))) sel.value = String(P2F.state.pitcherId);
}

P2F.modes.matchup = {
  label: 'Pitcher matchup',
  help: 'Pick a pitcher: the hitter\'s blended spray for each pitch type and zone is weighted by <strong>where that pitcher actually throws each pitch to this batter side</strong> and how often (optionally in a count), giving an expected matchup spray map and xwOBA on contact.',
  async load() {
    const s = P2F.state;
    if (!s.pitcherId || !P2F.pitchers.some(p => String(p.id) === String(s.pitcherId))) {
      s.pitcherId = (P2F.pitchers.find(p => /skubal/i.test(p.name)) || P2F.pitchers[0] || {}).id;
    }
    MATCHUP.dist = await p2fGetPitcher(s.pitcherId);
    s.hand = MATCHUP.dist.p_throws;
    const pts = P2F.meta.pitch_types.map(p => p.id);
    const profs = await Promise.all(pts.map(pt => p2fEffective('hitter', s.batterId, s.stand, pt).catch(() => null)));
    MATCHUP.profiles = Object.fromEntries(pts.map((pt, i) => [pt, profs[i]]));
    MATCHUP.rec = null;
    MATCHUP.recErr = null;
    if (s.mixSource === 'situational' && !p2fIsStatic()) {
      try {
        MATCHUP.rec = await p2fJSON(`/api/recommend?pitcher_id=${s.pitcherId}&batter_id=${s.batterId}&count=${s.sitCount}&stand=${s.stand}&p_throws=${MATCHUP.dist.p_throws}`);
      } catch (e) {
        MATCHUP.recErr = e.message;
      }
    }
  },
  leave() { P2F.state.hand = 'all'; },
  render(prof) {
    const s = P2F.state;
    const dist = MATCHUP.dist;
    const name = prof.batter_name;
    const mixInfo = mixFromRows(dist.rows, s.stand, s.count);
    const base = mixFromRows(leagueMixRows(s.stand, dist.p_throws), s.stand, s.count);
    const res = matchupCombine(MATCHUP.profiles, mixInfo);
    const avg = matchupCombine(MATCHUP.profiles, base);
    const sit = s.mixSource === 'situational' && MATCHUP.rec ? MATCHUP.rec : null;
    let sitEntry = null, sitPt = null, sitZone = null;
    if (sit) {
      sitPt = sit.recommended_pitch;
      const locs = (sit.locations || {})[sitPt] || [];
      sitZone = locs.length ? locs[0].zone : null;
      const sp = MATCHUP.profiles[sitPt];
      if (sp && sitZone) sitEntry = sp.zones[sitZone];
    }
    // Left: pitcher controls, mix table, his location map for the selected pitch type.
    document.getElementById('p2f-left-title').textContent = '1 · Pitcher & pitch mix';
    document.getElementById('p2f-left-tag').innerHTML = `${_esc(dist.name)} (${dist.p_throws}HP) vs ${s.stand}HH, ${_esc(filterSets(s.count, 'all').countLabel)}: ${Math.round(mixInfo.n).toLocaleString()} season-weighted pitches. Hitter maps use his profile vs ${dist.p_throws}HP.`;
    document.getElementById('p2f-waste').style.display = 'none';
    const rows = res.perPt.sort((a, b) => b.mix - a.mix).map(r =>
      `<tr class="${r.pt === s.pt ? 'sel' : ''}" data-pt="${r.pt}"><td title="${_esc(ptName(r.pt))}">${r.pt}</td><td>${pct(r.mix)}</td><td>${pct(r.share)}</td><td>${f3(r.xw)}</td><td>${r.top ? _esc(zoneLabel(r.top.z)) : '–'}</td></tr>`).join('');
    const sitOpts = ['0-0', '0-1', '0-2', '1-0', '1-1', '1-2', '2-0', '2-1', '2-2', '3-0', '3-1', '3-2'];
    const zoneInfo = id => {
      const pi = ptIdx(s.pt), zi = zoneIdx(id);
      const share = mixInfo.loc[pi] ? mixInfo.loc[pi][zi] : 0;
      const e = MATCHUP.profiles[s.pt] && MATCHUP.profiles[s.pt].zones[id];
      const mx = Math.max(1e-9, ...(mixInfo.loc[pi] || [0]));
      return {
        fill: share > 0 ? blueColor(share / mx) : '#f4f4f1',
        dark: share / mx > 0.55,
        l1: pct(share), l2: e ? `xw ${f3(e.xwoba_con)}` : '',
        tip: `${zoneLabel(id)}\n${dist.name} throws ${pct(share, 1)} of his ${ptName(s.pt).toLowerCase()}s to ${s.stand}HH here\n${name}: xwOBA on contact ${e ? f3(e.xwoba_con) : '–'} (blend ${e ? pct(e.blend_weight) : '–'})`,
      };
    };
    document.getElementById('p2f-zone').innerHTML =
      `<div class="def-controls"><label class="tag">Pitcher <input type="search" id="p2f-pitcher-search" placeholder="Search pitchers…" autocomplete="off"/><select id="p2f-pitcher"></select></label>` +
      `<label class="tag">Pitch mix <select id="p2f-mix-src"><option value="actual">His actual mix &amp; locations (count filter above)</option><option value="situational"${p2fIsStatic() ? ' disabled' : ''}>Situational model's pick for a count${p2fIsStatic() ? ' (live app only)' : ''}</option></select></label>` +
      (s.mixSource === 'situational' ? `<label class="tag">Count <select id="p2f-sit-count">${sitOpts.map(c => `<option${c === s.sitCount ? ' selected' : ''}>${c}</option>`).join('')}</select></label>` : '') +
      `</div><table class="def-table mix-table"><thead><tr><th>Pitch</th><th>Mix</th><th>Share of contact</th><th>xwOBA con</th><th>Most common zone</th></tr></thead><tbody>${rows}</tbody></table>` +
      `<div class="tag">Mix = how often he throws it to ${s.stand}HH; share of contact also weights by ${shortName(name)}'s swing × in-play rate in each zone. Click a row to see that pitch's locations.</div>` +
      `<h3 style="margin-top:10px">Where he throws the ${_esc(ptName(s.pt).toLowerCase())}</h3>` +
      zoneGridSVG(s.stand, `Catcher's view · ${dist.name} ${s.pt} to ${s.stand}HH`, zoneInfo, null);
    document.getElementById('p2f-zone-legend').innerHTML = `<div class="legend"><span>Share of his ${s.pt}s: 0</span><span class="ramp" style="background:linear-gradient(90deg,${[0, 0.5, 1].map(blueColor).join(',')})"></span><span>max</span><span>· xw = ${_esc(shortName(name))}'s xwOBA on contact there</span></div>`;
    fillPitchers(P2F.pitchers);
    document.getElementById('p2f-pitcher').addEventListener('change', e => { s.pitcherId = Number(e.target.value); p2fLoad(); });
    let timer = null;
    document.getElementById('p2f-pitcher-search').addEventListener('input', e => {
      const needle = foldName(e.target.value.trim());
      clearTimeout(timer);
      timer = setTimeout(async () => {
        let list = P2F.pitchers.filter(p => !needle || foldName(p.name).includes(needle));
        if (!p2fIsStatic() && needle && list.length < 5) list = await p2fJSON(`/api/field/pitchers?q=${encodeURIComponent(needle)}&limit=50`).catch(() => list);
        list.forEach(p => { if (!P2F.pitchers.some(x => x.id === p.id)) P2F.pitchers.push(p); });
        fillPitchers(list);
        if (list.length && !list.some(p => String(p.id) === String(s.pitcherId))) { s.pitcherId = list[0].id; p2fLoad(); }
      }, 200);
    });
    document.getElementById('p2f-mix-src').value = s.mixSource;
    document.getElementById('p2f-mix-src').addEventListener('change', e => { s.mixSource = e.target.value; p2fLoad(); });
    const sc = document.getElementById('p2f-sit-count');
    if (sc) sc.addEventListener('change', e => { s.sitCount = e.target.value; p2fLoad(); });
    document.querySelectorAll('.mix-table tr[data-pt]').forEach(tr => tr.addEventListener('click', () => { s.pt = tr.dataset.pt; p2fLoad(); }));

    // Right: expected matchup spray (or the situational pick's cell).
    const fake = { stand: s.stand, cell_scale: 1000 };
    const shown = sitEntry || { cells: res.cells01.map(v => v * 1000) };
    document.getElementById('p2f-field-title').textContent = sitEntry
      ? `2 · Situational pick in ${s.sitCount}: ${ptName(sitPt).toLowerCase()} ${zoneLabel(sitZone).toLowerCase()} — where ${shortName(name)}'s contact goes`
      : `2 · Expected matchup spray: ${dist.name} vs ${name} (${s.stand}HH, ${filterSets(s.count, 'all').countLabel})`;
    const opts = { color: s.color, filter: s.filter, showBalls: false, who: sitEntry ? 'his' : 'expected' };
    document.getElementById('p2f-field').innerHTML = fieldSVG(fake, shown, opts);
    document.getElementById('p2f-field-legend').innerHTML = fieldLegend(opts) +
      `<div class="legend"><span>Map = Σ over pitch types and zones of (his blended landing distribution) × (pitcher's mix × location share × hitter's swing × in-play rate there). Not shown: sequencing, velocity within a pitch type.</span></div>`;
    document.getElementById('p2f-field-extra').innerHTML = MATCHUP.recErr ? `<p class="tag">Situational model unavailable: ${_esc(MATCHUP.recErr)}</p>` : '';

    const dir = directionOf(res.cells01, s.stand);
    const avgDir = directionOf(avg.cells01, s.stand);
    const tiles = [
      tile('Expected xwOBA on contact', res.xw, avg.xw, f3, true, d => signed(d, 3).replace('0.', '.')),
      tile('Expected avg exit velo (mph)', res.ev, avg.ev, v => v.toFixed(1), true, d => `${signed(d, 1)} mph`),
      tile('Ground-ball share', res.bb[0], avg.bb[0], v => pct(v), false, d => `${signed(100 * d, 0)} pts`),
      tile('Balls in play per 100 pitches', 100 * res.W, 100 * avg.W, v => v.toFixed(1), true, d => signed(d, 1)),
    ].join('');
    const sitHTML = sit ? `<div><h3>Situational model · ${_esc(s.sitCount)}</h3><p>Recommends <strong>${_esc(ptName(sitPt))}</strong>${sitZone ? `, best zone <strong>${_esc(zoneLabel(sitZone))}</strong>` : ''}.</p>` +
      `<table class="def-table"><thead><tr><th>Pitch</th><th>pred. xwOBA</th></tr></thead><tbody>${sit.scores.map(x => `<tr class="${x.is_recommended ? 'sel' : ''}"><td>${x.pitch_type}</td><td>${f3(x.pred_xwoba)}</td></tr>`).join('')}</tbody></table>` +
      (sitEntry ? `<p class="tag">Contact on that pitch there: xwOBA ${f3(sitEntry.xwoba_con)}, GB ${pct(sitEntry.bb.ground_ball)}, pulled ${pct(sitEntry.direction.pull)} — ${sitEntry.n_own_bip} of his own balls in this slice, so ${pct(sitEntry.blend_weight)} hitter-specific.</p>` : '') + `</div>` : '';
    document.getElementById('p2f-summary').style.display = '';
    document.getElementById('p2f-summary').innerHTML = `<div class="sum-grid">
      <div><h3>Matchup vs an average ${dist.p_throws}HP</h3><div class="tiles">${tiles}</div><div class="tag">"vs league" here = same hitter, league-average ${dist.p_throws}HP pitch mix and locations to ${s.stand}HH in the same counts.</div></div>
      <div><h3>Direction of expected contact</h3><div class="stack-label">vs ${_esc(dist.name)}</div>${stackBar(dir)}<div class="stack-label">vs average ${dist.p_throws}HP</div>${stackBar(avgDir)}</div>
      ${sitHTML || `<div><h3>How to read this</h3><p>The map is what ${_esc(shortName(name))}'s contact looks like <em>if he faces this pitcher's actual pitch and location pattern</em>. The pitch table shows which pitches produce the contact; click one to see its location map.</p></div>`}
    </div>`;
    const worst = res.perPt.filter(r => r.share >= 0.08).sort((a, b) => b.xw - a.xw)[0];
    const best = res.perPt.filter(r => r.share >= 0.08).sort((a, b) => a.xw - b.xw)[0];
    const diff = res.xw - avg.xw;
    let txt = `${dist.name} vs ${name} (${s.stand}HH, ${filterSets(s.count, 'all').countLabel}): expected xwOBA on contact ${f3(res.xw)} vs ${f3(avg.xw)} against an average ${dist.p_throws}HP mix (${signed(1000 * diff, 0)} points).`;
    if (best && worst && best.pt !== worst.pt) txt += ` Safest high-volume pitch: ${ptName(best.pt).toLowerCase()} (${f3(best.xw)}, ${pct(best.share)} of contact); most dangerous: ${ptName(worst.pt).toLowerCase()} (${f3(worst.xw)}).`;
    txt += ` Contact goes ${pct(dir.pull)} pull side (${pct(avgDir.pull)} vs average).`;
    if (sitEntry) txt += ` Situational pick in ${s.sitCount}: ${ptName(sitPt).toLowerCase()} ${zoneLabel(sitZone).toLowerCase()} → contact xwOBA ${f3(sitEntry.xwoba_con)}.`;
    p2fTakeaway2(`Matchup · ${dist.name} vs ${name}`, txt);
  },
};

// ---------------------------------------------------------------- compare

const COMPARE = { other: null, league: null };

P2F.modes.compare = {
  label: 'Compare',
  help: 'Same pitch type, zone and filters, two ways: <strong>hitter minus league</strong> as a difference map (red = more of his contact lands there than league), or <strong>two hitters side by side</strong>.',
  async load() {
    const s = P2F.state;
    if (s.compare === 'hitter') {
      if (!s.compareId || String(s.compareId) === String(s.batterId)) {
        const alt = P2F.hitters.find(h => String(h.id) !== String(s.batterId) && h.stands.includes(s.stand)) || P2F.hitters.find(h => String(h.id) !== String(s.batterId));
        s.compareId = alt.id;
      }
      const h = P2F.hitters.find(x => String(x.id) === String(s.compareId));
      const stand = h.stands.includes(s.stand) ? s.stand : h.stands[0];
      COMPARE.other = await p2fEffective('hitter', s.compareId, stand, s.pt);
    } else {
      COMPARE.league = await p2fEffective('league', null, s.stand, s.pt);
    }
  },
  render(prof, entry) {
    const s = P2F.state;
    const savedBrush = s.brush;
    s.brush = null;
    P2F.modes.explore.render.call(this, prof, entry);
    s.brush = savedBrush;
    const ctl = `<div class="cmp-controls"><label class="tag">Compare <select id="p2f-cmp-kind"><option value="league">${_esc(shortName(prof.batter_name))} minus league (difference map)</option><option value="hitter">Two hitters side by side</option></select></label>` +
      (s.compare === 'hitter' ? `<label class="tag">Second hitter <select id="p2f-cmp-id">${P2F.hitters.filter(h => String(h.id) !== String(s.batterId)).map(h => `<option value="${h.id}">${_esc(h.name)} (${h.stands.join('/')})</option>`).join('')}</select></label>` : '') + `</div>`;
    let fieldHTML, legend, txt;
    if (s.compare === 'hitter') {
      const o = COMPARE.other;
      const e2 = o.zones[s.zone];
      const side = (p, e, uid) => `<div><h3>${_esc(p.batter_name)} · ${p.stand}HH</h3>` +
        `<div class="tag">xwOBA con ${f3(e.xwoba_con)} · GB ${pct(e.bb.ground_ball)} · pull ${pct(e.direction.pull)} · ${e.n_own_bip} balls (blend ${pct(e.blend_weight)})</div>` +
        fieldSVG(p, e, { color: s.color, filter: s.filter, showBalls: false, uid, compact: false }) + `</div>`;
      fieldHTML = ctl + `<div class="cmp-grid">${side(prof, entry, 'A')}${side(o, e2, 'B')}</div>`;
      legend = fieldLegend({ color: s.color, filter: s.filter, showBalls: false });
      document.getElementById('p2f-field-title').textContent = `2 · ${ptName(s.pt)}s, ${entry.label.toLowerCase()}: ${shortName(prof.batter_name)} vs ${shortName(o.batter_name)}`;
      const dPull = entry.direction.pull - e2.direction.pull, dGb = entry.bb.ground_ball - e2.bb.ground_ball;
      txt = `${ptName(s.pt)}s ${entry.label.toLowerCase()}: ${shortName(prof.batter_name)} xwOBA on contact ${f3(entry.xwoba_con)} vs ${shortName(o.batter_name)} ${f3(e2.xwoba_con)}; ` +
        `${shortName(prof.batter_name)} pulls ${Math.abs(100 * dPull).toFixed(0)} pts ${dPull >= 0 ? 'more' : 'less'} often and hits ${Math.abs(100 * dGb).toFixed(0)} pts ${dGb >= 0 ? 'more' : 'fewer'} grounders.` +
        (o.stand !== prof.stand ? ' Note: different batting sides, so pull side is mirrored on the field.' : '') +
        (Math.min(entry.blend_weight, e2.blend_weight) < 0.25 ? ' At least one side is mostly prior here — differences are muted by shrinkage.' : '');
    } else {
      const lg = COMPARE.league;
      const le = lg.zones[s.zone];
      const a = fieldCells(prof, entry, s.stand, s.filter).cells;
      const b = fieldCells(lg, le, s.stand, s.filter).cells;
      const diff = a.map((c, i) => c.share - b[i].share);
      const diffLabel = `${shortName(prof.batter_name)} minus league ${s.stand}HH`;
      const opts = { diff, diffLabel, filter: s.filter, showBalls: false };
      fieldHTML = ctl + fieldSVG(prof, entry, opts);
      legend = fieldLegend(opts);
      document.getElementById('p2f-field-title').textContent = `2 · Difference map: ${shortName(prof.batter_name)} minus league, ${ptName(s.pt).toLowerCase()}s ${entry.label.toLowerCase()}`;
      const iMax = argmax(diff), iMin = argmax(diff.map(v => -v));
      const where = c => `${c.r0}–${c.r1} ft, ${sideOfAngle((c.a0 + c.a1) / 2, s.stand)}`;
      txt = `Versus league ${s.stand}HH on ${ptName(s.pt).toLowerCase()}s ${entry.label.toLowerCase()}, ${shortName(prof.batter_name)} puts ${(100 * diff[iMax]).toFixed(1)} pts more of his contact ${where(a[iMax])} ` +
        `and ${Math.abs(100 * diff[iMin]).toFixed(1)} pts less ${where(a[iMin])}. Pull share ${pct(entry.direction.pull)} vs ${pct(le.direction.pull)}; GB ${pct(entry.bb.ground_ball)} vs ${pct(le.bb.ground_ball)}.` +
        (entry.blend_weight < 0.25 ? ' Mostly prior here, so the difference mainly reflects his overall tendencies.' : '');
    }
    document.getElementById('p2f-field').innerHTML = fieldHTML;
    document.getElementById('p2f-field-legend').innerHTML = legend;
    p2fTakeaway2(`Compare · ${prof.batter_name}`, txt);
    const kind = document.getElementById('p2f-cmp-kind');
    kind.value = s.compare;
    kind.addEventListener('change', e => { s.compare = e.target.value; p2fLoad(); });
    const cid = document.getElementById('p2f-cmp-id');
    if (cid) {
      cid.value = String(s.compareId);
      cid.addEventListener('change', e => { s.compareId = Number(e.target.value); p2fLoad(); });
    }
  },
};

// ---------------------------------------------------------------- replay

const REPLAY = { balls: [], idx: 0, prog: 0, playing: false, speed: 4, raf: null, last: 0, key: null, scope: 'all' };

function replayStop() {
  REPLAY.playing = false;
  if (REPLAY.raf) cancelAnimationFrame(REPLAY.raf);
  REPLAY.raf = null;
}

function replayDot(b, recent) {
  return `<circle class="p2f-ball" data-i="${b.i}" cx="${b.x}" cy="${-b.y}" r="${recent ? 6 : 3.6}" fill="${BB_COLORS[b.bb]}" stroke="${recent ? '#111' : '#fff'}" stroke-width="${recent ? 1.6 : 0.9}"><title>${_esc(ballTip(b))}</title></circle>`;
}

function replayDrawDots() {
  const g = document.getElementById('p2f-replay-dots');
  if (!g) return;
  g.innerHTML = REPLAY.balls.slice(0, REPLAY.idx).map((b, i) => replayDot(b, i === REPLAY.idx - 1)).join('');
}

function replayFlight() {
  const g = document.getElementById('p2f-replay-flight');
  if (!g) return;
  const b = REPLAY.balls[REPLAY.idx];
  if (!b || !REPLAY.playing) { g.innerHTML = ''; return; }
  const p = Math.min(1, REPLAY.prog / 0.7);
  const x = b.x * p, y = b.y * p;
  const air = b.bb !== 'GB';
  const lift = air ? Math.sin(Math.PI * p) * Math.min(1, Math.max(0.2, (b.la || 20) / 35)) : 0;
  g.innerHTML = `<line x1="0" y1="0" x2="${x}" y2="${-y}" stroke="${BB_COLORS[b.bb]}" stroke-width="2" stroke-opacity="0.7" stroke-dasharray="${air ? '6 4' : ''}"/>` +
    (air ? `<ellipse cx="${x}" cy="${-y}" rx="${3 + 2 * lift}" ry="${2 + lift}" fill="#000" fill-opacity="0.18"/>` : '') +
    `<circle cx="${x}" cy="${-y - 30 * lift}" r="${4 + 4 * lift}" fill="#fff" stroke="${BB_COLORS[b.bb]}" stroke-width="2"/>`;
}

function replayInfo() {
  const shown = REPLAY.balls.slice(0, REPLAY.idx);
  const cur = shown[shown.length - 1];
  const el = document.getElementById('p2f-replay-info');
  if (!el) return;
  const stand = P2F.state.stand;
  const n = shown.length;
  const w = sum(shown.map(b => b.w)) || 1;
  const pull = shown.filter(b => (stand === 'R' ? b.x < 0 : b.x > 0) && Math.abs(sprayAngle(b.x, b.y)) >= 15).length;
  const gb = shown.filter(b => b.bb === 'GB').length;
  const xw = shown.filter(b => b.xw != null);
  const evs = shown.filter(b => b.ev != null);
  const hits = shown.filter(b => ['single', 'double', 'triple', 'home_run'].includes(b.res)).length;
  const hr = shown.filter(b => b.hr).length;
  el.innerHTML = (cur ? `<div class="replay-cur"><div class="k">Ball ${n} of ${REPLAY.balls.length} · ${cur.d}</div>` +
    `<div><strong>${_esc((cur.res || 'in play').replace(/_/g, ' '))}</strong> — ${BB_NAMES[cur.bb]}</div>` +
    `<div>vs ${_esc(cur.pname)} (${cur.ph}HP) · ${_esc(ptName(cur.pt))}, ${_esc(zoneLabel(cur.z).toLowerCase())} · ${_esc(ATOM_LABELS[cur.k])}</div>` +
    `<div>EV ${cur.ev ?? '–'} mph · LA ${cur.la ?? '–'}° · ${cur.dist != null ? `${cur.dist} ft` : '–'} · xwOBA ${f3(cur.xw)}</div></div>` : '<p class="tag">Press play to start.</p>') +
    `<h3 style="margin-top:10px">Running totals (${n} balls)</h3><div class="tiles">` +
    `<div class="tile"><div class="v">${pct(n ? pull / n : null)}</div><div class="l">pulled (≥ 15° to pull side)</div></div>` +
    `<div class="tile"><div class="v">${pct(n ? gb / n : null)}</div><div class="l">ground balls</div></div>` +
    `<div class="tile"><div class="v">${evs.length ? (sum(evs.map(b => b.ev)) / evs.length).toFixed(1) : '–'}</div><div class="l">avg exit velo (mph)</div></div>` +
    `<div class="tile"><div class="v">${xw.length ? f3(sum(xw.map(b => b.xw)) / xw.length) : '–'}</div><div class="l">avg xwOBA on contact</div></div>` +
    `<div class="tile"><div class="v">${hits}</div><div class="l">hits (${hr} HR)</div></div>` +
    `<div class="tile"><div class="v">${w.toFixed(0)}</div><div class="l">season-weighted n</div></div></div>`;
  const sl = document.getElementById('p2f-replay-scrub');
  if (sl) sl.value = String(REPLAY.idx);
  const lbl = document.getElementById('p2f-replay-date');
  if (lbl) lbl.textContent = cur ? `${cur.d} · ${n}/${REPLAY.balls.length}` : `0/${REPLAY.balls.length}`;
}

function replayTick(ts) {
  if (!REPLAY.playing) return;
  const dt = REPLAY.last ? Math.min(0.1, (ts - REPLAY.last) / 1000) : 0;
  REPLAY.last = ts;
  REPLAY.prog += dt * REPLAY.speed;
  let added = false;
  while (REPLAY.prog >= 1 && REPLAY.idx < REPLAY.balls.length) {
    REPLAY.prog -= 1;
    REPLAY.idx += 1;
    added = true;
  }
  if (added) { replayDrawDots(); replayInfo(); }
  if (REPLAY.idx >= REPLAY.balls.length) {
    replayStop();
    const btn = document.getElementById('p2f-replay-play');
    if (btn) btn.textContent = '▶ Replay again';
    replayFlight();
    return;
  }
  replayFlight();
  REPLAY.raf = requestAnimationFrame(replayTick);
}

function replayPlay() {
  if (REPLAY.idx >= REPLAY.balls.length) { REPLAY.idx = 0; replayDrawDots(); }
  REPLAY.playing = true;
  REPLAY.last = 0;
  document.getElementById('p2f-replay-play').textContent = '❚❚ Pause';
  REPLAY.raf = requestAnimationFrame(replayTick);
}

P2F.modes.replay = {
  label: 'Replay',
  help: 'Animates his actual batted balls in date order. <strong>Play / pause, change speed, or scrub</strong>; hover any dot for date, pitcher, pitch type, zone, exit velo, launch angle and result.',
  leave() { replayStop(); },
  render(prof) {
    const s = P2F.state;
    replayStop();
    if (prof.batter_id == null || !P2F.detail) { p2fTakeaway2('Replay', 'Replay needs a hitter.'); return; }
    const key = `${s.batterId}|${s.stand}|${REPLAY.scope}|${s.pt}|${s.count}|${s.hand}`;
    if (REPLAY.key !== key) {
      REPLAY.balls = p2fBalls({ stand: s.stand, pt: REPLAY.scope === 'pt' ? s.pt : null });
      REPLAY.idx = 0;
      REPLAY.prog = 0;
      REPLAY.key = key;
    }
    const N = REPLAY.balls.length;
    document.getElementById('p2f-left-title').textContent = '1 · Current ball & running totals';
    document.getElementById('p2f-left-tag').innerHTML = `${_esc(prof.batter_name)} as a ${s.stand}HH${isFiltered() ? `, ${_esc(filterSets(s.count, s.hand).label)}` : ''}: ${N} balls in play${N ? `, ${REPLAY.balls[0].d} → ${REPLAY.balls[N - 1].d}` : ''}.`;
    document.getElementById('p2f-waste').style.display = 'none';
    document.getElementById('p2f-zone').innerHTML = '<div id="p2f-replay-info"></div>';
    document.getElementById('p2f-zone-legend').innerHTML = '';
    document.getElementById('p2f-field-title').textContent = `2 · Replay: ${prof.batter_name}'s batted balls in date order (${REPLAY.scope === 'pt' ? ptName(s.pt).toLowerCase() + 's' : 'all pitch types'})`;
    const overlay = '<g id="p2f-replay-dots"></g><g id="p2f-replay-flight" pointer-events="none"></g>';
    document.getElementById('p2f-field').innerHTML = fieldSVG(prof, null, { noCells: true, showBalls: false, overlay, filter: 'all' });
    document.getElementById('p2f-field-legend').innerHTML = fieldLegend({ color: 'density', showBalls: true, ballLegendTitle: 'Dot color = batted-ball type (largest dot = most recent):' })
      .replace(/<div class="legend"><span>Darker blue[^<]*<\/span><\/div>/, '');
    document.getElementById('p2f-field-extra').innerHTML =
      `<div class="replay-controls"><button type="button" class="btn primary" id="p2f-replay-play">▶ Play</button>` +
      `<button type="button" class="btn" id="p2f-replay-reset">⟲ Reset</button>` +
      `<label class="tag">Speed <select id="p2f-replay-speed"><option value="1">1 ball/s</option><option value="4">4 balls/s</option><option value="12">12 balls/s</option><option value="40">40 balls/s</option></select></label>` +
      `<label class="tag">Balls <select id="p2f-replay-scope"><option value="all">All pitch types</option><option value="pt">Current pitch type (${s.pt})</option></select></label>` +
      `<input type="range" id="p2f-replay-scrub" min="0" max="${N}" value="${REPLAY.idx}" aria-label="Scrub through balls in play"/><span class="tag" id="p2f-replay-date"></span></div>`;
    document.getElementById('p2f-replay-speed').value = String(REPLAY.speed);
    document.getElementById('p2f-replay-scope').value = REPLAY.scope;
    document.getElementById('p2f-replay-play').addEventListener('click', () => {
      if (REPLAY.playing) { replayStop(); document.getElementById('p2f-replay-play').textContent = '▶ Play'; replayFlight(); } else replayPlay();
    });
    document.getElementById('p2f-replay-reset').addEventListener('click', () => { replayStop(); REPLAY.idx = 0; REPLAY.prog = 0; document.getElementById('p2f-replay-play').textContent = '▶ Play'; replayDrawDots(); replayFlight(); replayInfo(); });
    document.getElementById('p2f-replay-speed').addEventListener('change', e => { REPLAY.speed = Number(e.target.value); });
    document.getElementById('p2f-replay-scope').addEventListener('change', e => { REPLAY.scope = e.target.value; p2fRender(); });
    document.getElementById('p2f-replay-scrub').addEventListener('input', e => { REPLAY.idx = Number(e.target.value); REPLAY.prog = 0; replayDrawDots(); replayFlight(); replayInfo(); });
    replayDrawDots();
    replayInfo();
    document.getElementById('p2f-summary').style.display = 'none';
    const first = REPLAY.balls.slice(0, Math.floor(N / 2)), second = REPLAY.balls.slice(Math.floor(N / 2));
    const pullOf = arr => (arr.length ? arr.filter(b => (s.stand === 'R' ? b.x < 0 : b.x > 0) && Math.abs(sprayAngle(b.x, b.y)) >= 15).length / arr.length : null);
    const xwOf = arr => { const v = arr.filter(b => b.xw != null); return v.length ? sum(v.map(b => b.xw)) / v.length : null; };
    p2fTakeaway2(`Replay · ${prof.batter_name}`, N
      ? `${N} balls in play. First half (${first.length ? first[0].d : '–'} →): pulled ${pct(pullOf(first))}, xwOBA on contact ${f3(xwOf(first))}; second half (→ ${N ? REPLAY.balls[N - 1].d : '–'}): pulled ${pct(pullOf(second))}, xwOBA ${f3(xwOf(second))}.`
      : 'No balls in play with these filters.');
  },
};

window.P2F = P2F;
p2fInit();
