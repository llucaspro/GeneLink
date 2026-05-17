// ── Admin Panel ───────────────────────────────────────────────────────────────

let _activeTab = "overview";
let _userPage = 1;
let _forumPage = 1;
let _userSearch = "";
let _forumSearch = "";
let _confirmCallback = null;
let _resetPwdUserId = null;
let _statusPreprintId = null;
let _searchTimer = null;

document.addEventListener("DOMContentLoaded", async () => {
  requireAuth();
  injectNavbar("/gl/admin");
  await checkAdminAccess();
});

async function checkAdminAccess() {
  try {
    const [statsRes, activityRes] = await Promise.all([
      apiFetch("/admin/stats"),
      apiFetch("/admin/activity"),
    ]);
    if (statsRes.status === 403) {
      document.getElementById("access-denied").style.display = "block";
      return;
    }
    document.getElementById("admin-content").style.display = "block";

    const stats = await statsRes.json();
    document.getElementById("s-users").textContent    = stats.users        ?? "—";
    document.getElementById("s-insts").textContent    = stats.institutions ?? "—";
    document.getElementById("s-verified").textContent = stats.verified_users ?? "—";
    document.getElementById("s-posts").textContent    = stats.posts        ?? "—";
    document.getElementById("s-new-week").textContent  = stats.new_users   ?? "—";
    document.getElementById("s-preprints").textContent = stats.preprints   ?? "—";

    if (activityRes.ok) {
      const act = await activityRes.json();
      if (act.new_users_week != null) document.getElementById("s-new-week").textContent  = act.new_users_week;
      if (act.total_preprints != null) document.getElementById("s-preprints").textContent = act.total_preprints;
      renderActivityFeed(act);
    }
  } catch {
    document.getElementById("access-denied").style.display = "block";
  }
}

// ── Tab switching ──────────────────────────────────────────────────────────────

const TAB_ORDER = ["overview", "users", "institutions", "forum", "preprints"];

function switchTab(name) {
  _activeTab = name;
  document.querySelectorAll(".tab-link").forEach((el, i) => {
    el.classList.toggle("active", TAB_ORDER[i] === name);
  });
  TAB_ORDER.forEach(t => {
    const panel = document.getElementById("tab-" + t);
    if (panel) panel.classList.toggle("active", t === name);
  });
  if (name === "users")        loadUsers();
  if (name === "institutions") loadInstitutions();
  if (name === "forum")        loadForumPosts();
  if (name === "preprints")    loadAdminPreprints();
}

// ── Activity Feed (Visão Geral) ────────────────────────────────────────────────

function renderActivityFeed(act) {
  const feedUsers = document.getElementById("feed-users");
  if (act.recent_users && act.recent_users.length) {
    feedUsers.innerHTML = act.recent_users.map(u => `
      <div class="feed-item">
        <div class="feed-icon" style="background:#dbeafe">👤</div>
        <div class="feed-main">
          <div class="feed-title">@${esc(u.username)}</div>
          <div class="feed-meta">${esc(u.email)} · ${timeAgo(u.created_at)}</div>
        </div>
      </div>`).join("");
  } else {
    feedUsers.innerHTML = `<p style="color:var(--text-muted);font-size:.84rem;padding:10px 0">Nenhum cadastro recente.</p>`;
  }

  const feedPosts = document.getElementById("feed-posts");
  if (act.recent_posts && act.recent_posts.length) {
    feedPosts.innerHTML = act.recent_posts.map(p => `
      <div class="feed-item">
        <div class="feed-icon" style="background:#f3e8ff">📋</div>
        <div class="feed-main">
          <div class="feed-title">${esc(p.title)}</div>
          <div class="feed-meta">por @${esc(p.username)} · ${timeAgo(p.created_at)}</div>
        </div>
        <a href="/gl/forum/${p.id}" target="_blank" class="btn btn-sm btn-ghost" style="flex-shrink:0">→</a>
      </div>`).join("");
  } else {
    feedPosts.innerHTML = `<p style="color:var(--text-muted);font-size:.84rem;padding:10px 0">Nenhum post recente.</p>`;
  }

  const feedPreprints = document.getElementById("feed-preprints");
  if (act.recent_preprints && act.recent_preprints.length) {
    feedPreprints.innerHTML = act.recent_preprints.map(p => `
      <div class="feed-item">
        <div class="feed-icon" style="background:#d1fae5">🔬</div>
        <div class="feed-main">
          <div class="feed-title">${esc(p.title)}</div>
          <div class="feed-meta">${esc(p.type)} · @${esc(p.username)} · ${timeAgo(p.created_at)}</div>
        </div>
        <a href="/gl/preprint/${p.id}" target="_blank" class="btn btn-sm btn-ghost" style="flex-shrink:0">→</a>
      </div>`).join("");
  } else {
    feedPreprints.innerHTML = `<p style="color:var(--text-muted);font-size:.84rem;padding:10px 0">Nenhuma pré-publicação recente.</p>`;
  }
}

function timeAgo(ts) {
  if (!ts) return "—";
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "agora mesmo";
  if (m < 60) return `${m}min atrás`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h atrás`;
  const d = Math.floor(h / 24);
  return `${d}d atrás`;
}

// ── Usuários ──────────────────────────────────────────────────────────────────

function debounceUserSearch() {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => { _userPage = 1; loadUsers(); }, 350);
}

async function loadUsers() {
  const search  = document.getElementById("user-search")?.value.trim() || "";
  const filter  = document.getElementById("user-filter-verified")?.value || "";
  _userSearch = search;
  const tbody   = document.getElementById("user-table-body");
  tbody.innerHTML = `<tr><td colspan="7"><div class="loading-state"><div class="spinner spinner-dark"></div></div></td></tr>`;

  try {
    let url = `/admin/users?page=${_userPage}`;
    if (search)           url += `&search=${encodeURIComponent(search)}`;
    if (filter === "1")   url += "&verified=1";
    if (filter === "0")   url += "&verified=0";
    if (filter === "admin") url += "&admin=1";

    const res  = await apiFetch(url);
    const data = await res.json();
    const users = data.users || [];
    const total = data.total || users.length;
    const perPage = 30;

    document.getElementById("user-count-label").textContent = `${total} usuário(s)`;
    document.getElementById("user-page-info").textContent =
      `Página ${_userPage} · exibindo ${users.length} de ${total}`;

    renderUserPagination(total, perPage);

    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:28px">Nenhum usuário encontrado.</td></tr>`;
      return;
    }

    tbody.innerHTML = users.map(u => `
      <tr>
        <td>
          <div style="font-weight:600">${esc(u.username)}</div>
          <div style="font-size:.74rem;color:var(--text-muted)">${esc(u.full_name || "")}</div>
        </td>
        <td style="font-size:.82rem;color:var(--text-muted)">${esc(u.email)}</td>
        <td style="font-size:.8rem;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(u.research_area||'')}">
          ${esc(u.research_area || "—")}
        </td>
        <td style="text-align:center">
          ${u.is_verified
            ? `<span class="badge-v">✓ Verificado</span>`
            : `<span class="badge-u">Não verificado</span>`}
        </td>
        <td style="text-align:center">
          ${u.is_admin ? `<span class="badge-admin">⚙ Admin</span>` : "—"}
        </td>
        <td style="font-size:.78rem;color:var(--text-muted);white-space:nowrap">${fmtDate(u.created_at)}</td>
        <td>
          <div class="action-cell">
            ${u.is_verified
              ? `<button class="btn btn-sm btn-ghost" onclick="verifyUser(${u.id},false)" title="Remover verificação">✕ Verificado</button>`
              : `<button class="btn btn-sm btn-primary" onclick="verifyUser(${u.id},true)" title="Verificar pesquisador">✓ Verificar</button>`}
            ${u.is_admin
              ? `<button class="btn btn-sm btn-ghost" onclick="setAdmin(${u.id},false)">Remover Admin</button>`
              : `<button class="btn btn-sm btn-outline" onclick="setAdmin(${u.id},true)">Tornar Admin</button>`}
            <button class="btn btn-sm btn-outline" onclick="openResetPwd(${u.id},'${esc(u.username)}')" title="Redefinir senha">🔑</button>
            <button class="btn btn-sm btn-danger"  onclick="confirmDelete('user',${u.id},'${esc(u.username).replace(/'/g,"\\'")}')">🗑</button>
          </div>
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

function renderUserPagination(total, perPage) {
  const pages = Math.ceil(total / perPage);
  const el = document.getElementById("user-pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }
  let html = "";
  if (_userPage > 1) html += `<button class="page-btn" onclick="_userPage=${_userPage-1};loadUsers()">‹</button>`;
  for (let i = 1; i <= pages; i++) {
    if (i === 1 || i === pages || Math.abs(i - _userPage) <= 1) {
      html += `<button class="page-btn${i===_userPage?' active':''}" onclick="_userPage=${i};loadUsers()">${i}</button>`;
    } else if (Math.abs(i - _userPage) === 2) {
      html += `<span style="padding:0 4px;color:var(--text-muted)">…</span>`;
    }
  }
  if (_userPage < pages) html += `<button class="page-btn" onclick="_userPage=${_userPage+1};loadUsers()">›</button>`;
  el.innerHTML = html;
}

async function verifyUser(id, verified) {
  const alertEl = document.getElementById("admin-alert-user");
  try {
    const res = await apiFetch(`/admin/users/${id}/verify`, {
      method: "POST", body: JSON.stringify({ verified }),
    });
    if (res.ok) {
      showAlert(alertEl, verified ? "✓ Usuário verificado com sucesso!" : "Verificação removida.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadUsers();
    } else {
      const d = await res.json();
      showAlert(alertEl, d.error || "Erro", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

async function setAdmin(id, isAdmin) {
  const alertEl = document.getElementById("admin-alert-user");
  try {
    const res = await apiFetch(`/admin/users/${id}/admin`, {
      method: "POST", body: JSON.stringify({ admin: isAdmin }),
    });
    if (res.ok) {
      showAlert(alertEl, isAdmin ? "⚙ Permissão de admin concedida!" : "Admin removido.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadUsers();
    } else {
      const d = await res.json();
      showAlert(alertEl, d.error || "Erro", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

async function deleteUser(id) {
  const alertEl = document.getElementById("admin-alert-user");
  try {
    const res  = await apiFetch(`/admin/users/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Conta excluída com sucesso.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadUsers();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir conta", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

// ── Redefinir senha ────────────────────────────────────────────────────────────

function openResetPwd(userId, username) {
  _resetPwdUserId = userId;
  document.getElementById("reset-pwd-label").textContent = `Nova senha para @${username}`;
  document.getElementById("reset-pwd-input").value = "";
  hideAlert(document.getElementById("reset-pwd-alert"));
  document.getElementById("reset-pwd-modal").style.display = "flex";
}

async function confirmResetPwd() {
  const alertEl  = document.getElementById("reset-pwd-alert");
  const password = document.getElementById("reset-pwd-input").value.trim();
  if (password.length < 6) {
    showAlert(alertEl, "A senha deve ter ao menos 6 caracteres.", "error");
    return;
  }
  try {
    const res  = await apiFetch(`/admin/users/${_resetPwdUserId}/reset-password`, {
      method: "POST", body: JSON.stringify({ password }),
    });
    const data = await res.json();
    if (res.ok) {
      closeModal("reset-pwd-modal");
      const alertMain = document.getElementById("admin-alert-user");
      showAlert(alertMain, "🔑 Senha redefinida com sucesso!", "success");
      setTimeout(() => hideAlert(alertMain), 4000);
    } else {
      showAlert(alertEl, data.error || "Erro ao redefinir", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

// ── Instituições ───────────────────────────────────────────────────────────────

async function loadInstitutions() {
  const filter = document.getElementById("inst-filter")?.value || "";
  try {
    const res  = await apiFetch("/admin/institutions");
    const data = await res.json();
    let insts  = data.institutions || [];
    if (filter === "pending")  insts = insts.filter(i => !i.is_verified);
    if (filter === "verified") insts = insts.filter(i => i.is_verified);
    const pending = insts.filter(i => !i.is_verified).length;

    document.getElementById("inst-count-label").textContent =
      `${insts.length} instituição(ões)${pending ? ` · ${pending} pendente(s)` : ""}`;

    const tbody = document.getElementById("inst-table-body");
    if (!insts.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:28px">Nenhuma instituição encontrada.</td></tr>`;
      return;
    }
    tbody.innerHTML = insts.map(i => `
      <tr>
        <td>
          <div style="font-weight:600">${esc(i.name)}</div>
          <div style="font-size:.74rem;color:var(--text-muted)">${esc(i.short_name||"")} · por @${esc(i.creator_name||"?")}</div>
        </td>
        <td style="font-size:.8rem;color:var(--text-muted)">${esc(i.cnpj || "—")}</td>
        <td style="font-size:.82rem">${esc(i.type || "—")}</td>
        <td style="font-size:.82rem">${esc(i.city || "—")}</td>
        <td style="text-align:center">${i.member_count || 0}</td>
        <td>
          ${i.is_verified
            ? `<span class="badge-v">✓ Verificada</span>`
            : `<span class="badge-u">⏳ Pendente</span>`}
        </td>
        <td>
          <div class="action-cell">
            ${i.is_verified
              ? `<button class="btn btn-sm btn-ghost" onclick="verifyInstitution(${i.id},false)">Remover ✓</button>`
              : `<button class="btn btn-sm btn-primary" onclick="verifyInstitution(${i.id},true)">✓ Verificar</button>`}
            <a href="/gl/instituicao/${i.id}" class="btn btn-sm btn-outline" target="_blank">Ver →</a>
            <button class="btn btn-sm btn-danger" onclick="confirmDelete('inst',${i.id},'${esc(i.name).replace(/'/g,"\\'")}')">🗑</button>
          </div>
        </td>
      </tr>`).join("");
  } catch (e) {
    document.getElementById("inst-table-body").innerHTML =
      `<tr><td colspan="7" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

async function verifyInstitution(id, verified) {
  const alertEl = document.getElementById("admin-alert-inst");
  try {
    const res = await apiFetch(`/admin/institutions/${id}/verify`, {
      method: "POST", body: JSON.stringify({ verified }),
    });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, verified ? "✓ Instituição verificada!" : "Verificação removida.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadInstitutions();
    } else {
      showAlert(alertEl, data.error || "Erro", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

async function deleteInstitution(id) {
  const alertEl = document.getElementById("admin-alert-inst");
  try {
    const res  = await apiFetch(`/admin/institutions/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Instituição excluída com sucesso.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadInstitutions();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

// ── Fórum ──────────────────────────────────────────────────────────────────────

function debounceForumSearch() {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => { _forumPage = 1; loadForumPosts(); }, 350);
}

async function loadForumPosts() {
  const search = document.getElementById("forum-search")?.value.trim() || "";
  _forumSearch = search;
  const tbody  = document.getElementById("forum-table-body");
  tbody.innerHTML = `<tr><td colspan="6"><div class="loading-state"><div class="spinner spinner-dark"></div></div></td></tr>`;
  try {
    let url = `/admin/posts?page=${_forumPage}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res  = await apiFetch(url);
    const data = await res.json();
    const posts  = data.posts  || [];
    const total  = data.total  || posts.length;
    document.getElementById("forum-count-label").textContent = `${total} publicação(ões)`;
    renderForumPagination(total, 30);
    if (!posts.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:28px">Nenhum post encontrado.</td></tr>`;
      return;
    }
    tbody.innerHTML = posts.map(p => `
      <tr>
        <td>
          <div style="font-weight:600;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(p.title)}">${esc(p.title)}</div>
          <div style="font-size:.74rem;color:var(--text-muted)">ID #${p.id}</div>
        </td>
        <td><span class="badge-sub" style="background:#f3f4f6;color:#374151;border-color:#e5e7eb">${esc(p.category||"—")}</span></td>
        <td style="font-size:.82rem">@${esc(p.username)}</td>
        <td style="text-align:center">${p.comment_count||0}</td>
        <td style="font-size:.78rem;color:var(--text-muted);white-space:nowrap">${fmtDate(p.created_at)}</td>
        <td>
          <div class="action-cell">
            <a href="/gl/forum/${p.id}" class="btn btn-sm btn-outline" target="_blank">Ver →</a>
            <button class="btn btn-sm btn-danger" onclick="confirmDelete('post',${p.id},'${esc(p.title).replace(/'/g,"\\'")}')">🗑</button>
          </div>
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

function renderForumPagination(total, perPage) {
  const pages = Math.ceil(total / perPage);
  const el = document.getElementById("forum-pagination");
  if (pages <= 1) { el.innerHTML = ""; return; }
  let html = "";
  if (_forumPage > 1) html += `<button class="page-btn" onclick="_forumPage=${_forumPage-1};loadForumPosts()">‹</button>`;
  for (let i = 1; i <= pages; i++) {
    if (i === 1 || i === pages || Math.abs(i - _forumPage) <= 1) {
      html += `<button class="page-btn${i===_forumPage?' active':''}" onclick="_forumPage=${i};loadForumPosts()">${i}</button>`;
    } else if (Math.abs(i - _forumPage) === 2) {
      html += `<span style="padding:0 4px;color:var(--text-muted)">…</span>`;
    }
  }
  if (_forumPage < pages) html += `<button class="page-btn" onclick="_forumPage=${_forumPage+1};loadForumPosts()">›</button>`;
  el.innerHTML = html;
}

async function deletePost(id) {
  const alertEl = document.getElementById("admin-alert-forum");
  try {
    const res  = await apiFetch(`/admin/posts/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Post excluído com sucesso.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadForumPosts();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

// ── Pré-publicações ────────────────────────────────────────────────────────────

const STATUS_LABELS = { draft:"Rascunho", submitted:"Submetido", under_review:"Em revisão", published:"Publicado" };

async function loadAdminPreprints() {
  const type   = document.getElementById("preprint-filter-type")?.value || "";
  const status = document.getElementById("preprint-filter-status")?.value || "";
  const tbody  = document.getElementById("preprint-table-body");
  tbody.innerHTML = `<tr><td colspan="7"><div class="loading-state"><div class="spinner spinner-dark"></div></div></td></tr>`;
  try {
    let url = "/admin/preprints?page=1";
    const res  = await apiFetch(url);
    const data = await res.json();
    let preprints = data.preprints || [];
    if (type)   preprints = preprints.filter(p => p.type === type);
    if (status) preprints = preprints.filter(p => p.status === status);

    document.getElementById("preprint-count-label").textContent =
      `${preprints.length} pré-publicação(ões)`;

    if (!preprints.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:28px">Nenhuma pré-publicação encontrada.</td></tr>`;
      return;
    }

    const statusBadge = s => {
      const cls = { draft:"badge-draft", submitted:"badge-sub", under_review:"badge-rev", published:"badge-pub" };
      return `<span class="${cls[s]||'badge-draft'}">${STATUS_LABELS[s]||s}</span>`;
    };

    tbody.innerHTML = preprints.map(p => `
      <tr>
        <td>
          <div style="font-weight:600;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(p.title)}">${esc(p.title)}</div>
          <div style="font-size:.74rem;color:var(--text-muted)">ID #${p.id}</div>
        </td>
        <td style="font-size:.82rem">${esc(p.type||"—")}</td>
        <td style="font-size:.82rem">@${esc(p.username)}</td>
        <td style="text-align:center">${p.review_count||0}</td>
        <td>${statusBadge(p.status)}</td>
        <td style="font-size:.78rem;color:var(--text-muted);white-space:nowrap">${fmtDate(p.created_at)}</td>
        <td>
          <div class="action-cell">
            <a href="/gl/preprint/${p.id}" class="btn btn-sm btn-outline" target="_blank">Ver →</a>
            <button class="btn btn-sm btn-ghost" onclick="openStatusModal(${p.id},'${esc(p.title).replace(/'/g,"\\'")}','${p.status}')">🔄 Status</button>
            <button class="btn btn-sm btn-danger" onclick="confirmDelete('preprint',${p.id},'${esc(p.title).replace(/'/g,"\\'")}')">🗑</button>
          </div>
        </td>
      </tr>`).join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

async function adminDeletePreprint(id) {
  const alertEl = document.getElementById("admin-alert-preprint");
  try {
    const res  = await apiFetch(`/admin/preprints/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Pré-publicação excluída.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadAdminPreprints();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

function openStatusModal(id, title, currentStatus) {
  _statusPreprintId = id;
  document.getElementById("status-modal-label").textContent = `"${title}"`;
  document.querySelectorAll('input[name="new-status"]').forEach(r => {
    r.checked = r.value === currentStatus;
  });
  hideAlert(document.getElementById("status-modal-alert"));
  document.getElementById("status-modal").style.display = "flex";
}

async function confirmStatusChange() {
  const alertEl = document.getElementById("status-modal-alert");
  const selected = document.querySelector('input[name="new-status"]:checked');
  if (!selected) { showAlert(alertEl, "Selecione um status.", "error"); return; }
  try {
    const res  = await apiFetch(`/admin/preprints/${_statusPreprintId}/status`, {
      method: "POST", body: JSON.stringify({ status: selected.value }),
    });
    const data = await res.json();
    if (res.ok) {
      closeModal("status-modal");
      const alertMain = document.getElementById("admin-alert-preprint");
      showAlert(alertMain, `Status alterado para "${STATUS_LABELS[selected.value]}" com sucesso.`, "success");
      setTimeout(() => hideAlert(alertMain), 4000);
      loadAdminPreprints();
    } else {
      showAlert(alertEl, data.error || "Erro", "error");
    }
  } catch { showAlert(alertEl, "Erro de conexão", "error"); }
}

// ── Confirm delete modal ────────────────────────────────────────────────────────

function confirmDelete(type, id, label) {
  const titles = {
    inst:     "🏛️ Excluir Instituição",
    post:     "📋 Excluir Post do Fórum",
    user:     "👤 Excluir Conta de Usuário",
    preprint: "🔬 Excluir Pré-publicação"
  };
  const warnings = {
    user: "Isso vai remover todos os dados do usuário: posts, comentários, buscas, pré-publicações e mensagens.",
    inst: "Isso vai remover todos os membros e parcerias desta instituição.",
    post: "Isso vai remover todos os comentários deste post.",
    preprint: "Isso vai remover todas as revisões desta pré-publicação."
  };
  document.getElementById("confirm-title").textContent = titles[type] || "Confirmar exclusão";
  document.getElementById("confirm-body").textContent  =
    `Tem certeza que deseja excluir "${label}"? ${warnings[type]||""} Esta ação não pode ser desfeita.`;

  document.getElementById("confirm-ok-btn").onclick = () => {
    closeModal("confirm-modal");
    if (type === "inst")     deleteInstitution(id);
    else if (type === "user")     deleteUser(id);
    else if (type === "preprint") adminDeletePreprint(id);
    else                          deletePost(id);
  };
  document.getElementById("confirm-modal").style.display = "flex";
}

// ── Modal helpers ──────────────────────────────────────────────────────────────

function closeModal(id) {
  document.getElementById(id).style.display = "none";
}
document.addEventListener("click", e => {
  ["confirm-modal","reset-pwd-modal","status-modal"].forEach(id => {
    const modal = document.getElementById(id);
    if (modal && e.target === modal) closeModal(id);
  });
});

// ── Helpers ────────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function fmtDate(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("pt-BR",{day:"2-digit",month:"short",year:"numeric"});
}
