// ── Parcerias & Oportunidades ──────────────────────────────────────────────

const token    = localStorage.getItem('gl_token') || '';
const instTok  = localStorage.getItem('gl_inst_token') || '';
const instData = JSON.parse(localStorage.getItem('gl_inst') || 'null');

let currentFilter = '';
let currentPage   = 1;
let totalResults  = 0;
let allLoaded     = [];
let selectedPid   = null;

document.addEventListener('DOMContentLoaded', () => {
  // Inject appropriate navbar based on who is logged in
  if (token) {
    injectNavbar('/gl/parcerias');
  } else if (instTok && instData) {
    injectInstNavbar('/gl/parcerias');
  }
  loadPartnerships();
});

function setFilter(type) {
  currentFilter = type;
  currentPage   = 1;
  allLoaded     = [];
  document.querySelectorAll('.filter-chip').forEach(c => {
    c.classList.toggle('active', c.textContent.trim().includes(type) || (!type && c.textContent.trim() === 'Todos'));
  });
  loadPartnerships();
}

async function loadPartnerships(append = false) {
  const list = document.getElementById('partnerships-list');
  if (!append) list.innerHTML = `<p style="color:var(--text-muted);text-align:center;padding:40px">Carregando…</p>`;

  let url = `/gl/api/partnerships?page=${currentPage}`;
  if (currentFilter) url += `&type=${encodeURIComponent(currentFilter)}`;

  try {
    const res  = await fetch(url);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Erro ao carregar');

    const items = data.partnerships || [];
    totalResults = data.total || items.length;
    allLoaded    = append ? [...allLoaded, ...items] : items;

    document.getElementById('results-count').textContent =
      `${totalResults} oportunidade${totalResults !== 1 ? 's' : ''}`;

    if (!allLoaded.length) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="icon">📢</div>
          <p>Nenhuma oportunidade disponível no momento.<br>Verifique novamente em breve!</p>
        </div>`;
      document.getElementById('load-more-wrap').style.display = 'none';
      return;
    }

    list.innerHTML = allLoaded.map(p => renderCard(p)).join('');
    document.getElementById('load-more-wrap').style.display =
      allLoaded.length < totalResults ? 'block' : 'none';

  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger);text-align:center">${e.message}</p>`;
  }
}

function loadMore() {
  currentPage++;
  loadPartnerships(true);
}

function renderCard(p) {
  const initials = p.logo_initials || p.inst_short?.[0] || '🏛';
  return `
    <div class="partner-card">
      <div class="partner-header">
        <div class="inst-logo">${esc(initials)}</div>
        <div style="flex:1">
          <div class="partner-title">${esc(p.title)}</div>
          <div class="partner-inst">
            ${esc(p.inst_name || p.inst_short || 'Instituição')}
            ${p.inst_verified ? '<span class="tag tag-verified" style="font-size:.65rem;margin-left:4px">✅ Verificada</span>' : ''}
          </div>
        </div>
      </div>
      <div class="partner-body">
        <p>${esc(p.description).slice(0,280)}${(p.description || '').length > 280 ? '…' : ''}</p>
        ${p.requirements ? `<p style="font-size:.78rem"><strong>Requisitos:</strong> ${esc(p.requirements).slice(0,150)}${p.requirements.length > 150 ? '…':''}</p>` : ''}
      </div>
      <div class="partner-footer">
        <span class="tag tag-type">${esc(p.type || 'Oportunidade')}</span>
        ${p.city ? `<span class="tag tag-loc">📍 ${esc(p.city)}, ${esc(p.state || '')}</span>` : ''}
        ${p.location ? `<span class="tag tag-loc">📍 ${esc(p.location)}</span>` : ''}
        ${p.deadline ? `<span class="tag tag-date">⏰ até ${fmtDate(p.deadline)}</span>` : ''}
        <span style="font-size:.72rem;color:var(--text-light)">${fmtDate(p.created_at)}</span>
        ${token
          ? `<button class="apply-btn" onclick="openApplyModal(${p.id},'${esc(p.title).replace(/'/g,"\\'")}','${esc(p.inst_name || '').replace(/'/g,"\\'")}')">Candidatar-se</button>`
          : `<a href="/gl/login" class="apply-btn" style="text-decoration:none;display:inline-block">Entrar para candidatar</a>`
        }
      </div>
    </div>
  `;
}

function openApplyModal(pid, title, instName) {
  selectedPid = pid;
  document.getElementById('apply-title').textContent = title;
  document.getElementById('apply-inst-name').textContent = instName;
  document.getElementById('apply-message').value = '';
  document.getElementById('apply-alert').className = 'alert';
  document.getElementById('apply-alert').textContent = '';
  document.getElementById('apply-modal').classList.add('open');
}

function closeApplyModal() {
  document.getElementById('apply-modal').classList.remove('open');
  selectedPid = null;
}

async function confirmApply() {
  if (!selectedPid) return;
  const btn     = document.getElementById('apply-confirm-btn');
  const alertEl = document.getElementById('apply-alert');
  const message = document.getElementById('apply-message').value.trim();

  btn.disabled = true; btn.textContent = 'Enviando…';

  try {
    const res = await fetch(`/gl/api/partnerships/${selectedPid}/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ message })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Erro ao enviar candidatura');

    alertEl.className = 'alert alert-success';
    alertEl.textContent = '✅ Candidatura enviada com sucesso!';
    btn.textContent = 'Enviado!';
    setTimeout(closeApplyModal, 1800);
  } catch (e) {
    alertEl.className = 'alert alert-error';
    alertEl.textContent = e.message;
    btn.disabled = false; btn.textContent = 'Enviar Candidatura';
  }
}

function esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtDate(d) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('pt-BR', { day:'2-digit', month:'short', year:'numeric' });
}
