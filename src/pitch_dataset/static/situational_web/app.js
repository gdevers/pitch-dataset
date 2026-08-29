let pitchers = [];
let batters = [];
let meta = {};
let fetchTimer = null;

function shortName(n) {
  if (!n) return '';
  if (n.includes(',')) return n.split(',')[0].trim();
  const p = n.trim().split(/\s+/);
  return p[p.length - 1];
}

function fillSelect(el, items, valueKey, labelKey) {
  const prev = el.value;
  el.innerHTML = '';
  items.forEach(item => {
    const o = document.createElement('option');
    o.value = String(item[valueKey]);
    o.textContent = item[labelKey];
    el.appendChild(o);
  });
  if (prev && [...el.options].some(o => o.value === prev)) {
    el.value = prev;
  }
}

function filterList(list, query) {
  if (!query) return list;
  const needle = query.trim().toLowerCase();
  return list.filter(p =>
    p.name.toLowerCase().includes(needle) ||
    String(p.id).includes(needle)
  );
}

function syncPlatoonDefaults() {
  const pid = document.getElementById('pitcher').value;
  const bid = document.getElementById('batter').value;
  const p = pitchers.find(x => String(x.id) === pid);
  const b = batters.find(x => String(x.id) === bid);
  if (p && p.p_throws) document.getElementById('p_throws').value = p.p_throws;
  if (b && b.stand) document.getElementById('stand').value = b.stand;
}

function renderRec(rec) {
  const maxX = Math.max(...rec.scores.map(s => s.pred_xwoba));
  const minX = Math.min(...rec.scores.map(s => s.pred_xwoba));
  const span = Math.max(0.001, maxX - minX);
  const imp = (-rec.expected_improvement_xwoba).toFixed(3);
  const impSign = rec.expected_improvement_xwoba >= 0 ? '' : '+';
  const bars = rec.scores.map(s => {
    const w = ((s.pred_xwoba - minX) / span) * 100;
    const cls = s.is_recommended ? 'pick' : (s.is_default ? 'def' : '');
    const tag = s.is_recommended ? '<span class="pick-label">pick</span>' :
      (s.is_default ? '<span class="tag">default</span>' : '');
    return `<div class="bar-row">
      <div><strong>${s.pitch_type}</strong></div>
      <div class="bar-track"><div class="bar-fill ${cls}" style="width:${Math.max(8, w)}%"></div></div>
      <div>${s.pred_xwoba.toFixed(3)} ${tag}</div>
    </div>`;
  }).join('');
  document.getElementById('panel').innerHTML = `
    <div class="hero">
      <div class="stat"><div class="v">${shortName(rec.pitcher_name)}</div><div class="l">Pitcher · ${rec.p_throws}HP</div></div>
      <div class="stat"><div class="v">${shortName(rec.batter_name)}</div><div class="l">Batter · ${rec.batter_side}</div></div>
      <div class="stat"><div class="v">${rec.count}</div><div class="l">${rec.leverage} leverage</div></div>
      <div class="stat"><div class="v">${rec.recommended_pitch}</div><div class="l">vs default ${rec.default_pitch}</div></div>
    </div>
    <div class="card">
      <h2>Recommended: ${rec.recommended_pitch}${rec.recommended_pitch !== rec.default_pitch ? ` (not ${rec.default_pitch})` : ''}</h2>
      <p>Expected improvement vs default: <strong>${impSign}${imp} xwOBA</strong></p>
      ${bars}
    </div>`;
}

async function fetchRecommend() {
  const pitcherId = document.getElementById('pitcher').value;
  const batterId = document.getElementById('batter').value;
  if (!pitcherId || !batterId) return;

  const params = new URLSearchParams({
    pitcher_id: pitcherId,
    batter_id: batterId,
    count: document.getElementById('count').value,
    leverage: document.getElementById('leverage').value,
    stand: document.getElementById('stand').value,
    p_throws: document.getElementById('p_throws').value,
  });

  const panel = document.getElementById('panel');
  panel.innerHTML = '<div class="card empty loading">Scoring pitches…</div>';

  try {
    const res = await fetch(`/api/recommend?${params}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    const rec = await res.json();
    renderRec(rec);
  } catch (e) {
    panel.innerHTML = `<div class="card empty error">${e.message || 'Request failed'}</div>`;
  }
}

function scheduleFetch() {
  clearTimeout(fetchTimer);
  fetchTimer = setTimeout(fetchRecommend, 200);
}

function onPitcherSearch() {
  const q = document.getElementById('pitcher-search').value;
  fillSelect(document.getElementById('pitcher'), filterList(pitchers, q), 'id', 'label');
  syncPlatoonDefaults();
  scheduleFetch();
}

function onBatterSearch() {
  const q = document.getElementById('batter-search').value;
  fillSelect(document.getElementById('batter'), filterList(batters, q), 'id', 'label');
  syncPlatoonDefaults();
  scheduleFetch();
}

function pickDefaults() {
  const cease = pitchers.find(p => p.name.toLowerCase().includes('cease'));
  const devers = batters.find(b => b.name.toLowerCase().includes('devers'));
  if (cease) document.getElementById('pitcher').value = String(cease.id);
  if (devers) document.getElementById('batter').value = String(devers.id);
  document.getElementById('count').value = '1-2';
  document.getElementById('leverage').value = 'high';
  syncPlatoonDefaults();
}

async function init() {
  try {
    const [metaRes, pRes, bRes] = await Promise.all([
      fetch('/api/meta'),
      fetch('/api/pitchers'),
      fetch('/api/batters'),
    ]);
    if (!metaRes.ok || !pRes.ok || !bRes.ok) {
      throw new Error('Failed to load roster data');
    }
    meta = await metaRes.json();
    pitchers = await pRes.json();
    batters = await bRes.json();

    document.getElementById('data-note').textContent = meta.data_note || '';

    fillSelect(document.getElementById('pitcher'), pitchers, 'id', 'label');
    fillSelect(document.getElementById('batter'), batters, 'id', 'label');
    fillSelect(
      document.getElementById('count'),
      (meta.counts || []).map(c => ({ v: c })),
      'v',
      'v'
    );

    pickDefaults();

    document.getElementById('pitcher-search').addEventListener('input', onPitcherSearch);
    document.getElementById('batter-search').addEventListener('input', onBatterSearch);
    ['pitcher', 'batter', 'count', 'leverage', 'stand', 'p_throws'].forEach(id => {
      document.getElementById(id).addEventListener('change', () => {
        syncPlatoonDefaults();
        scheduleFetch();
      });
    });

    await fetchRecommend();
  } catch (e) {
    document.getElementById('panel').innerHTML =
      `<div class="card empty error">${e.message || 'Initialization failed'}</div>`;
  }
}

init();
