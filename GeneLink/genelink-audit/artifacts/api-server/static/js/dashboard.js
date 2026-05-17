// ── Dashboard ────────────────────────────────────────────────────────────────

let _activeTab = 'overview';
let _dashFilter = '';
let _dashPreprintFilter = '';
let _dashLoaded = { partnerships: false, community: false, preprints: false };
let _selectedPid = null;

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireAuth()) return;
  injectNavbar('/gl/dashboard');

  const cached = getUser();
  document.getElementById('welcome-name').textContent =
    cached.full_name || cached.username;

  await Promise.all([loadStats(), loadRecentSearches(), loadRecentPosts()]);
});

// ── Tab switching ─────────────────────────────────────────────────────────────

function switchTab(tab) {
  _activeTab = tab;
  document.querySelectorAll('.dash-tab').forEach((btn, i) => {
    const tabs = ['overview', 'partnerships', 'community', 'preprints'];
    btn.classList.toggle('active', tabs[i] === tab);
  });
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');

  if (tab === 'partnerships' && !_dashLoaded.partnerships) {
    _dashLoaded.partnerships = true;
    loadDashPartnerships();
  }
  if (tab === 'community' && !_dashLoaded.community) {
    _dashLoaded.community = true;
    loadCommunityPosts();
  }
  if (tab === 'preprints' && !_dashLoaded.preprints) {
    _dashLoaded.preprints = true;
    loadDashPreprints();
  }
}

// ── Stats / hero ──────────────────────────────────────────────────────────────

async function loadStats() {
  let user = getUser();
  try {
    const res = await apiFetch('/user');
    if (res.ok) {
      const fresh = await res.json();
      setAuth(getToken(), fresh);
      user = fresh;
      document.getElementById('welcome-name').textContent =
        fresh.full_name || fresh.username;
    }
  } catch (_) {}

  document.getElementById('hero-institution').textContent =
    user.institution || 'Sem instituição';
  document.getElementById('hero-area').textContent =
    user.research_area || 'Área não definida';
  document.getElementById('hero-joined').textContent = user.created_at
    ? formatDate(user.created_at) : '—';

  document.getElementById('m-account').textContent = '@' + (user.username || '—');
  document.getElementById('m-badge').textContent =
    user.research_area || 'Não definida';
}

// ── Recent searches ───────────────────────────────────────────────────────────

async function loadRecentSearches() {
  const el = document.getElementById('recent-searches');
  try {
    const res = await apiFetch('/search-history');
    const data = await res.json();
    if (!data.length) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">🔬</div>
        <h3>Nenhuma busca ainda</h3>
        <p style="font-size:.85rem;margin-top:6px"><a href="/gl/search">Comece a buscar genes</a></p>
      </div>`;
      document.getElementById('m-searches').textContent = '0';
      return;
    }
    document.getElementById('m-searches').textContent = data.length;
    el.innerHTML = data.map(s => `
      <div class="hist-row">
        <div>
          <div class="hist-gene">${escHtml(s.query)}</div>
          <div class="hist-meta">${s.result_count} resultado${s.result_count !== 1 ? 's' : ''} · ${timeAgo(s.searched_at)}</div>
        </div>
        <a href="/gl/search?q=${encodeURIComponent(s.query)}" class="btn btn-ghost btn-sm" style="flex-shrink:0">Repetir →</a>
      </div>`).join('');
  } catch (_) {
    el.innerHTML = `<p style="color:var(--text-muted);font-size:.875rem;padding:20px">Não foi possível carregar o histórico.</p>`;
  }
}

// ── Recent posts (overview tab) ───────────────────────────────────────────────

async function loadRecentPosts() {
  const el = document.getElementById('recent-posts');
  try {
    const res = await fetch('/gl/api/posts?page=1');
    const data = await res.json();
    const posts = (data.posts || []).slice(0, 5);
    if (!posts.length) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <h3>Nenhuma publicação ainda</h3>
        <p style="font-size:.85rem;margin-top:6px"><a href="/gl/forum">Inicie uma discussão</a></p>
      </div>`;
      return;
    }
    el.innerHTML = posts.map(p => `
      <div class="post-row" onclick="window.location='/gl/forum/${p.id}'">
        <div class="post-cat-dot" style="background:#f0f4f9">📋</div>
        <div style="flex:1;min-width:0">
          <div class="post-row-title">${escHtml(p.title)}</div>
          <div class="post-row-meta">
            <span class="badge badge-muted">${escHtml(p.category)}</span>
            <span>${escHtml(p.username)}</span>
            <span>${timeAgo(p.created_at)}</span>
            <span>${p.comment_count} comentário${p.comment_count !== 1 ? 's' : ''}</span>
          </div>
        </div>
      </div>`).join('');
  } catch (_) {
    el.innerHTML = `<p style="color:var(--text-muted);font-size:.875rem;padding:20px">Não foi possível carregar as publicações.</p>`;
  }
}

// ── Community tab posts ────────────────────────────────────────────────────────

async function loadCommunityPosts() {
  const el = document.getElementById('comm-posts');
  try {
    const res = await fetch('/gl/api/posts?page=1');
    const data = await res.json();
    const posts = (data.posts || []).slice(0, 8);
    if (!posts.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">💬</div><h3>Sem publicações ainda</h3></div>`;
      return;
    }
    el.innerHTML = posts.map(p => `
      <div class="post-row" onclick="window.location='/gl/forum/${p.id}'">
        <div class="post-cat-dot" style="background:#fce4ec">💬</div>
        <div style="flex:1;min-width:0">
          <div class="post-row-title">${escHtml(p.title)}</div>
          <div class="post-row-meta">
            <span class="badge badge-muted">${escHtml(p.category)}</span>
            <span>${escHtml(p.username)}</span>
            <span>${timeAgo(p.created_at)}</span>
          </div>
        </div>
      </div>`).join('');
  } catch (_) {
    el.innerHTML = `<p style="color:var(--text-muted);font-size:.875rem;padding:20px">Não foi possível carregar.</p>`;
  }
}

// ── Partnerships tab ──────────────────────────────────────────────────────────

function dashFilter(type) {
  _dashFilter = type;
  document.querySelectorAll('#tab-partnerships .filter-chip').forEach(c => {
    const label = c.textContent.trim();
    c.classList.toggle('active', type === '' ? label === 'Todos' : label === type);
  });
  loadDashPartnerships();
}

async function loadDashPartnerships() {
  const el = document.getElementById('dash-pships');
  el.innerHTML = `<div class="loading-state"><div class="spinner spinner-dark"></div></div>`;

  let url = '/gl/api/partnerships?page=1';
  if (_dashFilter) url += `&type=${encodeURIComponent(_dashFilter)}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Erro ao carregar');

    const items = data.partnerships || [];
    const total = data.total || items.length;

    const pip = document.getElementById('pship-pip');
    if (total > 0) { pip.textContent = total; pip.style.display = 'inline'; }

    if (!items.length) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">📢</div>
        <h3>Nenhuma oportunidade disponível</h3>
        <p style="font-size:.85rem;margin-top:6px">Verifique novamente em breve.</p>
      </div>`;
      return;
    }

    el.innerHTML = items.map(p => renderPshipCard(p)).join('');
    if (items.length < total) {
      el.innerHTML += `<div style="text-align:center;margin-top:16px">
        <a href="/gl/parcerias" class="btn btn-outline">Ver todas as ${total} oportunidades →</a>
      </div>`;
    }
  } catch (e) {
    el.innerHTML = `<p style="color:var(--danger);text-align:center;padding:30px">${e.message}</p>`;
  }
}

function renderPshipCard(p) {
  const token = getToken();
  const initials = p.logo_initials || (p.inst_short ? p.inst_short[0] : '🏛');
  return `
    <div class="pship-card">
      <div class="pship-hd">
        <div class="pship-logo">${escHtml(initials)}</div>
        <div style="flex:1">
          <div class="pship-title">${escHtml(p.title)}</div>
          <div class="pship-inst">
            ${escHtml(p.inst_name || p.inst_short || 'Instituição')}
            ${p.inst_verified ? '<span class="badge badge-accent" style="font-size:.62rem;margin-left:4px">✅ Verificada</span>' : ''}
          </div>
        </div>
      </div>
      <div class="pship-desc">${escHtml(p.description || '').slice(0, 260)}${(p.description || '').length > 260 ? '…' : ''}</div>
      <div class="pship-foot">
        <span class="tag tag-type">${escHtml(p.type || 'Oportunidade')}</span>
        ${p.city ? `<span class="tag tag-loc">📍 ${escHtml(p.city)}${p.state ? ', ' + escHtml(p.state) : ''}</span>` : ''}
        ${p.deadline ? `<span class="tag tag-date">⏰ até ${fmtDate(p.deadline)}</span>` : ''}
        <span style="font-size:.72rem;color:var(--text-light)">${fmtDate(p.created_at)}</span>
        ${token
          ? `<button class="apply-btn" onclick="openApplyModal(${p.id},'${escHtml(p.title).replace(/'/g,"\\'")}','${escHtml(p.inst_name||'').replace(/'/g,"\\'")}')">Candidatar-se</button>`
          : `<a href="/gl/login" class="apply-btn">Entrar para candidatar</a>`
        }
      </div>
    </div>`;
}

// ── Apply modal ───────────────────────────────────────────────────────────────

function openApplyModal(pid, title, instName) {
  _selectedPid = pid;
  document.getElementById('apply-title').textContent = title;
  document.getElementById('apply-inst-name').textContent = instName;
  document.getElementById('apply-message').value = '';
  const al = document.getElementById('apply-alert');
  al.className = 'alert'; al.textContent = '';
  const modal = document.getElementById('apply-modal');
  modal.style.display = 'flex';
}

function closeApplyModal() {
  document.getElementById('apply-modal').style.display = 'none';
  _selectedPid = null;
}

async function confirmApply() {
  if (!_selectedPid) return;
  const btn = document.getElementById('apply-confirm-btn');
  const alertEl = document.getElementById('apply-alert');
  const message = document.getElementById('apply-message').value.trim();

  btn.disabled = true; btn.textContent = 'Enviando…';

  try {
    const res = await apiFetch(`/partnerships/${_selectedPid}/apply`, {
      method: 'POST',
      body: JSON.stringify({ message })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Erro ao enviar candidatura');
    alertEl.className = 'alert alert-success show';
    alertEl.textContent = '✅ Candidatura enviada com sucesso!';
    btn.textContent = 'Enviado!';
    setTimeout(closeApplyModal, 1800);
  } catch (e) {
    alertEl.className = 'alert alert-error show';
    alertEl.textContent = e.message;
    btn.disabled = false; btn.textContent = 'Enviar Candidatura';
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function escHtml(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtDate(d) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
}

// tag helpers (reused from parcerias)
const tagStyles = {
  'tag-type': 'background:#ede9fe;color:#5b21b6',
  'tag-loc':  'background:#fef3c7;color:#92400e',
  'tag-date': 'background:#dbeafe;color:#1e40af'
};

// ── Pré-publicações tab ───────────────────────────────────────────────────────

const PREPRINT_TYPE_STYLES = {
  'Hipótese':        'background:#e8f0fe;color:#1a56db;border:1px solid #a4c0f4',
  'Artigo Preliminar':'background:#fce8ff;color:#7c3aed;border:1px solid #d8b4fe',
  'Revisão':         'background:#e8fdf0;color:#166534;border:1px solid #86efac',
  'Experimento':     'background:#fff7e8;color:#b45309;border:1px solid #fcd34d',
};

function dashPreprintFilter(type) {
  _dashPreprintFilter = type;
  document.querySelectorAll('#tab-preprints .filter-chip').forEach(c => {
    const val = c.getAttribute('onclick').match(/'([^']*)'/)?.[1] ?? '';
    c.classList.toggle('active', val === type);
  });
  _dashLoaded.preprints = true;
  loadDashPreprints();
}

async function loadDashPreprints() {
  const el = document.getElementById('dash-preprints');
  el.innerHTML = `<div class="loading-state"><div class="spinner spinner-dark"></div></div>`;
  try {
    let url = '/preprints?status=submitted&limit=10';
    if (_dashPreprintFilter) url += `&type=${encodeURIComponent(_dashPreprintFilter)}`;
    const res = await apiFetch(url);
    const data = await res.json();
    const list = data.preprints || [];
    if (!list.length) {
      el.innerHTML = `<div style="text-align:center;padding:40px 20px;color:var(--text-muted)">
        <div style="font-size:2.5rem;margin-bottom:10px">🔬</div>
        <p>Nenhuma pré-publicação encontrada.</p>
        <a href="/gl/preprints/criar" class="btn btn-primary" style="margin-top:14px">Seja o primeiro a publicar</a>
      </div>`;
      return;
    }
    el.innerHTML = list.map(p => {
      const typeStyle = PREPRINT_TYPE_STYLES[p.type] || '';
      const abstract = (p.abstract || '').slice(0, 160) + ((p.abstract || '').length > 160 ? '…' : '');
      return `
        <div onclick="window.location='/gl/preprint/${p.id}'" style="cursor:pointer;border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px 18px;margin-bottom:12px;background:var(--surface);transition:.15s" onmouseover="this.style.borderColor='var(--primary)'" onmouseout="this.style.borderColor='var(--border)'">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">
            <span style="border-radius:20px;padding:2px 10px;font-size:.72rem;font-weight:700;${typeStyle}">${escHtml(p.type)}</span>
            <span style="font-size:.75rem;color:var(--text-muted)">por <strong>${escHtml(p.author_username)}</strong></span>
            ${p.author_institution ? `<span style="font-size:.73rem;color:var(--text-muted)">· ${escHtml(p.author_institution)}</span>` : ''}
          </div>
          <div style="font-weight:700;font-size:.95rem;margin-bottom:6px;line-height:1.4">${escHtml(p.title)}</div>
          <div style="font-size:.84rem;color:var(--text-muted);line-height:1.6;margin-bottom:10px">${escHtml(abstract)}</div>
          <div style="display:flex;gap:14px;font-size:.76rem;color:var(--text-muted)">
            <span>💬 ${p.review_count || 0} revisão(ões)</span>
            <span>${timeAgo(p.created_at)}</span>
          </div>
        </div>`;
    }).join('');
  } catch (e) {
    el.innerHTML = `<p style="color:var(--danger);padding:20px">${e.message}</p>`;
  }
}
