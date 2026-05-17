// ── Institution Candidates ─────────────────────────────────────────────────

const instToken = localStorage.getItem('gl_inst_token') || '';
const instData  = JSON.parse(localStorage.getItem('gl_inst') || 'null');

if (!instToken || !instData) {
  window.location.href = '/gl/login#instituicao';
}

function instHeaders() {
  return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${instToken}` };
}

document.addEventListener('DOMContentLoaded', async () => {
  injectInstNavbar('/gl/inst-candidates');

  // Show institution name in hero
  const heroName = document.getElementById('inst-name-hero');
  if (heroName && instData) heroName.textContent = instData.name || 'sua instituição';

  await loadCandidates();
});

async function loadCandidates() {
  const container = document.getElementById('candidates-container');
  try {
    const res  = await fetch('/gl/api/inst/applications', { headers: instHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Erro ao carregar candidaturas');

    const apps = data.applications || [];

    // Update stats
    document.getElementById('s-total').textContent = apps.length;

    const vagas = new Set(apps.map(a => a.partnership_id)).size;
    document.getElementById('s-vagas').textContent = vagas;

    if (apps.length > 0) {
      const latest = apps.reduce((a, b) => new Date(a.created_at) > new Date(b.created_at) ? a : b);
      document.getElementById('s-recent').textContent = fmtDate(latest.created_at);
    } else {
      document.getElementById('s-recent').textContent = '—';
    }

    if (!apps.length) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📋</div>
          <h3>Nenhuma candidatura ainda.</h3>
          <p style="margin-top:8px;font-size:.83rem">Quando pesquisadores se candidatarem às suas vagas, aparecerão aqui.</p>
        </div>`;
      return;
    }

    // Group by partnership
    const grouped = {};
    for (const app of apps) {
      const key = app.partnership_id;
      if (!grouped[key]) {
        grouped[key] = { title: app.partnership_title, type: app.partnership_type, apps: [] };
      }
      grouped[key].apps.push(app);
    }

    const instInitials = instData.logo_initials || instData.short_name?.[0] || 'GL';

    let html = '';
    for (const [pid, group] of Object.entries(grouped)) {
      html += `
        <div class="group-hd">
          <div class="group-hd-icon">${esc(instInitials)}</div>
          <div class="group-hd-info">
            <div class="group-hd-title">${esc(group.title)}</div>
            <div class="group-hd-meta">
              <span style="background:#ede9fe;color:#5b21b6;padding:2px 8px;border-radius:10px;font-size:.7rem;font-weight:600">${esc(group.type || 'Vaga')}</span>
            </div>
          </div>
          <span class="group-count">${group.apps.length} candidato${group.apps.length !== 1 ? 's' : ''}</span>
        </div>`;

      for (const app of group.apps) {
        const avatarInitials = app.avatar_initials || app.username?.[0]?.toUpperCase() || '?';
        html += `
          <div class="cand-card">
            <div class="cand-avatar">${esc(avatarInitials)}</div>
            <div class="cand-info">
              <div class="cand-name">${esc(app.full_name || app.username)}</div>
              <div class="cand-email">
                <span>✉️</span>
                <a href="mailto:${esc(app.email)}" style="color:var(--primary-light)">${esc(app.email)}</a>
              </div>
              ${app.research_area ? `<span class="cand-area">🔬 ${esc(app.research_area)}</span>` : ''}
              ${app.message
                ? `<div class="cand-message">"${esc(app.message)}"</div>`
                : `<div class="cand-message" style="color:var(--text-light);font-style:italic">Sem mensagem adicional</div>`
              }
              <div class="cand-footer">📅 Candidatou-se em ${fmtDate(app.created_at)}</div>
            </div>
          </div>`;
      }
    }

    container.innerHTML = html;

  } catch (e) {
    container.innerHTML = `<p style="color:var(--danger);padding:20px;text-align:center">${esc(e.message)}</p>`;
  }
}

function esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
}
