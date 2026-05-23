let _searchTimeout = null;

document.addEventListener("DOMContentLoaded", () => {
  if (!requireAuth()) return;
  injectNavbar("/user-search");

  const input = document.getElementById("user-search-input");
  const form = document.getElementById("user-search-form");

  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");
  if (q) {
    input.value = q;
    performUserSearch(q);
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (q.length >= 2) performUserSearch(q);
  });

  input.addEventListener("input", () => {
    clearTimeout(_searchTimeout);
    const q = input.value.trim();
    if (q.length >= 2) {
      _searchTimeout = setTimeout(() => performUserSearch(q), 400);
    } else if (q.length === 0) {
      resetResults();
    }
  });
});

function resetResults() {
  document.getElementById("user-results").innerHTML = `
    <div class="empty-state">
      <div class="empty-state-icon">👥</div>
      <h3>Pesquise por pesquisadores</h3>
      <p style="font-size:.85rem;margin-top:6px">Digite um nome, username ou instituição para encontrar outros pesquisadores.</p>
    </div>`;
  document.getElementById("user-search-meta").textContent = "";
}

async function performUserSearch(query) {
  const resultsEl = document.getElementById("user-results");
  const metaEl = document.getElementById("user-search-meta");

  const url = new URL(window.location.href);
  url.searchParams.set("q", query);
  window.history.replaceState({}, "", url);

  resultsEl.innerHTML = `<div class="loading-state"><div class="spinner spinner-dark"></div><p style="margin-top:12px">Buscando pesquisadores…</p></div>`;
  metaEl.textContent = "";

  try {
    const res = await apiFetch(`/users/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();

    if (!res.ok) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><h3>${escHtml(data.error || "Erro na busca")}</h3></div>`;
      return;
    }

    const { users, total } = data;
    if (!users || !users.length) {
      metaEl.textContent = `Nenhum pesquisador encontrado para "${query}"`;
      resultsEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">🔎</div>
          <h3>Nenhum pesquisador encontrado</h3>
          <p style="font-size:.85rem;margin-top:8px">Tente um nome, username ou instituição diferente.</p>
        </div>`;
      return;
    }

    metaEl.textContent = `${total} pesquisador${total !== 1 ? "es" : ""} encontrado${total !== 1 ? "s" : ""} para "${query}"`;

    resultsEl.innerHTML = `<div class="user-grid">${users.map(renderUserCard).join("")}</div>`;
  } catch (err) {
    resultsEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⚠️</div><h3>Erro de conexão. Tente novamente.</h3></div>`;
  }
}

function renderUserCard(u) {
  const initials = escHtml(u.avatar_initials || u.username.slice(0, 2).toUpperCase());
  const joined = u.created_at ? formatDate(u.created_at) : "—";
  return `
    <a href="/gl/user/${escHtml(u.username)}" class="user-card-link">
      <div class="user-card">
        <div class="user-card-avatar">${initials}</div>
        <div class="user-card-body">
          <div class="user-card-username">@${escHtml(u.username)}
            ${u.is_verified ? `<span class="badge badge-accent" style="font-size:.65rem;margin-left:6px">✓ Verificado</span>` : ""}
          </div>
          ${u.full_name ? `<div class="user-card-name">${escHtml(u.full_name)}</div>` : ""}
          <div class="user-card-meta">
            ${u.institution ? `<span>🏛️ ${escHtml(u.institution)}</span>` : ""}
            ${u.research_area ? `<span>🔬 ${escHtml(u.research_area)}</span>` : ""}
            <span>Membro desde ${joined}</span>
          </div>
        </div>
        <div class="user-card-arrow">→</div>
      </div>
    </a>`;
}

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
