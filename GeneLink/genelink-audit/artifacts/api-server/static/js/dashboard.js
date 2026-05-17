// ── Dashboard ────────────────────────────────────────────────────────────────

let _activeTab = 'overview';
let _dashFilter = '';
let _dashLoaded = { partnerships: false, community: false };
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
    const tabs = ['overview', 'partnerships', 'community'];
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
