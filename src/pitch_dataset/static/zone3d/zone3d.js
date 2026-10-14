// 3D strike zone: pitch flight through a true 3D zone volume, tunneling, back-of-zone calls, batted-ball arcs.
// Works from embedded data (window.Z3D_STATIC, GitHub Pages) or the select-web /api/zone3d endpoints.
// Requires three.js r147 (global THREE) + examples/js OrbitControls. Scene uses Statcast coordinates
// directly with z up: x + toward 1B (catcher's right), y from the back tip of home plate toward the mound.
(function () {
  'use strict';

  const PT_COLORS = {
    FF: '#d22d49', FA: '#d22d49', SI: '#f08c00', FC: '#933f2c', SL: '#b3a400', ST: '#c4902a', SV: '#7a8fc4',
    CU: '#00a8c4', KC: '#6236cd', CS: '#0068ff', CH: '#1dae3a', FS: '#2f9696', FO: '#55ccab', SC: '#60a833',
    KN: '#3c44cd', EP: '#888888', PO: '#aaaaaa',
  };
  const BB_COLORS = { ground_ball: '#7a4b1e', line_drive: '#c0392b', fly_ball: '#1f4b99', popup: '#7b7b75' };
  const BB_NAMES = { ground_ball: 'Ground ball', line_drive: 'Line drive', fly_ball: 'Fly ball', popup: 'Popup' };
  const FLAG_COLORS = { 2: '#111111', 3: '#d0021b', 4: '#8e24aa' };
  const FLAG_SHORT = { 2: 'Strike that only clipped the back of the zone', 3: 'Strike that missed the 3D zone', 4: 'Ball whose path touched the 3D zone' };
  const N_PATH = 48;
  const N_PICK = 16;
  const N_ARC = 40;
  const FIT_Y = 50;
  const GAP_S = 0.45;
  const CAMS = {
    catcher: { label: "Catcher's view", fov: 38 },
    batter: { label: "Batter's eyes (over the shoulder)", fov: 62 },
    pitcher: { label: "Pitcher's view (from behind the mound)", fov: 13 },
    side: { label: 'Side view from the 1B side (last ~30 ft of flight)', fov: 17 },
    field: { label: 'Field view (batted-ball arcs)', fov: 45 },
    zone: { label: 'Zone close-up (from the 1B side, above the plate)', fov: 40 },
  };
  const VIEW_NOTES = {
    catcher: 'You are behind home plate looking out at the mound. Pitches start at the release point and end at the back tip of the plate; the blue box is the 3D zone for an average opponent.',
    batter: "From the hitter's eyes, looking out at the pitcher. Most of each pitch's break happens after the orange decision-point plane, which is the point of tunneling.",
    pitcher: "From behind the mound looking in. Pitches separate late, near the plate. The hitter's side is mirrored relative to the catcher's view.",
    side: 'From the first-base side, so the vertical drop of each pitch is visible: the plate and zone are on the left, the orange decision plane in the middle, the mound off to the right (orbit or zoom out to see the release). Heights are true scale (ft).',
    field: 'Zoomed out to the field. Batted-ball arcs run from contact to where the ball landed or was fielded; the arc shape is approximate (see method).',
    zone: "Close-up of the 3D zone: the plate is 17\" deep, so a pitch can miss the front face and still pass through the volume behind it. A selected pitch shows the ball (to scale) at five depths across the plate.",
  };
  const COUNT_LABELS = [['all', 'All counts'], ['ahead', 'Pitcher ahead'], ['even', 'Even'], ['behind', 'Pitcher behind'], ['two_strike', 'Two strikes']];
  const RESULT_OPTS = [['all', 'All results'], ['CS', 'Called strike'], ['B', 'Ball'], ['SS', 'Swinging strike'], ['F', 'Foul'], ['IP', 'In play']];

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fold = s => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const fmt = (v, d = 1) => (v == null || isNaN(v) ? '–' : Number(v).toFixed(d));
  const ptColor = pt => PT_COLORS[pt] || '#666666';
  const isStatic = () => typeof window.Z3D_STATIC === 'object' && window.Z3D_STATIC !== null;
  const $ = id => document.getElementById(id);

  const Z = {
    meta: null, G: null, pitchers: [], data: null, rows: [], vis: [], liveBatters: null,
    f: { pitcherId: null, batter: 'all', pt: 'all', count: 'all', result: 'all', n: 100 },
    view: 'catcher', tunnel: false, playing: false, speed: 1, mode: 'seq', selected: -1,
    play: { seq: 0, tau: 0, hold: 0 }, stand: 'R', sz: [1.6, 3.4], ready: false, errors: [],
  };

  // ---------------------------------------------------------------- data

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  }

  function tAtY(r, y) {
    const c = FIT_Y - y;
    if (Math.abs(r.ay) < 1e-6) return -c / r.vy;
    return (-r.vy - Math.sqrt(Math.max(r.vy * r.vy - 2 * r.ay * c, 0))) / r.ay;
  }
  function posAt(r, t, out) {
    return out.set(r.x0 + r.vx * t + 0.5 * r.ax * t * t, FIT_Y + r.vy * t + 0.5 * r.ay * t * t, r.z0 + r.vz * t + 0.5 * r.az * t * t);
  }

  function unpack(payload) {
    const keys = payload.keys;
    return payload.rows.map((arr, i) => {
      const r = {};
      keys.forEach((k, j) => { r[k] = arr[j]; });
      r.i = i;
      r.rowId = payload.row_ids[i];
      r.tr = tAtY(r, r.yr);
      r.tf = tAtY(r, Z.G.plate_front_y);
      r.te = tAtY(r, 0);
      r.flight = r.te - r.tr;
      r.batterName = (payload.batters[String(r.b)] || [String(r.b)])[0];
      return r;
    });
  }

  async function loadPitcher(pid) {
    Z.f.pitcherId = pid;
    if (isStatic()) {
      Z.data = window.Z3D_STATIC.data[String(pid)];
    } else {
      const q = new URLSearchParams({ pitcher_id: pid, sample: Math.max(Z.f.n, 100) });
      if (Z.f.batter !== 'all') q.set('batter_id', Z.f.batter);
      if (Z.f.pt !== 'all') q.set('pitch_type', Z.f.pt);
      if (Z.f.count !== 'all') q.set('count', Z.f.count);
      if (Z.f.result !== 'all') q.set('result', Z.f.result);
      Z.data = await getJSON(`/api/zone3d/pitches?${q}`);
    }
    Z.rows = unpack(Z.data);
  }

  function filterRows() {
    const f = Z.f;
    const showFlags = $('z3-show-flags').checked;
    const ok = r => (f.batter === 'all' || String(r.b) === String(f.batter))
      && (f.pt === 'all' || r.pt === f.pt)
      && (f.result === 'all' || r.res === f.result)
      && countOk(r, f.count);
    const out = [];
    let n = 0;
    for (const r of Z.rows) {
      if (!ok(r)) continue;
      if (r.ex > 0) { if (showFlags) out.push(r); continue; }
      if (n < f.n) { out.push(r); n++; }
    }
    return out;
  }
  function countOk(r, c) {
    if (c === 'all') return true;
    if (c === 'ahead') return r.sk > r.bl;
    if (c === 'even') return r.sk === r.bl;
    if (c === 'behind') return r.bl > r.sk;
    if (c === 'two_strike') return r.sk === 2;
    const [b, s] = c.split('-').map(Number);
    return r.bl === b && r.sk === s;
  }

  // ---------------------------------------------------------------- three.js scene

  let renderer, scene, camera, controls, stage;
  let pathGroup, arcGroup, markGroup, zoneGroup, batterGroup, tunnelGroup, selGroup, labelGroup, dpGroup, ballMesh;
  let needsRender = true;
  let pathLines = [];
  let pickPts = null;
  const tmpV = new THREE.Vector3();
  const tmpV2 = new THREE.Vector3();
  const tmpM = new THREE.Matrix4();
  const tmpQ = new THREE.Quaternion();
  const tmpS = new THREE.Vector3();
  const matCache = {};

  function lineMat(color, dashed, opacity) {
    const key = `${color}|${dashed}|${opacity}`;
    if (!matCache[key]) {
      matCache[key] = dashed
        ? new THREE.LineDashedMaterial({ color, dashSize: 0.9, gapSize: 0.55, transparent: true, opacity })
        : new THREE.LineBasicMaterial({ color, transparent: true, opacity });
      matCache[key].userData.base = opacity;
      if (Z.selected >= 0) matCache[key].opacity = Math.min(opacity, 0.18);
    }
    return matCache[key];
  }
  function dimOthers(on) {
    Object.values(matCache).forEach(m => { m.opacity = on ? Math.min(m.userData.base, 0.18) : m.userData.base; });
  }

  function makeLabel(text, opts = {}) {
    const size = opts.size || 26;
    const c = document.createElement('canvas');
    const ctx = c.getContext('2d');
    const font = `${opts.weight || 500} ${size}px "IBM Plex Sans", "Segoe UI", sans-serif`;
    ctx.font = font;
    const w = Math.ceil(ctx.measureText(text).width) + 18;
    const h = size + 14;
    c.width = w; c.height = h;
    ctx.font = font;
    ctx.fillStyle = opts.bg || 'rgba(255,255,255,0.86)';
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = opts.border || 'rgba(0,0,0,0.12)';
    ctx.strokeRect(0.5, 0.5, w - 1, h - 1);
    ctx.fillStyle = opts.color || '#1a1a1a';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 9, h / 2 + 1);
    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    const mat = new THREE.SpriteMaterial({ map: tex, sizeAttenuation: false, depthTest: false, transparent: true });
    const s = new THREE.Sprite(mat);
    const k = (opts.scale || 1) * 0.00062;
    s.userData.base = [w * k, h * k];
    s.userData.views = opts.views || null;
    s.center.set(opts.cx == null ? 0.5 : opts.cx, opts.cy == null ? 0.5 : opts.cy);
    s.renderOrder = 20;
    scaleLabel(s);
    return s;
  }
  // Fixed-pixel sprites still scale with 1 / tan(fov / 2); undo that so labels read the same in every view.
  function fovFactor() { return camera ? Math.tan(camera.fov * Math.PI / 360) / Math.tan(20 * Math.PI / 180) : 1; }
  function scaleLabel(s) {
    const f = fovFactor();
    s.scale.set(s.userData.base[0] * f, s.userData.base[1] * f, 1);
  }
  function applyViewVisibility() {
    const labelsOn = $('z3-show-labels').checked;
    scene.traverse(o => {
      if (!o.isSprite || !o.userData.base) return;
      scaleLabel(o);
      if (o.parent === labelGroup) o.visible = !o.userData.views || o.userData.views.includes(Z.view);
    });
    labelGroup.visible = labelsOn;
    batterGroup.visible = Z.view !== 'batter' && Z.view !== 'zone';
    markGroup.visible = !Z.tunnel && !Z.play.active;
    selGroup.children.forEach(c => { if (c.userData.fieldOnly) c.visible = Z.view === 'field'; });
    arcGroup.visible = !Z.tunnel && !Z.play.active && Z.view === 'field' && $('z3-show-arcs').checked;
  }

  function ringTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const ctx = c.getContext('2d');
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 9;
    ctx.beginPath(); ctx.arc(32, 32, 25, 0, Math.PI * 2); ctx.stroke();
    const t = new THREE.CanvasTexture(c);
    return t;
  }
  function dotTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(32, 32, 26, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,0.55)'; ctx.lineWidth = 5; ctx.stroke();
    return new THREE.CanvasTexture(c);
  }

  function segs(points, color, opacity = 1) {
    const g = new THREE.BufferGeometry().setFromPoints(points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
    return new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity }));
  }
  function polyline(points, color, opacity = 1) {
    const g = new THREE.BufferGeometry().setFromPoints(points.map(p => new THREE.Vector3(p[0], p[1], p[2])));
    return new THREE.Line(g, new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity }));
  }
  function disc(r, color, x, y, z, seg = 48) {
    const m = new THREE.Mesh(new THREE.CircleGeometry(r, seg), new THREE.MeshBasicMaterial({ color }));
    m.position.set(x, y, z);
    return m;
  }

  const wallDist = a => 330 + 70 * Math.cos(2 * a * Math.PI / 180);
  const polar = (a, d, z = 0.03) => [d * Math.sin(a * Math.PI / 180), d * Math.cos(a * Math.PI / 180), z];

  function buildWorld() {
    const G = Z.G;
    const world = new THREE.Group();
    // ground + fair territory + dirt
    world.add(disc(470, 0xe3eadb, 0, 0, -0.02, 96));
    const fair = new THREE.Shape();
    fair.moveTo(0, 0);
    for (let a = -45; a <= 45.01; a += 1.5) { const p = polar(a, wallDist(a)); fair.lineTo(p[0], p[1]); }
    fair.lineTo(0, 0);
    const fairM = new THREE.Mesh(new THREE.ShapeGeometry(fair), new THREE.MeshBasicMaterial({ color: 0xd5e3c8 }));
    fairM.position.z = -0.01;
    world.add(fairM);
    // infield dirt: foul lines out to a 95 ft arc around the rubber (meets the lines at ±71.8° from the mound)
    const dirtArc = new THREE.Shape();
    dirtArc.moveTo(0, 0);
    for (let phi = -71.8; phi <= 71.81; phi += 2.0) {
      dirtArc.lineTo(95 * Math.sin(phi * Math.PI / 180), G.rubber_y + 95 * Math.cos(phi * Math.PI / 180));
    }
    dirtArc.lineTo(0, 0);
    const dirtM = new THREE.Mesh(new THREE.ShapeGeometry(dirtArc), new THREE.MeshBasicMaterial({ color: 0xebdfc8 }));
    dirtM.position.z = -0.005;
    world.add(dirtM);
    // infield grass square inside the bases
    const sq = 63.64;
    const grass = new THREE.Shape();
    grass.moveTo(0, 8); grass.lineTo(sq - 5, sq); grass.lineTo(0, 2 * sq - 8); grass.lineTo(-sq + 5, sq); grass.lineTo(0, 8);
    const grassM = new THREE.Mesh(new THREE.ShapeGeometry(grass), new THREE.MeshBasicMaterial({ color: 0xd5e3c8 }));
    grassM.position.z = -0.002;
    world.add(grassM);
    world.add(disc(13, 0xebdfc8, 0, 0.7, 0.0, 48));
    // mound (10 in high) + rubber
    const mound = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 9, 10 / 12, 40, 1),
      new THREE.MeshLambertMaterial({ color: 0xe4d4b6 }));
    mound.rotation.x = Math.PI / 2;
    mound.position.set(0, 59, 5 / 12);
    world.add(mound);
    const rubber = new THREE.Mesh(new THREE.BoxGeometry(2, 0.5, 0.06), new THREE.MeshLambertMaterial({ color: 0xffffff }));
    rubber.position.set(0, G.rubber_y + 0.25, 10 / 12 + 0.03);
    world.add(rubber);
    // foul lines, bases, wall
    world.add(segs([polar(-45, 0, 0.02), polar(-45, 330, 0.02), polar(45, 0, 0.02), polar(45, 330, 0.02)], 0xffffff));
    world.add(polyline([[0, 0, 0.02], [sq, sq, 0.02], [0, 2 * sq, 0.02], [-sq, sq, 0.02], [0, 0, 0.02]], 0xffffff, 0.9));
    for (const [x, y] of [[sq, sq], [0, 2 * sq], [-sq, sq]]) {
      const b = new THREE.Mesh(new THREE.PlaneGeometry(1.25, 1.25), new THREE.MeshBasicMaterial({ color: 0xffffff }));
      b.position.set(x, y, 0.04);
      b.rotation.z = Math.PI / 4;
      world.add(b);
    }
    const wallPts = [];
    for (let a = -45; a <= 45.01; a += 1.5) { const p = polar(a, wallDist(a)); wallPts.push([p[0], p[1], 0.05]); }
    const wallTop = wallPts.map(p => [p[0], p[1], 10]);
    world.add(polyline(wallPts, 0x2e5d32));
    world.add(polyline(wallTop, 0x2e5d32));
    const wallSeg = [];
    for (let i = 0; i < wallPts.length; i += 4) wallSeg.push(wallPts[i], wallTop[i]);
    world.add(segs(wallSeg, 0x2e5d32, 0.6));
    // batter's boxes (4 ft × 6 ft, 6 in from the plate), catcher's box hint
    for (const s of [-1, 1]) {
      const x0 = s * (G.plate_half_w + 0.5), x1 = s * (G.plate_half_w + 4.5);
      world.add(polyline([[x0, -2.3, 0.02], [x1, -2.3, 0.02], [x1, 3.7, 0.02], [x0, 3.7, 0.02], [x0, -2.3, 0.02]], 0xffffff));
    }
    // distance grid near the pitching lane (1 ft side ticks, 10 ft rungs)
    const grid = [];
    for (let y = 0; y <= 60; y += 5) grid.push([-4, y, 0.01], [4, y, 0.01]);
    grid.push([-4, 0, 0.01], [-4, 60, 0.01], [4, 0, 0.01], [4, 60, 0.01]);
    world.add(segs(grid, 0xb9c0b0, 0.8));
    return world;
  }

  function buildLabels() {
    labelGroup.clear();
    const G = Z.G;
    const add = (text, x, y, z, o) => { const s = makeLabel(text, o); s.position.set(x, y, z); labelGroup.add(s); };
    const near = ['side'];
    for (const y of [10, 20, 30, 40, 50]) add(`${y} ft from plate`, 4.3, y, 0.05, { size: 20, cx: 0, color: '#5c5c5c', bg: 'rgba(255,255,255,0.7)', views: near });
    add('Rubber · 60.5 ft', 1.6, G.rubber_y, 1.0, { size: 20, cx: 0, color: '#5c5c5c', views: ['catcher', 'side', 'field'] });
    add('Home plate', 0, -0.9, 0.05, { size: 20, color: '#5c5c5c', views: ['pitcher', 'side', 'field'] });
    add(`Decision point · ${G.decision_dist} ft in front of the plate`, 0, G.decision_y, 7.8, { size: 20, color: '#a35b00' });
    for (const [a, txt] of [[-45, '330 ft'], [-22.5, '380 ft'], [0, '400 ft'], [22.5, '380 ft'], [45, '330 ft']]) {
      const p = polar(a, wallDist(a)); add(txt, p[0], p[1], 14, { size: 22, color: '#2e5d32', views: ['field'] });
    }
    add('1B', 63.6 + 6, 63.6, 1, { size: 20, views: ['field'] });
    add('3B', -63.6 - 6, 63.6, 1, { size: 20, views: ['field'] });
    add('2B', 0, 127.3 + 7, 1, { size: 20, views: ['field'] });
    add('Strike zone', 0, Z.G.plate_front_y, Z.G.league_sz[1] + 0.35, { size: 20, color: '#1f4b99', views: ['side'] });
  }

  function buildZone() {
    zoneGroup.clear();
    const G = Z.G;
    const [bot, top] = Z.sz;
    const a = G.plate_half_w, f = G.plate_front_y, s = G.plate_side_y;
    const shape = new THREE.Shape();
    shape.moveTo(-a, f); shape.lineTo(a, f); shape.lineTo(a, s); shape.lineTo(0, 0); shape.lineTo(-a, s); shape.lineTo(-a, f);
    const plate = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    plate.position.z = 0.02;
    zoneGroup.add(plate);
    const plateEdge = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(shape.getPoints().map(p => new THREE.Vector3(p.x, p.y, 0.03))),
      new THREE.LineBasicMaterial({ color: 0x555555 }));
    zoneGroup.add(plateEdge);
    const geo = new THREE.ExtrudeGeometry(shape, { depth: top - bot, bevelEnabled: false });
    const vol = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: 0x1f4b99, transparent: true, opacity: 0.13, depthWrite: false, side: THREE.DoubleSide }));
    vol.position.z = bot;
    vol.renderOrder = 2;
    zoneGroup.add(vol);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0x1f4b99, transparent: true, opacity: 0.9 }));
    edges.position.z = bot;
    zoneGroup.add(edges);
    // front plane (the 2D zone) outline + thirds
    const fr = [];
    for (const t of [1 / 3, 2 / 3]) {
      const z = bot + t * (top - bot);
      fr.push([-a, f, z], [a, f, z]);
      const x = -a + t * 2 * a;
      fr.push([x, f, bot], [x, f, top]);
    }
    zoneGroup.add(segs(fr, 0x1f4b99, 0.35));
    // drop lines from zone corners to the plate for depth cues
    zoneGroup.add(segs([[-a, f, 0.03], [-a, f, bot], [a, f, 0.03], [a, f, bot], [0, 0, 0.03], [0, 0, bot]], 0x1f4b99, 0.25));
  }

  function buildBatter() {
    batterGroup.clear();
    const [bot, top] = Z.sz;
    const side = Z.stand === 'L' ? 1 : -1; // RHH on the 3B side (x < 0)
    const cx = side * 2.55;
    const mat = new THREE.MeshLambertMaterial({ color: 0x8a909c, transparent: true, opacity: 0.32, depthWrite: false });
    const scale = (top - bot) / 1.7;
    const knee = bot + 0.1, hip = knee + 1.3 * scale, shoulder = top + 1.05 * scale;
    const add = (geo, x, y, z, rx = 0) => { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); m.rotation.x = rx; batterGroup.add(m); return m; };
    for (const dy of [-0.75, 0.95]) add(new THREE.CylinderGeometry(0.2, 0.17, hip, 12), cx, 0.7 + dy, hip / 2, Math.PI / 2);
    add(new THREE.BoxGeometry(0.75, 1.15, shoulder - hip), cx, 0.75, (shoulder + hip) / 2);
    add(new THREE.SphereGeometry(0.42, 16, 12), cx, 0.75, shoulder + 0.55);
    const bat = add(new THREE.CylinderGeometry(0.06, 0.03, 2.8, 8), cx - side * 0.1, 0.0, shoulder + 0.55);
    bat.rotation.set(Math.PI / 2 + 0.6, 0, side * 0.3);
    const lab = makeLabel(Z.stand === 'L' ? 'LHH (bats left, 1B side)' : 'RHH (bats right, 3B side)', { size: 20, color: '#3a3a3a' });
    lab.position.set(cx + side * 0.4, 0.7, shoulder + 1.45);
    lab.visible = $('z3-show-labels').checked;
    batterGroup.add(lab);
  }

  function buildDecisionPlane() {
    dpGroup.clear();
    const G = Z.G;
    const w = 7, h = 7.5;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: 0xf08c00, transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false }));
    m.rotation.x = Math.PI / 2;
    m.position.set(0, G.decision_y, h / 2);
    dpGroup.add(m);
    dpGroup.add(polyline([[-w / 2, G.decision_y, 0], [w / 2, G.decision_y, 0], [w / 2, G.decision_y, h], [-w / 2, G.decision_y, h], [-w / 2, G.decision_y, 0]], 0xd27800, 0.8));
    dpGroup.visible = $('z3-show-dp').checked;
  }

  function disposeGroup(g) {
    g.traverse(o => { if (o.geometry) o.geometry.dispose(); });
    g.clear();
  }

  function pathPositions(r, n) {
    const arr = new Float32Array(n * 3);
    for (let k = 0; k < n; k++) {
      posAt(r, r.tr + (k / (n - 1)) * r.flight, tmpV);
      arr[3 * k] = tmpV.x; arr[3 * k + 1] = tmpV.y; arr[3 * k + 2] = tmpV.z;
    }
    return arr;
  }

  function arcPositions(r, n) {
    const G = Z.G;
    const sx = r.fx, sy = G.contact_y, sz = Math.min(Math.max(r.fz, 0.4), 5);
    const ex = r.lx, ey = r.ly;
    const v = (r.ls || 80) * 1.46667, la = (r.la == null ? 15 : r.la) * Math.PI / 180;
    const vacApex = Math.max(Math.pow(v * Math.sin(la), 2) / (2 * 32.174), 0);
    const arr = new Float32Array(n * 3);
    const groundish = r.la == null || r.la <= 10;
    const sLand = r.la != null && r.la > 0 ? 0.3 : 0.05;
    const H = groundish ? Math.min(vacApex * 0.6, 4) : vacApex * 0.72;
    const p = 1.35, fmax = Math.pow(p / (p + 1), p) * (1 / (p + 1));
    for (let k = 0; k < n; k++) {
      const s = k / (n - 1);
      let z;
      if (groundish) {
        const u = s / sLand;
        z = s < sLand ? sz * (1 - u) + 4 * H * u * (1 - u) : 0.05;
      } else {
        z = sz * (1 - s) + H * Math.pow(s, p) * (1 - s) / fmax;
      }
      arr[3 * k] = sx + (ex - sx) * s; arr[3 * k + 1] = sy + (ey - sy) * s; arr[3 * k + 2] = Math.max(z, 0.05);
    }
    return arr;
  }

  function buildPitches() {
    stopPlayback(false);
    disposeGroup(pathGroup); disposeGroup(arcGroup); disposeGroup(markGroup);
    if (ballMesh) { scene.remove(ballMesh); ballMesh.geometry.dispose(); ballMesh = null; }
    pathLines = [];
    const vis = Z.vis;
    const flags = $('z3-show-flags').checked;
    const pick = new Float32Array(vis.length * N_PICK * 3 * 2);
    const markPos = [], markCol = [];
    const ringPos = { 2: [], 3: [], 4: [] };
    vis.forEach((r, i) => {
      const pos = pathPositions(r, N_PATH);
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      const flagged = flags && (r.z3 === 2 || r.z3 === 3 || r.z3 === 4);
      const line = new THREE.Line(g, lineMat(ptColor(r.pt), flagged, flagged ? 0.95 : 0.72));
      if (flagged) line.computeLineDistances();
      line.userData.i = i;
      pathGroup.add(line);
      pathLines.push(line);
      for (let k = 0; k < N_PICK; k++) {
        const src = Math.round(k * (N_PATH - 1) / (N_PICK - 1));
        pick.set(pos.subarray(3 * src, 3 * src + 3), (i * N_PICK + k) * 3);
      }
      markPos.push(r.fx, Z.G.plate_front_y, r.fz);
      const c = new THREE.Color(ptColor(r.pt));
      markCol.push(c.r, c.g, c.b);
      if (flagged) ringPos[r.z3].push(r.fx, Z.G.plate_front_y, r.fz);
      if (r.res === 'IP' && r.lx != null) {
        const apos = arcPositions(r, N_ARC);
        const ag = new THREE.BufferGeometry();
        ag.setAttribute('position', new THREE.BufferAttribute(apos, 3));
        const arc = new THREE.Line(ag, lineMat(BB_COLORS[r.bb] || '#555555', false, 0.6));
        arc.userData.i = i;
        arcGroup.add(arc);
        const land = new THREE.Mesh(new THREE.CircleGeometry(1.6, 16), new THREE.MeshBasicMaterial({ color: BB_COLORS[r.bb] || '#555555', transparent: true, opacity: 0.75 }));
        land.position.set(r.lx, r.ly, 0.06);
        arcGroup.add(land);
        for (let k = 0; k < N_PICK; k++) {
          const src = Math.round(k * (N_ARC - 1) / (N_PICK - 1));
          pick.set(apos.subarray(3 * src, 3 * src + 3), (vis.length * N_PICK + i * N_PICK + k) * 3);
        }
      } else {
        for (let k = 0; k < N_PICK; k++) pick[(vis.length * N_PICK + i * N_PICK + k) * 3] = NaN;
      }
    });
    pickPts = pick;
    const mg = new THREE.BufferGeometry();
    mg.setAttribute('position', new THREE.Float32BufferAttribute(markPos, 3));
    mg.setAttribute('color', new THREE.Float32BufferAttribute(markCol, 3));
    markGroup.add(new THREE.Points(mg, new THREE.PointsMaterial({ size: 7, sizeAttenuation: false, vertexColors: true, map: DOT_TEX, transparent: true, alphaTest: 0.3 })));
    for (const code of [2, 3, 4]) {
      if (!ringPos[code].length) continue;
      const rg = new THREE.BufferGeometry();
      rg.setAttribute('position', new THREE.Float32BufferAttribute(ringPos[code], 3));
      const pm = new THREE.Points(rg, new THREE.PointsMaterial({ size: 17, sizeAttenuation: false, color: FLAG_COLORS[code], map: RING_TEX, transparent: true, alphaTest: 0.3, depthTest: false }));
      pm.renderOrder = 15;
      markGroup.add(pm);
    }
    ballMesh = new THREE.InstancedMesh(new THREE.SphereGeometry(Z.G.ball_r, 16, 12), new THREE.MeshLambertMaterial({ color: 0xffffff }), Math.max(vis.length, 1));
    vis.forEach((r, i) => { ballMesh.setColorAt(i, new THREE.Color(ptColor(r.pt))); });
    tmpM.makeScale(0, 0, 0);
    for (let i = 0; i < ballMesh.count; i++) ballMesh.setMatrixAt(i, tmpM);
    ballMesh.instanceMatrix.needsUpdate = true;
    if (ballMesh.instanceColor) ballMesh.instanceColor.needsUpdate = true;
    ballMesh.frustumCulled = false;
    scene.add(ballMesh);
    pathGroup.visible = !Z.tunnel;
    applyViewVisibility();
    needsRender = true;
  }

  function buildTunnel() {
    disposeGroup(tunnelGroup);
    const T = Z.data.tunnel;
    if (!T || !T.types.length) return;
    for (const t of T.types) {
      const [x0, z0, vx, vy, vz, ax, ay, az, yr] = t.coef;
      const r = { x0, z0, vx, vy, vz, ax, ay, az, yr };
      r.tr = tAtY(r, yr); r.flight = tAtY(r, 0) - r.tr;
      const pts = [];
      for (let k = 0; k < 40; k++) pts.push(posAt(r, r.tr + (k / 39) * r.flight, new THREE.Vector3()));
      const tube = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 80, 0.045, 8, false),
        new THREE.MeshLambertMaterial({ color: ptColor(t.pt) }));
      tunnelGroup.add(tube);
      const dp = new THREE.Mesh(new THREE.SphereGeometry(Z.G.ball_r, 16, 12), new THREE.MeshLambertMaterial({ color: ptColor(t.pt) }));
      dp.position.set(t.dp[0], Z.G.decision_y, t.dp[1]);
      tunnelGroup.add(dp);
      const lab = makeLabel(t.pt, { size: 22, weight: 600, color: ptColor(t.pt) });
      lab.position.set(t.plate[0], Z.G.plate_front_y, t.plate[1] - 0.25);
      tunnelGroup.add(lab);
    }
  }

  // ---------------------------------------------------------------- selection

  function selectPitch(i) {
    disposeGroup(selGroup);
    const r = Z.vis[i];
    Z.selected = r ? i : -1;
    dimOthers(!!r);
    if (!r) { renderPanel(null); needsRender = true; return; }
    const pts = [];
    for (let k = 0; k < 60; k++) pts.push(posAt(r, r.tr + (k / 59) * r.flight, new THREE.Vector3()));
    selGroup.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 120, 0.03, 8, false),
      new THREE.MeshLambertMaterial({ color: ptColor(r.pt), emissive: 0x222222 })));
    const ball = new THREE.Mesh(new THREE.SphereGeometry(Z.G.ball_r, 20, 16), new THREE.MeshLambertMaterial({ color: 0xffffff, emissive: 0x333333 }));
    ball.position.set(r.fx, Z.G.plate_front_y, r.fz);
    selGroup.add(ball);
    const seam = new THREE.Mesh(new THREE.TorusGeometry(Z.G.ball_r * 1.02, 0.008, 6, 24), new THREE.MeshBasicMaterial({ color: 0xc0392b }));
    seam.position.copy(ball.position);
    selGroup.add(seam);
    const ghostMat = new THREE.MeshLambertMaterial({ color: ptColor(r.pt), transparent: true, opacity: 0.35, depthWrite: false });
    for (const frac of [0.25, 0.5, 0.75, 1]) {
      const g = new THREE.Mesh(new THREE.SphereGeometry(Z.G.ball_r, 16, 12), ghostMat);
      posAt(r, tAtY(r, Z.G.plate_front_y * (1 - frac)), g.position);
      selGroup.add(g);
    }
    if (r.res === 'IP' && r.lx != null) {
      const a = arcPositions(r, 80);
      const ap = [];
      for (let k = 0; k < 80; k++) ap.push(new THREE.Vector3(a[3 * k], a[3 * k + 1], a[3 * k + 2]));
      const col = BB_COLORS[r.bb] || '#555555';
      const arcSel = new THREE.Group();
      arcSel.userData.fieldOnly = true;
      arcSel.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(ap), 160, 0.9, 8, false), new THREE.MeshLambertMaterial({ color: col })));
      const ring = new THREE.Mesh(new THREE.RingGeometry(3.5, 5.5, 32), new THREE.MeshBasicMaterial({ color: col, side: THREE.DoubleSide }));
      ring.position.set(r.lx, r.ly, 0.08);
      arcSel.add(ring);
      const lab = makeLabel(`${BB_NAMES[r.bb] || 'Batted ball'} · ${fmt(r.ls, 1)} mph, ${fmt(r.la, 0)}° → ${fmt(r.dist, 0)} ft`, { size: 22, weight: 600, color: col });
      lab.position.set(r.lx, r.ly, 18);
      arcSel.add(lab);
      selGroup.add(arcSel);
      applyViewVisibility();
    }
    renderPanel(r);
    document.querySelectorAll('.z3-ex').forEach(b => b.classList.toggle('active', Number(b.dataset.row) === r.rowId));
    needsRender = true;
  }

  function onClick(ev) {
    if (!pickPts || !Z.vis.length) return;
    const rect = renderer.domElement.getBoundingClientRect();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    const W = rect.width, H = rect.height;
    const nv = Z.vis.length;
    let best = -1, bestD = 14;
    const arcsOn = arcGroup.visible;
    const proj = (o, out) => {
      tmpV.set(pickPts[o], pickPts[o + 1], pickPts[o + 2]).project(camera);
      if (tmpV.z > 1 || tmpV.z < -1) return false;
      out.set((tmpV.x + 1) * W / 2, (1 - tmpV.y) * H / 2, 0);
      return true;
    };
    const a = new THREE.Vector2(), b = new THREE.Vector2();
    for (let blk = 0; blk < 2; blk++) {
      if (blk === 1 && !arcsOn) break;
      if (blk === 0 && Z.tunnel) continue;
      for (let i = 0; i < nv; i++) {
        const base = (blk * nv * N_PICK + i * N_PICK) * 3;
        if (isNaN(pickPts[base])) continue;
        let okPrev = proj(base, tmpV2); a.set(tmpV2.x, tmpV2.y);
        for (let k = 1; k < N_PICK; k++) {
          const ok = proj(base + 3 * k, tmpV2); b.set(tmpV2.x, tmpV2.y);
          if (ok && okPrev) {
            const dx = b.x - a.x, dy = b.y - a.y;
            const L2 = dx * dx + dy * dy || 1;
            const u = Math.max(0, Math.min(1, ((mx - a.x) * dx + (my - a.y) * dy) / L2));
            const d = Math.hypot(a.x + u * dx - mx, a.y + u * dy - my);
            if (d < bestD) { bestD = d; best = i; }
          }
          a.copy(b); okPrev = ok;
        }
      }
    }
    selectPitch(best);
  }

  // ---------------------------------------------------------------- cameras

  function standForCam() { return Z.stand; }

  function setCamera(name) {
    if (!CAMS[name]) throw new Error(`Unknown camera ${name}`);
    Z.view = name;
    const G = Z.G;
    const mid = (Z.sz[0] + Z.sz[1]) / 2;
    const side = standForCam() === 'L' ? 1 : -1;
    let pos, tgt;
    if (name === 'catcher') { pos = [0, -6.2, mid + 0.75]; tgt = [0, 20, mid + 0.55]; }
    else if (name === 'batter') { pos = [side * 2.3, -2.6, Z.sz[1] + 1.9]; tgt = [-side * 0.4, 7, 2.6]; }
    else if (name === 'pitcher') { pos = [0, 68, 6.4]; tgt = [0, 0, mid]; }
    else if (name === 'side') { pos = [75, 14, mid + 0.4]; tgt = [0, 14, mid + 0.4]; }
    else if (name === 'zone') { pos = [4.6, 6.2, Z.sz[1] + 2.2]; tgt = [0, 0.7, mid]; }
    else { pos = [0, -160, 205]; tgt = [0, 175, 0]; }
    camera.fov = CAMS[name].fov;
    camera.near = name === 'field' ? 1 : 0.05;
    camera.far = 3000;
    camera.updateProjectionMatrix();
    camera.position.set(...pos);
    controls.target.set(...tgt);
    controls.update();
    applyViewVisibility();
    document.querySelectorAll('[data-cam]').forEach(b => b.classList.toggle('active', b.dataset.cam === name));
    renderHud();
    renderText();
    needsRender = true;
  }

  function setTunnel(on) {
    Z.tunnel = !!on;
    $('z3-tunnel-btn').classList.toggle('active', Z.tunnel);
    if (Z.tunnel) {
      buildTunnel();
      $('z3-show-dp').checked = true;
      dpGroup.visible = true;
      setCamera('batter');
    }
    tunnelGroup.visible = Z.tunnel;
    pathGroup.visible = !Z.tunnel;
    markGroup.visible = !Z.tunnel;
    applyViewVisibility();
    renderHud();
    renderText();
    needsRender = true;
  }

  // ---------------------------------------------------------------- playback

  function setDraw(i, count) { pathLines[i].geometry.setDrawRange(0, count); }
  function hideBall(i) { tmpM.makeScale(0, 0, 0); ballMesh.setMatrixAt(i, tmpM); }
  function placeBall(i, r, t) {
    posAt(r, t, tmpV);
    tmpS.set(1, 1, 1);
    tmpM.compose(tmpV, tmpQ, tmpS);
    ballMesh.setMatrixAt(i, tmpM);
  }

  function startPlayback() {
    if (!Z.vis.length) return;
    if (Z.tunnel) setTunnel(false);
    Z.playing = true;
    Z.play.active = true;
    Z.play.seq = 0; Z.play.tau = 0; Z.play.hold = 0;
    pathLines.forEach((l, i) => { setDraw(i, Z.mode === 'seq' ? 0 : 1); hideBall(i); });
    ballMesh.instanceMatrix.needsUpdate = true;
    applyViewVisibility();
    $('z3-play').textContent = '❚❚ Pause';
    needsRender = true;
  }
  function pausePlayback() {
    Z.playing = false;
    $('z3-play').textContent = '▶ Play';
  }
  function stopPlayback(render = true) {
    Z.playing = false;
    Z.play.active = false;
    if ($('z3-play')) $('z3-play').textContent = '▶ Play';
    pathLines.forEach((l, i) => { setDraw(i, Infinity); if (ballMesh) hideBall(i); });
    if (ballMesh) ballMesh.instanceMatrix.needsUpdate = true;
    if (arcGroup) applyViewVisibility();
    $('z3-clock').textContent = '';
    if (render) needsRender = true;
  }

  function stepPlayback(dtReal) {
    const vis = Z.vis;
    const dt = dtReal * Z.speed;
    if (Z.mode === 'seq') {
      if (Z.play.hold > 0) {
        Z.play.hold -= dtReal;
        if (Z.play.hold <= 0) { Z.play.seq = (Z.play.seq + 1) % vis.length; Z.play.tau = 0; if (Z.play.seq === 0) pathLines.forEach((l, i) => setDraw(i, 0)); }
        return;
      }
      const i = Z.play.seq, r = vis[i];
      Z.play.tau += dt;
      const u = Math.min(Z.play.tau / r.flight, 1);
      setDraw(i, Math.max(2, Math.floor(u * (N_PATH - 1)) + 1));
      placeBall(i, r, r.tr + u * r.flight);
      ballMesh.instanceMatrix.needsUpdate = true;
      $('z3-clock').textContent = `Pitch ${i + 1} of ${vis.length} · ${r.pt} ${fmt(r.v)} mph · t = ${(u * r.flight).toFixed(3)} s after release`;
      if (u >= 1) { Z.play.hold = GAP_S; hideBall(i); setDraw(i, Infinity); }
    } else {
      if (Z.play.hold > 0) {
        Z.play.hold -= dtReal;
        if (Z.play.hold <= 0) { Z.play.tau = 0; vis.forEach((r, i) => setDraw(i, 1)); }
        return;
      }
      Z.play.tau += dt;
      let maxU = 0;
      vis.forEach((r, i) => {
        const u = Math.min(Z.play.tau / r.flight, 1);
        maxU = Math.max(maxU, u < 1 ? u : 0);
        setDraw(i, Math.max(2, Math.floor(u * (N_PATH - 1)) + 1));
        if (u < 1) placeBall(i, r, r.tr + u * r.flight); else hideBall(i);
      });
      ballMesh.instanceMatrix.needsUpdate = true;
      $('z3-clock').textContent = `All ${vis.length} pitches released together · t = ${Z.play.tau.toFixed(3)} s`;
      if (vis.every(r => Z.play.tau >= r.flight)) Z.play.hold = 1.2;
    }
  }

  // ---------------------------------------------------------------- 2D panels

  const ordinalDate = d => { const dt = new Date(`${d}T12:00:00`); return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); };

  function sideWord(hbIn, pThrows) {
    const arm = (pThrows === 'L') === (hbIn > 0);
    return `${fmt(Math.abs(hbIn), 1)}" ${arm ? 'arm-side' : 'glove-side'}`;
  }

  function p2fLink(r) {
    if (!r.ppt || !r.zid) return '<p class="empty-p">No Pitch-to-Field link for this pitch type / location.</p>';
    const q = new URLSearchParams({ batter_id: r.b, stand: r.st, pitch_type: r.ppt, zone: r.zid });
    const href = `${isStatic() ? 'pitch-to-field.html' : '/field'}?${q}`;
    if (isStatic() && !(Z.meta.demo_batter_ids || []).includes(r.b)) {
      return `<p class="empty-p">${esc(r.batterName)} is not in the static Pitch-to-Field demo; run <code>uv run pitch-dataset select-web</code> for all hitters.</p>`;
    }
    return `<p><a href="${href}">Where does ${esc(r.batterName)} hit a ${esc(r.ppt)} in this zone (${esc(r.zid.replace(/_/g, ' '))})? → Pitch-to-Field</a></p>`;
  }

  function renderPanel(r) {
    const el = $('z3-panel');
    if (!r) {
      el.innerHTML = `<h2>Pitch details</h2><p class="empty-p">Click any pitch path (or a batted-ball arc) in the 3D view to see its velocity,
        movement, location, how the umpire's call compares with the 3D zone, and — if it was put in play — the batted ball.</p>
        <p class="empty-p">Flagged examples are listed under <em>Back of the zone</em> below.</p>`;
      return;
    }
    const pThrows = Z.data.pitcher.p_throws;
    const z3 = Z.meta.z3_labels[String(r.z3)];
    const called = r.z3 > 0;
    const kv = rows => `<div class="kv">${rows.map(([k, v]) => `<span class="k">${k}</span><span>${v}</span>`).join('')}</div>`;
    const pull = r.spr == null ? '' : (Math.abs(r.spr) < 15 ? 'center' : ((r.spr < 0) === (r.st === 'R') ? 'pull side' : 'opposite field'));
    el.innerHTML = `
      <h2><span class="z3-chip" style="background:${ptColor(r.pt)}"></span>${esc(Z.meta.pitch_names[r.pt] || r.pt)} · ${fmt(r.v)} mph</h2>
      <p class="tag">${esc(ordinalDate(r.d))} · vs ${esc(r.batterName)} (${r.st === 'L' ? 'LHH' : 'RHH'}) · count ${r.bl}-${r.sk}</p>
      <div class="sec">Result</div>
      <p style="margin:0;color:var(--fg)">${esc(Z.meta.result_labels[r.res] || r.res)}${r.desc ? ` <span class="tag">(${esc(r.desc.replace(/_/g, ' '))})</span>` : ''}${r.evt ? ` → <strong>${esc(r.evt.replace(/_/g, ' '))}</strong>` : ''}</p>
      <div class="sec">Pitch</div>
      ${kv([
        ['Spin', r.sp == null ? '–' : `${r.sp.toLocaleString()} rpm`],
        ['IVB', `${fmt(r.ivb)}" (induced vertical break)`],
        ['HB', r.hb == null ? '–' : sideWord(r.hb, pThrows)],
        ['Plate (Statcast)', `x ${fmt(r.px * 12, 1)}" from center, z ${fmt(r.pz, 2)} ft`],
        ['Front edge', `x ${fmt(r.fx * 12, 1)}", z ${fmt(r.fz, 2)} ft (reconstructed)`],
        ['Zone (batter)', `${fmt(r.bot, 2)}–${fmt(r.top, 2)} ft · ${esc((r.zid || '–').replace(/_/g, ' '))}`],
      ])}
      <div class="sec">Call vs 3D zone</div>
      <div class="call ${r.z3 >= 2 && r.z3 <= 4 ? 'flag' : ''}">${called ? esc(z3) : 'Not a called pitch (batter swung or was hit).'}
        <br><span class="tag">Front-plane test: ${r.f2 ? 'in' : (r.mf < 0.05 ? 'out, on the edge' : `out by ${fmt(r.mf)}"`)} · 3D volume: ${r.h3 ? `touched (${fmt(-r.m3)}" overlap)` : `missed by ${fmt(r.m3)}"`}</span></div>
      ${r.res === 'IP' ? `<div class="sec">Batted ball</div>${kv([
        ['Exit velo', `${fmt(r.ls)} mph`], ['Launch angle', `${fmt(r.la, 0)}°`], ['Distance', `${fmt(r.dist, 0)} ft`],
        ['Spray', r.spr == null ? '–' : `${fmt(Math.abs(r.spr), 0)}° ${r.spr < 0 ? 'toward LF' : 'toward RF'} (${pull})`],
        ['Type', esc(BB_NAMES[r.bb] || '–')], ['xwOBA', r.xw == null ? '–' : r.xw.toFixed(3)],
      ])}<p class="tag">Arc shape is approximate; endpoints are measured.</p>` : ''}
      <div class="sec">Pitch-to-Field</div>${p2fLink(r)}`;
  }

  function renderHud() {
    const cam = CAMS[Z.view];
    const extra = Z.tunnel ? ' · <strong>Tunnel view</strong>: thick lines are each pitch type\'s average path; dots on the orange plane are where they sit at the decision point.' : '';
    $('z3-hud').innerHTML = `<strong>${esc(cam.label)}</strong>${extra}<br><span class="tag">Drag to orbit · scroll to zoom · right-drag to pan · click a path for details. Scene units: feet.</span>`;
  }

  function renderLegend() {
    const counts = {};
    Z.vis.forEach(r => { counts[r.pt] = (counts[r.pt] || 0) + 1; });
    const pts = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
    const ptItems = pts.map(pt => `<span><span class="sw" style="background:${ptColor(pt)}"></span>${esc(pt)} ${esc(Z.meta.pitch_names[pt] || '')} (${counts[pt]})</span>`).join('');
    const bb = Object.keys(BB_COLORS).map(k => `<span><span class="sw" style="background:${BB_COLORS[k]};height:4px"></span>${BB_NAMES[k]}</span>`).join('');
    const flags = [2, 3, 4].map(c => `<span><span class="ring" style="border-color:${FLAG_COLORS[c]}"></span>${FLAG_SHORT[c]}</span>`).join('');
    $('z3-legend').innerHTML = `<span class="grp">Pitch type</span>${ptItems}
      <span class="grp">Calls</span><span><span class="sw dash"></span>dashed path = flagged call</span>${flags}
      <span class="grp">Batted balls</span>${bb}
      <span class="grp">Scene</span><span><span class="box" style="background:rgba(31,75,153,.15);border-color:#1f4b99"></span>3D strike zone (${fmt(Z.sz[0], 2)}–${fmt(Z.sz[1], 2)} ft)</span>
      <span><span class="box" style="background:rgba(240,140,0,.15);border-color:#d27800"></span>Decision point (${Z.G.decision_dist} ft)</span>`;
  }

  function renderText() {
    if (!Z.data) return;
    const p = Z.data.pitcher;
    const f = Z.f;
    const bits = [];
    if (f.pt !== 'all') bits.push(Z.meta.pitch_names[f.pt] || f.pt);
    if (f.batter !== 'all') bits.push(`vs ${batterName(f.batter)}`);
    if (f.count !== 'all') bits.push(`count: ${(COUNT_LABELS.find(c => c[0] === f.count) || [0, f.count])[1]}`);
    if (f.result !== 'all') bits.push((RESULT_OPTS.find(c => c[0] === f.result) || [0, f.result])[1].toLowerCase());
    const nReg = Z.vis.filter(r => !r.ex).length;
    const nEx = Z.vis.length - nReg;
    $('z3-title').textContent = `${p.name} (${p.p_throws}HP) · ${Z.meta.seasons.join('+')} · ${Z.vis.length} pitches${bits.length ? ' · ' + bits.join(', ') : ''} · ${CAMS[Z.view].label}`;
    const pool = isStatic() ? `${Z.rows.length} sampled for this demo out of ${Z.data.n_total.toLocaleString()} thrown` : `${Z.data.n_match.toLocaleString()} match the filters out of ${Z.data.n_total.toLocaleString()} thrown`;
    $('z3-subtitle').textContent = `Drawing ${nReg} pitches (${pool})${nEx ? ` + ${nEx} flagged 3D-call examples` : ''}. Units: feet in the scene; movement and separations in inches; velocity in mph. Zone volume: ${Z.f.batter !== 'all' ? "this batter's average" : "his opponents' average"} sz_bot–sz_top.`;
    $('z3-read').innerHTML = `<strong>How to read this:</strong> ${esc(VIEW_NOTES[Z.view])} Colors are pitch types; a dot marks where each pitch crosses the front edge of the plate. Playback at 1× is real time (~0.4 s release to plate).`;
    renderLegend();
    renderTakeaway();
  }

  function batterName(id) {
    const hit = Z.data.batters[String(id)];
    if (hit) return hit[0];
    const live = (Z.liveBatters || []).find(b => String(b.id) === String(id));
    return live ? live.name : String(id);
  }

  function renderTakeaway() {
    const items = [...(Z.data.takeaways || [])];
    const vis = Z.vis.filter(r => !r.ex);
    const f = Z.f;
    if (f.pt !== 'all' && vis.length) {
      const m = k => vis.reduce((s, r) => s + (r[k] || 0), 0) / vis.length;
      items.unshift(`Shown ${f.pt} (${vis.length}): ${fmt(m('v'))} mph, ${fmt(m('ivb'))}" induced vertical break, ${sideWord(m('hb'), Z.data.pitcher.p_throws)} horizontal break.`);
    }
    const ip = vis.filter(r => r.res === 'IP' && r.ls != null);
    if (ip.length >= 5) {
      const hard = ip.filter(r => r.ls >= 95).length;
      items.push(`${ip.length} of the drawn pitches were put in play; ${hard} (${Math.round(100 * hard / ip.length)}%) left the bat at 95+ mph.`);
    }
    $('z3-takeaway').innerHTML = `<span class="k">Takeaways · tunneling and 3D-call counts use his full season</span>${items.map(t => `<div>• ${esc(t)}</div>`).join('')}`;
  }

  function renderTunnel() {
    const T = Z.data.tunnel;
    const el = $('z3-tunnel');
    if (!T || T.types.length < 2) { el.innerHTML = '<h2>Tunneling</h2><p class="empty">Needs at least two pitch types with enough pitches.</p>'; return; }
    const best = T.best;
    const panel = (title, key, showZone) => {
      const W = 240, H = 240;
      const xs = T.types.map(t => t[key][0] * 12), zs = T.types.map(t => t[key][1] * 12);
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cz = (Math.min(...zs) + Math.max(...zs)) / 2;
      const half = Math.max(15, Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs)) * 0.5 + 8;
      const sc = (W / 2 - 14) / half;
      const X = x => W / 2 + (x - cx) * sc, Y = z => H / 2 - (z - cz) * sc;
      let g = '';
      for (let v = Math.ceil((cx - half) / 6) * 6; v <= cx + half; v += 6) g += `<line x1="${X(v)}" y1="0" x2="${X(v)}" y2="${H}" stroke="#ececea"/>`;
      for (let v = Math.ceil((cz - half) / 6) * 6; v <= cz + half; v += 6) g += `<line x1="0" y1="${Y(v)}" x2="${W}" y2="${Y(v)}" stroke="#ececea"/>`;
      if (showZone) {
        const a = Z.G.plate_half_w * 12;
        g += `<rect x="${X(-a)}" y="${Y(Z.sz[1] * 12)}" width="${2 * a * sc}" height="${(Z.sz[1] - Z.sz[0]) * 12 * sc}" fill="rgba(31,75,153,.08)" stroke="#1f4b99"/>`;
      }
      if (best) {
        const A = T.types.find(t => t.pt === best.a), B = T.types.find(t => t.pt === best.b);
        g += `<line x1="${X(A[key][0] * 12)}" y1="${Y(A[key][1] * 12)}" x2="${X(B[key][0] * 12)}" y2="${Y(B[key][1] * 12)}" stroke="#111" stroke-dasharray="3 2"/>`;
        const d = key === 'dp' ? best.dp_in : best.plate_in;
        g += `<text x="${W - 6}" y="${H - 8}" text-anchor="end" font-size="11" fill="#111">${best.a}–${best.b}: ${d.toFixed(1)}"</text>`;
      }
      T.types.forEach(t => {
        g += `<circle cx="${X(t[key][0] * 12)}" cy="${Y(t[key][1] * 12)}" r="6" fill="${ptColor(t.pt)}" stroke="#fff"/>` +
          `<text x="${X(t[key][0] * 12) + 8}" y="${Y(t[key][1] * 12) + 4}" font-size="11" font-weight="600" fill="${ptColor(t.pt)}">${t.pt}</text>`;
      });
      g += `<line x1="10" y1="${H - 26}" x2="${10 + 6 * sc}" y2="${H - 26}" stroke="#333" stroke-width="2"/><text x="10" y="${H - 12}" font-size="10" fill="#555">6 in</text>`;
      return `<svg viewBox="0 0 ${W} ${H + 22}" role="img" aria-label="${esc(title)}"><text x="${W / 2}" y="${H + 16}" text-anchor="middle" font-size="12" font-weight="600" fill="#333">${esc(title)}</text>${g}</svg>`;
    };
    const rows = T.pairs.slice(0, 8).map(p => `<tr class="${best && p.a === best.a && p.b === best.b ? 'best' : ''}">
      <td><span class="z3-chip" style="background:${ptColor(p.a)}"></span>${p.a} / <span class="z3-chip" style="background:${ptColor(p.b)}"></span>${p.b}</td>
      <td class="num">${p.release_in.toFixed(1)}"</td><td class="num">${p.dp_in.toFixed(1)}"</td><td class="num">${p.plate_in.toFixed(1)}"</td><td class="num">${p.ratio.toFixed(1)}×</td></tr>`).join('');
    el.innerHTML = `<h2>Tunneling: same look at the decision point, different spot at the plate</h2>
      <p class="tag">Catcher's view of each pitch type's <em>mean</em> position (full season, ${T.n.toLocaleString()} pitches) on a plane ${Z.G.decision_dist} ft in front of the plate
        (~${T.commit_ms || 170} ms before it arrives) vs at the front of the plate. Grid = 6 in. Pitch types with ≥5% usage.</p>
      <div class="z3-insets">${panel(`At decision point (${Z.G.decision_dist} ft out)`, 'dp', false)}${panel('At the front of the plate', 'plate', true)}</div>
      <table class="z3-tbl"><thead><tr><th>Pair</th><th class="num">Release</th><th class="num">Decision pt</th><th class="num">Plate</th><th class="num">Plate ÷ decision</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="tag" style="margin-top:6px">Separations are distances between mean positions, in inches. A big plate ÷ decision ratio means the two pitches look alike when the hitter must commit and then split apart. <a href="#" id="z3-tunnel-link">Open tunnel view in 3D →</a></p>`;
    $('z3-tunnel-link').addEventListener('click', e => { e.preventDefault(); setTunnel(true); $('z3-stage').scrollIntoView({ behavior: 'smooth', block: 'center' }); });
  }

  function renderBackZone() {
    const bz = Z.data.back_zone, lg = Z.meta.back_zone;
    const pctOf = (n, d) => (d ? `${(100 * n / d).toFixed(1)}%` : '–');
    const ex = bz.examples.map(e => {
      const what = e.z3 === 2 ? `Called strike · ${fmt(e.front_miss_in)}" outside the front plane, ${fmt(-e.clear3d_in)}" into the zone behind it`
        : e.z3 === 4 ? `Called ball · path overlapped the 3D zone by ${fmt(-e.clear3d_in)}" behind the front plane`
          : `Called strike · missed the 3D zone by ${fmt(e.clear3d_in)}"`;
      return `<button type="button" class="z3-ex" data-row="${e.row}"><span class="ring" style="display:inline-block;width:10px;height:10px;border-radius:50%;border:2px solid ${FLAG_COLORS[e.z3]};margin-right:5px;vertical-align:middle"></span><span class="t">${esc(ordinalDate(e.date))} · ${esc(e.pt)} to ${esc(e.batter)} (${e.count})</span><br><span class="s">${esc(what)}</span></button>`;
    }).join('');
    $('z3-backzone').innerHTML = `<h2>Back of the zone: 3D calls vs the front-plane box</h2>
      <p class="tag">Rule book: a strike is any part of the ball passing through any part of the zone — a 3D volume, not the flat front plane most zone charts show.
        Each called pitch's path is tested against the pentagon prism (expanded by the ball's 1.45" radius) through the plate's full 17" depth.</p>
      <div class="z3-counts"><span class="h"></span><span class="h r">${esc(Z.data.pitcher.name.split(' ').slice(-1)[0])}</span><span class="h r">MLB</span>
        <span>Called strikes</span><span class="r">${bz.n_called_strikes.toLocaleString()}</span><span class="r">${lg.n_called_strikes.toLocaleString()}</span>
        <span><span class="ring" style="display:inline-block;width:9px;height:9px;border-radius:50%;border:2px solid ${FLAG_COLORS[2]}"></span> missed front plane, clipped 3D zone</span><span class="r">${bz.strike_back_only} (${pctOf(bz.strike_back_only, bz.n_called_strikes)})</span><span class="r">${lg.strike_back_only.toLocaleString()} (${pctOf(lg.strike_back_only, lg.n_called_strikes)})</span>
        <span><span class="ring" style="display:inline-block;width:9px;height:9px;border-radius:50%;border:2px solid ${FLAG_COLORS[3]}"></span> missed the 3D zone entirely</span><span class="r">${bz.strike_miss} (${pctOf(bz.strike_miss, bz.n_called_strikes)})</span><span class="r">${lg.strike_miss.toLocaleString()} (${pctOf(lg.strike_miss, lg.n_called_strikes)})</span>
        <span>Called balls</span><span class="r">${bz.n_called_balls.toLocaleString()}</span><span class="r">${lg.n_called_balls.toLocaleString()}</span>
        <span><span class="ring" style="display:inline-block;width:9px;height:9px;border-radius:50%;border:2px solid ${FLAG_COLORS[4]}"></span> path touched the 3D zone</span><span class="r">${bz.ball_touch} (${pctOf(bz.ball_touch, bz.n_called_balls)})</span><span class="r">${lg.ball_touch.toLocaleString()} (${pctOf(lg.ball_touch, lg.n_called_balls)})</span>
        <span>&nbsp;&nbsp;…only behind the front plane</span><span class="r">${bz.ball_touch_back_only}</span><span class="r">${lg.ball_touch_back_only.toLocaleString()}</span>
      </div>
      <h3>Examples (click to show in 3D)</h3>${ex || '<p class="empty-p">No flagged called pitches.</p>'}`;
    document.querySelectorAll('.z3-ex').forEach(b => b.addEventListener('click', () => selectRowId(Number(b.dataset.row))));
  }

  async function selectRowId(rowId) {
    let i = Z.vis.findIndex(r => r.rowId === rowId);
    if (i < 0) {
      $('z3-show-flags').checked = true;
      Object.assign(Z.f, { batter: 'all', pt: 'all', count: 'all', result: 'all' });
      syncControls();
      await refresh(true);
      i = Z.vis.findIndex(r => r.rowId === rowId);
    }
    if (i >= 0) {
      if (Z.tunnel) setTunnel(false);
      setCamera('zone');
      selectPitch(i);
    }
    return i;
  }

  function renderMethod() {
    const v = Z.meta.validation, G = Z.G, lg = Z.meta.back_zone;
    $('z3-method').innerHTML = `<ul>
      <li><strong>Trajectories.</strong> Statcast's 9-parameter fit gives velocity and constant acceleration at y = 50 ft (from the back tip of the plate) but not the position there.
        I solve for the release time where the fit reaches <code>release_pos_y</code>, pin the path to the published release point, and evaluate it at any time. Constant acceleration (gravity + drag + Magnus lumped) is Statcast's own assumption.</li>
      <li><strong>Validation</strong> (n = ${v.n.toLocaleString()} pitches) against Statcast's <code>plate_x / plate_z</code>: at mid-plate (y = 8.5 in) median ${v.mid_plate.median_in}", p95 ${v.mid_plate.p95_in}", max ${v.mid_plate.max_in}";
        at the front edge (y = 17 in) median ${v.front.median_in}", p95 ${v.front.p95_in}", max ${v.front.max_in}" (bias ${v.front.bias_z_in}" vertical).
        A depth scan puts the best match at y = ${(v.best_fit.y_ft * 12).toFixed(1)} in, i.e. <em>Statcast's plate location is reported mid-plate, not at the front edge</em>. The front-plane test here therefore uses the reconstructed front-edge crossing. Rounding the shipped coefficients adds ≤ ${v.shipped_rounding_mid_plate.p95_in}" (p95).</li>
      <li><strong>3D zone.</strong> Plate pentagon 17" wide × 17" deep (sides 8.5", then 45° edges to the back tip), extruded from <code>sz_bot</code> to <code>sz_top</code>. Those are Statcast's per-pitch estimates of each batter's zone, used per pitch for every call test; the drawn volume uses the average for the selected batter, else the pitcher's opponents. A pitch "touches" the zone if the ball center comes within ${(G.ball_r * 12).toFixed(2)}" (ball radius) of the prism at any of 18 depths between the front edge and the back tip. The 2D comparison is the usual box at the front plane: |x| ≤ 8.5" + r, sz_bot − r ≤ z ≤ sz_top + r.</li>
      <li><strong>League totals</strong> (${Z.meta.n_pitches.toLocaleString()} pitches): ${lg.strike_back_only.toLocaleString()} called strikes missed the front plane but clipped the 3D zone; ${lg.strike_miss.toLocaleString()} missed it entirely; ${lg.ball_touch.toLocaleString()} called balls touched it (${lg.ball_touch_back_only.toLocaleString()} only behind the front plane).
        Using Statcast's mid-plate <code>plate_x/z</code> instead: ${lg.statcast_plate_strike_miss.toLocaleString()} called strikes fail the 2D box and ${lg.statcast_plate_ball_hit.toLocaleString()} balls pass it. sz_top / sz_bot are estimates, so single-pitch verdicts within ~1" are noise.</li>
      <li><strong>Decision point.</strong> A plane ${G.decision_dist} ft in front of the plate, the commonly cited commit point (~0.15–0.17 s before the plate; ~${Z.data.tunnel.commit_ms || '–'} ms for this pitcher). Tunneling compares each pitch type's mean position there with its mean at the plate. Means mix locations and both batter sides; they are not consecutive-pitch pairs.</li>
      <li><strong>Batted balls.</strong> Landing / fielding spot from Statcast hit coordinates (feet = 2.49 × pixels), direction from <code>hc_x/hc_y</code>, distance = <code>hit_distance_sc</code>. Ground balls end where they were fielded. The 3D arc between contact and that spot is an approximate drag-shortened parabola (apex ≈ 0.72 × the vacuum apex from exit velocity and launch angle), for illustration only.</li>
      <li><strong>Samples.</strong> ${isStatic() ? `This static page embeds ~${Z.rows.length} pitches per pitcher (stratified so balls in play and called pitches are included) plus flagged examples; tunneling and 3D-call counts are computed on each pitcher's full season.` : 'Live: each request samples from all of the pitcher\'s matching pitches; tunneling and 3D-call counts use his full season.'}
        Season ${Z.meta.seasons.join(', ')}, ${Z.meta.date_range[0]} → ${Z.meta.date_range[1]}; ${Z.meta.n_dropped.toLocaleString()} pitches without a trajectory fit were dropped.</li>
    </ul>`;
  }

  // ---------------------------------------------------------------- controls

  function fillSelect(sel, opts, value) {
    sel.innerHTML = opts.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
    if (value != null) sel.value = String(value);
  }

  function fillPitchers(list) {
    fillSelect($('z3-pitcher'), list.map(p => [p.id, `${p.name} (${p.p_throws}HP) — ${p.n_pitches.toLocaleString()}`]), Z.f.pitcherId);
  }

  async function fillBatters() {
    let list;
    if (isStatic()) {
      const counts = {};
      Z.rows.forEach(r => { counts[r.b] = (counts[r.b] || 0) + 1; });
      list = Object.entries(Z.data.batters).map(([id, [name, st]]) => ({ id, name, stand: st, n: counts[id] || 0 })).sort((a, b) => b.n - a.n);
    } else {
      if (!Z.liveBatters || Z.liveBatters.pid !== Z.f.pitcherId) {
        Z.liveBatters = await getJSON(`/api/zone3d/batters?pitcher_id=${Z.f.pitcherId}`);
        Z.liveBatters.pid = Z.f.pitcherId;
      }
      list = Z.liveBatters;
    }
    const unit = isStatic() ? 'in sample' : 'pitches';
    fillSelect($('z3-batter'), [['all', 'All batters'], ...list.map(b => [b.id, `${b.name} (${b.stand}) — ${b.n} ${unit}`])], Z.f.batter);
  }

  function fillFilters() {
    const pts = Z.data.pitch_types.filter(p => p.n > 0);
    fillSelect($('z3-pt'), [['all', 'All pitch types'], ...pts.map(p => [p.pt, `${p.pt} · ${p.name} (${p.n.toLocaleString()})`])], Z.f.pt);
    const exact = [];
    for (let b = 0; b <= 3; b++) for (let s = 0; s <= 2; s++) exact.push([`${b}-${s}`, `${b}-${s}`]);
    fillSelect($('z3-count'), [...COUNT_LABELS, ...exact], Z.f.count);
    fillSelect($('z3-result'), RESULT_OPTS, Z.f.result);
  }

  function syncControls() {
    $('z3-pt').value = Z.f.pt; $('z3-count').value = Z.f.count; $('z3-result').value = Z.f.result;
    $('z3-batter').value = String(Z.f.batter); $('z3-n').value = String(Z.f.n);
  }

  function computeStandAndZone() {
    const vis = Z.vis.length ? Z.vis : Z.rows;
    const L = vis.filter(r => r.st === 'L').length;
    Z.stand = L > vis.length / 2 ? 'L' : 'R';
    if (Z.f.batter !== 'all' && vis.length) {
      const m = k => vis.reduce((s, r) => s + r[k], 0) / vis.length;
      Z.sz = [m('bot'), m('top')];
    } else {
      Z.sz = [Z.data.zone.sz_bot || Z.G.league_sz[0], Z.data.zone.sz_top || Z.G.league_sz[1]];
    }
  }

  async function refresh(refetch) {
    if (refetch && !isStatic()) await loadPitcher(Z.f.pitcherId);
    Z.vis = filterRows();
    computeStandAndZone();
    buildZone();
    buildBatter();
    buildPitches();
    if (Z.tunnel) buildTunnel();
    disposeGroup(selGroup);
    Z.selected = -1;
    dimOthers(false);
    renderPanel(null);
    renderText();
    needsRender = true;
  }

  async function setPitcher(pid) {
    pid = Number(pid);
    Object.assign(Z.f, { batter: 'all', pt: 'all', count: 'all', result: 'all' });
    await loadPitcher(pid);
    fillFilters();
    await fillBatters();
    $('z3-pitcher').value = String(pid);
    renderTunnel();
    renderBackZone();
    renderMethod();
    await refresh(false);
    if (Z.tunnel) buildTunnel();
    setCamera(Z.view);
  }

  async function setFilter(patch) {
    const pitcherChange = patch.pitcherId != null && Number(patch.pitcherId) !== Z.f.pitcherId;
    if (pitcherChange) { await setPitcher(patch.pitcherId); delete patch.pitcherId; }
    Object.assign(Z.f, patch);
    if ('n' in patch) Z.f.n = Number(patch.n);
    syncControls();
    await refresh(true);
    setCamera(Z.view);
  }

  function bindControls() {
    $('z3-pitcher').addEventListener('change', e => setPitcher(e.target.value).catch(showErr));
    $('z3-search').addEventListener('input', e => {
      const needle = fold(e.target.value.trim());
      const list = needle ? Z.pitchers.filter(p => fold(p.name).includes(needle) || String(p.id).includes(needle)) : Z.pitchers;
      fillPitchers(list.slice(0, 400));
      if (list.length && !list.some(p => p.id === Z.f.pitcherId)) setPitcher(list[0].id).catch(showErr);
    });
    $('z3-batter').addEventListener('change', e => setFilter({ batter: e.target.value }).catch(showErr));
    $('z3-pt').addEventListener('change', e => setFilter({ pt: e.target.value }).catch(showErr));
    $('z3-count').addEventListener('change', e => setFilter({ count: e.target.value }).catch(showErr));
    $('z3-result').addEventListener('change', e => setFilter({ result: e.target.value }).catch(showErr));
    $('z3-n').addEventListener('change', e => setFilter({ n: e.target.value }).catch(showErr));
    document.querySelectorAll('[data-cam]').forEach(b => b.addEventListener('click', () => { if (Z.tunnel) setTunnel(false); setCamera(b.dataset.cam); }));
    $('z3-tunnel-btn').addEventListener('click', () => setTunnel(!Z.tunnel));
    $('z3-play').addEventListener('click', () => {
      if (Z.playing) pausePlayback();
      else if (Z.play.active) resume();
      else startPlayback();
    });
    $('z3-stop').addEventListener('click', () => stopPlayback());
    $('z3-mode').addEventListener('change', e => { Z.mode = e.target.value; if (Z.playing) startPlayback(); });
    $('z3-speed').addEventListener('change', e => { Z.speed = Number(e.target.value); });
    $('z3-show-dp').addEventListener('change', e => { dpGroup.visible = e.target.checked; needsRender = true; });
    $('z3-show-arcs').addEventListener('change', () => { applyViewVisibility(); needsRender = true; });
    $('z3-show-flags').addEventListener('change', () => refresh(false));
    $('z3-show-labels').addEventListener('change', () => { buildBatter(); applyViewVisibility(); needsRender = true; });
  }
  function resume() { Z.playing = true; $('z3-play').textContent = '❚❚ Pause'; }

  function showErr(err) {
    Z.errors.push(String(err && err.message || err));
    $('z3-note').textContent = `Error: ${err && err.message || err}`;
    console.error(err);
  }

  // ---------------------------------------------------------------- init

  let DOT_TEX, RING_TEX;

  function initScene() {
    stage = $('z3-stage');
    renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0xf1f3ee);
    stage.appendChild(renderer.domElement);
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(40, 1.6, 0.05, 3000);
    camera.up.set(0, 0, 1);
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.addEventListener('change', () => { needsRender = true; });
    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const sun = new THREE.DirectionalLight(0xffffff, 0.55);
    sun.position.set(-30, -40, 80);
    scene.add(sun);
    DOT_TEX = dotTexture();
    RING_TEX = ringTexture();
    scene.add(buildWorld());
    for (const name of ['zoneGroup', 'batterGroup', 'pathGroup', 'arcGroup', 'markGroup', 'tunnelGroup', 'selGroup', 'labelGroup', 'dpGroup']) {
      const g = new THREE.Group();
      scene.add(g);
      if (name === 'zoneGroup') zoneGroup = g; else if (name === 'batterGroup') batterGroup = g; else if (name === 'pathGroup') pathGroup = g;
      else if (name === 'arcGroup') arcGroup = g; else if (name === 'markGroup') markGroup = g; else if (name === 'tunnelGroup') tunnelGroup = g;
      else if (name === 'selGroup') selGroup = g; else if (name === 'labelGroup') labelGroup = g; else dpGroup = g;
    }
    tunnelGroup.visible = false;
    buildLabels();
    buildDecisionPlane();
    const resize = () => {
      const w = stage.clientWidth, h = stage.clientHeight;
      renderer.setSize(w, h, false);
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
      needsRender = true;
    };
    new ResizeObserver(resize).observe(stage);
    resize();
    let down = null;
    renderer.domElement.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
    renderer.domElement.addEventListener('pointerup', e => {
      if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 5) onClick(e);
      down = null;
    });
    let last = performance.now();
    const loop = now => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      if (Z.playing) { stepPlayback(dt); needsRender = true; }
      if (needsRender) { renderer.render(scene, camera); needsRender = false; }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  async function init() {
    if (isStatic()) {
      Z.meta = window.Z3D_STATIC.meta;
      Z.pitchers = window.Z3D_STATIC.pitchers;
    } else {
      Z.meta = await getJSON('/api/zone3d/meta');
      Z.pitchers = await getJSON('/api/zone3d/pitchers');
    }
    Z.G = Z.meta.geometry;
    const m = Z.meta;
    $('z3-note').textContent = `MLB ${m.seasons.join(' + ')} Statcast pitch tracking (${m.date_range[0]} → ${m.date_range[1]}), ${m.n_pitches.toLocaleString()} pitches; ` +
      `${Z.pitchers.length.toLocaleString()} pitchers ${isStatic() ? 'in this demo' : 'available'}. Paths reconstructed from Statcast's trajectory fit (median error ${m.validation.mid_plate.median_in}" vs published plate location).`;
    initScene();
    bindControls();
    const q = new URLSearchParams(location.search);
    const qp = q.get('pitcher_id') && Z.pitchers.find(p => String(p.id) === q.get('pitcher_id'));
    const qn = q.get('pitcher') && Z.pitchers.find(p => fold(p.name).includes(fold(q.get('pitcher'))));
    const def = qp || qn || Z.pitchers.find(p => p.id === m.default_pitcher_id) || Z.pitchers[0];
    Z.f.pitcherId = def.id;
    fillPitchers(Z.pitchers.slice(0, 400).some(p => p.id === def.id) ? Z.pitchers.slice(0, 400) : [def, ...Z.pitchers.slice(0, 399)]);
    Z.view = CAMS[q.get('view')] ? q.get('view') : 'catcher';
    await setPitcher(def.id);
    if (q.get('pitch_type')) await setFilter({ pt: q.get('pitch_type').toUpperCase() });
    Z.ready = true;
  }

  window.Z3D = {
    get state() {
      return {
        ready: Z.ready, view: Z.view, tunnel: Z.tunnel, playing: Z.playing, speed: Z.speed, mode: Z.mode,
        filters: { ...Z.f }, nRows: Z.rows.length, nShown: Z.vis.length, selected: Z.selected,
        selectedRowId: Z.vis[Z.selected] ? Z.vis[Z.selected].rowId : null, stand: Z.stand, sz: Z.sz, errors: Z.errors,
        pitcher: Z.data && Z.data.pitcher,
      };
    },
    setCamera, setTunnel,
    play: () => startPlayback(), pause: pausePlayback, stop: () => stopPlayback(),
    setSpeed: x => { Z.speed = Number(x); $('z3-speed').value = String(x); },
    setMode: m => { Z.mode = m; $('z3-mode').value = m; },
    selectPitch, selectRowId, setPitcher, setFilter,
    findPitch: pred => Z.vis.findIndex(pred),
    rows: () => Z.vis,
    render: () => { needsRender = true; },
    ready: null,
  };
  window.Z3D.ready = init().catch(showErr);
})();
