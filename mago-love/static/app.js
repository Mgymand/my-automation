/* ============================================================
   孫LOVE — フロントエンド (SPA, 依存: Leaflet / markercluster)
   ============================================================ */
(() => {
'use strict';

// ---------------------------------------------------------------- state
const S = {
  boot: null, props: [], pois: [], stats: [],
  view: '', q: '',
  filter: { pref: '', city: '', ward: '', status: [] },
  map: null, mapLayers: {}, mapSelected: null, poiTypes: ['city_hall', 'pref_office', 'hospital', 'care'],
  calMonth: null, schedTab: 'calendar', listSort: { key: 'updated_at', dir: -1 },
  drawerId: null, drawerTab: 'overview',
};
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const yen = (n) => (n === null || n === undefined || n === '') ? '—' : '¥' + Number(n).toLocaleString();
const num = (n, unit = '') => (n === null || n === undefined || n === '') ? '—' : Number(n).toLocaleString() + unit;
const today = () => new Date().toISOString().slice(0, 10);
const fmtDate = (d) => d ? d.replace(/-/g, '/') : '—';
const fmtDT = (d) => d ? d.slice(0, 16).replace('T', ' ') : '';
const statusOf = (k) => S.boot.statuses.find(s => s.key === k) || S.boot.statuses[0];
const phaseOf = (k) => S.boot.phases.find(p => p.key === k) || S.boot.phases[0];
const poiTypeOf = (k) => S.boot.poi_types.find(p => p.key === k) || S.boot.poi_types.at(-1);
const isAdmin = () => S.boot.me.role === 'admin';
const canEdit = () => ['admin', 'member'].includes(S.boot.me.role);
const PREFS = ['茨城県', '栃木県', '群馬県', '埼玉県', '千葉県', '東京都', '神奈川県'];
const charOf = (id) => S.boot.characters.find(c => c.id === id) || S.boot.characters[0];
const myChar = () => charOf(S.boot.my_character || S.boot.characters[0].id);
const charAvatarHtml = (c, cls = 'av') => c.image ? `<span class="${cls}" style="background-image:url('${esc(c.image)}')"></span>` : `<span class="${cls}">${c.emoji}</span>`;
const charForPhase = (phase) => S.boot.characters.find(c => c.phases.includes(phase)) || S.boot.characters[0];
function scoreBadge(sc) { if (!sc || sc.total === null || sc.total === undefined) return ''; const cls = sc.total >= 70 ? 's-hi' : sc.total >= 45 ? 's-mid' : 's-lo'; return `<span class="score-badge ${cls}" title="価格 ${sc.price ?? '-'} / 需要 ${sc.demand ?? '-'} / アクセス ${sc.access ?? '-'}">★ ${sc.total}</span>`; }
const SCHED = [['viewing_date', '内見日'], ['survey_date', '現調日'], ['approval_date', '稟議承認'], ['contract_date', '契約日'],
               ['construction_start', '着工'], ['construction_end', '竣工'], ['opening_date', '開業予定日']];

// ---------------------------------------------------------------- api / ui utils
async function api(method, url, body, isForm = false) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opt.body = body; else { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  }
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.hash); throw new Error('login'); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `エラー (${r.status})`);
  return d;
}
function toast(msg, kind = '') {
  const el = document.createElement('div'); el.className = 'toast ' + kind; el.textContent = msg;
  $('#toasts').appendChild(el); setTimeout(() => el.remove(), 3200);
}
const err = (e) => toast(e.message || String(e), 'err');
function modal(title, html, onMount) {
  $('#modal-title').textContent = title; $('#modal-body').innerHTML = html; $('#modal').hidden = false;
  onMount && onMount($('#modal-body'));
  const first = $('#modal-body input, #modal-body textarea, #modal-body select'); first && first.focus();
}
function closeModal() { $('#modal').hidden = true; $('#modal-body').innerHTML = ''; }
function confirmDlg(msg) { return Promise.resolve(window.confirm(msg)); }
function badgeStatus(k) { const s = statusOf(k); return `<span class="badge badge-status" style="background:${s.color}">${s.label}</span>`; }
function field(label, name, value = '', opts = {}) {
  const { type = 'text', placeholder = '', span = '', hint = '', options = null, rows = 0 } = opts;
  let input;
  if (options) input = `<select name="${name}">${options.map(o => { const [v, l] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(v)}" ${String(v) === String(value) ? 'selected' : ''}>${esc(l)}</option>`; }).join('')}</select>`;
  else if (rows) input = `<textarea name="${name}" rows="${rows}" placeholder="${esc(placeholder)}">${esc(value)}</textarea>`;
  else input = `<input type="${type}" name="${name}" value="${esc(value ?? '')}" placeholder="${esc(placeholder)}">`;
  return `<div class="field ${span}"><label>${esc(label)}</label>${input}${hint ? `<div class="hint">${esc(hint)}</div>` : ''}</div>`;
}
function formData(form) {
  const out = {};
  $$('input, select, textarea', form).forEach(el => {
    if (!el.name) return;
    let v = el.type === 'checkbox' ? el.checked : el.value;
    if (el.type === 'number') v = v === '' ? null : Number(v);
    const path = el.name.split('.'); let o = out;
    for (let i = 0; i < path.length - 1; i++) o = (o[path[i]] = o[path[i]] || {});
    o[path.at(-1)] = v;
  });
  return out;
}
function taskStats(p) {
  const t = p.tasks || []; const done = t.filter(x => x.done).length;
  const overdue = t.filter(x => !x.done && x.due && x.due < today()).length;
  return { total: t.length, done, overdue, pct: t.length ? Math.round(done / t.length * 100) : 0 };
}
function gmapsUrl(p) { return p.lat ? `https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lon}` : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.address || p.name)}`; }
function streetViewUrl(p) { return `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${p.lat},${p.lon}`; }

// ---------------------------------------------------------------- filters
function filteredProps() {
  const q = S.q.trim().toLowerCase(); const f = S.filter;
  return S.props.filter(p => {
    if (f.pref && p.pref !== f.pref) return false;
    if (f.city && p.city !== f.city) return false;
    if (f.ward && p.ward !== f.ward) return false;
    if (f.status.length && !f.status.includes(p.status)) return false;
    if (q && !`${p.name} ${p.address} ${p.assignee} ${p.memo} ${(p.tags || []).join(' ')}`.toLowerCase().includes(q)) return false;
    return true;
  });
}
function munisOf(pref) { return S.boot.municipalities.filter(m => m.pref === pref && !m.ward); }
function wardsOf(pref, city) { return S.boot.municipalities.filter(m => m.pref === pref && m.city === city && m.ward); }
function muniCenter() {
  const f = S.filter; if (!f.pref) return null;
  const m = S.boot.municipalities.find(x => x.pref === f.pref && (f.city ? x.city === f.city : !x.ward && !x.city) ) ||
            S.boot.municipalities.find(x => x.pref === f.pref && x.city === f.city && (f.ward ? x.ward === f.ward : !x.ward)) ||
            S.boot.municipalities.find(x => x.pref === f.pref);
  return m;
}
function areaFilterHtml() {
  const f = S.filter;
  const cities = f.pref ? munisOf(f.pref) : []; const wards = (f.pref && f.city) ? wardsOf(f.pref, f.city) : [];
  return `<div class="area-select">
    <select data-area="pref"><option value="">関東（全域）</option>${PREFS.map(p => `<option ${f.pref === p ? 'selected' : ''}>${p}</option>`).join('')}</select>
    <select data-area="city" ${!f.pref ? 'disabled' : ''}><option value="">${f.pref ? f.pref + ' 全域' : '市区町村'}</option>${cities.map(c => `<option ${f.city === c.city ? 'selected' : ''}>${c.city}</option>`).join('')}</select>
    ${wards.length ? `<select data-area="ward" class="span2" style="grid-column:1/-1"><option value="">${f.city} 全区</option>${wards.map(w => `<option ${f.ward === w.ward ? 'selected' : ''}>${w.ward}</option>`).join('')}</select>` : ''}
  </div>`;
}
function bindAreaFilter(root, onChange) {
  $$('[data-area]', root).forEach(sel => sel.addEventListener('change', () => {
    const k = sel.dataset.area; S.filter[k] = sel.value;
    if (k === 'pref') { S.filter.city = ''; S.filter.ward = ''; }
    if (k === 'city') S.filter.ward = '';
    const wrap = sel.closest('.area-select');
    if (wrap && wrap.isConnected) { wrap.outerHTML = areaFilterHtml(); bindAreaFilter(root, onChange); }
    onChange();
  }));
}
function statusChipsHtml() {
  return `<div class="chips">${S.boot.statuses.map(s => `<button class="chip c-status ${S.filter.status.includes(s.key) ? 'active' : ''}" data-status="${s.key}" style="${S.filter.status.includes(s.key) ? `background:${s.color};border-color:${s.color}` : ''}">${s.label} <span class="muted small">${S.props.filter(p => p.status === s.key).length}</span></button>`).join('')}</div>`;
}
function bindStatusChips(root, onChange) {
  $$('[data-status]', root).forEach(b => b.addEventListener('click', () => {
    const k = b.dataset.status; const i = S.filter.status.indexOf(k);
    i >= 0 ? S.filter.status.splice(i, 1) : S.filter.status.push(k); onChange();
  }));
}

// ---------------------------------------------------------------- router
const VIEWS = {
  dashboard: ['ダッシュボード', renderDashboard], map: ['マップ', renderMap], board: ['パイプライン', renderBoard],
  list: ['物件一覧', renderList], schedule: ['スケジュール', renderSchedule], import: ['取込（PDF / テキスト / CSV）', renderImport],
  pois: ['周辺施設（役所・病院・介護施設）', renderPois], stats: ['統計データ', renderStats], settings: ['設定・連携', renderSettings],
};
async function route() {
  const hash = location.hash || '#/dashboard';
  const m = hash.match(/^#\/property\/([^/]+)/);
  if (m) { if (!S.view) await showView('dashboard'); openDrawer(m[1]); return; }
  const v = hash.replace(/^#\//, '').split('?')[0];
  closeDrawer(false);
  await showView(VIEWS[v] ? v : 'dashboard');
}
async function showView(v) {
  S.view = v; $('#view-title').textContent = VIEWS[v][0];
  $$('.nav a, .bottom-nav a').forEach(a => a.classList.toggle('active', a.dataset.view === v));
  $('#sidebar').classList.remove('open');
  const el = $('#view'); el.className = 'view' + (v === 'map' ? ' view-map' : ''); el.innerHTML = '';
  if (v !== 'map' && S.map) { S.map.remove(); S.map = null; }
  try { await VIEWS[v][1](el); } catch (e) { err(e); }
}
window.addEventListener('hashchange', route);

// ---------------------------------------------------------------- data
async function refreshProps() { S.props = await api('GET', '/api/properties'); }
async function refreshPois() { S.pois = await api('GET', '/api/pois'); }
async function refreshStats() { S.stats = await api('GET', '/api/stats'); }

// ================================================================ ダッシュボード
async function renderDashboard(el) {
  const d = await api('GET', '/api/dashboard');
  await refreshProps();
  const st = S.boot.statuses;
  const total = d.total || 0;
  const maxCnt = Math.max(1, ...Object.values(d.by_status));
  el.innerHTML = `
    <div class="kpis">
      <div class="kpi" style="--kpi-color:#0f172a" data-go="#/list"><div class="label">物件総数</div><div class="value">${total}</div><div class="sub">関東 全域</div></div>
      ${st.filter(s => s.key !== 'dropped').map(s => `<div class="kpi" style="--kpi-color:${s.color}" data-status-go="${s.key}"><div class="label">${s.label}</div><div class="value">${d.by_status[s.key] || 0}</div><div class="sub">件</div></div>`).join('')}
      <div class="kpi" style="--kpi-color:${d.overdue.length ? '#dc2626' : '#16a34a'}" data-go="#/schedule"><div class="label">期限超過タスク</div><div class="value">${d.overdue.length}</div><div class="sub">要対応</div></div>
    </div>
    <div class="dash-grid">
      <div class="col">
        <div class="card"><div class="card-head"><div class="card-title">パイプライン</div><span class="muted small">ステータス別の物件数</span><a class="btn btn-sm" href="#/board" style="margin-left:auto">カンバンで見る</a></div>
          <div class="card-body"><div class="funnel">${st.map(s => `<div class="funnel-row"><span>${s.label}</span><div class="bar"><i style="width:${(d.by_status[s.key] || 0) / maxCnt * 100}%;background:${s.color}"></i></div><b class="right mono">${d.by_status[s.key] || 0}</b></div>`).join('')}</div>
          <div class="section-title mt16">都道府県別</div>
          <div class="chips">${Object.entries(d.by_pref).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<button class="chip" data-pref-go="${esc(k)}">${esc(k)} <b>${v}</b></button>`).join('') || '<span class="muted">まだ物件がありません</span>'}</div></div></div>
        <div class="card"><div class="card-head"><div class="card-title">🗺️ クエストボード</div><span class="muted small">物件ごとの冒険の進み具合（7工程）</span></div>
          <div class="card-body tight">${S.props.filter(p => p.status !== 'dropped' && p.status !== 'opened').length ? S.props.filter(p => p.status !== 'dropped' && p.status !== 'opened').slice(0, 12).map(p => { const ts = taskStats(p); const cur = S.boot.phases.findIndex(ph => p.tasks.some(t => t.phase === ph.key && !t.done)); return `<div class="quest" data-open="${p.id}"><div class="qn">${esc(p.name)}<div class="qs">${badgeStatus(p.status)} ${scoreBadge(p.score)}</div></div><div class="track">${S.boot.phases.map((ph, i) => `<div class="node ${cur === -1 || i < cur ? 'done' : i === cur ? 'cur' : ''}" data-ico="${ph.icon}" title="${ph.label}"></div>`).join('')}</div><div class="qp">${ts.pct}%</div></div>`; }).join('') : '<div class="empty">進行中のクエスト（物件）はありません。「＋ 物件を追加」から始めよう！</div>'}</div></div>
        <div class="card"><div class="card-head"><div class="card-title">開業スケジュール</div><a class="btn btn-sm" href="#/schedule" style="margin-left:auto">タイムライン</a></div>
          <div class="card-body tight">${d.openings.length ? d.openings.map(o => `<div class="list-item" data-open="${o.prop_id}"><div class="li-date ${o.date < today() ? '' : ''}">${fmtDate(o.date)}</div><div class="grow"><div class="li-title">${esc(o.name)}</div><div class="li-sub">${esc(o.pref || '')}${esc(o.city || '')}</div></div>${badgeStatus(o.status)}</div>`).join('') : '<div class="empty">開業予定日が設定された物件はありません</div>'}</div></div>
      </div>
      <div class="col">
        <div class="card"><div class="card-body" style="display:flex;gap:14px;align-items:center">${charAvatarHtml(myChar(), 'av').replace('class="av"', 'class="av" style="width:72px;height:72px;border-radius:50%;background-size:cover;display:inline-flex;align-items:center;justify-content:center;font-size:36px;flex-shrink:0;border:3px solid ' + myChar().color + '"')}<div class="grow"><div class="small muted">パートナー</div><div style="font-weight:900;font-size:15px">${esc(myChar().name)} <span class="small muted">${esc(myChar().role)}</span></div><div class="small mt8"><b>Lv.${S.boot.progress.level} ${esc(S.boot.progress.title)}</b> ・ 累計 ${S.boot.progress.xp} XP</div><div class="progress mt8"><i style="width:${Math.round(S.boot.progress.xp_in_level / S.boot.progress.xp_next * 100)}%"></i></div><div class="small muted mt8">タスク完了 ${S.boot.progress.counts?.task_done || 0} ・ 報告 ${S.boot.progress.counts?.report || 0} ・ ステータス更新 ${S.boot.progress.counts?.status || 0}</div></div><button class="btn btn-sm" id="btn-char">変更</button></div></div>
        <div class="card"><div class="card-head"><div class="card-title">期限超過・直近のタスク</div><span class="badge ${d.overdue.length ? 'badge-danger' : 'badge-ok'}">${d.overdue.length} 超過</span></div>
          <div class="card-body tight">${[...d.overdue, ...d.upcoming].length ? [...d.overdue, ...d.upcoming].slice(0, 14).map(e => `<div class="list-item" data-open="${e.prop_id}"><div class="li-date ${e.date < today() ? 'over' : ''}">${fmtDate(e.date)}</div><div class="grow"><div class="li-title">${esc(e.label)}</div><div class="li-sub">${esc(e.prop_name)}${e.assignee ? ' ・ ' + esc(e.assignee) : ''}${e.kind === 'milestone' ? ' ・ マイルストーン' : ''}</div></div></div>`).join('') : '<div class="empty">直近14日の予定はありません</div>'}</div></div>
        <div class="card"><div class="card-head"><div class="card-title">最近の動き</div></div>
          <div class="card-body tight">${d.recent.length ? d.recent.slice(0, 12).map(h => `<div class="list-item" data-open="${h.prop_id}"><div class="li-date">${fmtDT(h.at).slice(5)}</div><div class="grow"><div class="li-title">${esc(h.prop_name)}</div><div class="li-sub">${esc(h.detail || h.action)}${h.by ? ' ・ ' + esc(h.by) : ''}</div></div></div>`).join('') : '<div class="empty">まだ活動がありません</div>'}</div></div>
      </div>
    </div>`;
  $$('[data-open]', el).forEach(x => x.onclick = () => openDrawer(x.dataset.open));
  $('#btn-char').onclick = () => chooseCharacter(false);
  $$('[data-go]', el).forEach(x => x.onclick = () => location.hash = x.dataset.go);
  $$('[data-status-go]', el).forEach(x => x.onclick = () => { S.filter.status = [x.dataset.statusGo]; location.hash = '#/list'; });
  $$('[data-pref-go]', el).forEach(x => x.onclick = () => { S.filter = { pref: x.dataset.prefGo === '未設定' ? '' : x.dataset.prefGo, city: '', ward: '', status: [] }; location.hash = '#/map'; });
}

// ================================================================ マップ
function tileLayers() {
  const s = S.boot.settings;
  const layers = {
    '地理院 淡色': L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png', { attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>', maxZoom: 18 }),
    '地理院 標準': L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png', { attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a>', maxZoom: 18 }),
    '航空写真': L.tileLayer('https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg', { attribution: '国土地理院', maxZoom: 18 }),
    'OpenStreetMap': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap contributors', maxZoom: 19 }),
  };
  if (s.zenrin_tile_url) layers['ZENRIN'] = L.tileLayer(s.zenrin_tile_url, { attribution: '&copy; ZENRIN', maxZoom: 19 });
  return layers;
}
function pinIcon(status) {
  const s = statusOf(status);
  return L.divIcon({ className: '', html: `<div class="marker-pin" style="background:${s.color}"><span>${s.label[0]}</span></div>`, iconSize: [26, 26], iconAnchor: [13, 26], popupAnchor: [0, -24] });
}
const POI_EMOJI = { city_hall: '🏛', pref_office: '🏢', hospital: '🏥', clinic: '➕', care: '🛏', caremanager: '🧑‍⚕️', station: '🚉', other: '📍' };
function poiIcon(type) {
  const t = poiTypeOf(type);
  return L.divIcon({ className: '', html: `<div class="marker-poi" style="background:${t.color}">${POI_EMOJI[type] || '📍'}</div>`, iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10] });
}
async function renderMap(el) {
  await Promise.all([refreshProps(), refreshPois(), refreshStats()]);
  el.innerHTML = `<div class="map-layout">
    <div class="map-side">
      <div class="map-side-head">
        <div class="area-nav" id="area-nav"></div>
        ${areaFilterHtml()}
        ${statusChipsHtml()}
      </div>
      <div class="map-list" id="map-list"></div>
    </div>
    <div class="map-main">
      <div id="map"></div>
      <div class="map-toolbar">
        <div class="map-panel"><span class="lbl">施設</span>${S.boot.poi_types.map(t => `<button class="chip ${S.poiTypes.includes(t.key) ? 'active' : ''}" data-poi="${t.key}" style="${S.poiTypes.includes(t.key) ? `background:${t.color};border-color:${t.color}` : ''}">${POI_EMOJI[t.key]} ${t.label}</button>`).join('')}</div>
        <div class="map-panel"><button class="btn btn-sm" id="btn-osm">🌐 この範囲の施設を取得(OSM)</button><button class="btn btn-sm" id="btn-fit">⤢ 全体表示</button><button class="btn btn-sm" id="btn-gmaps">Googleマップで開く</button></div>
      </div>
      <div class="stats-panel" id="stats-panel" hidden></div>
    </div>
  </div>`;
  const s = S.boot.settings;
  const base = tileLayers();
  const map = L.map('map', { center: s.default_center, zoom: s.default_zoom, zoomControl: false, layers: [base[s.zenrin_tile_url ? 'ZENRIN' : '地理院 淡色']] });
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  S.map = map;
  S.mapLayers.props = L.markerClusterGroup({ maxClusterRadius: 40, showCoverageOnHover: false });
  S.mapLayers.pois = L.layerGroup();
  map.addLayer(S.mapLayers.props); map.addLayer(S.mapLayers.pois);
  L.control.layers(base, { '物件': S.mapLayers.props, '周辺施設': S.mapLayers.pois }, { position: 'bottomleft', collapsed: true }).addTo(map);
  map.on('click', (e) => { if (e.originalEvent.shiftKey) quickAddAt(e.latlng); });
  const rerender = () => { drawMapMarkers(); drawMapList(); drawAreaNav(); drawStatsPanel(); };
  bindAreaFilter(el, () => { rerender(); flyToArea(); });
  const onStatusChange = () => { $('.map-side-head .chips').outerHTML = statusChipsHtml(); bindStatusChips(el, onStatusChange); rerender(); };
  bindStatusChips(el, onStatusChange);
  $$('[data-poi]', el).forEach(b => b.onclick = () => { const k = b.dataset.poi; const i = S.poiTypes.indexOf(k); i >= 0 ? S.poiTypes.splice(i, 1) : S.poiTypes.push(k); const t = poiTypeOf(k); b.classList.toggle('active', i < 0); b.style.cssText = i < 0 ? `background:${t.color};border-color:${t.color}` : ''; drawMapMarkers(); });
  $('#btn-fit').onclick = fitAll;
  $('#btn-gmaps').onclick = () => { const c = map.getCenter(); window.open(`https://www.google.com/maps/@${c.lat},${c.lng},${map.getZoom()}z`, '_blank'); };
  $('#btn-osm').onclick = fetchOsmHere;
  rerender();
  if (S.filter.pref) flyToArea(); else fitAll();
  setTimeout(() => map.invalidateSize(), 50);
}
function drawAreaNav() {
  const f = S.filter; const nav = $('#area-nav'); if (!nav) return;
  const parts = [`<button data-nav="">関東</button>`];
  if (f.pref) parts.push('<span class="sep">›</span>', f.city ? `<button data-nav="pref">${f.pref}</button>` : `<span class="cur">${f.pref}</span>`);
  if (f.city) parts.push('<span class="sep">›</span>', f.ward ? `<button data-nav="city">${f.city}</button>` : `<span class="cur">${f.city}</span>`);
  if (f.ward) parts.push('<span class="sep">›</span>', `<span class="cur">${f.ward}</span>`);
  nav.innerHTML = parts.join('');
  $$('[data-nav]', nav).forEach(b => b.onclick = () => {
    const lvl = b.dataset.nav;
    if (lvl === '') S.filter = { ...S.filter, pref: '', city: '', ward: '' };
    if (lvl === 'pref') S.filter = { ...S.filter, city: '', ward: '' };
    if (lvl === 'city') S.filter.ward = '';
    $('.map-side-head .area-select').outerHTML = areaFilterHtml(); bindAreaFilter($('.map-side'), () => { drawMapMarkers(); drawMapList(); drawAreaNav(); drawStatsPanel(); flyToArea(); });
    drawMapMarkers(); drawMapList(); drawAreaNav(); drawStatsPanel(); flyToArea();
  });
}
function flyToArea() {
  const f = S.filter; if (!S.map) return;
  if (!f.pref) { fitAll(); return; }
  const m = f.ward ? S.boot.municipalities.find(x => x.pref === f.pref && x.city === f.city && x.ward === f.ward)
          : f.city ? S.boot.municipalities.find(x => x.pref === f.pref && x.city === f.city && !x.ward) : null;
  if (m && m.lat) { S.map.flyTo([m.lat, m.lon], f.ward ? 14 : 12.5, { duration: .7 }); return; }
  const ms = munisOf(f.pref).filter(x => x.lat);
  if (ms.length) S.map.flyToBounds(L.latLngBounds(ms.map(x => [x.lat, x.lon])), { padding: [30, 30], duration: .7, maxZoom: 11 });
}
function fitAll() {
  const pts = filteredProps().filter(p => p.lat).map(p => [p.lat, p.lon]);
  if (pts.length) S.map.fitBounds(L.latLngBounds(pts), { padding: [50, 50], maxZoom: 14 });
  else S.map.setView(S.boot.settings.default_center, S.boot.settings.default_zoom);
}
function poiInArea(x) {
  const f = S.filter;
  if (!f.pref) return true;
  if (x.pref && x.pref !== f.pref) return false;
  if (f.city && x.city && x.city !== f.city) return false;
  if (!x.pref && x.lat && S.map) { // 住所未分解のPOIは表示範囲で判定
    return S.map.getBounds().pad(0.5).contains([x.lat, x.lon]);
  }
  return true;
}
function drawMapMarkers() {
  const g = S.mapLayers.props; g.clearLayers();
  filteredProps().forEach(p => {
    if (!p.lat) return;
    const m = L.marker([p.lat, p.lon], { icon: pinIcon(p.status), title: p.name });
    const ts = taskStats(p);
    m.bindPopup(`<div class="pp-title">${esc(p.name || '(名称未設定)')}</div><div class="pp-sub">${esc(p.address || '')}</div>
      <div class="mt8 flex">${badgeStatus(p.status)}<span class="badge badge-outline">${p.spec?.floor_area_tsubo ? num(p.spec.floor_area_tsubo, '坪') : (p.spec?.floor_area_sqm ? num(p.spec.floor_area_sqm, '㎡') : '面積 —')}</span><span class="badge badge-outline">${yen(p.spec?.rent_yen)}</span></div>
      <div class="mt8 flex"><button class="btn btn-sm btn-primary" onclick="MagoLove.openDrawer('${p.id}')">詳細を開く</button><span class="small muted">タスク ${ts.done}/${ts.total}</span></div>`);
    m.on('click', () => highlightCard(p.id));
    g.addLayer(m);
  });
  const pg = S.mapLayers.pois; pg.clearLayers();
  S.pois.filter(x => x.lat && S.poiTypes.includes(x.type) && poiInArea(x)).forEach(x => {
    const t = poiTypeOf(x.type);
    L.marker([x.lat, x.lon], { icon: poiIcon(x.type), title: x.name }).bindPopup(`<div class="pp-title">${POI_EMOJI[x.type] || ''} ${esc(x.name)}</div><div class="pp-sub">${esc(t.label)}${x.address ? '<br>' + esc(x.address) : ''}${x.tel ? '<br>☎ ' + esc(x.tel) : ''}${x.capacity ? '<br>定員 ' + esc(x.capacity) : ''}</div>${x.url ? `<div class="mt8"><a href="${esc(x.url)}" target="_blank">Webサイト</a></div>` : ''}<div class="mt8"><a href="https://www.google.com/maps/search/?api=1&query=${x.lat},${x.lon}" target="_blank" class="small">Googleマップ</a></div>`).addTo(pg);
  });
}
function highlightCard(id) { S.mapSelected = id; $$('.map-card').forEach(c => c.classList.toggle('active', c.dataset.id === id)); const c = $(`.map-card[data-id="${id}"]`); c && c.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
function drawMapList() {
  const list = $('#map-list'); if (!list) return;
  const items = filteredProps();
  list.innerHTML = items.length ? items.map(p => { const ts = taskStats(p); return `<div class="map-card ${S.mapSelected === p.id ? 'active' : ''}" data-id="${p.id}">
      <div class="t"><span class="prio prio-${p.priority || 'B'}">${p.priority || 'B'}</span>${esc(p.name || '(名称未設定)')}</div>
      <div class="a">${esc(p.address || '住所未設定')}${!p.lat ? ' <span class="badge badge-warn">座標なし</span>' : ''}</div>
      <div class="m">${badgeStatus(p.status)}${scoreBadge(p.score)}<span>${p.spec?.floor_area_tsubo ? num(p.spec.floor_area_tsubo, '坪') : ''}</span><span>${p.spec?.rent_yen ? yen(p.spec.rent_yen) + '/月' : ''}</span><span>${p.assignee ? '👤 ' + esc(p.assignee) : ''}</span>${ts.overdue ? `<span class="badge badge-danger">期限超過 ${ts.overdue}</span>` : ''}</div>
    </div>`; }).join('') : `<div class="empty"><div class="big">🗺️</div>該当する物件がありません<br><button class="btn btn-sm mt12" onclick="MagoLove.newProperty()">物件を追加</button></div>`;
  $$('.map-card', list).forEach(c => {
    c.onclick = () => { const p = S.props.find(x => x.id === c.dataset.id); highlightCard(p.id); if (p.lat) { S.map.flyTo([p.lat, p.lon], Math.max(S.map.getZoom(), 15), { duration: .5 }); S.mapLayers.props.eachLayer(m => { if (m.options.title === p.name && m.getLatLng().lat === p.lat) setTimeout(() => m.openPopup(), 550); }); } };
    c.ondblclick = () => openDrawer(c.dataset.id);
  });
}
function drawStatsPanel() {
  const panel = $('#stats-panel'); if (!panel) return;
  const f = S.filter;
  const rows = S.stats.filter(x => (f.city ? x.city === f.city && (!x.pref || x.pref === f.pref) : (f.pref ? x.pref === f.pref : false)));
  if (!f.pref || !rows.length) { panel.hidden = true; return; }
  panel.hidden = false;
  const byDs = {}; rows.forEach(r => (byDs[r.dataset] = byDs[r.dataset] || []).push(r));
  panel.innerHTML = `<div class="card"><div class="card-head"><div class="card-title">📈 ${esc(f.city || f.pref)} の統計</div><button class="icon-btn" onclick="this.closest('.stats-panel').hidden=true" style="margin-left:auto">✕</button></div><div class="card-body">${Object.entries(byDs).map(([ds, rs]) => {
    if (f.city) return `<div class="small muted mb8">${esc(ds)}</div>` + Object.entries(rs[0].metrics).map(([k, v]) => `<div class="stat-row"><span>${esc(k)}</span><b>${typeof v === 'number' ? v.toLocaleString() : esc(v)}</b></div>`).join('');
    // 都道府県レベル: 数値指標は合計、上位3市区町村を表示
    const sum = {}; rs.forEach(r => Object.entries(r.metrics).forEach(([k, v]) => { if (typeof v === 'number') sum[k] = (sum[k] || 0) + v; }));
    return `<div class="small muted mb8">${esc(ds)}（${rs.length}市区町村 合計）</div>` + Object.entries(sum).map(([k, v]) => `<div class="stat-row"><span>${esc(k)}</span><b>${v.toLocaleString()}</b></div>`).join('');
  }).join('<hr class="mt8 mb8" style="border:0;border-top:1px solid var(--line)">')}</div></div>`;
}
async function fetchOsmHere() {
  if (!canEdit()) return toast('閲覧権限のみです', 'err');
  const b = S.map.getBounds();
  if (S.map.getZoom() < 12) return toast('市区町村レベル（ズーム12以上）までズームしてください', 'err');
  const btn = $('#btn-osm'); btn.disabled = true; btn.textContent = '取得中…';
  try {
    const r = await api('POST', '/api/pois/fetch_osm', { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast(), types: ['hospital', 'clinic', 'city_hall', 'care', 'station'] });
    toast(`OpenStreetMapから ${r.created} 件の施設を追加しました（検出 ${r.found} 件）`, 'ok');
    await refreshPois(); drawMapMarkers();
  } catch (e) { err(e); } finally { btn.disabled = false; btn.textContent = '🌐 この範囲の施設を取得(OSM)'; }
}
function quickAddAt(latlng) {
  if (!canEdit()) return;
  newProperty({ lat: +latlng.lat.toFixed(6), lon: +latlng.lng.toFixed(6) });
}

// ================================================================ カンバン
async function renderBoard(el) {
  await refreshProps();
  const draw = () => {
    const items = filteredProps();
    el.innerHTML = `<div class="flex flex-wrap mb12" id="board-filters">${areaFilterHtml()}<span class="grow"></span><a class="btn btn-sm" href="/api/export/properties.csv">⬇ CSV（スプレッドシート用）</a></div>
    <div class="board">${S.boot.statuses.map(s => `<div class="board-col" data-col="${s.key}" style="--col-color:${s.color}"><div class="board-col-head"><span class="badge badge-status" style="background:${s.color}">${s.label}</span><span class="cnt">${items.filter(p => p.status === s.key).length}</span></div><div class="board-col-body">${items.filter(p => p.status === s.key).map(p => { const ts = taskStats(p); return `<div class="kcard" draggable="${canEdit()}" data-id="${p.id}"><div class="t"><span class="prio prio-${p.priority || 'B'}">${p.priority || 'B'}</span> ${esc(p.name || '(名称未設定)')}</div><div class="a">${esc((p.pref || '') + (p.city || ''))}${p.ward ? esc(p.ward) : ''} ${p.spec?.floor_area_tsubo ? '・' + num(p.spec.floor_area_tsubo, '坪') : ''}</div><div class="foot">${scoreBadge(p.score)}<div class="progress"><i style="width:${ts.pct}%"></i></div><span>${ts.done}/${ts.total}</span>${ts.overdue ? `<span class="badge badge-danger">${ts.overdue}</span>` : ''}${p.schedule?.opening_date ? `<span class="badge badge-outline">🎉 ${fmtDate(p.schedule.opening_date).slice(2)}</span>` : ''}${p.assignee ? `<span>👤${esc(p.assignee)}</span>` : ''}</div></div>`; }).join('')}</div></div>`).join('')}</div>`;
    bindAreaFilter(el, draw);
    $$('.kcard', el).forEach(c => {
      c.onclick = () => openDrawer(c.dataset.id);
      c.ondragstart = (e) => { e.dataTransfer.setData('text/plain', c.dataset.id); c.classList.add('dragging'); };
      c.ondragend = () => c.classList.remove('dragging');
    });
    $$('.board-col', el).forEach(col => {
      col.ondragover = (e) => { e.preventDefault(); col.classList.add('drag-over'); };
      col.ondragleave = () => col.classList.remove('drag-over');
      col.ondrop = async (e) => { e.preventDefault(); col.classList.remove('drag-over'); const id = e.dataTransfer.getData('text/plain'); const p = S.props.find(x => x.id === id); if (!p || p.status === col.dataset.col) return; await changeStatus(id, col.dataset.col); draw(); };
    });
  };
  draw();
}
async function changeStatus(id, status) {
  try { const p = await api('PUT', `/api/properties/${id}`, { status }); Object.assign(S.props.find(x => x.id === id), p); toast(`「${p.name}」を ${statusOf(status).label} に変更しました`, 'ok'); refreshProgress(); } catch (e) { err(e); }
}

// ================================================================ 一覧
async function renderList(el) {
  await refreshProps();
  const cols = [['name', '物件名'], ['status', 'ステータス'], ['pref', 'エリア'], ['spec.floor_area_tsubo', '坪数'], ['spec.rent_yen', '月額賃料'], ['spec.rooms_planned', '居室数'], ['schedule.opening_date', '開業予定'], ['assignee', '担当'], ['tasks', '進捗'], ['updated_at', '更新']];
  const get = (p, k) => k.split('.').reduce((o, x) => (o || {})[x], p);
  const draw = () => {
    let items = filteredProps();
    const { key, dir } = S.listSort;
    items = [...items].sort((a, b) => { let x = key === 'tasks' ? taskStats(a).pct : get(a, key); let y = key === 'tasks' ? taskStats(b).pct : get(b, key); if (key === 'status') { x = S.boot.statuses.findIndex(s => s.key === x); y = S.boot.statuses.findIndex(s => s.key === y); } x = x ?? ''; y = y ?? ''; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
    el.innerHTML = `<div class="flex flex-wrap mb12">${areaFilterHtml()}<span class="grow"></span><a class="btn btn-sm" href="/api/export/properties.csv">⬇ CSV</a></div><div class="mb12">${statusChipsHtml()}</div>
      <div class="card"><div class="table-wrap"><table class="tbl"><thead><tr><th style="width:36px"></th>${cols.map(([k, l]) => `<th class="sortable" data-sort="${k}">${l} ${S.listSort.key === k ? (dir > 0 ? '▲' : '▼') : ''}</th>`).join('')}</tr></thead>
      <tbody>${items.map(p => { const ts = taskStats(p); return `<tr class="row-link" data-id="${p.id}"><td><span class="prio prio-${p.priority || 'B'}">${p.priority || 'B'}</span></td><td class="name">${esc(p.name || '(名称未設定)')}<div class="small muted">${esc(p.address || '')}</div></td><td>${badgeStatus(p.status)} ${scoreBadge(p.score)}</td><td class="nowrap">${esc((p.pref || '') + ' ' + (p.city || '') + (p.ward || ''))}</td><td class="mono">${num(p.spec?.floor_area_tsubo)}</td><td class="mono">${yen(p.spec?.rent_yen)}${p.score?.tsubo_price ? `<div class="small muted">坪 ${yen(p.score.tsubo_price)}</div>` : ''}</td><td class="mono">${num(p.spec?.rooms_planned)}</td><td class="nowrap">${fmtDate(p.schedule?.opening_date)}</td><td>${esc(p.assignee || '')}</td><td style="min-width:120px"><div class="flex"><div class="progress grow"><i style="width:${ts.pct}%"></i></div><span class="small muted">${ts.done}/${ts.total}</span>${ts.overdue ? `<span class="badge badge-danger">${ts.overdue}</span>` : ''}</div></td><td class="small muted nowrap">${fmtDT(p.updated_at).slice(0, 10)}</td></tr>`; }).join('') || `<tr><td colspan="11"><div class="empty"><div class="big">📋</div>該当する物件がありません</div></td></tr>`}</tbody></table></div></div>`;
    bindAreaFilter(el, draw); bindStatusChips(el, draw);
    $$('[data-sort]', el).forEach(th => th.onclick = () => { const k = th.dataset.sort; S.listSort = { key: k, dir: S.listSort.key === k ? -S.listSort.dir : 1 }; draw(); });
    $$('tr[data-id]', el).forEach(tr => tr.onclick = () => openDrawer(tr.dataset.id));
  };
  draw();
}

// ================================================================ スケジュール
async function renderSchedule(el) {
  await refreshProps();
  const events = await api('GET', '/api/schedule');
  if (!S.calMonth) { const d = new Date(); S.calMonth = [d.getFullYear(), d.getMonth()]; }
  const draw = () => {
    const [y, m] = S.calMonth;
    el.innerHTML = `<div class="tabs"><button class="${S.schedTab === 'calendar' ? 'active' : ''}" data-tab="calendar">カレンダー</button><button class="${S.schedTab === 'gantt' ? 'active' : ''}" data-tab="gantt">タイムライン（物件別）</button><button class="${S.schedTab === 'tasks' ? 'active' : ''}" data-tab="tasks">タスク一覧</button>
      <span class="grow"></span><button class="btn btn-sm" id="btn-ics" style="align-self:center">📆 Googleカレンダーに連携</button></div><div id="sched-body"></div>`;
    $$('[data-tab]', el).forEach(b => b.onclick = () => { S.schedTab = b.dataset.tab; draw(); });
    $('#btn-ics').onclick = () => modal('Googleカレンダー連携', `<p>下記のURLを Googleカレンダーの「他のカレンダー ＋ → URLで追加」に貼り付けると、内見・現調・開業予定やタスク期限が自動で同期されます。</p><div class="pre mt12">${esc(location.origin)}/api/export/calendar.ics?token=（設定画面の ICS トークン）</div><p class="small muted mt8">トークンは「設定・連携」で発行できます。ログイン中のブラウザなら <a href="/api/export/calendar.ics" target="_blank">こちら</a> から .ics をダウンロードできます。</p>`);
    const body = $('#sched-body');
    if (S.schedTab === 'calendar') drawCalendar(body, events);
    else if (S.schedTab === 'gantt') drawGantt(body);
    else drawTaskList(body, events);
  };
  const drawCalendar = (body, evs) => {
    const [y, m] = S.calMonth;
    const first = new Date(y, m, 1); const startDow = first.getDay(); const days = new Date(y, m + 1, 0).getDate();
    const cells = [];
    for (let i = 0; i < startDow; i++) { const d = new Date(y, m, i - startDow + 1); cells.push({ d, other: true }); }
    for (let i = 1; i <= days; i++) cells.push({ d: new Date(y, m, i) });
    while (cells.length % 7) { const d = new Date(y, m, days + (cells.length - startDow - days) + 1); cells.push({ d, other: true }); }
    const key = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const byDay = {}; evs.forEach(e => (byDay[e.date] = byDay[e.date] || []).push(e));
    body.innerHTML = `<div class="cal-head"><button class="btn btn-sm" id="prev">‹</button><div class="cal-month">${y}年${m + 1}月</div><button class="btn btn-sm" id="next">›</button><button class="btn btn-sm btn-ghost" id="cur">今月</button><span class="muted small">◆ マイルストーン（内見/現調/契約/着工/竣工/開業） ■ タスク期限</span></div>
      <div class="cal-grid">${['日', '月', '火', '水', '木', '金', '土'].map(d => `<div class="cal-dow">${d}</div>`).join('')}${cells.map(c => { const k = key(c.d); const list = byDay[k] || []; return `<div class="cal-cell ${c.other ? 'other' : ''} ${k === today() ? 'today' : ''}"><span class="d">${c.d.getDate()}</span>${list.slice(0, 4).map(e => e.kind === 'milestone' ? `<span class="cal-ev" style="background:${statusOf(e.status).color}" data-open="${e.prop_id}" title="${esc(e.prop_name)} ${e.label}">◆ ${esc(e.label)}: ${esc(e.prop_name)}</span>` : `<span class="cal-ev task ${e.done ? 'done' : ''} ${!e.done && e.date < today() ? 'over' : ''}" data-open="${e.prop_id}" title="${esc(e.prop_name)}">${esc(e.label)}</span>`).join('')}${list.length > 4 ? `<span class="small muted">+${list.length - 4}</span>` : ''}</div>`; }).join('')}</div>`;
    $('#prev', body).onclick = () => { S.calMonth = m === 0 ? [y - 1, 11] : [y, m - 1]; draw(); };
    $('#next', body).onclick = () => { S.calMonth = m === 11 ? [y + 1, 0] : [y, m + 1]; draw(); };
    $('#cur', body).onclick = () => { const d = new Date(); S.calMonth = [d.getFullYear(), d.getMonth()]; draw(); };
    $$('[data-open]', body).forEach(x => x.onclick = () => openDrawer(x.dataset.open));
  };
  const drawGantt = (body) => {
    const props = filteredProps().filter(p => p.status !== 'dropped');
    const start = new Date(); start.setDate(1); start.setMonth(start.getMonth() - 1);
    const months = []; for (let i = 0; i < 18; i++) { const d = new Date(start.getFullYear(), start.getMonth() + i, 1); months.push(d); }
    const end = new Date(start.getFullYear(), start.getMonth() + 18, 1);
    const span = end - start; const pct = (d) => Math.min(100, Math.max(0, (new Date(d) - start) / span * 100));
    const curMonth = new Date(); curMonth.setDate(1);
    body.innerHTML = `<div class="card"><div class="gantt"><table class="gantt-table"><thead><tr><th class="name">物件</th>${months.map(d => `<th class="${d.getMonth() === curMonth.getMonth() && d.getFullYear() === curMonth.getFullYear() ? 'cur' : ''}">${d.getFullYear() !== months[0].getFullYear() && d.getMonth() === 0 ? d.getFullYear() + '年' : ''}${d.getMonth() + 1}月</th>`).join('')}</tr></thead>
      <tbody>${props.map(p => { const sc = p.schedule || {}; const s = statusOf(p.status);
        const bars = []; const c0 = sc.contract_date || sc.approval_date, c1 = sc.construction_start, c2 = sc.construction_end, o = sc.opening_date;
        if (c1 && c2) bars.push(`<div class="gbar" style="left:${pct(c1)}%;width:${Math.max(1.5, pct(c2) - pct(c1))}%;background:#f59e0b">内装工事</div>`);
        if (c0 && (c1 || o)) bars.push(`<div class="gbar" style="left:${pct(c0)}%;width:${Math.max(1.5, pct(c1 || o) - pct(c0))}%;background:#8b5cf6;top:9px;opacity:.85">申請・採用・集客</div>`);
        const ms = SCHED.filter(([k]) => sc[k]).map(([k, l]) => `<div class="gms" style="left:calc(${pct(sc[k])}% - 8px);background:${k === 'opening_date' ? '#16a34a' : s.color}" title="${l} ${sc[k]}"></div>`);
        return `<tr><td class="name" data-open="${p.id}">${esc(p.name)}<div class="small muted">${badgeStatus(p.status)} ${o ? '🎉 ' + fmtDate(o) : ''}</div></td><td class="cell" colspan="${months.length}" style="position:relative">${bars.join('')}${ms.join('')}</td></tr>`; }).join('') || `<tr><td colspan="19"><div class="empty">物件がありません</div></td></tr>`}</tbody></table></div></div>
      <p class="small muted mt8">物件詳細の「スケジュール」に日付を入れると、ここに自動で反映されます（契約→着工→竣工→開業）。</p>`;
    $$('[data-open]', body).forEach(x => x.onclick = () => openDrawer(x.dataset.open));
  };
  const drawTaskList = (body, evs) => {
    const tasks = evs.filter(e => e.kind === 'task' && !e.done);
    const over = tasks.filter(t => t.date < today()); const soon = tasks.filter(t => t.date >= today());
    const row = (t) => `<tr class="row-link" data-open="${t.prop_id}"><td class="mono ${t.date < today() ? 'over' : ''}" style="${t.date < today() ? 'color:var(--danger);font-weight:700' : ''}">${fmtDate(t.date)}</td><td>${esc(t.label)}</td><td><span class="badge">${phaseOf(t.phase).icon} ${phaseOf(t.phase).label}</span></td><td>${esc(t.prop_name)}</td><td>${esc(t.assignee || '')}</td></tr>`;
    body.innerHTML = `<div class="card"><div class="card-head"><div class="card-title">未完了タスク（期限あり）</div><span class="badge badge-danger">${over.length} 超過</span><span class="badge badge-info">${soon.length} 予定</span></div><div class="table-wrap"><table class="tbl"><thead><tr><th>期限</th><th>タスク</th><th>工程</th><th>物件</th><th>担当</th></tr></thead><tbody>${[...over, ...soon].map(row).join('') || '<tr><td colspan="5"><div class="empty">期限付きの未完了タスクはありません</div></td></tr>'}</tbody></table></div></div>`;
    $$('[data-open]', body).forEach(x => x.onclick = () => openDrawer(x.dataset.open));
  };
  draw();
}

// ================================================================ 取込
async function renderImport(el) {
  el.innerHTML = `<div class="import-grid">
    <div class="card"><div class="card-head"><div class="card-title">📄 物件PDF（マイソク・図面）を取り込む</div></div><div class="card-body">
      <div class="drop" id="pdf-drop"><div class="big">📄</div><b>PDFをドロップ / クリックして選択</b><div class="small mt8">テキスト付きPDFは自動で物件名・住所・賃料・面積などを抽出し、住所から地図にプロットします${S.boot.settings.llm_enabled ? '（AI構造化 ON）' : ''}</div></div>
      <input type="file" id="pdf-file" accept="application/pdf" hidden>
      <div class="small muted mt12">スキャンPDF（文字が読めないPDF）の場合: Googleドライブに入れて「アプリで開く → Googleドキュメント」でOCRし、テキストを下の「テキスト貼り付け」に貼ってください（無料）。</div>
    </div></div>
    <div class="card"><div class="card-head"><div class="card-title">📝 テキストを貼り付けて取り込む</div></div><div class="card-body">
      <div class="field"><textarea id="paste-text" rows="8" placeholder="物件概要のテキストを貼り付け（物件サイトのコピー、OCR結果、メールなど）"></textarea></div>
      <button class="btn btn-primary mt8" id="btn-paste">解析してドラフト作成</button>
    </div></div>
    <div class="card"><div class="card-head"><div class="card-title">📊 CSVで物件を一括登録</div></div><div class="card-body">
      <p class="small">Googleスプレッドシートで管理中のリストを「CSVでダウンロード」して取込。列名は日本語でOK（住所から自動で座標を取得します）。</p>
      <div class="pre mt8">物件名,住所,ステータス,担当,優先度,賃料,坪数,居室数,開業予定日,Driveフォルダ,メモ
サンプル荘,東京都杉並区高円寺南1-2-3,机上候補,岩本,A,850000,120,18,2027-04-01,https://drive.google.com/...,駅近</div>
      <div class="flex mt12"><input type="file" id="csv-file" accept=".csv,text/csv"><button class="btn btn-primary" id="btn-csv">取込</button></div>
    </div></div>
  </div>`;
  const drop = $('#pdf-drop'), fileIn = $('#pdf-file');
  drop.onclick = () => fileIn.click();
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); const f = e.dataTransfer.files[0]; f && importPdf(f); };
  fileIn.onchange = () => fileIn.files[0] && importPdf(fileIn.files[0]);
  $('#btn-paste').onclick = async () => { try { const d = await api('POST', '/api/import/text', { text: $('#paste-text').value }); newProperty(d); } catch (e) { err(e); } };
  $('#btn-csv').onclick = async () => { const f = $('#csv-file').files[0]; if (!f) return toast('CSVを選択してください', 'err'); const fd = new FormData(); fd.append('file', f); try { toast('取込中…（住所の座標取得に時間がかかります）'); const r = await api('POST', '/api/import/csv/properties', fd, true); toast(`${r.created} 件の物件を登録しました`, 'ok'); location.hash = '#/list'; } catch (e) { err(e); } };
}
async function importPdf(file) {
  const fd = new FormData(); fd.append('file', file);
  toast('PDFを解析中…');
  try { const d = await api('POST', '/api/import/pdf', fd, true); if (d.scanned) toast('テキストが含まれないPDFです。項目は手入力してください（OCR案内は取込画面参照）', 'err'); newProperty(d); } catch (e) { err(e); }
}

// ================================================================ 物件 新規作成
function propertyFormHtml(d = {}) {
  const sp = d.spec || {}, sc = d.schedule || {}, fi = d.finance || {};
  const users = S.boot.users.map(u => u.name);
  return `<form id="prop-form">
    <div class="section-title">基本情報</div>
    <div class="form-grid">
      ${field('物件名 *', 'name', d.name, { span: 'span2', placeholder: '例: 〇〇ビル 1-2F / 旧〇〇寮' })}
      ${field('ステータス', 'status', d.status || 'desk', { options: S.boot.statuses.map(s => [s.key, s.label]) })}
      ${field('優先度', 'priority', d.priority || 'B', { options: ['A', 'B', 'C'] })}
      ${field('住所 *', 'address', d.address, { span: 'span2', placeholder: '東京都〇〇区〇〇1-2-3（座標を自動取得）' })}
      ${field('担当', 'assignee', d.assignee, { options: ['', ...users].map(u => [u, u || '未設定']) })}
      ${field('種別', 'spec.property_type', sp.property_type, { options: ['', '一棟貸', '区分', '土地', '既存施設転用', '建貸(BTS)', '中古住宅', '売買'] })}
      ${field('取引', 'spec.transaction_type', sp.transaction_type || '賃貸', { options: ['賃貸', '売買'] })}
      ${field('売買価格 (円)', 'spec.price_yen', sp.price_yen, { type: 'number', hint: '売買の場合' })}
      ${field('公示地価 (円/㎡)', 'spec.land_price_sqm', sp.land_price_sqm, { type: 'number', hint: '近傍標準地' })}
      ${field('緯度', 'lat', d.lat ?? '', { type: 'number', hint: '空欄なら住所から自動取得' })}
      ${field('経度', 'lon', d.lon ?? '', { type: 'number' })}
    </div>
    <div class="section-title">物件スペック（統一フォーマット）</div>
    <div class="form-grid">
      ${field('延床面積 (㎡)', 'spec.floor_area_sqm', sp.floor_area_sqm, { type: 'number' })}
      ${field('延床面積 (坪)', 'spec.floor_area_tsubo', sp.floor_area_tsubo, { type: 'number' })}
      ${field('敷地面積 (㎡)', 'spec.site_area_sqm', sp.site_area_sqm, { type: 'number' })}
      ${field('想定居室数', 'spec.rooms_planned', sp.rooms_planned, { type: 'number' })}
      ${field('月額賃料 (円)', 'spec.rent_yen', sp.rent_yen, { type: 'number' })}
      ${field('管理費 (円)', 'spec.management_fee_yen', sp.management_fee_yen, { type: 'number' })}
      ${field('敷金・保証金', 'spec.deposit', sp.deposit)}
      ${field('礼金', 'spec.key_money', sp.key_money)}
      ${field('契約形態', 'spec.contract_type', sp.contract_type, { options: ['', '普通借家', '定期借家', '事業用定期借地', '売買'] })}
      ${field('契約年数', 'spec.contract_years', sp.contract_years)}
      ${field('構造', 'spec.structure', sp.structure, { placeholder: 'RC造 / S造 / 木造' })}
      ${field('階数', 'spec.floors', sp.floors, { placeholder: '地上3階' })}
      ${field('築年月', 'spec.built_ym', sp.built_ym, { placeholder: '1998-04' })}
      ${field('入居可能時期', 'spec.availability', sp.availability)}
      ${field('用途地域', 'spec.zoning', sp.zoning, { placeholder: '第一種住居地域' })}
      ${field('建ぺい率', 'spec.building_coverage', sp.building_coverage)}
      ${field('容積率', 'spec.floor_area_ratio', sp.floor_area_ratio)}
      ${field('防火地域', 'spec.fire_zone', sp.fire_zone)}
      ${field('接道', 'spec.road_access', sp.road_access)}
      ${field('駐車場', 'spec.parking', sp.parking)}
      ${field('エレベーター', 'spec.elevator', sp.elevator, { options: ['', '有', '無'] })}
      ${field('スプリンクラー', 'spec.sprinkler', sp.sprinkler, { options: ['', '有', '無', '要設置'] })}
      ${field('元付・情報提供会社', 'spec.source_company', sp.source_company)}
      ${field('連絡先', 'spec.contact', sp.contact)}
      ${field('物件番号', 'spec.property_number', sp.property_number)}
      ${field('最寄駅（自動抽出）', 'stations_text', (sp.stations || []).map(s => `${s.line} ${s.station} 徒歩${s.walk_min}分`).join(' / '), { span: 'span2', hint: '「路線 駅 徒歩N分 / …」で入力' })}
    </div>
    <div class="section-title">収支（概算）</div>
    <div class="form-grid">
      ${field('初期投資 (円)', 'finance.capex_yen', fi.capex_yen, { type: 'number' })}
      ${field('目標稼働率 (%)', 'finance.target_occupancy', fi.target_occupancy, { type: 'number' })}
      ${field('月間売上 (円)', 'finance.monthly_revenue_yen', fi.monthly_revenue_yen, { type: 'number' })}
      ${field('月間利益 (円)', 'finance.monthly_profit_yen', fi.monthly_profit_yen, { type: 'number' })}
      ${field('投資回収 (月)', 'finance.payback_months', fi.payback_months, { type: 'number' })}
    </div>
    <div class="section-title">スケジュール</div>
    <div class="form-grid">${SCHED.map(([k, l]) => field(l, 'schedule.' + k, sc[k], { type: 'date' })).join('')}</div>
    <div class="section-title">Googleドライブ・メモ</div>
    <div class="form-grid">
      ${field('Driveフォルダ URL', 'drive.folder_url', (d.drive || {}).folder_url, { span: 'span2', placeholder: 'https://drive.google.com/drive/folders/…' })}
      ${field('タグ（カンマ区切り）', 'tags_text', (d.tags || []).join(', '))}
      ${field('メモ（個別・特記事項）', 'memo', d.memo, { span: 'span-all', rows: 4, placeholder: '統一フォーマットに入らない個別の内容はここに' })}
    </div>
  </form>`;
}
function readPropertyForm(form) {
  const d = formData(form);
  d.spec.stations = (d.stations_text || '').split('/').map(s => s.trim()).filter(Boolean).map(s => { const m = s.match(/^(\S+)\s+(\S+?)\s*(?:徒歩)?(\d+)?/); return m ? { line: m[1], station: m[2].replace(/駅$/, ''), walk_min: m[3] ? +m[3] : null } : { line: '', station: s, walk_min: null }; });
  d.tags = (d.tags_text || '').split(/[,、]/).map(s => s.trim()).filter(Boolean);
  delete d.stations_text; delete d.tags_text;
  if (d.lat === null || d.lat === '') { delete d.lat; delete d.lon; }
  return d;
}
function newProperty(draft = {}) {
  if (!canEdit()) return toast('閲覧権限のみです', 'err');
  const src = draft.source || {};
  modal('物件を追加', `${src.type === 'pdf' ? `<div class="flex mb12"><span class="badge badge-info">PDF: ${esc(src.filename)}</span><a class="small" href="${esc(src.url)}" target="_blank">原本を開く</a>${!draft.lat && draft.address ? '<span class="badge badge-warn">座標が取得できませんでした（住所を修正してください）</span>' : ''}</div>` : ''}${propertyFormHtml(draft)}<div class="modal-foot"><button class="btn" id="m-cancel">キャンセル</button><button class="btn btn-primary" id="m-save">登録する</button></div>`, (body) => {
    $('#m-cancel', body).onclick = closeModal;
    $('#m-save', body).onclick = async () => {
      const d = readPropertyForm($('#prop-form', body));
      if (!d.name && !d.address) return toast('物件名または住所を入力してください', 'err');
      if (src.type) d.source = src;
      try { const p = await api('POST', '/api/properties', d); closeModal(); toast('物件を登録しました', 'ok'); refreshProgress(); await refreshProps(); if (S.view !== 'map') showView(S.view); else { drawMapMarkers(); drawMapList(); } openDrawer(p.id); } catch (e) { err(e); }
    };
  });
}

// ================================================================ 物件詳細ドロワー
async function openDrawer(id, tab) {
  let p; try { p = await api('GET', `/api/properties/${id}`); } catch (e) { return err(e); }
  S.drawerId = id; if (tab) S.drawerTab = tab;
  if (!location.hash.startsWith('#/property/')) history.replaceState(null, '', location.hash);
  $('#drawer').hidden = false; $('#drawer-backdrop').hidden = false;
  drawDrawer(p);
}
function closeDrawer(nav = true) { $('#drawer').hidden = true; $('#drawer-backdrop').hidden = true; S.drawerId = null; if (nav && location.hash.startsWith('#/property/')) location.hash = '#/' + (S.view || 'dashboard'); }
async function reloadDrawer() { if (S.drawerId) { const p = await api('GET', `/api/properties/${S.drawerId}`); const i = S.props.findIndex(x => x.id === p.id); if (i >= 0) S.props[i] = p; drawDrawer(p); } }
function drawDrawer(p) {
  const ts = taskStats(p); const st = statusOf(p.status);
  const idx = S.boot.statuses.findIndex(s => s.key === p.status);
  const tabs = [['overview', '概要'], ['tasks', `工程・タスク`], ['outreach', '営業先'], ['reports', '内見・現調報告'], ['docs', '書類・Drive'], ['history', 'メモ・履歴']];
  const cnt = { tasks: `${ts.done}/${ts.total}`, reports: p.reports.length, docs: p.docs.length, outreach: (p.outreach || []).length };
  const d = $('#drawer');
  d.innerHTML = `<div class="drawer-head">
    <div class="row1"><div class="grow"><div class="drawer-title"><input value="${esc(p.name)}" id="d-name" ${canEdit() ? '' : 'readonly'} placeholder="物件名"></div>
      <div class="drawer-sub"><span>📍 ${esc(p.address || '住所未設定')}</span>${p.lat ? `<a href="${gmapsUrl(p)}" target="_blank">Googleマップ</a><a href="${streetViewUrl(p)}" target="_blank">ストリートビュー</a>` : `<button class="btn btn-xs" id="d-geocode">座標を取得</button>`}<span class="prio prio-${p.priority || 'B'}">${p.priority || 'B'}</span>${p.assignee ? `<span>👤 ${esc(p.assignee)}</span>` : ''}${p.drive?.folder_url ? `<a href="${esc(p.drive.folder_url)}" target="_blank">📁 Drive</a>` : ''}</div></div>
      <button class="btn btn-sm" id="d-edit">✎ 編集</button>${isAdmin() ? '<button class="btn btn-sm btn-danger" id="d-delete">削除</button>' : ''}<button class="icon-btn" id="d-close">✕</button></div>
    <div class="stepper">${S.boot.statuses.filter(s => s.key !== 'dropped').map((s, i) => `<div class="step ${i < idx ? 'done' : ''} ${s.key === p.status ? 'cur' : ''}" data-st="${s.key}" style="${s.key === p.status ? `background:${s.color}` : ''}">${s.label}</div>`).join('')}<div class="step ${p.status === 'dropped' ? 'cur' : ''}" data-st="dropped" style="flex:.6;${p.status === 'dropped' ? 'background:#9ca3af' : ''}">見送り</div></div>
    <div class="tabs" style="margin-bottom:0;border-bottom:0">${tabs.map(([k, l]) => `<button class="${S.drawerTab === k ? 'active' : ''}" data-dtab="${k}">${l}${cnt[k] !== undefined ? `<span class="cnt">${cnt[k]}</span>` : ''}</button>`).join('')}</div>
  </div><div class="drawer-body" id="d-body"></div>`;
  $('#d-close').onclick = () => closeDrawer();
  $('#drawer-backdrop').onclick = () => closeDrawer();
  $('#d-edit').onclick = () => editProperty(p);
  const nameIn = $('#d-name'); nameIn.onchange = async () => { try { await api('PUT', `/api/properties/${p.id}`, { name: nameIn.value }); toast('物件名を更新しました', 'ok'); await refreshProps(); } catch (e) { err(e); } };
  $('#d-geocode') && ($('#d-geocode').onclick = async () => { try { await api('POST', `/api/properties/${p.id}/geocode`); toast('座標を取得しました', 'ok'); reloadDrawer(); } catch (e) { err(e); } });
  $('#d-delete') && ($('#d-delete').onclick = async () => { if (!await confirmDlg(`「${p.name}」を削除しますか？この操作は取り消せません。`)) return; try { await api('DELETE', `/api/properties/${p.id}`); toast('削除しました'); closeDrawer(); await refreshProps(); showView(S.view); } catch (e) { err(e); } });
  $$('[data-st]', d).forEach(s => s.onclick = async () => { if (!canEdit() || s.dataset.st === p.status) return; await changeStatus(p.id, s.dataset.st); reloadDrawer(); });
  $$('[data-dtab]', d).forEach(b => b.onclick = () => { S.drawerTab = b.dataset.dtab; drawDrawer(p); });
  const body = $('#d-body');
  ({ overview: drawOverview, tasks: drawTasks, outreach: drawOutreach, reports: drawReports, docs: drawDocs, history: drawHistory })[S.drawerTab](body, p);
  if (Math.random() < 0.5) partnerNext();
}
function drawOverview(body, p) {
  const sp = p.spec || {}, sc = p.schedule || {}, fi = p.finance || {};
  const kv = (rows) => `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v || '—'}</dd>`).join('')}</dl>`;
  const ts = taskStats(p);
  const src = p.source || {};
  body.innerHTML = `
    <div class="card"><div class="card-head"><div class="card-title">進捗サマリー</div><span class="muted small">タスク ${ts.done}/${ts.total} 完了</span>${ts.overdue ? `<span class="badge badge-danger">期限超過 ${ts.overdue}</span>` : ''}</div><div class="card-body">
      <div class="progress mb12"><i style="width:${ts.pct}%"></i></div>
      <div class="flex flex-wrap">${S.boot.phases.map(ph => { const t = p.tasks.filter(x => x.phase === ph.key); const dn = t.filter(x => x.done).length; return `<span class="badge ${t.length && dn === t.length ? 'badge-ok' : dn ? 'badge-info' : ''}">${ph.icon} ${ph.label} ${dn}/${t.length}</span>`; }).join('')}</div></div></div>
    ${scoreCardHtml(p)}
    ${surveyCardHtml(p)}
    <div class="card"><div class="card-head"><div class="card-title">スケジュール</div></div><div class="card-body">
      <div class="form-grid">${SCHED.map(([k, l]) => `<div class="field"><label>${l}</label><input type="date" data-sched="${k}" value="${esc(sc[k] || '')}" ${canEdit() ? '' : 'disabled'}></div>`).join('')}</div>
      <div class="small muted mt8">日付を変更すると保存され、Slackに予定更新の通知が届きます。</div></div></div>
    <div class="dash-grid">
      <div class="col"><div class="card"><div class="card-head"><div class="card-title">物件スペック</div></div><div class="card-body">${kv([
        ['種別', [sp.property_type, sp.transaction_type].filter(Boolean).map(esc).join(' / ')], ['売買価格', sp.price_yen ? yen(sp.price_yen) : ''], ['公示地価', sp.land_price_sqm ? yen(sp.land_price_sqm) + '/㎡' : ''], ['延床面積', sp.floor_area_sqm ? `${num(sp.floor_area_sqm, '㎡')} / ${num(sp.floor_area_tsubo, '坪')}` : (sp.floor_area_tsubo ? num(sp.floor_area_tsubo, '坪') : '')], ['敷地面積', sp.site_area_sqm ? num(sp.site_area_sqm, '㎡') : ''], ['想定居室数', sp.rooms_planned ? num(sp.rooms_planned, '室') : ''],
        ['月額賃料', sp.rent_yen ? yen(sp.rent_yen) + (sp.floor_area_tsubo ? ` <span class="muted small">(坪 ${yen(Math.round(sp.rent_yen / sp.floor_area_tsubo))})</span>` : '') : ''], ['管理費', sp.management_fee_yen ? yen(sp.management_fee_yen) : ''], ['敷金・礼金', [sp.deposit, sp.key_money].filter(Boolean).map(esc).join(' / ')], ['契約', [sp.contract_type, sp.contract_years].filter(Boolean).map(esc).join(' ')],
        ['構造・階数', [sp.structure, sp.floors].filter(Boolean).map(esc).join(' ')], ['築年月', esc(sp.built_ym)], ['入居可能', esc(sp.availability)], ['最寄駅', (sp.stations || []).map(s => esc(`${s.line} ${s.station}駅 徒歩${s.walk_min ?? '?'}分`)).join('<br>')],
        ['元付', esc(sp.source_company)], ['連絡先', esc(sp.contact)], ['物件番号', esc(sp.property_number)]])}</div></div></div>
      <div class="col">
        <div class="card"><div class="card-head"><div class="card-title">法規制</div></div><div class="card-body">${kv([['用途地域', esc(sp.zoning)], ['建ぺい率 / 容積率', [sp.building_coverage, sp.floor_area_ratio].filter(Boolean).map(esc).join(' / ')], ['防火地域', esc(sp.fire_zone)], ['接道', esc(sp.road_access)], ['駐車場', esc(sp.parking)], ['EV / SP', [sp.elevator && 'EV:' + sp.elevator, sp.sprinkler && 'SP:' + sp.sprinkler].filter(Boolean).map(esc).join(' ')]])}</div></div>
        <div class="card"><div class="card-head"><div class="card-title">収支（概算）</div></div><div class="card-body">${kv([['初期投資', fi.capex_yen ? yen(fi.capex_yen) : ''], ['目標稼働率', fi.target_occupancy ? fi.target_occupancy + '%' : ''], ['月間売上', fi.monthly_revenue_yen ? yen(fi.monthly_revenue_yen) : ''], ['月間利益', fi.monthly_profit_yen ? yen(fi.monthly_profit_yen) : ''], ['投資回収', fi.payback_months ? fi.payback_months + 'ヶ月' : '']])}</div></div>
      </div>
    </div>
    ${src.type === 'pdf' && src.url ? `<div class="card"><div class="card-head"><div class="card-title">取込元PDF</div><a class="btn btn-sm" href="${esc(src.url)}" target="_blank" style="margin-left:auto">原本を開く</a></div><div class="card-body"><img class="pdf-preview" src="${esc(src.url)}/preview.png" alt="PDFプレビュー" loading="lazy"></div></div>` : ''}
    ${p.memo ? `<div class="card"><div class="card-head"><div class="card-title">メモ・特記事項</div></div><div class="card-body" style="white-space:pre-wrap">${esc(p.memo)}</div></div>` : ''}`;
  $('#btn-survey') && ($('#btn-survey').onclick = async () => { const b = $('#btn-survey'); b.disabled = true; b.textContent = '調査中…（公開APIを照会）'; try { await api('POST', `/api/properties/${p.id}/survey`); toast('リスク調査が完了しました', 'ok'); refreshProgress(false); reloadDrawer(); } catch (e) { err(e); b.disabled = false; b.textContent = '🔎 自動調査を実行'; } });
  $$('[data-sched]', body).forEach(inp => inp.onchange = async () => { try { await api('PUT', `/api/properties/${p.id}`, { schedule: { [inp.dataset.sched]: inp.value } }); toast('予定を更新しました', 'ok'); await refreshProps(); } catch (e) { err(e); } });
}
function scoreCardHtml(p) {
  const sc = (S.props.find(x => x.id === p.id) || {}).score; if (!sc) return '';
  const bar = (l, v, hint) => `<div class="funnel-row"><span>${l}</span><div class="bar"><i style="width:${v ?? 0}%;background:${v === null || v === undefined ? '#e5e7eb' : v >= 70 ? '#16a34a' : v >= 45 ? '#f59e0b' : '#94a3b8'}"></i></div><b class="right mono">${v ?? '—'}</b></div><div class="small muted" style="margin:-4px 0 6px 100px">${hint}</div>`;
  const d = sc.demand_detail || {};
  return `<div class="card"><div class="card-head"><div class="card-title">候補スコア</div>${scoreBadge(sc)}<span class="muted small">「需要のある市に近く・坪単価が低い」ほど高評価（登録物件内の相対評価）</span></div><div class="card-body"><div class="funnel">
    ${bar('価格', sc.price, sc.tsubo_price ? `坪単価 ${yen(sc.tsubo_price)}/月${p.spec?.transaction_type === '売買' ? '（売買価格を20年で月額換算）' : ''}` : '賃料と面積を入力すると算出')}
    ${bar('需要', sc.demand, d.certified ? `${esc(p.city)} 要介護認定者 ${Number(d.certified).toLocaleString()}人` : d.elderly ? `${esc(p.city)} 65歳以上 ${Number(d.elderly).toLocaleString()}人` : '統計データ（65歳以上人口・要介護認定者数）を取り込むと算出')}
    ${bar('アクセス', sc.access, Object.keys(sc.near || {}).length ? '3km以内: ' + Object.entries(sc.near).map(([k, v]) => `${poiTypeOf(k).label} ${v}`).join('・') : '周辺施設（ケアマネ事業所・病院）を登録すると算出')}
  </div></div></div>`;
}
function surveyCardHtml(p) {
  const sv = p.survey || {};
  const head = `<div class="card-head"><div class="card-title">🔎 現地リスク調査（自動）</div><span class="muted small">${sv.at ? '調査日時 ' + fmtDT(sv.at) + ' ・ ' + esc(sv.by || '') : '標高・地盤・ハザードマップを公開APIで自動判定'}</span>${canEdit() && p.lat ? `<button class="btn btn-sm ${sv.at ? '' : 'btn-primary'}" id="btn-survey" style="margin-left:auto">${sv.at ? '🔄 再調査' : '🔎 自動調査を実行'}</button>` : ''}</div>`;
  if (!sv.at) return `<div class="card">${head}<div class="card-body small muted">${p.lat ? '国土地理院 標高API / J-SHIS 表層地盤 / 重ねるハザードマップ（洪水・浸水継続・家屋倒壊・土砂・津波・高潮）を座標で判定します。' : '座標を取得すると自動調査ができます。'}</div></div>`;
  const e = sv.elevation || {}, g = sv.ground || {};
  return `<div class="card">${head}<div class="card-body">
    <div class="dash-grid"><div class="col"><dl class="kv"><dt>標高</dt><dd>${e.ok ? e.elevation_m + ' m' : '取得不可'} <span class="small muted">${esc(e.source || '')}</span></dd><dt>微地形</dt><dd>${esc(g.landform || '—')}</dd><dt>揺れやすさ</dt><dd>${esc(g.grade || '—')} <span class="small muted">${g.avs30 ? 'AVS30 ' + g.avs30 + ' m/s ・ 増幅率 ' + g.arv : ''}</span></dd></dl></div>
    <div class="col">${(sv.hazards || []).map(h => `<div class="hz"><span class="lab">${esc(h.label)}</span><span class="${h.hit ? 'ng' : 'ok'}">${h.hit ? '⚠ ' + esc(h.detail) : '該当なし'}</span></div>`).join('')}</div></div>
    ${(sv.notes || []).map(n => `<div class="note">${esc(n)}</div>`).join('')}
    <div class="flex flex-wrap mt12">${Object.entries(sv.links || {}).map(([k, v]) => `<a class="btn btn-xs" href="${esc(v)}" target="_blank">${esc(k)}</a>`).join('')}</div>
    <div class="small muted mt8">※ タイルの色による参考判定です。用途地域・地価公示・埋蔵文化財は不動産情報ライブラリ／自治体窓口で確認し、「書類」に調査資料を登録してください。</div></div></div>`;
}
function drawOutreach(body, p) {
  const st = S.boot.outreach_statuses; const stLabel = (k) => (st.find(x => x.key === k) || {}).label || k;
  const list = p.outreach || [];
  const counts = st.map(x => `<span class="badge ${x.key === 'referral' ? 'badge-ok' : x.key === 'requested' ? 'badge-info' : ''}">${x.label} ${list.filter(o => o.status === x.key).length}</span>`).join('');
  body.innerHTML = `<div class="card"><div class="card-head"><div class="card-title">📣 入居者獲得の営業先</div><span class="muted small">居宅介護支援事業所（ケアマネ）・病院・紹介会社への訪問と斡旋依頼を記録</span><span class="grow"></span>${canEdit() ? `<button class="btn btn-sm" id="o-near">📍 近くの施設から追加</button><button class="btn btn-primary btn-sm" id="o-add">＋ 営業先</button>` : ''}</div>
    <div class="card-body"><div class="flex flex-wrap mb12">${counts}</div>
    ${list.map(o => `<div class="out" data-oid="${o.id}"><div class="on">${POI_EMOJI[o.type] || '📍'} ${esc(o.name)}<small>${esc(poiTypeOf(o.type).label)}${o.contact ? ' ・ ' + esc(o.contact) : ''}${o.memo ? ' ・ ' + esc(o.memo) : ''}</small></div><select data-ost ${canEdit() ? '' : 'disabled'}>${st.map(x => `<option value="${x.key}" ${o.status === x.key ? 'selected' : ''}>${x.label}</option>`).join('')}</select><input type="date" data-odate value="${esc(o.date || '')}" class="inline" style="border:1px solid var(--line);border-radius:7px;padding:4px 6px;font-size:12px" ${canEdit() ? '' : 'disabled'}>${canEdit() ? `<button class="btn btn-xs" data-odel>✕</button>` : '<span></span>'}</div>`).join('') || '<div class="empty"><div class="big">📣</div>まだ営業先がありません。<br>「近くの施設から追加」で周辺のケアマネ事業所・病院をリストにできます。</div>'}
    <div class="phase-links mt12" style="padding:0">${(S.boot.phase_links.leads || []).map(([l, u]) => `<a href="${esc(u)}" target="_blank">${esc(l)}</a>`).join('')}</div></div></div>`;
  const put = async (oid, d) => { try { await api('PUT', `/api/properties/${p.id}/outreach/${oid}`, d); refreshProgress(false); reloadDrawer(); } catch (e) { err(e); } };
  $$('.out', body).forEach(row => { const oid = row.dataset.oid; $('[data-ost]', row).onchange = (e) => put(oid, { status: e.target.value, date: $('[data-odate]', row).value || today() }); $('[data-odate]', row).onchange = (e) => put(oid, { date: e.target.value }); const del = $('[data-odel]', row); del && (del.onclick = async () => { try { await api('DELETE', `/api/properties/${p.id}/outreach/${oid}`); reloadDrawer(); } catch (e) { err(e); } }); });
  $('#o-add') && ($('#o-add').onclick = () => modal('営業先を追加', `<div class="form-grid">${field('種別', 'type', 'caremanager', { options: S.boot.poi_types.map(t => [t.key, t.label]) })}${field('名称', 'name', '')}${field('担当者・連絡先', 'contact', '', { span: 'span2' })}${field('ステータス', 'status', 'todo', { options: st.map(x => [x.key, x.label]) })}${field('日付', 'date', today(), { type: 'date' })}${field('メモ', 'memo', '', { span: 'span-all', rows: 2 })}</div><div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="o-save">追加</button></div>`, (m) => { $('#o-save', m).onclick = async () => { const d = formData(m); if (!d.name) return toast('名称を入力', 'err'); try { await api('POST', `/api/properties/${p.id}/outreach`, d); closeModal(); refreshProgress(); reloadDrawer(); } catch (e) { err(e); } }; }));
  $('#o-near') && ($('#o-near').onclick = async () => {
    let near = []; try { near = await api('GET', `/api/properties/${p.id}/nearby?km=3`); } catch (e) { return err(e); }
    near = near.filter(x => ['caremanager', 'hospital', 'clinic', 'care', 'other'].includes(x.type) && !list.some(o => o.poi_id === x.id));
    modal('近くの施設から営業先を追加（3km以内）', near.length ? `<div class="small muted mb8">チェックして追加。周辺施設は「周辺施設」画面やマップのOSM取得で増やせます。</div>${near.map(x => `<label class="task"><input type="checkbox" value="${x.id}"><span class="tt">${POI_EMOJI[x.type]} ${esc(x.name)} <span class="small muted">${esc(poiTypeOf(x.type).label)} ・ ${x.distance_km}km${x.tel ? ' ・ ' + esc(x.tel) : ''}</span></span></label>`).join('')}<div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="o-bulk">選択を追加</button></div>` : '<div class="empty">3km以内に登録済みの施設がありません。マップの「この範囲の施設を取得(OSM)」か、周辺施設のCSV取込で追加してください。</div>', (m) => {
      $('#o-bulk', m) && ($('#o-bulk', m).onclick = async () => { const ids = $$('input:checked', m).map(i => i.value); for (const id of ids) { const x = near.find(n => n.id === id); await api('POST', `/api/properties/${p.id}/outreach`, { name: x.name, type: x.type, poi_id: x.id, contact: x.tel || '', status: 'todo' }); } closeModal(); toast(`${ids.length} 件追加しました`, 'ok'); refreshProgress(); reloadDrawer(); });
    });
  });
}
function drawTasks(body, p) {
  const users = S.boot.users.map(u => u.name);
  body.innerHTML = `<div class="card"><div class="card-body">${S.boot.phases.map(ph => {
    const list = p.tasks.filter(t => t.phase === ph.key); const dn = list.filter(t => t.done).length; const pct = list.length ? Math.round(dn / list.length * 100) : 0;
    const rc = charForPhase(ph.key); const links = S.boot.phase_links[ph.key] || [];
    return `<div class="phase-block"><div class="phase-head">${ph.icon} ${ph.label}<span class="char-mini" title="${esc(rc.role)}">${charAvatarHtml(rc, 'av')} ${esc(rc.name)}</span><div class="progress"><i style="width:${pct}%"></i></div><span class="pct">${dn}/${list.length}</span><button class="btn btn-xs" data-add="${ph.key}" style="margin-left:auto">＋ タスク</button></div>
      ${links.length ? `<div class="phase-links">${links.map(([l, u]) => `<a href="${esc(u)}" target="_blank">🔗 ${esc(l)}</a>`).join('')}</div>` : ''}
      ${list.map(t => `<div class="task ${t.done ? 'done' : ''}" data-tid="${t.id}"><input type="checkbox" ${t.done ? 'checked' : ''} ${canEdit() ? '' : 'disabled'}><span class="tt">${esc(t.title)}</span>${t.assignee ? `<span class="who">${esc(t.assignee)}</span>` : ''}<input type="date" class="inline" value="${esc(t.due || '')}" data-due title="期限" ${canEdit() ? '' : 'disabled'}><select class="inline" data-who style="width:90px" ${canEdit() ? '' : 'disabled'}>${['', ...users].map(u => `<option value="${esc(u)}" ${t.assignee === u ? 'selected' : ''}>${u || '担当'}</option>`).join('')}</select>${t.due && !t.done ? `<span class="due ${t.due < today() ? 'over' : ''}">${t.due < today() ? '超過' : ''}</span>` : ''}<button class="del" data-del title="削除">✕</button></div>`).join('') || '<div class="small muted" style="padding:4px 10px">タスクなし</div>'}</div>`;
  }).join('')}</div></div>`;
  $$('.task', body).forEach(row => {
    const tid = row.dataset.tid;
    const put = async (d) => { try { await api('PUT', `/api/properties/${p.id}/tasks/${tid}`, d); await reloadDrawer(); } catch (e) { err(e); } };
    $('input[type=checkbox]', row).onchange = (e) => { put({ done: e.target.checked }); if (e.target.checked) refreshProgress(); };
    $('[data-due]', row).onchange = (e) => put({ due: e.target.value });
    $('[data-who]', row).onchange = (e) => put({ assignee: e.target.value });
    $('[data-del]', row).onclick = async () => { if (!canEdit()) return; try { await api('DELETE', `/api/properties/${p.id}/tasks/${tid}`); reloadDrawer(); } catch (e) { err(e); } };
  });
  $$('[data-add]', body).forEach(b => b.onclick = () => {
    if (!canEdit()) return;
    modal('タスクを追加', `<div class="form-grid">${field('タスク名', 'title', '', { span: 'span-all' })}${field('工程', 'phase', b.dataset.add, { options: S.boot.phases.map(x => [x.key, x.label]) })}${field('期限', 'due', '', { type: 'date' })}${field('担当', 'assignee', '', { options: ['', ...users] })}</div><div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="t-save">追加</button></div>`, (m) => {
      $('#t-save', m).onclick = async () => { const d = formData(m); if (!d.title) return toast('タスク名を入力', 'err'); try { await api('POST', `/api/properties/${p.id}/tasks`, d); closeModal(); reloadDrawer(); } catch (e) { err(e); } };
    });
  });
}
function drawReports(body, p) {
  const kind = { viewing: '内見報告', survey: '現調報告', other: 'その他報告' };
  body.innerHTML = `<div class="flex mb12"><span class="muted small">内見・現地調査の結果を記録します。登録するとSlackに通知されます。</span><span class="grow"></span>${canEdit() ? '<button class="btn btn-primary btn-sm" id="r-add">＋ 報告を書く</button>' : ''}</div>
    ${p.reports.map(r => `<div class="report"><div class="rh"><span class="badge badge-info">${kind[r.type] || '報告'}</span><span>${fmtDate(r.date)}</span><span>👤 ${esc(r.author)}</span><span class="stars">${'★'.repeat(r.rating || 0)}${'☆'.repeat(5 - (r.rating || 0))}</span><span class="grow"></span>${r.url ? `<a href="${esc(r.url)}" target="_blank" class="small">📎 写真・資料</a>` : ''}${canEdit() ? `<button class="btn btn-xs" data-rdel="${r.id}">削除</button>` : ''}</div><div class="sum">${esc(r.summary)}</div>${(r.pros || r.cons) ? `<div class="pc"><div class="pros">👍 ${esc(r.pros || '—')}</div><div class="cons">👎 ${esc(r.cons || '—')}</div></div>` : ''}${r.next_action ? `<div class="mt8 small"><b>次のアクション:</b> ${esc(r.next_action)}</div>` : ''}</div>`).join('') || '<div class="empty"><div class="big">📝</div>まだ報告はありません</div>'}`;
  $('#r-add') && ($('#r-add').onclick = () => modal('内見・現調 報告', `<div class="form-grid">${field('種類', 'type', p.status === 'survey' ? 'survey' : 'viewing', { options: [['viewing', '内見報告'], ['survey', '現調報告'], ['other', 'その他']] })}${field('実施日', 'date', today(), { type: 'date' })}${field('評価 (1-5)', 'rating', 3, { options: [[1, '★ 1'], [2, '★★ 2'], [3, '★★★ 3'], [4, '★★★★ 4'], [5, '★★★★★ 5']] })}${field('所感・総評', 'summary', '', { span: 'span-all', rows: 4, placeholder: '立地・建物の状態・改修の必要性・周辺の競合など' })}${field('良い点', 'pros', '', { rows: 3 })}${field('懸念点', 'cons', '', { rows: 3 })}${field('次のアクション', 'next_action', '', { span: 'span-all' })}${field('写真・資料 URL (Drive)', 'url', '', { span: 'span-all', placeholder: 'https://drive.google.com/…' })}</div><div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="r-save">登録してSlack通知</button></div>`, (m) => {
    $('#r-save', m).onclick = async () => { const d = formData(m); if (!d.summary) return toast('所感を入力してください', 'err'); try { await api('POST', `/api/properties/${p.id}/reports`, d); closeModal(); toast('報告を登録しました', 'ok'); refreshProgress(); reloadDrawer(); } catch (e) { err(e); } };
  }));
  $$('[data-rdel]', body).forEach(b => b.onclick = async () => { if (!await confirmDlg('この報告を削除しますか？')) return; try { await api('DELETE', `/api/properties/${p.id}/reports/${b.dataset.rdel}`); reloadDrawer(); } catch (e) { err(e); } });
}
function drawDocs(body, p) {
  const s = S.boot.settings; const folder = p.drive?.folder_url;
  const pickerReady = !!(s.google_client_id && s.google_api_key);
  body.innerHTML = `<div class="card"><div class="card-head"><div class="card-title">📁 Googleドライブ</div><span class="grow"></span>${folder ? `<a class="btn btn-sm" href="${esc(folder)}" target="_blank">フォルダを開く</a>` : ''}${canEdit() ? `<button class="btn btn-sm" id="d-folder">${folder ? 'フォルダを変更' : 'フォルダを設定'}</button>` : ''}${pickerReady && canEdit() ? `<button class="btn btn-sm" id="d-mkfolder">＋ Driveにフォルダ作成</button>` : ''}</div>
    <div class="card-body"><div class="small muted mb8">標準フォルダ構成: ${S.boot.drive_folders.map(f => `<code>${esc(f)}</code>`).join(' ')}</div>${folder ? `<div class="small muted">この物件の書類は ${esc(folder)} に保存。${s.drive_root_url ? `<a href="${esc(s.drive_root_url)}" target="_blank">ルートフォルダ</a>` : ''}</div>` : `<div class="small muted">Driveフォルダが未設定です。${s.drive_root_url ? `<a href="${esc(s.drive_root_url)}" target="_blank">ルートフォルダ</a>に「${esc(p.name)}」フォルダを作り、URLを設定してください。` : ''}</div>`}</div></div>
    <div class="card"><div class="card-head"><div class="card-title">書類（稟議書・収支・図面・契約書 など）</div><span class="grow"></span>${canEdit() ? `<button class="btn btn-primary btn-sm" id="doc-add">＋ リンクを追加</button>${pickerReady ? `<button class="btn btn-sm" id="doc-pick">Driveから選択</button>` : ''}` : ''}</div>
    <div class="card-body">${p.docs.map(d => `<div class="doc"><span class="dt">${esc(d.type)}</span><a class="dn" href="${esc(d.url || (d.drive_id ? 'https://drive.google.com/open?id=' + d.drive_id : '#'))}" target="_blank">${esc(d.title)}</a><span class="small muted nowrap">${esc(d.updated_at)} ${esc(d.by || '')}</span>${canEdit() ? `<button class="btn btn-xs" data-ddel="${d.id}">✕</button>` : ''}</div>`).join('') || '<div class="empty">書類リンクはまだありません。稟議書・収支計画などのDriveリンクを登録しましょう。</div>'}</div></div>`;
  $('#d-folder') && ($('#d-folder').onclick = () => modal('Driveフォルダを設定', `<div class="field"><label>フォルダURL</label><input id="f-url" value="${esc(folder || '')}" placeholder="https://drive.google.com/drive/folders/…"></div><div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="f-save">保存</button></div>`, (m) => { $('#f-save', m).onclick = async () => { try { await api('PUT', `/api/properties/${p.id}`, { drive: { folder_url: $('#f-url', m).value } }); closeModal(); reloadDrawer(); } catch (e) { err(e); } }; }));
  $('#doc-add') && ($('#doc-add').onclick = () => modal('書類リンクを追加', `<div class="form-grid">${field('種別', 'type', '稟議書', { options: S.boot.doc_types })}${field('タイトル', 'title', '')}${field('URL（Drive等）', 'url', '', { span: 'span-all', placeholder: 'https://docs.google.com/… または https://drive.google.com/…' })}</div><div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="doc-save">追加</button></div>`, (m) => { $('#doc-save', m).onclick = async () => { const d = formData(m); if (!d.url) return toast('URLを入力', 'err'); try { await api('POST', `/api/properties/${p.id}/docs`, d); closeModal(); reloadDrawer(); } catch (e) { err(e); } }; }));
  $('#doc-pick') && ($('#doc-pick').onclick = () => drivePick(async (files) => { for (const f of files) { await api('POST', `/api/properties/${p.id}/docs`, { type: guessDocType(f.name), title: f.name, url: f.url, drive_id: f.id, mime: f.mimeType }); } toast(`${files.length} 件の書類を追加しました`, 'ok'); reloadDrawer(); }));
  $('#d-mkfolder') && ($('#d-mkfolder').onclick = () => driveCreateFolder(p));
  $$('[data-ddel]', body).forEach(b => b.onclick = async () => { try { await api('DELETE', `/api/properties/${p.id}/docs/${b.dataset.ddel}`); reloadDrawer(); } catch (e) { err(e); } });
}
function guessDocType(name) { for (const t of S.boot.doc_types) if (name.includes(t.split('・')[0])) return t; if (/収支|P\/?L|シミュ/.test(name)) return '収支計画'; if (/稟議/.test(name)) return '稟議書'; if (/図面|マイソク|平面/.test(name)) return 'マイソク・図面'; if (/契約/.test(name)) return '契約書'; if (/見積/.test(name)) return '見積書'; return 'その他'; }
function drawHistory(body, p) {
  body.innerHTML = `<div class="card"><div class="card-head"><div class="card-title">メモ・特記事項</div><span class="muted small">統一フォーマットに収まらない個別の内容</span></div><div class="card-body"><div class="field"><textarea id="memo" rows="6" ${canEdit() ? '' : 'disabled'}>${esc(p.memo || '')}</textarea></div>${canEdit() ? '<button class="btn btn-primary btn-sm mt8" id="memo-save">メモを保存</button>' : ''}</div></div>
    <div class="card"><div class="card-head"><div class="card-title">履歴</div></div><div class="card-body">${[...(p.history || [])].reverse().map(h => `<div class="hist"><span class="mono">${fmtDT(h.at)}</span><b>${esc(h.by || '')}</b><span>${esc(h.detail || h.action)}</span></div>`).join('') || '<div class="muted">履歴なし</div>'}</div></div>`;
  $('#memo-save') && ($('#memo-save').onclick = async () => { try { await api('PUT', `/api/properties/${p.id}`, { memo: $('#memo').value }); toast('メモを保存しました', 'ok'); reloadDrawer(); } catch (e) { err(e); } });
}
function editProperty(p) {
  if (!canEdit()) return toast('閲覧権限のみです', 'err');
  modal('物件を編集', `${propertyFormHtml(p)}<div class="modal-foot"><button class="btn" id="m-cancel">キャンセル</button><button class="btn btn-primary" id="m-save">保存</button></div>`, (body) => {
    $('#m-cancel', body).onclick = closeModal;
    $('#m-save', body).onclick = async () => { const d = readPropertyForm($('#prop-form', body)); if (d.address !== p.address && !('lat' in d && d.lat !== p.lat)) { delete d.lat; delete d.lon; } try { await api('PUT', `/api/properties/${p.id}`, d); closeModal(); toast('保存しました', 'ok'); await refreshProps(); reloadDrawer(); if (S.view === 'map' && S.map) { drawMapMarkers(); drawMapList(); } } catch (e) { err(e); } };
  });
}

// ================================================================ Google Drive（Picker / フォルダ作成: ブラウザ側 OAuth、サーバーに秘密情報を置かない）
let _gToken = null;
function gToken(scope) {
  return new Promise((resolve, reject) => {
    if (!window.google?.accounts?.oauth2) return reject(new Error('Googleライブラリの読み込み待ちです。数秒後に再試行してください'));
    if (_gToken && _gToken.scope === scope && _gToken.exp > Date.now()) return resolve(_gToken.token);
    const client = google.accounts.oauth2.initTokenClient({ client_id: S.boot.settings.google_client_id, scope, callback: (r) => { if (r.error) return reject(new Error(r.error)); _gToken = { token: r.access_token, scope, exp: Date.now() + (r.expires_in - 60) * 1000 }; resolve(r.access_token); } });
    client.requestAccessToken();
  });
}
async function drivePick(onPicked) {
  try {
    const token = await gToken('https://www.googleapis.com/auth/drive.readonly');
    await new Promise(res => gapi.load('picker', res));
    const view = new google.picker.DocsView(google.picker.ViewId.DOCS).setIncludeFolders(true).setSelectFolderEnabled(false);
    new google.picker.PickerBuilder().setOAuthToken(token).setDeveloperKey(S.boot.settings.google_api_key).addView(view).setLocale('ja').enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
      .setCallback((d) => { if (d.action === google.picker.Action.PICKED) onPicked(d.docs.map(x => ({ id: x.id, name: x.name, url: x.url, mimeType: x.mimeType }))).catch(err); }).build().setVisible(true);
  } catch (e) { err(e); }
}
async function driveCreateFolder(p) {
  try {
    const token = await gToken('https://www.googleapis.com/auth/drive.file');
    const rootId = (S.boot.settings.drive_root_url.match(/folders\/([\w-]+)/) || [])[1];
    const meta = { name: `${p.pref || ''}${p.city || ''} ${p.name}`.trim(), mimeType: 'application/vnd.google-apps.folder', ...(rootId ? { parents: [rootId] } : {}) };
    const r = await fetch('https://www.googleapis.com/drive/v3/files?fields=id,webViewLink', { method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: JSON.stringify(meta) });
    const d = await r.json(); if (!r.ok) throw new Error(d.error?.message || 'フォルダ作成に失敗');
    await api('PUT', `/api/properties/${p.id}`, { drive: { folder_url: d.webViewLink, folder_id: d.id } });
    toast('Driveにフォルダを作成しました', 'ok'); reloadDrawer();
  } catch (e) { err(e); }
}

// ================================================================ 周辺施設
async function renderPois(el) {
  await refreshPois();
  const draw = () => {
    const f = S.filter;
    const items = S.pois.filter(x => (!f.pref || x.pref === f.pref) && (!f.city || x.city === f.city) && (!S.q || `${x.name} ${x.address}`.includes(S.q)));
    el.innerHTML = `<div class="flex flex-wrap mb12">${areaFilterHtml()}<span class="grow"></span>${canEdit() ? '<button class="btn btn-sm" id="poi-csv">📥 CSV取込</button><button class="btn btn-primary btn-sm" id="poi-add">＋ 施設を追加</button>' : ''}</div>
      <div class="card mb16"><div class="card-body small"><b>無料データの入手先:</b> 国土数値情報「医療機関」「福祉施設」「市町村役場等」（国土交通省）/ 各都道府県の「有料老人ホーム一覧」「居宅介護支援事業所一覧」（Excel/CSV公開）/ 介護サービス情報公表システム。CSVの列名は「名称・住所・緯度・経度・種別・電話」を想定（住所のみでも座標を自動取得）。地図画面の「この範囲の施設を取得(OSM)」でOpenStreetMapからも取り込めます。</div></div>
      <div class="card"><div class="table-wrap"><table class="tbl"><thead><tr><th>種別</th><th>名称</th><th>住所</th><th>電話</th><th>定員</th><th>備考</th><th></th></tr></thead><tbody>${items.slice(0, 500).map(x => { const t = poiTypeOf(x.type); return `<tr><td><span class="badge" style="background:${t.color};color:#fff">${POI_EMOJI[x.type]} ${t.label}</span></td><td class="name">${esc(x.name)}${!x.lat ? ' <span class="badge badge-warn">座標なし</span>' : ''}</td><td class="small">${esc(x.address)}</td><td class="small">${esc(x.tel)}</td><td>${esc(x.capacity)}</td><td class="small muted">${esc(x.memo)}</td><td class="nowrap">${x.lat ? `<a class="btn btn-xs" href="https://www.google.com/maps/search/?api=1&query=${x.lat},${x.lon}" target="_blank">地図</a>` : ''} ${canEdit() ? `<button class="btn btn-xs" data-pdel="${x.id}">✕</button>` : ''}</td></tr>`; }).join('') || '<tr><td colspan="7"><div class="empty"><div class="big">🏥</div>施設データがありません。CSV取込か地図のOSM取得で追加できます。</div></td></tr>'}</tbody></table></div>${items.length > 500 ? `<div class="small muted" style="padding:8px 12px">${items.length} 件中 500 件を表示（エリアで絞り込んでください）</div>` : ''}</div>`;
    bindAreaFilter(el, draw);
    $('#poi-add') && ($('#poi-add').onclick = () => modal('施設を追加', `<div class="form-grid">${field('種別', 'type', 'hospital', { options: S.boot.poi_types.map(t => [t.key, t.label]) })}${field('名称', 'name', '')}${field('住所', 'address', '', { span: 'span2', hint: '座標を自動取得' })}${field('電話', 'tel', '')}${field('定員', 'capacity', '')}${field('URL', 'url', '', { span: 'span2' })}${field('備考', 'memo', '', { span: 'span-all', rows: 2 })}</div><div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="poi-save">追加</button></div>`, (m) => { $('#poi-save', m).onclick = async () => { const d = formData(m); if (!d.name) return toast('名称を入力', 'err'); try { await api('POST', '/api/pois', d); closeModal(); await refreshPois(); draw(); } catch (e) { err(e); } }; }));
    $('#poi-csv') && ($('#poi-csv').onclick = () => modal('施設CSVを取込', `<div class="form-grid">${field('既定の種別（CSVに種別列がない場合）', 'type', 'hospital', { options: S.boot.poi_types.map(t => [t.key, t.label]), span: 'span-all' })}<div class="field span-all"><label>CSVファイル（UTF-8 / Shift_JIS）</label><input type="file" id="poi-file" accept=".csv"></div></div><div class="modal-foot"><button class="btn" onclick="MagoLove.closeModal()">キャンセル</button><button class="btn btn-primary" id="poi-imp">取込</button></div>`, (m) => { $('#poi-imp', m).onclick = async () => { const f = $('#poi-file', m).files[0]; if (!f) return toast('CSVを選択', 'err'); const fd = new FormData(); fd.append('file', f); fd.append('type', $('[name=type]', m).value); try { toast('取込中…'); const r = await api('POST', '/api/pois/import', fd, true); closeModal(); toast(`${r.created} 件取込`, 'ok'); await refreshPois(); draw(); } catch (e) { err(e); } }; }));
    $$('[data-pdel]', el).forEach(b => b.onclick = async () => { try { await api('DELETE', `/api/pois/${b.dataset.pdel}`); await refreshPois(); draw(); } catch (e) { err(e); } });
  };
  draw();
}

// ================================================================ 統計
async function renderStats(el) {
  await refreshStats();
  const ds = await api('GET', '/api/stats/datasets');
  S.areaScores = await api('GET', '/api/area_scores');
  const draw = () => {
    const f = S.filter;
    const rows = S.stats.filter(x => (!f.pref || x.pref === f.pref) && (!f.city || x.city === f.city));
    const cols = [...new Set(rows.flatMap(r => Object.keys(r.metrics)))].slice(0, 12);
    el.innerHTML = `<div class="import-grid mb16">
      <div class="card"><div class="card-head"><div class="card-title">📈 統計CSVを取り込む</div></div><div class="card-body"><p class="small">必須列: <code>都道府県</code>, <code>市区町村</code>。ほかの列（総人口・65歳以上人口・高齢化率・要介護認定者数 など）はそのまま指標として保存され、地図で市区町村を選ぶと表示されます。</p>
        <div class="pre mt8">都道府県,市区町村,総人口,65歳以上人口,高齢化率,要介護認定者数
東京都,杉並区,570000,120000,21.1,28000</div>
        <p class="small muted mt8">入手先: e-Stat（国勢調査・住民基本台帳）、各自治体の統計ページ、介護保険事業状況報告。</p>
        <div class="form-grid mt12">${field('データセット名', 'dataset', '人口統計', { hint: '同じ名前で再取込すると上書き' })}<div class="field"><label>CSV</label><input type="file" id="stat-file" accept=".csv"></div></div>
        ${canEdit() ? '<button class="btn btn-primary mt12" id="stat-imp">取込</button>' : ''}</div></div>
      <div class="card"><div class="card-head"><div class="card-title">取込済みデータセット</div></div><div class="card-body">${ds.map(d => `<div class="flex mb8"><b>${esc(d.dataset)}</b><span class="muted small">${d.rows} 行</span><span class="grow"></span>${isAdmin() ? `<button class="btn btn-xs btn-danger" data-dsdel="${esc(d.dataset)}">削除</button>` : ''}</div>`).join('') || '<div class="muted">まだありません</div>'}</div></div>
    </div>
    <div class="card mb16"><div class="card-head"><div class="card-title">🏆 エリア比較（需要 ÷ 他社施設 が高く、坪単価が低い順）</div><span class="muted small">統計CSV・周辺施設・登録物件から自動集計</span></div><div class="table-wrap"><table class="tbl"><thead><tr><th>#</th><th>都道府県</th><th>市区町村</th><th class="right">要介護認定者</th><th class="right">65歳以上</th><th class="right">高齢化率</th><th class="right">他社施設</th><th class="right">ケアマネ</th><th class="right">病院</th><th class="right">需要/供給</th><th class="right">候補 坪単価</th><th class="right">候補数</th></tr></thead><tbody>${(S.areaScores || []).slice(0, 50).map((r, i) => `<tr class="row-link" data-area-go="${esc(r.pref)}|${esc(r.city)}"><td class="muted">${i + 1}</td><td>${esc(r.pref || '')}</td><td class="name">${esc(r.city)}</td><td class="right mono">${num(r.certified)}</td><td class="right mono">${num(r.elderly)}</td><td class="right mono">${r.rate ?? '—'}${r.rate ? '%' : ''}</td><td class="right mono">${r.care}</td><td class="right mono">${r.caremanager}</td><td class="right mono">${r.hospital}</td><td class="right mono"><b>${num(r.demand_per_supply)}</b></td><td class="right mono">${r.avg_tsubo_price ? yen(r.avg_tsubo_price) : '—'}</td><td class="right mono">${r.props}</td></tr>`).join('') || '<tr><td colspan="12"><div class="empty">統計CSVや周辺施設を取り込むとエリア比較が表示されます</div></td></tr>'}</tbody></table></div></div>
    <div class="flex flex-wrap mb12">${areaFilterHtml()}</div>
    <div class="card"><div class="table-wrap"><table class="tbl"><thead><tr><th>データセット</th><th>都道府県</th><th>市区町村</th>${cols.map(c => `<th class="right">${esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0, 400).map(r => `<tr><td class="small muted">${esc(r.dataset)}</td><td>${esc(r.pref)}</td><td class="name">${esc(r.city)}</td>${cols.map(c => `<td class="right mono">${r.metrics[c] === undefined ? '' : (typeof r.metrics[c] === 'number' ? r.metrics[c].toLocaleString() : esc(r.metrics[c]))}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${3 + cols.length}"><div class="empty">統計データがありません</div></td></tr>`}</tbody></table></div></div>`;
    bindAreaFilter(el, draw);
    $$('[data-area-go]', el).forEach(tr => tr.onclick = () => { const [pref, city] = tr.dataset.areaGo.split('|'); S.filter = { pref, city, ward: '', status: [] }; location.hash = '#/map'; });
    $('#stat-imp') && ($('#stat-imp').onclick = async () => { const f = $('#stat-file').files[0]; if (!f) return toast('CSVを選択', 'err'); const fd = new FormData(); fd.append('file', f); fd.append('dataset', $('[name=dataset]', el).value); try { const r = await api('POST', '/api/stats/import', fd, true); toast(`${r.created} 行を取込`, 'ok'); renderStats(el); } catch (e) { err(e); } });
    $$('[data-dsdel]', el).forEach(b => b.onclick = async () => { if (!await confirmDlg(`データセット「${b.dataset.dsdel}」を削除しますか？`)) return; try { await api('DELETE', `/api/stats/datasets/${encodeURIComponent(b.dataset.dsdel)}`); renderStats(el); } catch (e) { err(e); } });
  };
  draw();
}

// ================================================================ 設定
async function renderSettings(el) {
  if (!isAdmin()) { el.innerHTML = `<div class="card"><div class="card-body"><div class="section-title">連携状況</div><dl class="kv"><dt>Slack通知</dt><dd>${S.boot.settings.slack_configured ? '<span class="badge badge-ok">設定済み</span>' : '<span class="badge">未設定</span>'}</dd><dt>Googleログイン</dt><dd>${S.boot.settings.google_login ? '有効' : '開発モード'}</dd><dt>ZENRIN地図</dt><dd>${S.boot.settings.zenrin_tile_url ? '有効' : '未設定（地理院地図を使用）'}</dd></dl><p class="muted mt12">設定の変更は管理者のみ行えます。</p><button class="btn btn-sm mt12" id="c-choose">🎮 パートナーを変更</button></div></div>`; $('#c-choose').onclick = () => chooseCharacter(false); return; }
  const s = await api('GET', '/api/settings'); const users = await api('GET', '/api/users');
  const origin = location.origin;
  el.innerHTML = `<div class="dash-grid">
    <div class="col">
      <div class="card"><div class="card-head"><div class="card-title">🔔 Slack通知</div>${S.boot.settings.slack_configured ? '<span class="badge badge-ok">接続済み</span>' : '<span class="badge">未接続</span>'}</div><div class="card-body">
        <p class="small">Slackで <b>アプリ → Incoming Webhook</b> を追加し、通知したいチャンネルのWebhook URLを貼り付けてください（無料）。</p>
        <div class="form-grid mt12">${field('Webhook URL', 'slack_webhook_url', s.slack_webhook_url || '', { span: 'span-all', placeholder: 'https://hooks.slack.com/services/…' })}${field('アプリURL（通知内リンク用）', 'app_url', s.app_url || origin, { span: 'span-all' })}</div>
        <div class="section-title">通知する内容</div>
        <div class="flex flex-wrap">${[['notify_on_create', '物件登録'], ['notify_on_status', 'ステータス変更'], ['notify_on_report', '内見・現調報告'], ['notify_on_schedule', '予定（内見日・開業日など）の更新']].map(([k, l]) => `<label class="chip ${s[k] !== false ? 'active' : ''}"><input type="checkbox" name="${k}" ${s[k] !== false ? 'checked' : ''} hidden>${l}</label>`).join('')}</div>
        <div class="form-grid mt12">${field('ダイジェストで先読みする日数', 'digest_days_ahead', s.digest_days_ahead || 7, { type: 'number' })}${field('cron トークン（日次ダイジェスト用）', 'cron_token', s.cron_token || '', { hint: '任意の長い文字列' })}</div>
        <div class="flex mt12"><button class="btn btn-primary" id="s-save">保存</button><button class="btn" id="s-test">テスト送信</button><button class="btn" id="s-digest">今すぐダイジェスト送信</button></div>
        <div class="section-title">毎朝の自動リマインド（無料cron）</div>
        <p class="small">cron-job.org や GitHub Actions などから毎朝 8:00 に次のURLを叩くと、期限超過・7日以内のタスク・今後14日の予定がSlackに届きます。</p>
        <div class="pre mt8">GET ${esc(origin)}/api/cron/digest?token=（cronトークン）</div>
      </div></div>
      <div class="card"><div class="card-head"><div class="card-title">🗺️ 地図・Google連携</div></div><div class="card-body">
        <div class="form-grid">
          ${field('ZENRIN タイルURL（任意）', 'zenrin_tile_url', s.zenrin_tile_url || '', { span: 'span-all', placeholder: 'https://…/{z}/{x}/{y}.png?key=…', hint: 'ZENRIN Maps API 契約後に発行されるラスタタイルURL。未設定時は国土地理院地図（無料）' })}
          ${field('Google API キー（Drive Picker用・任意）', 'google_api_key', s.google_api_key || '', { span: 'span-all', hint: 'Google Cloud Console で Picker API を有効化したAPIキー。Googleログイン用 CLIENT_ID と組み合わせて「Driveから選択」「フォルダ作成」が使えます' })}
          ${field('Google ドライブ ルートフォルダURL', 'drive_root_url', s.drive_root_url || '', { span: 'span-all', placeholder: 'https://drive.google.com/drive/folders/…', hint: '出店案件を格納している共有ドライブ／フォルダ' })}
          ${field('カレンダー(ICS) トークン', 'ics_token', s.ics_token || '', { hint: 'Googleカレンダー「URLで追加」用' })}
          ${field('初期表示 中心（緯度,経度）', 'default_center_text', (s.default_center || [35.75, 139.75]).join(','))}
          ${field('初期ズーム', 'default_zoom', s.default_zoom || 9, { type: 'number' })}
        </div>
        <div class="flex mt12"><button class="btn btn-primary" id="s-save2">保存</button></div>
        <div class="section-title">Googleカレンダー</div><div class="pre">${esc(origin)}/api/export/calendar.ics?token=（ICSトークン）</div>
        <div class="section-title">Googleスプレッドシート</div><p class="small">物件一覧の「⬇ CSV」をスプレッドシートにインポート、または <code>=IMPORTDATA("${esc(origin)}/api/export/properties.csv")</code>（ログインが必要なため共有時はCSVを配置してください）。</p>
      </div></div>
    </div>
    <div class="col">
      <div class="card"><div class="card-head"><div class="card-title">👥 ユーザー（招待制）</div></div><div class="card-body">
        <div class="form-grid">${field('メール', 'u_email', '', { placeholder: 'name@example.com' })}${field('表示名', 'u_name', '')}${field('権限', 'u_role', 'member', { options: [['admin', '管理者'], ['member', 'メンバー'], ['viewer', '閲覧']] })}</div>
        <button class="btn btn-primary btn-sm mt12" id="u-add">＋ 招待</button>
        <div class="table-wrap mt12"><table class="tbl"><thead><tr><th>名前</th><th>メール</th><th>権限</th><th></th></tr></thead><tbody>${users.map(u => `<tr><td>${esc(u.name)}</td><td class="small">${esc(u.email)}</td><td><select data-urole="${esc(u.email)}">${[['admin', '管理者'], ['member', 'メンバー'], ['viewer', '閲覧']].map(([k, l]) => `<option value="${k}" ${u.role === k ? 'selected' : ''}>${l}</option>`).join('')}</select></td><td>${u.email !== S.boot.me.email ? `<button class="btn btn-xs btn-danger" data-udel="${esc(u.email)}">削除</button>` : ''}</td></tr>`).join('')}</tbody></table></div>
        <p class="small muted mt8">Googleログイン（GOOGLE_CLIENT_ID）を有効にすると、ここに登録したメールのGoogleアカウントだけがログインできます。</p>
      </div></div>
      <div class="card"><div class="card-head"><div class="card-title">🎮 パートナーキャラクター</div></div><div class="card-body">
        <p class="small muted">各キャラの画像（PNG/JPG、正方形推奨）をアップロードすると、画面右下のパートナーや選択画面に表示されます。名前も変更できます。</p>
        ${S.boot.characters.map(c => `<div class="flex mt12" style="gap:12px">${charAvatarHtml(c, 'av').replace('class="av"', 'class="av" style="width:56px;height:56px;border-radius:50%;background-size:cover;display:inline-flex;align-items:center;justify-content:center;font-size:28px;flex-shrink:0;background-color:#f1f5f9"')}<div class="grow"><input data-cname="${c.id}" value="${esc(c.name)}" style="font-weight:800;border:1px solid var(--line);border-radius:8px;padding:4px 8px;width:160px"> <span class="small muted">${esc(c.species)} ・ ${esc(c.role)}</span></div><input type="file" accept="image/*" data-cimg="${c.id}" style="max-width:190px">${c.image ? `<button class="btn btn-xs btn-danger" data-cdel="${c.id}">画像削除</button>` : ''}</div>`).join('')}
        <div class="flex mt12"><button class="btn btn-primary btn-sm" id="c-names">名前を保存</button><button class="btn btn-sm" id="c-choose">自分のパートナーを変更</button></div>
      </div></div>
      <div class="card"><div class="card-head"><div class="card-title">ℹ️ 環境</div></div><div class="card-body"><dl class="kv"><dt>Googleログイン</dt><dd>${S.boot.settings.google_login ? '<span class="badge badge-ok">有効</span>' : '<span class="badge badge-warn">開発モード</span>'}</dd><dt>AI構造化</dt><dd>${S.boot.settings.llm_enabled ? '<span class="badge badge-ok">有効</span>' : '<span class="badge">無効（正規表現抽出）</span>'}</dd><dt>市区町村マスタ</dt><dd>${S.boot.municipalities.length} 件（関東1都6県）</dd></dl></div></div>
    </div></div>`;
  const save = async () => { const d = formData(el); const out = {}; ['slack_webhook_url', 'app_url', 'notify_on_create', 'notify_on_status', 'notify_on_report', 'notify_on_schedule', 'digest_days_ahead', 'cron_token', 'zenrin_tile_url', 'google_api_key', 'drive_root_url', 'ics_token', 'default_zoom'].forEach(k => out[k] = d[k]); const c = (d.default_center_text || '').split(',').map(Number); if (c.length === 2 && !c.some(isNaN)) out.default_center = c; try { await api('PUT', '/api/settings', out); toast('設定を保存しました', 'ok'); S.boot = await api('GET', '/api/bootstrap'); } catch (e) { err(e); } };
  $('#s-save').onclick = save; $('#s-save2').onclick = save;
  $$('label.chip input', el).forEach(i => i.onchange = () => i.parentElement.classList.toggle('active', i.checked));
  $('#s-test').onclick = async () => { await save(); try { const r = await api('POST', '/api/slack/test'); toast(r.ok ? 'Slackに送信しました' : 'Webhookが未設定または送信失敗', r.ok ? 'ok' : 'err'); } catch (e) { err(e); } };
  $('#s-digest').onclick = async () => { await save(); try { const r = await api('POST', '/api/slack/digest'); toast(r.sent ? `送信しました（超過${r.overdue}/直近${r.soon}/予定${r.events}）` : '送る内容がないか、Webhook未設定です'); } catch (e) { err(e); } };
  $$('[data-cimg]', el).forEach(inp => inp.onchange = async () => { const f = inp.files[0]; if (!f) return; const fd = new FormData(); fd.append('file', f); try { S.boot.characters = await api('POST', `/api/characters/${inp.dataset.cimg}/image`, fd, true); toast('画像を設定しました', 'ok'); renderPartner(); renderSettings(el); } catch (e) { err(e); } });
  $$('[data-cdel]', el).forEach(b => b.onclick = async () => { try { S.boot.characters = await api('DELETE', `/api/characters/${b.dataset.cdel}/image`); renderPartner(); renderSettings(el); } catch (e) { err(e); } });
  $('#c-names').onclick = async () => { const names = {}; $$('[data-cname]', el).forEach(i => names[i.dataset.cname] = i.value.trim() || undefined); try { S.boot.characters = await api('PUT', '/api/characters/names', names); toast('名前を保存しました', 'ok'); renderPartner(); } catch (e) { err(e); } };
  $('#c-choose').onclick = () => chooseCharacter(false);
  $('#u-add').onclick = async () => { const d = formData(el); try { await api('POST', '/api/users', { email: d.u_email, name: d.u_name, role: d.u_role }); toast('招待しました', 'ok'); renderSettings(el); } catch (e) { err(e); } };
  $$('[data-urole]', el).forEach(sel => sel.onchange = async () => { try { await api('PUT', `/api/users/${encodeURIComponent(sel.dataset.urole)}`, { role: sel.value }); toast('権限を更新', 'ok'); } catch (e) { err(e); } });
  $$('[data-udel]', el).forEach(b => b.onclick = async () => { if (!await confirmDlg(`${b.dataset.udel} を削除しますか？`)) return; try { await api('DELETE', `/api/users/${encodeURIComponent(b.dataset.udel)}`); renderSettings(el); } catch (e) { err(e); } });
}

// ================================================================ パートナー（キャラクター）・レベル
let _typing = null, _lineIdx = 0, _lastKind = '';
function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
function partnerSay(text, opts = {}) {
  const c = myChar(); const bubble = $('#partner-bubble'), span = $('#partner-text');
  bubble.classList.remove('hidden'); clearInterval(_typing);
  span.innerHTML = `<span class="name">${esc(c.name)}</span>`;
  const body = document.createElement('span'); span.appendChild(body);
  let i = 0; _typing = setInterval(() => { body.textContent = text.slice(0, ++i); if (i >= text.length) clearInterval(_typing); }, 22);
  if (opts.bounce) { const av = $('#partner-avatar'); av.classList.remove('bounce'); void av.offsetWidth; av.classList.add('bounce'); }
}
function partnerContextLines() {
  const c = myChar(); const lines = [];
  const overdue = S.props.reduce((n, p) => n + taskStats(p).overdue, 0);
  if (overdue) lines.push(pick(c.lines.warn).replace('期限切れのタスク', `期限切れのタスク（${overdue}件）`).replace('期限を過ぎたタスク', `期限を過ぎたタスク（${overdue}件）`).replace('期限が過ぎているタスク', `期限が過ぎているタスク（${overdue}件）`));
  const soon = S.props.flatMap(p => SCHED.filter(([k]) => p.schedule?.[k] && p.schedule[k] >= today() && p.schedule[k] <= addDays(3)).map(([k, l]) => `${p.name}の${l}が ${fmtDate(p.schedule[k])} だよ。準備は大丈夫？`));
  lines.push(...soon.slice(0, 2));
  if (S.view === 'map') lines.push('地図では「関東 → 都道府県 → 市区町村」で絞り込めるよ。坪単価が低くてケアマネ事業所が近い場所を探そう。');
  if (S.view === 'board') lines.push('カードをドラッグしてステータスを進めよう。ステータスが進むと経験値も入るよ！');
  if (S.view === 'import') lines.push('マイソクPDFをドロップすれば、住所や賃料を自動で読み取るよ。');
  if (S.drawerId) { const p = S.props.find(x => x.id === S.drawerId); if (p) { const ph = S.boot.phases.find(ph => p.tasks.some(t => t.phase === ph.key && !t.done)); if (ph) { const rc = charForPhase(ph.key); lines.push(rc.id === c.id ? `「${p.name}」は今「${ph.label}」の工程。ここは${c.name === rc.name ? '私' : rc.name}の得意分野！` : `「${p.name}」の次は「${ph.label}」。${rc.name}が詳しいよ。`); } if (!p.survey?.at && p.lat) lines.push('この物件はまだリスク調査をしてないね。概要タブの「自動調査」を押してみて。'); } }
  lines.push(...c.lines.idle);
  return lines;
}
function partnerNext() { const lines = partnerContextLines(); _lineIdx = (_lineIdx + 1) % lines.length; partnerSay(lines[_lineIdx]); }
function partnerGreet() { const c = myChar(); partnerSay(pick(c.lines.greet), { bounce: true }); _lineIdx = -1; }
function partnerPraise() { partnerSay(pick(myChar().lines.praise), { bounce: true }); }
function addDays(n) { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); }
function renderPartner() {
  const c = myChar(); const av = $('#partner-avatar');
  av.style.backgroundImage = c.image ? `url('${c.image}')` : ''; av.textContent = c.image ? '' : c.emoji;
  av.style.borderColor = c.color; $('#partner').hidden = false;
}
function renderLevel() {
  const pr = S.boot.progress; if (!pr) return;
  $('#lv-num').textContent = `Lv.${pr.level}`; $('#lv-title').textContent = pr.title;
  $('#xp-bar').style.width = `${Math.round(pr.xp_in_level / pr.xp_next * 100)}%`;
  $('#lv-xp').textContent = `${pr.xp_in_level} / ${pr.xp_next} XP（累計 ${pr.xp}）`;
}
async function refreshProgress(praise = true) {
  const before = S.boot.progress?.level || 1;
  try { S.boot.progress = await api('GET', '/api/me/progress'); } catch { return; }
  renderLevel();
  if (S.boot.progress.level > before) levelUp(S.boot.progress); else if (praise) partnerPraise();
}
function levelUp(pr) {
  const el = document.createElement('div'); el.className = 'levelup';
  el.innerHTML = `<div class="box"><div class="big">🎉</div><h2>レベルアップ！ Lv.${pr.level}</h2><div>${esc(pr.title)}</div><div class="muted small mt8">${esc(myChar().name)}「${esc(pick(myChar().lines.praise))}」</div><button class="btn btn-primary mt16">やったー！</button></div>`;
  el.querySelector('button').onclick = () => el.remove(); el.onclick = (e) => { if (e.target === el) el.remove(); };
  document.body.appendChild(el);
}
function chooseCharacter(force = false) {
  const cur = S.boot.my_character;
  modal(force ? 'パートナーを選ぼう' : 'パートナーを変更', `<p class="small muted mb12">一緒に出店を進めるパートナーを選んでください。各キャラは得意な工程があり、画面右下で状況に合わせてアドバイスします。あとから「設定」で変更できます。</p>
    <div class="char-grid">${S.boot.characters.map(c => `<div class="char-card ${c.id === cur ? 'sel' : ''}" data-cid="${c.id}">${charAvatarHtml(c)}<div class="nm">${esc(c.name)}</div><div class="rl">${esc(c.role)}</div><div class="ps">${esc(c.personality)}</div><div class="ps">得意: ${c.phases.map(k => phaseOf(k).label).join('・')}</div></div>`).join('')}</div>`, (m) => {
    $$('.char-card', m).forEach(card => card.onclick = async () => {
      try { await api('PUT', '/api/me/character', { character: card.dataset.cid }); S.boot.my_character = card.dataset.cid; closeModal(); renderPartner(); partnerGreet(); toast(`${myChar().name} がパートナーになりました`, 'ok'); } catch (e) { err(e); }
    });
  });
}
function bindPartner() {
  $('#partner-avatar').onclick = partnerNext; $('#partner-next').onclick = partnerNext;
  $('#partner-bubble').ondblclick = () => $('#partner-bubble').classList.add('hidden');
}

// ================================================================ 起動
async function init() {
  S.boot = await api('GET', '/api/bootstrap');
  $('#user-role').textContent = { admin: '管理者', member: 'メンバー', viewer: '閲覧' }[S.boot.me.role] || S.boot.me.role;
  $('#btn-new-property').onclick = () => newProperty();
  $('#menu-btn').onclick = () => $('#sidebar').classList.toggle('open');
  $('#modal-close').onclick = closeModal;
  $('#modal').addEventListener('click', (e) => { if (e.target === $('#modal')) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { if (!$('#modal').hidden) closeModal(); else if (!$('#drawer').hidden) closeDrawer(); } if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') { e.preventDefault(); $('#global-search').focus(); } });
  let t; $('#global-search').addEventListener('input', (e) => { clearTimeout(t); t = setTimeout(() => { S.q = e.target.value; if (S.view === 'map') { drawMapMarkers(); drawMapList(); } else showView(S.view); }, 250); });
  if (!canEdit()) $('#btn-new-property').hidden = true;
  $('#bn-more').onclick = (e) => { e.preventDefault(); $('#sidebar').classList.toggle('open'); };
  document.addEventListener('click', (e) => { const sb = $('#sidebar'); if (sb.classList.contains('open') && !sb.contains(e.target) && !e.target.closest('#menu-btn,#bn-more')) sb.classList.remove('open'); });
  bindPartner(); renderLevel();
  await route();
  if (!S.boot.my_character) chooseCharacter(true); else { renderPartner(); setTimeout(partnerGreet, 400); }
}
window.MagoLove = { openDrawer, closeModal, newProperty };
document.addEventListener('DOMContentLoaded', init);
})();
