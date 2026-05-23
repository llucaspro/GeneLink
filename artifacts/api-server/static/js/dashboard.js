document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  injectNavbar("/dashboard");

  const cached = getUser();
  document.getElementById("welcome-name").textContent =
    cached.full_name || cached.username;

  await Promise.all([loadStats(), loadRecentSearches(), loadRecentPosts()]);
});

async function loadStats() {
  let user = getUser();
  try {
    const res = await apiFetch("/user");
    if (res.ok) {
      const fresh = await res.json();
      setAuth(getToken(), fresh);
      user = fresh;
      document.getElementById("welcome-name").textContent =
        fresh.full_name || fresh.username;
    }
  } catch {}
  document.getElementById("stat-username").textContent = `@${user.username}`;
  document.getElementById("stat-institution").textContent =
    user.institution || "Nenhuma instituição definida";
  document.getElementById("stat-area").textContent =
    user.research_area || "Não especificada";
  document.getElementById("stat-joined").textContent = user.created_at
    ? formatDate(user.created_at)
    : "—";
}

async function loadRecentSearches() {
  const el = document.getElementById("recent-searches");
  try {
    const res = await apiFetch("/search-history");
    const data = await res.json();
    if (!data.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🔬</div><h3>Nenhuma busca ainda</h3><p style="font-size:.85rem;margin-top:6px"><a href="/search">Comece a buscar genes</a></p></div>`;
      return;
    }
    el.innerHTML = data
      .map(
        (s) => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border)">
        <div>
          <span style="font-weight:600;font-family:var(--mono);color:var(--primary)">${escHtml(s.query)}</span>
          <span style="font-size:.8rem;color:var(--text-muted);margin-left:8px">${s.result_count} resultado${s.result_count !== 1 ? "s" : ""}</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <span style="font-size:.78rem;color:var(--text-light)">${timeAgo(s.searched_at)}</span>
          <a href="/search?q=${encodeURIComponent(s.query)}" class="btn btn-ghost btn-sm">Buscar novamente</a>
        </div>
      </div>`
      )
      .join("");
  } catch {
    el.innerHTML = `<p style="color:var(--text-muted);font-size:.875rem">Não foi possível carregar o histórico.</p>`;
  }
}

async function loadRecentPosts() {
  const el = document.getElementById("recent-posts");
  try {
    const res = await fetch("/api/posts?page=1");
    const data = await res.json();
    const posts = (data.posts || []).slice(0, 5);
    if (!posts.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📋</div><h3>Nenhuma publicação ainda</h3><p style="font-size:.85rem;margin-top:6px"><a href="/forum">Inicie uma discussão</a></p></div>`;
      return;
    }
    el.innerHTML = posts
      .map(
        (p) => `
      <div class="post-item" onclick="window.location='/forum/${p.id}'">
        <div class="post-title">${escHtml(p.title)}</div>
        <div class="post-meta">
          <span class="badge badge-muted">${escHtml(p.category)}</span>
          <span class="user-chip">
            <span class="avatar-sm">${escHtml(p.avatar_initials || "?")}</span>
            ${escHtml(p.username)}
          </span>
          <span>${timeAgo(p.created_at)}</span>
          <span>${p.comment_count} comentário${p.comment_count !== 1 ? "s" : ""}</span>
        </div>
      </div>`
      )
      .join("");
  } catch {
    el.innerHTML = `<p style="color:var(--text-muted);font-size:.875rem">Não foi possível carregar as publicações.</p>`;
  }
}

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
