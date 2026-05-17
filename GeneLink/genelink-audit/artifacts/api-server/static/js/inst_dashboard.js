// ── Institution Dashboard ──────────────────────────────────────────────────

let instToken = localStorage.getItem('gl_inst_token') || '';
let instData  = JSON.parse(localStorage.getItem('gl_inst') || 'null');

// Redirect if not logged in as institution
if (!instToken || !instData) {
  window.location.href = '/gl/login#instituicao';
}

function instHeaders() {
  return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${instToken}` };
}

function instLogout() {
  fetch('/gl/api/institutions/logout', { method: 'POST' });
  localStorage.removeItem('gl_inst_token');
  localStorage.removeItem('gl_inst');
  window.location.href = '/gl/login#instituicao';
}

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
  renderHero();
  await Promise.all([loadMembers(), loadLibrary(), loadPartnerships()]);
});

function renderHero() {
  if (!instData) return;
  const initial = instData.logo_initials || instData.short_name?.[0] || '🏛️';
  document.getElementById('inst-avatar').textContent = initial;
  document.getElementById('inst-name-title').textContent = instData.name;
  document.getElementById('inst-meta').textContent =
    `${instData.type || 'Instituição'} · ${instData.city || ''}, ${instData.state || ''}`;
  document.getElementById('seal-name').textContent = `[Verificado por: ${instData.name}]`;

  // Pills
  const typeEl = document.getElementById('inst-type-pill');
  const cityEl = document.getElementById('inst-city-pill');
  if (typeEl) typeEl.textContent = instData.type || 'Instituição';
  if (cityEl) cityEl.textContent = [instData.city, instData.state].filter(Boolean).join(', ') || '—';

  // Metrics
  const domainEl = document.getElementById('m-domain');
  if (domainEl) domainEl.textContent = instData.email_domain ? '@' + instData.email_domain : '—';
}

// ── Tab switching ──
const _TABS = ['members', 'library', 'partnerships'];

function switchTab(name) {
  document.querySelectorAll('.dash-tab').forEach((t, i) => {
    t.classList.toggle('active', _TABS[i] === name);
  });
  _TABS.forEach(id => {
    const panel = document.getElementById('tab-' + id);
    if (panel) panel.classList.toggle('active', id === name);
  });
}

// ── Members ──
async function loadMembers() {
  const list = document.getElementById('members-list');
  try {
    const res  = await fetch('/gl/api/inst/members', { headers: instHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    const members = data.members || [];

    // Update metric
    const mEl = document.getElementById('m-members');
    if (mEl) mEl.textContent = members.length;

    const countEl = document.getElementById('members-count');
    if (countEl) countEl.textContent = `${members.length} pesquisador${members.length !== 1 ? 'es' : ''}`;

    if (!members.length) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">👥</div>
          <h3>Nenhum pesquisador vinculado ainda.</h3>
          <p style="margin-top:8px;font-size:.83rem">Pesquisadores com e-mail <strong>@${instData.email_domain || 'seu-domínio'}</strong> aparecem automaticamente.</p>
        </div>`;
      return;
    }

    list.innerHTML = members.map(m => `
      <div class="member-row">
        <div class="member-avatar">${esc(m.avatar_initials || m.username?.[0]?.toUpperCase() || '?')}</div>
        <div class="member-info">
          <strong>${esc(m.full_name || m.username)}</strong>
          <span>${esc(m.email || '')}${m.research_area ? ' · ' + esc(m.research_area) : ''}</span>
        </div>
        <div class="member-actions">
          ${m.is_member
            ? `<span class="badge-member">✓ Membro</span>
               <button class="btn btn-sm" style="font-size:.72rem;padding:4px 10px;background:#fee2e2;color:#991b1b;border:none"
                 onclick="unlinkMember(${m.id}, this)">Desvincular</button>`
            : `<span class="badge-domain">Domínio</span>
               <button class="btn btn-sm btn-accent" style="font-size:.72rem;padding:4px 10px"
                 onclick="linkMember(${m.id}, this)">Vincular</button>`
          }
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger);padding:20px">${esc(e.message)}</p>`;
  }
}

async function linkMember(userId, btn) {
  btn.disabled = true;
  const res = await fetch(`/gl/api/inst/members/${userId}/link`, { method: 'POST', headers: instHeaders() });
  if (res.ok) loadMembers();
  else btn.disabled = false;
}

async function unlinkMember(userId, btn) {
  if (!confirm('Desvincular este pesquisador da instituição?')) return;
  btn.disabled = true;
  const res = await fetch(`/gl/api/inst/members/${userId}/unlink`, { method: 'POST', headers: instHeaders() });
  if (res.ok) loadMembers();
  else btn.disabled = false;
}

// ── Library ──
async function loadLibrary() {
  const list = document.getElementById('lib-list');
  try {
    const res  = await fetch('/gl/api/inst/library', { headers: instHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    const items = data.items || [];

    if (!items.length) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📚</div>
          <h3>Nenhum item na biblioteca ainda.</h3>
          <p style="margin-top:8px;font-size:.83rem">Adicione dados de pesquisa, protocolos ou artigos pré-publicação.</p>
        </div>`;
      return;
    }

    list.innerHTML = items.map(item => `
      <div class="lib-row">
        <div class="lib-meta-row">
          <div style="flex:1">
            <h4>${esc(item.title)}</h4>
            ${item.content ? `<p>${esc(item.content).slice(0,220)}${item.content.length > 220 ? '…' : ''}</p>` : ''}
            <div class="lib-meta">
              <span style="background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:10px;font-size:.7rem;font-weight:600">${esc(item.category)}</span>
              ${item.is_public
                ? `<span style="color:#16a34a;font-weight:600">🌐 Público</span>`
                : `<span>🔒 Restrito</span>`}
              <span>${fmtDate(item.created_at)}</span>
            </div>
          </div>
          <button onclick="deleteLibItem(${item.id}, this)"
            style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1.1rem;padding:4px;flex-shrink:0">🗑️</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger);padding:20px">${esc(e.message)}</p>`;
  }
}

function showLibModal() {
  document.getElementById('lib-modal').style.display = 'flex';
}

async function createLibItem() {
  const title    = document.getElementById('lib-title').value.trim();
  const content  = document.getElementById('lib-content').value.trim();
  const category = document.getElementById('lib-category').value;
  const isPublic = document.getElementById('lib-public').checked;
  if (!title) { alert('Título é obrigatório'); return; }

  const res = await fetch('/gl/api/inst/library', {
    method: 'POST', headers: instHeaders(),
    body: JSON.stringify({ title, content, category, is_public: isPublic })
  });
  if (res.ok) {
    document.getElementById('lib-modal').style.display = 'none';
    document.getElementById('lib-title').value   = '';
    document.getElementById('lib-content').value = '';
    loadLibrary();
  } else {
    const d = await res.json();
    alert(d.error || 'Erro ao salvar');
  }
}

async function deleteLibItem(itemId, btn) {
  if (!confirm('Remover este item da biblioteca?')) return;
  btn.disabled = true;
  const res = await fetch(`/gl/api/inst/library/${itemId}`, { method: 'DELETE', headers: instHeaders() });
  if (res.ok) loadLibrary();
  else btn.disabled = false;
}

// ── Partnerships ──
async function loadPartnerships() {
  const list = document.getElementById('partner-list');
  try {
    const res  = await fetch('/gl/api/partnerships', { headers: instHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error);
    const all = (data.partnerships || []).filter(p =>
      p.institution_id === instData.id || p.inst_id === instData.id
    );

    if (!all.length) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📢</div>
          <h3>Nenhum anúncio publicado ainda.</h3>
          <p style="margin-top:8px;font-size:.83rem">Crie oportunidades para pesquisadores da plataforma.</p>
        </div>`;
      return;
    }

    list.innerHTML = all.map(p => `
      <div class="pship-card">
        <div class="pship-hd">
          <div class="pship-logo">${esc(instData.logo_initials || instData.short_name?.[0] || 'GL')}</div>
          <div style="flex:1;min-width:0">
            <div class="pship-title">${esc(p.title)}</div>
          </div>
          <button onclick="deletePartnership(${p.id}, this)"
            style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1.1rem;padding:4px;flex-shrink:0">🗑️</button>
        </div>
        <div class="pship-desc">${esc(p.description).slice(0,220)}${p.description?.length > 220 ? '…' : ''}</div>
        <div class="pship-foot">
          <span class="partner-type">${esc(p.type)}</span>
          ${p.location ? `<span class="tag tag-loc">📍 ${esc(p.location)}</span>` : ''}
          ${p.deadline ? `<span class="tag tag-date">⏰ até ${p.deadline}</span>` : ''}
          <span style="font-size:.73rem;color:var(--text-light);margin-left:auto">${fmtDate(p.created_at)}</span>
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger);padding:20px">${esc(e.message)}</p>`;
  }
}

function showPartnerModal() {
  document.getElementById('partner-modal').style.display = 'flex';
}

async function createPartnership() {
  const title = document.getElementById('p-title').value.trim();
  const desc  = document.getElementById('p-desc').value.trim();
  if (!title || !desc) { alert('Título e descrição são obrigatórios'); return; }

  const res = await fetch('/gl/api/partnerships', {
    method: 'POST', headers: instHeaders(),
    body: JSON.stringify({
      title, description: desc,
      type        : document.getElementById('p-type').value,
      requirements: document.getElementById('p-req').value.trim(),
      location    : document.getElementById('p-loc').value.trim(),
      deadline    : document.getElementById('p-deadline').value || null,
    })
  });
  if (res.ok) {
    document.getElementById('partner-modal').style.display = 'none';
    document.getElementById('p-title').value = '';
    document.getElementById('p-desc').value  = '';
    loadPartnerships();
  } else {
    const d = await res.json();
    alert(d.error || 'Erro ao publicar');
  }
}

async function deletePartnership(pid, btn) {
  if (!confirm('Remover este anúncio?')) return;
  btn.disabled = true;
  const res = await fetch(`/gl/api/partnerships/${pid}`, { method: 'DELETE', headers: instHeaders() });
  if (res.ok) loadPartnerships();
  else btn.disabled = false;
}

// ── Helpers ──
function esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtDate(d) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('pt-BR', { day:'2-digit', month:'short', year:'numeric' });
}
