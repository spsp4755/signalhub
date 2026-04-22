/* ============== Core helpers ============== */
const api = async (path, opts = {}) => {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );

const toDate = (v) => {
  if (v == null) return null;
  if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
  const s = String(v);
  const d = new Date(s.includes('T') ? s : s.replace(' ', 'T') + 'Z');
  return isNaN(d.getTime()) ? null : d;
};

const formatDate = (v) => {
  const d = toDate(v);
  if (!d) return '—';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return '방금 전';
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}일 전`;
  return d.toLocaleDateString('ko-KR');
};

const formatDateFull = (v) => {
  const d = toDate(v);
  return d ? d.toLocaleString('ko-KR') : '—';
};

const toast = (msg, type = 'ok') => {
  const t = $('#toast');
  t.className = `toast ${type}`;
  t.textContent = msg;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), 3000);
};

const nextRunFromSchedule = (hour, minute) => {
  const now = new Date();
  const target = new Date();
  target.setHours(hour, minute, 0, 0);
  if (target <= now) target.setDate(target.getDate() + 1);
  return target;
};

/* ============== Markdown renderer ============== */
(() => {
  try { mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' }); } catch {}
  try {
    marked.setOptions({
      gfm: true,
      breaks: false,
      highlight: (code, lang) => {
        if (lang && hljs.getLanguage(lang)) {
          try { return hljs.highlight(code, { language: lang }).value; } catch {}
        }
        try { return hljs.highlightAuto(code).value; } catch { return code; }
      },
    });
  } catch {}
})();

function renderMarkdown(text, container) {
  const unescapedMermaid = (text || '').replace(
    /```mermaid\s*\n([\s\S]*?)```/g,
    (_, body) => `<div class="mermaid">${esc(body.trim())}</div>`
  );
  const html = DOMPurify.sanitize(marked.parse(unescapedMermaid), {
    ADD_TAGS: ['div'],
    ADD_ATTR: ['class'],
  });
  container.innerHTML = html;
  container.querySelectorAll('pre code').forEach((el) => {
    try { hljs.highlightElement(el); } catch {}
  });
  const mermaids = container.querySelectorAll('.mermaid');
  if (mermaids.length) {
    try { mermaid.run({ nodes: Array.from(mermaids) }); } catch {}
  }
  container.querySelectorAll('a').forEach((a) => {
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
  });
}

/* ============== Tabs ============== */
const TAB_META = {
  dashboard: { title: '대시보드', sub: 'AI / Agents 동향을 한눈에' },
  keywords:  { title: '키워드',    sub: '자동 수집 대상 키워드 관리' },
  insights:  { title: '인사이트', sub: '토픽 · 타임라인 · 온톨로지 네트워크' },
  results:   { title: '분석 결과', sub: '누적 분석 로그 및 필터 조회' },
  settings:  { title: '설정',      sub: '런타임 구성 편집 — 저장 시 즉시 반영' },
};

const TAB_STORAGE_KEY = 'signalhub.activeTab';

function activateTab(name, { push = true } = {}) {
  if (!TAB_META[name]) name = 'dashboard';
  $$('.sidebar nav a').forEach((a) => a.classList.toggle('active', a.dataset.tab === name));
  $$('.tab').forEach((s) => s.classList.toggle('hidden', s.dataset.tab !== name));
  const meta = TAB_META[name] || {};
  $('#page-title').textContent = meta.title || '';
  $('#page-sub').textContent = meta.sub || '';
  try { localStorage.setItem(TAB_STORAGE_KEY, name); } catch {}
  if (push && location.hash !== '#' + name) {
    history.replaceState(null, '', '#' + name);
  }
  if (name === 'dashboard') loadDashboard();
  if (name === 'keywords') loadKeywords();
  if (name === 'insights') loadInsights();
  if (name === 'results') { loadKeywordFilterOptions(); loadResults(); }
  if (name === 'settings') loadSettings();
}

function initialTab() {
  const fromHash = (location.hash || '').replace(/^#/, '');
  if (fromHash && TAB_META[fromHash]) return fromHash;
  try {
    const saved = localStorage.getItem(TAB_STORAGE_KEY);
    if (saved && TAB_META[saved]) return saved;
  } catch {}
  return 'dashboard';
}

window.addEventListener('hashchange', () => {
  const name = (location.hash || '').replace(/^#/, '');
  if (name && TAB_META[name]) activateTab(name, { push: false });
});

$$('.sidebar nav a').forEach((a) =>
  a.addEventListener('click', (e) => { e.preventDefault(); activateTab(a.dataset.tab); })
);
document.addEventListener('click', (e) => {
  const link = e.target.closest('[data-tab-link]');
  if (link) { e.preventDefault(); activateTab(link.dataset.tabLink); }
});

/* ============== Health ============== */
async function pingHealth() {
  try {
    await api('/healthz');
    $('#status-dot').classList.add('ok');
    $('#status-dot').classList.remove('err');
    $('#status-text').textContent = '정상';
  } catch {
    $('#status-dot').classList.add('err');
    $('#status-text').textContent = '연결 실패';
  }
}

/* ============== Dashboard ============== */
async function loadDashboard() {
  try {
    const [stats, recentPage] = await Promise.all([api('/stats'), api('/results?limit=5')]);
    const recent = recentPage.items || [];
    $('#s-keywords').textContent = stats.total_keywords;
    $('#s-keywords-enabled').textContent = `(ON ${stats.enabled_keywords})`;
    $('#s-total').textContent = stats.total_analyses;
    $('#s-auto').textContent = stats.auto_count;
    $('#s-manual').textContent = stats.manual_count;
    $('#s-model').textContent = stats.model;
    $('#s-endpoint').textContent = stats.base_url;

    const hh = String(stats.schedule.hour).padStart(2, '0');
    const mm = String(stats.schedule.minute).padStart(2, '0');
    $('#s-schedule').textContent = `매일 ${hh}:${mm}`;
    $('#s-next').textContent = formatDateFull(nextRunFromSchedule(stats.schedule.hour, stats.schedule.minute));
    $('#s-last').textContent = stats.last_analysis
      ? `${stats.last_analysis.keyword} · ${formatDateFull(stats.last_analysis.created_at)}`
      : '—';

    const tbody = $('#s-per-keyword');
    tbody.innerHTML = stats.per_keyword.length
      ? stats.per_keyword.map((k) => `
          <tr>
            <td>${esc(k.keyword)}</td>
            <td class="num">${k.count}</td>
            <td>${k.last_run ? formatDate(k.last_run) : '—'}</td>
          </tr>`).join('')
      : '<tr><td colspan="3" class="empty">키워드 없음</td></tr>';

    const rl = $('#recent-list');
    rl.innerHTML = recent.length
      ? recent.map(renderResultItem).join('')
      : '<div class="empty">아직 분석 기록이 없습니다.</div>';
    attachResultHandlers(rl);
  } catch (e) {
    toast('대시보드 로드 실패: ' + e.message, 'error');
  }
}

/* ============== Keywords ============== */
let _keywordCache = [];

async function loadKeywords() {
  try {
    const [rows, stats] = await Promise.all([api('/keywords'), api('/stats')]);
    _keywordCache = rows;
    const statsMap = Object.fromEntries(stats.per_keyword.map((s) => [s.keyword, s]));
    renderKeywordTable(rows, statsMap);
  } catch (e) {
    toast('키워드 로드 실패: ' + e.message, 'error');
  }
}

function renderKeywordTable(rows, statsMap) {
  const q = ($('#kw-search')?.value || '').toLowerCase();
  const filtered = rows.filter((r) => !q || r.name.toLowerCase().includes(q));
  const tbody = $('#kw-list');
  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">키워드 없음</td></tr>';
    return;
  }
  tbody.innerHTML = filtered.map((k) => {
    const stat = (statsMap || {})[k.name] || {};
    return `
      <tr data-kw-id="${k.id}" data-kw-name="${esc(k.name)}">
        <td><strong>${esc(k.name)}</strong></td>
        <td>
          <label class="toggle">
            <input type="checkbox" class="kw-toggle" ${k.enabled ? 'checked' : ''} />
            <span class="toggle-slider"></span>
          </label>
        </td>
        <td class="num">${stat.count ?? 0}</td>
        <td>${stat.last_run ? formatDate(stat.last_run) : '—'}</td>
        <td>${formatDate(k.created_at)}</td>
        <td class="actions">
          <button class="btn btn-ghost btn-sm kw-run">실행</button>
          <button class="btn btn-danger btn-sm kw-del">삭제</button>
        </td>
      </tr>`;
  }).join('');
}

$('#kw-search')?.addEventListener('input', () => {
  api('/stats').then((s) => {
    const map = Object.fromEntries(s.per_keyword.map((x) => [x.keyword, x]));
    renderKeywordTable(_keywordCache, map);
  });
});

async function addKeyword(name) {
  try {
    await api('/keywords', { method: 'POST', body: JSON.stringify({ name, enabled: true }) });
    toast(`"${name}" 추가됨`);
    if (!$('[data-tab="keywords"]').classList.contains('hidden')) loadKeywords();
    return true;
  } catch (e) {
    toast('추가 실패: ' + e.message, 'error');
    return false;
  }
}

$('#kw-add').addEventListener('click', async () => {
  const input = $('#kw-input');
  const name = input.value.trim();
  if (!name) return;
  if (await addKeyword(name)) input.value = '';
});
$('#kw-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $('#kw-add').click();
});

$('#kw-list').addEventListener('click', async (e) => {
  const tr = e.target.closest('tr[data-kw-id]');
  if (!tr) return;
  const id = tr.dataset.kwId;
  const name = tr.dataset.kwName;
  if (e.target.classList.contains('kw-del')) {
    if (!confirm(`"${name}" 삭제하시겠습니까?`)) return;
    try { await api(`/keywords/${id}`, { method: 'DELETE' }); toast(`"${name}" 삭제됨`); loadKeywords(); }
    catch (err) { toast('삭제 실패: ' + err.message, 'error'); }
  } else if (e.target.classList.contains('kw-run')) {
    toast(`"${name}" 실행 중...`);
    try {
      const r = await api('/run', { method: 'POST', body: JSON.stringify({ keyword: name }) });
      toast(`완료: arXiv ${r.arxiv} · HF ${r.huggingface} · GN ${r.geeknews} · AT ${r.aitimes}`);
      loadKeywords();
    } catch (err) { toast('실행 실패: ' + err.message, 'error'); }
  }
});

$('#kw-list').addEventListener('change', async (e) => {
  if (!e.target.classList.contains('kw-toggle')) return;
  const tr = e.target.closest('tr[data-kw-id]');
  const id = tr.dataset.kwId;
  const enabled = e.target.checked;
  try {
    await api(`/keywords/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) });
    toast(`${tr.dataset.kwName} ${enabled ? 'ON' : 'OFF'}`);
  } catch (err) {
    toast('변경 실패: ' + err.message, 'error');
    e.target.checked = !enabled;
  }
});

/* ============== Results ============== */
async function loadKeywordFilterOptions() {
  try {
    const rows = await api('/keywords');
    const sel = $('#f-keyword');
    const cur = sel.value;
    sel.innerHTML = '<option value="">전체 키워드</option>' +
      rows.map((r) => `<option value="${esc(r.name)}">${esc(r.name)}</option>`).join('');
    sel.value = cur;
  } catch {}
}

const RESULTS_STATE = {
  pageSize: 20,
  beforeId: null,
  keyword: '',
  runType: '',
  loading: false,
  total: 0,
  loaded: 0,
  hasMore: true,
  io: null,
};

function _currentFilters() {
  return {
    pageSize: Number($('#f-limit').value || '20'),
    keyword: $('#f-keyword').value || '',
    runType: $('#f-run-type').value || '',
  };
}

async function loadResults(reset = true) {
  const box = $('#results-list');
  if (reset) {
    const f = _currentFilters();
    RESULTS_STATE.pageSize = f.pageSize;
    RESULTS_STATE.keyword = f.keyword;
    RESULTS_STATE.runType = f.runType;
    RESULTS_STATE.beforeId = null;
    RESULTS_STATE.loaded = 0;
    RESULTS_STATE.hasMore = true;
    RESULTS_STATE.total = 0;
    box.innerHTML = '<div class="empty">로딩 중...</div>';
  }
  if (RESULTS_STATE.loading || !RESULTS_STATE.hasMore) return;
  RESULTS_STATE.loading = true;

  const qs = new URLSearchParams({ limit: String(RESULTS_STATE.pageSize) });
  if (RESULTS_STATE.beforeId) qs.set('before_id', String(RESULTS_STATE.beforeId));
  if (RESULTS_STATE.keyword) qs.set('keyword', RESULTS_STATE.keyword);
  if (RESULTS_STATE.runType) qs.set('run_type', RESULTS_STATE.runType);

  try {
    const page = await api('/results?' + qs.toString());
    const items = page.items || [];
    RESULTS_STATE.total = page.total || 0;
    RESULTS_STATE.loaded += items.length;
    RESULTS_STATE.hasMore = !!page.has_more;
    RESULTS_STATE.beforeId = page.next_before_id || null;

    if (reset && !items.length) {
      box.innerHTML = '<div class="empty">조건에 맞는 결과 없음</div>';
    } else {
      if (reset) box.innerHTML = '';
      const frag = document.createElement('div');
      frag.innerHTML = items.map(renderResultItem).join('');
      const added = Array.from(frag.children);
      added.forEach((n) => box.appendChild(n));
      attachResultHandlers(box);
    }

    _updateResultsSentinel(box);
    $('#r-count').textContent = `(${RESULTS_STATE.loaded} / ${RESULTS_STATE.total}건)`;
  } catch (e) {
    toast('결과 로드 실패: ' + e.message, 'error');
  } finally {
    RESULTS_STATE.loading = false;
  }
}

function _updateResultsSentinel(box) {
  box.querySelectorAll('.results-sentinel').forEach((el) => el.remove());
  if (!RESULTS_STATE.hasMore) return;
  const sentinel = document.createElement('div');
  sentinel.className = 'results-sentinel empty';
  sentinel.textContent = '더 불러오는 중...';
  box.appendChild(sentinel);
  if (RESULTS_STATE.io) RESULTS_STATE.io.disconnect();
  RESULTS_STATE.io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting && !RESULTS_STATE.loading && RESULTS_STATE.hasMore) {
        loadResults(false);
      }
    }
  }, { rootMargin: '200px' });
  RESULTS_STATE.io.observe(sentinel);
}

$('#f-apply').addEventListener('click', () => loadResults(true));

function renderResultItem(r) {
  const snippet = (r.result || '').replace(/[#*`>\-]/g, '').replace(/\s+/g, ' ').slice(0, 200);
  const chip = r.run_type === 'auto' ? 'chip-auto' : 'chip-manual';
  const tags = (r.tags || []).slice(0, 5).map((t) => `<span class="tag">${esc(t)}</span>`).join('');
  return `
    <div class="result-item" data-id="${r.id}">
      <div class="result-head">
        <div class="result-title"><span class="id">#${r.id}</span>${esc(r.keyword)}</div>
        <div class="row" style="gap:6px;">
          <span class="chip ${chip}">${r.run_type}</span>
          <span class="muted" style="font-size:12px;">${formatDate(r.created_at)}</span>
        </div>
      </div>
      <div class="result-snip">${esc(snippet)}</div>
      ${tags ? `<div class="tags-inline">${tags}</div>` : ''}
    </div>`;
}

function attachResultHandlers(container) {
  container.querySelectorAll('.result-item').forEach((el) => {
    el.addEventListener('click', () => openDetail(el.dataset.id));
  });
}

/* ============== Detail modal ============== */
async function openDetail(id) {
  try {
    const r = await api(`/results/${id}`);
    $('#m-title').textContent = r.keyword;
    $('#m-meta').textContent = `#${r.id} · ${r.run_type} · ${formatDateFull(r.created_at)}`;
    renderMarkdown(r.result, $('#m-body'));
    $('#m-body').dataset.raw = r.result;

    const tagsBox = $('#m-tags');
    if (r.tags && r.tags.length) {
      tagsBox.innerHTML = r.tags
        .map((t) => `<span class="tag" data-tag="${esc(t)}">${esc(t)}</span>`).join('');
      tagsBox.querySelectorAll('.tag').forEach((el) => {
        el.addEventListener('click', () => promptAddKeyword(el.dataset.tag));
      });
    } else {
      tagsBox.innerHTML = '<span class="muted">—</span>';
    }

    const papersEl = $('#m-papers-arxiv');
    const papers = (r.sources && r.sources.arxiv) || [];
    papersEl.innerHTML = papers.length
      ? papers.map((p) => `
          <li>
            ${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)}
            ${p.authors && p.authors.length ? `<span class="authors">${esc(p.authors.slice(0, 3).join(', '))}${p.authors.length > 3 ? ' 외' : ''}</span>` : ''}
          </li>`).join('')
      : '<li class="muted">—</li>';

    const papersHf = $('#m-papers-hf');
    const hfPapers = (r.sources && r.sources.huggingface_papers) || [];
    papersHf.innerHTML = hfPapers.length
      ? hfPapers.map((p) => `
          <li>
            ${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)}
            ${p.authors && p.authors.length ? `<span class="authors">${esc(p.authors.slice(0, 3).join(', '))}${p.authors.length > 3 ? ' 외' : ''}</span>` : ''}
          </li>`).join('')
      : '<li class="muted">—</li>';

    const newsEl = $('#m-news-geeknews');
    const news = (r.sources && r.sources.geeknews) || [];
    newsEl.innerHTML = news.length
      ? news.map((n) => `
          <li>${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>` : esc(n.title)}</li>`).join('')
      : '<li class="muted">—</li>';

    const aitimesEl = $('#m-news-aitimes');
    const aitimes = (r.sources && r.sources.aitimes) || [];
    aitimesEl.innerHTML = aitimes.length
      ? aitimes.map((n) => `
          <li>${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>` : esc(n.title)}</li>`).join('')
      : '<li class="muted">—</li>';

    $('#modal-backdrop').classList.remove('hidden');
  } catch (e) {
    toast('상세 로드 실패: ' + e.message, 'error');
  }
}

$('#m-close').addEventListener('click', () => $('#modal-backdrop').classList.add('hidden'));
$('#modal-backdrop').addEventListener('click', (e) => {
  if (e.target.id === 'modal-backdrop') $('#modal-backdrop').classList.add('hidden');
});
$('#m-copy').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('#m-body').dataset.raw || $('#m-body').textContent);
    toast('마크다운 원문 복사됨');
  } catch { toast('복사 실패', 'error'); }
});

/* ============== Add-keyword prompt modal ============== */
function promptAddKeyword(name) {
  $('#add-kw-name').textContent = name;
  $('#add-kw-backdrop').dataset.name = name;
  $('#add-kw-backdrop').classList.remove('hidden');
}
$('#add-kw-cancel').addEventListener('click', () => $('#add-kw-backdrop').classList.add('hidden'));
$('#add-kw-backdrop').addEventListener('click', (e) => {
  if (e.target.id === 'add-kw-backdrop') $('#add-kw-backdrop').classList.add('hidden');
});
$('#add-kw-confirm').addEventListener('click', async () => {
  const name = $('#add-kw-backdrop').dataset.name;
  if (!name) return;
  const ok = await addKeyword(name);
  $('#add-kw-backdrop').classList.add('hidden');
  if (ok) {
    if (!$('[data-tab="insights"]').classList.contains('hidden')) loadInsights();
  }
});

/* ============== Insights ============== */
let _chartTimeline = null;
let _chartTags = null;
let _network = null;

async function loadInsights() {
  try {
    const data = await api('/insights');
    $('#ins-sample').textContent = `표본: 최근 ${data.sample_size}건`;
    renderTimelineChart(data.timeline);
    renderWordCloud(data.top_tags);
    renderTopTagsChart(data.top_tags);
    renderNetwork(data.network);
    renderPairs(data.top_pairs);
  } catch (e) {
    toast('인사이트 로드 실패: ' + e.message, 'error');
  }
}

function renderTimelineChart(points) {
  const ctx = $('#chart-timeline');
  if (_chartTimeline) _chartTimeline.destroy();
  const labels = points.map((p) => p.date);
  _chartTimeline = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: '자동', data: points.map((p) => p.auto), backgroundColor: 'rgba(217,119,6,0.7)', stack: 's' },
        { label: '수동', data: points.map((p) => p.manual), backgroundColor: 'rgba(37,99,235,0.7)', stack: 's' },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
      },
      plugins: { legend: { position: 'bottom' } },
    },
  });
}

function renderTopTagsChart(tags) {
  const top = (tags || []).slice(0, 20);
  const ctx = $('#chart-tags');
  if (_chartTags) _chartTags.destroy();
  _chartTags = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: top.map((t) => t.tag),
      datasets: [{ data: top.map((t) => t.count), backgroundColor: 'rgba(124,58,237,0.75)' }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      scales: { x: { beginAtZero: true, ticks: { precision: 0 } } },
      plugins: { legend: { display: false } },
    },
  });
}

function renderWordCloud(tags) {
  const el = $('#wordcloud');
  const fb = $('#top-tags-fallback');
  fb.innerHTML = '';
  if (!tags || !tags.length) {
    el.innerHTML = '<div class="empty">태그 없음 — 분석을 몇 건 실행하면 표시됩니다.</div>';
    return;
  }
  el.innerHTML = '';
  const list = tags.map((t) => [t.tag, t.count]);
  const max = Math.max(...list.map((x) => x[1]));
  const palette = ['#2563eb', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2'];
  try {
    WordCloud(el, {
      list,
      gridSize: 8,
      weightFactor: (size) => 10 + (size / max) * 40,
      fontFamily: '-apple-system, "Segoe UI", Pretendard, sans-serif',
      color: () => palette[Math.floor(Math.random() * palette.length)],
      backgroundColor: 'transparent',
      rotateRatio: 0.1,
      shuffle: true,
      click: (item) => { if (item && item[0]) promptAddKeyword(item[0]); },
    });
  } catch (e) {
    el.innerHTML = '';
    fb.innerHTML = list.map(([t]) => `<span class="tag" data-tag="${esc(t)}">${esc(t)}</span>`).join('');
    fb.querySelectorAll('.tag').forEach((tagEl) =>
      tagEl.addEventListener('click', () => promptAddKeyword(tagEl.dataset.tag))
    );
  }
}

function renderNetwork(net) {
  const el = $('#network');
  if (!net || !net.nodes || !net.nodes.length) {
    el.innerHTML = '<div class="empty">네트워크 데이터 없음</div>';
    return;
  }
  el.innerHTML = '';
  const nodes = net.nodes.map((n) => ({
    id: n.id,
    label: n.label,
    group: n.group,
    value: n.value || 1,
    shape: n.group === 'keyword' ? 'dot' : 'dot',
    color: n.group === 'keyword'
      ? { background: '#2563eb', border: '#1d4ed8', highlight: { background: '#1d4ed8', border: '#1e3a8a' } }
      : { background: '#cbd5e1', border: '#94a3b8', highlight: { background: '#94a3b8', border: '#64748b' } },
    font: { color: n.group === 'keyword' ? '#0f172a' : '#334155', size: n.group === 'keyword' ? 16 : 13 },
  }));
  const edges = net.edges.map((e) => ({
    from: e.from,
    to: e.to,
    value: e.value,
    color: { color: 'rgba(148,163,184,0.6)', highlight: '#2563eb' },
    smooth: { type: 'continuous' },
  }));
  _network = new vis.Network(el, { nodes, edges }, {
    physics: { enabled: true, stabilization: { iterations: 150 }, barnesHut: { springLength: 120 } },
    interaction: { hover: true, tooltipDelay: 150 },
    nodes: { borderWidth: 1 },
    edges: { scaling: { min: 0.5, max: 5 } },
  });
  _network.on('click', (params) => {
    if (!params.nodes.length) return;
    const node = nodes.find((n) => n.id === params.nodes[0]);
    if (node && node.group === 'tag') promptAddKeyword(node.label);
  });
}

$('#net-physics-toggle').addEventListener('click', () => {
  if (!_network) return;
  const enabled = _network.physics.options.enabled;
  _network.setOptions({ physics: { enabled: !enabled } });
  toast(`물리 효과 ${!enabled ? 'ON' : 'OFF'}`);
});
$('#net-refit').addEventListener('click', () => _network && _network.fit());

function renderPairs(pairs) {
  const tbody = $('#ins-pairs');
  if (!pairs || !pairs.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty">데이터 없음</td></tr>';
    return;
  }
  tbody.innerHTML = pairs.map((p) =>
    `<tr><td>${esc(p.a)}</td><td>${esc(p.b)}</td><td class="num">${p.count}</td></tr>`
  ).join('');
}

/* ============== Settings ============== */
const SETTINGS_FORMS = ['#form-llm', '#form-schedule', '#form-sources', '#form-smtp', '#form-retention'];
const SETTINGS_SELECTOR = SETTINGS_FORMS.map((f) => `${f} input, ${f} select`).join(', ');

async function loadSettings() {
  try {
    const { values } = await api('/settings');
    $$(SETTINGS_SELECTOR).forEach((inp) => {
      if (!(inp.name in values)) return;
      const val = values[inp.name];
      if (val === null || val === undefined) return;
      if (inp.tagName === 'SELECT') {
        inp.value = String(val);
      } else {
        inp.value = val;
      }
    });
    loadRecipients();
  } catch (e) {
    toast('설정 로드 실패: ' + e.message, 'error');
  }
}

function collectSettings() {
  const payload = {};
  $$(SETTINGS_SELECTOR).forEach((inp) => {
    const name = inp.name;
    if (!name) return;
    let v = inp.value;
    if (v === '' || v === null) return;
    if (inp.tagName === 'SELECT') {
      if (v === 'true' || v === 'false') payload[name] = v === 'true';
      else payload[name] = v;
      return;
    }
    if (inp.type === 'number') {
      const n = Number(v);
      if (!Number.isNaN(n)) payload[name] = n;
      return;
    }
    payload[name] = v;
  });
  return payload;
}

$('#set-save').addEventListener('click', async () => {
  const st = $('#set-status');
  st.textContent = '저장 중...';
  try {
    const r = await api('/settings', { method: 'PUT', body: JSON.stringify(collectSettings()) });
    st.textContent = `저장 완료 · 변경된 키: ${r.updated_keys.join(', ') || '(없음)'}`;
    toast('설정 저장됨');
    loadSettings();
  } catch (e) {
    st.textContent = '';
    toast('저장 실패: ' + e.message, 'error');
  }
});

$('#set-reset').addEventListener('click', async () => {
  if (!confirm('모든 설정을 .env 기본값으로 초기화합니다. 계속할까요?')) return;
  try {
    await api('/settings/reset', { method: 'POST' });
    toast('초기화됨');
    loadSettings();
  } catch (e) { toast('초기화 실패: ' + e.message, 'error'); }
});

/* ============== Recipients ============== */
async function loadRecipients() {
  try {
    const rows = await api('/recipients');
    renderRecipients(rows);
  } catch (e) {
    toast('수신자 로드 실패: ' + e.message, 'error');
  }
}

function renderRecipients(rows) {
  const tbody = $('#rcpt-list');
  if (!rows || !rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">등록된 수신자가 없습니다.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((r) => `
    <tr data-rcpt-id="${r.id}" data-rcpt-email="${esc(r.email)}">
      <td>
        <span class="rcpt-view"><strong>${esc(r.email)}</strong></span>
        <input class="rcpt-edit input-sm" type="email" value="${esc(r.email)}" style="display:none; width:100%;" />
      </td>
      <td>
        <label class="toggle">
          <input type="checkbox" class="rcpt-toggle" ${r.enabled ? 'checked' : ''} />
          <span class="toggle-slider"></span>
        </label>
      </td>
      <td>${formatDate(r.created_at)}</td>
      <td class="actions">
        <button class="btn btn-ghost btn-sm rcpt-edit-btn">수정</button>
        <button class="btn btn-primary btn-sm rcpt-save-btn" style="display:none;">저장</button>
        <button class="btn btn-ghost btn-sm rcpt-cancel-btn" style="display:none;">취소</button>
        <button class="btn btn-danger btn-sm rcpt-del-btn">삭제</button>
      </td>
    </tr>`).join('');
}

async function addRecipient() {
  const input = $('#rcpt-input');
  const email = input.value.trim();
  if (!email) return;
  try {
    await api('/recipients', { method: 'POST', body: JSON.stringify({ email, enabled: true }) });
    input.value = '';
    toast(`수신자 "${email}" 추가됨`);
    loadRecipients();
  } catch (e) {
    toast('추가 실패: ' + e.message, 'error');
  }
}

$('#rcpt-add')?.addEventListener('click', addRecipient);
$('#rcpt-input')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') addRecipient(); });

$('#rcpt-list')?.addEventListener('click', async (e) => {
  const tr = e.target.closest('tr[data-rcpt-id]');
  if (!tr) return;
  const id = tr.dataset.rcptId;
  const currentEmail = tr.dataset.rcptEmail;

  if (e.target.classList.contains('rcpt-del-btn')) {
    if (!confirm(`"${currentEmail}" 수신자를 삭제할까요?`)) return;
    try {
      await api(`/recipients/${id}`, { method: 'DELETE' });
      toast('삭제됨');
      loadRecipients();
    } catch (err) { toast('삭제 실패: ' + err.message, 'error'); }
    return;
  }

  if (e.target.classList.contains('rcpt-edit-btn')) {
    tr.querySelector('.rcpt-view').style.display = 'none';
    tr.querySelector('.rcpt-edit').style.display = 'inline-block';
    tr.querySelector('.rcpt-edit-btn').style.display = 'none';
    tr.querySelector('.rcpt-save-btn').style.display = 'inline-block';
    tr.querySelector('.rcpt-cancel-btn').style.display = 'inline-block';
    tr.querySelector('.rcpt-edit').focus();
    return;
  }

  if (e.target.classList.contains('rcpt-cancel-btn')) {
    loadRecipients();
    return;
  }

  if (e.target.classList.contains('rcpt-save-btn')) {
    const newEmail = tr.querySelector('.rcpt-edit').value.trim();
    if (!newEmail || newEmail === currentEmail) { loadRecipients(); return; }
    try {
      await api(`/recipients/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ email: newEmail }),
      });
      toast('수정됨');
      loadRecipients();
    } catch (err) { toast('수정 실패: ' + err.message, 'error'); }
  }
});

$('#rcpt-list')?.addEventListener('change', async (e) => {
  if (!e.target.classList.contains('rcpt-toggle')) return;
  const tr = e.target.closest('tr[data-rcpt-id]');
  const id = tr.dataset.rcptId;
  const enabled = e.target.checked;
  try {
    await api(`/recipients/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) });
    toast(`${enabled ? '활성' : '비활성'}화됨`);
  } catch (err) {
    toast('변경 실패: ' + err.message, 'error');
    e.target.checked = !enabled;
  }
});

$('#rcpt-test-all')?.addEventListener('click', async () => {
  if (!confirm('현재 설정된 SMTP로 전체 수신자에게 테스트 메일을 발송할까요?')) return;
  try {
    const r = await api('/recipients/test', { method: 'POST', body: JSON.stringify({}) });
    toast(`테스트 발송 완료 · 수신자 ${r.recipients.length}명`);
  } catch (e) { toast('테스트 발송 실패: ' + e.message, 'error'); }
});

/* ============== Top actions ============== */
$('#refresh-all').addEventListener('click', () => {
  const active = document.querySelector('.sidebar nav a.active')?.dataset.tab || 'dashboard';
  activateTab(active);
  pingHealth();
  toast('새로고침 완료');
});

$('#quick-run-all').addEventListener('click', async () => {
  if (!confirm('활성 키워드 전체를 지금 실행할까요? 모델 응답에 따라 시간이 걸릴 수 있습니다.')) return;
  toast('전체 실행 시작...');
  try {
    const r = await api('/run-all', { method: 'POST' });
    const ok = r.outcomes.filter((o) => o.ok).length;
    toast(`완료: 성공 ${ok} / ${r.outcomes.length}`);
    loadDashboard();
  } catch (e) {
    toast('실행 실패: ' + e.message, 'error');
  }
});

$('#quick-run-input-toggle').addEventListener('click', () => {
  const w = $('#quick-run-input-wrap');
  w.style.display = w.style.display === 'none' ? 'block' : 'none';
});
$('#quick-run-btn').addEventListener('click', async () => {
  const name = $('#quick-run-input').value.trim();
  if (!name) return;
  $('#quick-run-status').textContent = `"${name}" 실행 중...`;
  try {
    const r = await api('/run', { method: 'POST', body: JSON.stringify({ keyword: name }) });
    $('#quick-run-status').textContent = `완료 #${r.id} · arXiv ${r.arxiv} · HF ${r.huggingface} · GN ${r.geeknews} · AT ${r.aitimes}`;
    loadDashboard();
  } catch (e) {
    $('#quick-run-status').textContent = '실패: ' + e.message;
  }
});

/* ============== Boot ============== */
pingHealth();
activateTab(initialTab());
setInterval(pingHealth, 30000);
