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
  document.getElementById('inst-avatar').textContent = instData.logo_initials || instData.short_name?.[0] || '🏛️';
  document.getElementById('inst-name-title').textContent = instData.name;
  document.getElementById('inst-meta').textContent =
    `${instData.type || 'Instituição'} · ${instData.city || ''}, ${instData.state || ''}`;
  document.getElementById('seal-name').textContent = `[Verificado por: ${instData.name}]`;
}

// ── Tab switching ──
function switchTab(name) {
  document.querySelectorAll('.panel-tab').forEach((t, i) => {
    const sections = ['members','library','partnerships'];
    t.classList.toggle('active', sections[i] === name);
    document.getElementById('tab-' + sections[i]).classList.toggle('active', sections[i] === name);
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
    document.getElementById('members-count').textContent = `${members.length} pesquisador${members.length !== 1 ? 'es' : ''}`;
    if (!members.length) {
      list.innerHTML = `<div class="empty-state"><div class="icon">👥</div><p>Nenhum pesquisador vinculado ainda.<br>Pesquisadores com e-mail <strong>@${instData.email_domain || 'seu-domínio'}</strong> aparecem automaticamente.</p></div>`;
      return;
    }
    list.innerHTML = members.map(m => `
      <div class="member-card">
        <div class="member-avatar">${m.avatar_initials || m.username?.[0]?.toUpperCase() || '?'}</div>
        <div class="member-info">
          <strong>${m.full_name || m.username}</strong>
          <span>${m.email || ''} ${m.research_area ? '· ' + m.research_area : ''}</span>
        </div>
        ${m.is_member
          ? `<span class="member-badge badge-member">✓ Membro</span>
             <button class="btn btn-sm" style="font-size:.72rem;padding:4px 10px;background:#fee2e2;color:#991b1b;border:none"
               onclick="unlinkMember(${m.id}, this)">Desvincular</button>`
          : `<span class="member-badge badge-domain">Domínio</span>
             <button class="btn btn-sm btn-accent" style="font-size:.72rem;padding:4px 10px"
               onclick="linkMember(${m.id}, this)">Vincular</button>`
        }
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`;
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
      list.innerHTML = `<div class="empty-state"><div class="icon">📚</div><p>Nenhum item na biblioteca ainda.<br>Adicione dados de pesquisa, protocolos ou artigos pré-publicação.</p></div>`;
      return;
    }
    list.innerHTML = items.map(item => `
      <div class="lib-item">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
          <div style="flex:1">
            <h4>${esc(item.title)}</h4>
            ${item.content ? `<p>${esc(item.content).slice(0,200)}${item.content.length>200?'…':''}</p>` : ''}
            <div class="lib-meta">
              <span style="background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:10px;font-size:.7rem;font-weight:600">${esc(item.category)}</span>
              ${item.is_public ? `<span style="color:#16a34a">🌐 Público</span>` : `<span>🔒 Restrito</span>`}
              <span>${fmtDate(item.created_at)}</span>
            </div>
          </div>
          <button onclick="deleteLibItem(${item.id}, this)" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1.1rem;padding:4px">🗑️</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`;
  }
}

function showLibModal() {
  const m = document.getElementById('lib-modal');
  m.style.display = 'flex';
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
    document.getElementById('lib-title').value = '';
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
    const all = (data.partnerships || []).filter(p => p.institution_id === instData.id || p.inst_id === instData.id);
    if (!all.length) {
      list.innerHTML = `<div class="empty-state"><div class="icon">📢</div><p>Nenhum anúncio publicado ainda.<br>Crie oportunidades para pesquisadores da plataforma.</p></div>`;
      return;
    }
    list.innerHTML = all.map(p => `
      <div class="partner-card">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
          <div style="flex:1">
            <h4>${esc(p.title)}</h4>
            <p>${esc(p.description).slice(0,200)}${p.description?.length>200?'…':''}</p>
            <div class="partner-meta">
              <span class="partner-type">${esc(p.type)}</span>
              ${p.location ? `<span>📍 ${esc(p.location)}</span>` : ''}
              ${p.deadline ? `<span>⏰ até ${p.deadline}</span>` : ''}
              <span style="color:var(--text-muted)">${fmtDate(p.created_at)}</span>
            </div>
          </div>
          <button onclick="deletePartnership(${p.id}, this)" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1.1rem;padding:4px">🗑️</button>
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`;
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
