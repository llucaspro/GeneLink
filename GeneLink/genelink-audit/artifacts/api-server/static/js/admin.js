// ── Admin Panel ───────────────────────────────────────────────────────────────

let _confirmCallback = null;

document.addEventListener("DOMContentLoaded", async () => {
  requireAuth();
  injectNavbar("/gl/admin");
  await checkAdminAccess();
});

async function checkAdminAccess() {
  try {
    const res = await apiFetch("/admin/stats");
    if (res.status === 403) {
      document.getElementById("access-denied").style.display = "block";
      return;
    }
    document.getElementById("admin-content").style.display = "block";
    const stats = await res.json();
    document.getElementById("s-users").textContent    = stats.users ?? "—";
    document.getElementById("s-insts").textContent    = stats.institutions ?? "—";
    document.getElementById("s-verified").textContent = stats.verified_institutions ?? "—";
    document.getElementById("s-posts").textContent    = stats.posts ?? "—";
    document.getElementById("s-searches").textContent = stats.gene_searches ?? "—";
    loadInstitutions();
  } catch {
    document.getElementById("access-denied").style.display = "block";
  }
}

// ── Tab switching ─────────────────────────────────────────────────────────────

function switchTab(name) {
  const tabs = ["institutions", "users", "forum", "preprints"];
  document.querySelectorAll(".tab-link").forEach((el, i) => {
    el.classList.toggle("active", tabs[i] === name);
  });
  tabs.forEach(t => {
    const panel = document.getElementById("tab-" + t);
    if (panel) panel.classList.toggle("active", t === name);
  });
  if (name === "users")        loadUsers();
  if (name === "institutions") loadInstitutions();
  if (name === "forum")        loadForumPosts();
  if (name === "preprints")    loadAdminPreprints();
}

// ── Institutions ──────────────────────────────────────────────────────────────

async function loadInstitutions() {
  try {
    const res = await apiFetch("/admin/institutions");
    const data = await res.json();
    const insts = data.institutions || [];
    document.getElementById("inst-count-label").textContent =
      insts.length + " instituição(ões)";
    const tbody = document.getElementById("inst-table-body");
    if (!insts.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">Nenhuma instituição cadastrada</td></tr>`;
      return;
    }
    tbody.innerHTML = insts.map(i => `
      <tr>
        <td>
          <div style="font-weight:600">${esc(i.name)}</div>
          <div style="font-size:.75rem;color:var(--text-muted)">${esc(i.short_name || "")} ${i.city ? "· " + esc(i.city) : ""}</div>
        </td>
        <td style="font-size:.82rem;color:var(--text-muted)">${esc(i.cnpj || "—")}</td>
        <td style="font-size:.82rem">${esc(i.type || "—")}</td>
        <td style="text-align:center">${i.member_count || 0}</td>
        <td>
          ${i.is_verified
            ? `<span class="badge-verified">✓ Verificada</span>`
            : `<span class="badge-unverified">Pendente</span>`}
        </td>
        <td>
          <div class="action-cell">
            ${i.is_verified
              ? `<button class="btn btn-sm btn-ghost" onclick="verifyInstitution(${i.id}, false)">Remover verificação</button>`
              : `<button class="btn btn-sm btn-primary" onclick="verifyInstitution(${i.id}, true)">Verificar ✓</button>`}
            <a href="/gl/instituicao/${i.id}" class="btn btn-sm btn-outline" target="_blank">Ver</a>
            <button class="btn btn-sm btn-danger" onclick="confirmDelete('inst', ${i.id}, '${esc(i.name).replace(/'/g,"\\'")}')">🗑 Excluir</button>
          </div>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    document.getElementById("inst-table-body").innerHTML =
      `<tr><td colspan="6" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

async function verifyInstitution(id, verified) {
  const alertEl = document.getElementById("admin-alert-inst");
  try {
    const res = await apiFetch(`/admin/institutions/${id}/verify`, {
      method: "POST",
      body: JSON.stringify({ verified }),
    });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, verified ? "Instituição verificada com sucesso!" : "Verificação removida.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadInstitutions();
    } else {
      showAlert(alertEl, data.error || "Erro", "error");
    }
  } catch {
    showAlert(alertEl, "Erro de conexão", "error");
  }
}

async function deleteInstitution(id) {
  const alertEl = document.getElementById("admin-alert-inst");
  try {
    const res = await apiFetch(`/admin/institutions/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Instituição excluída com sucesso.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadInstitutions();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir", "error");
    }
  } catch {
    showAlert(alertEl, "Erro de conexão", "error");
  }
}

// ── Users ─────────────────────────────────────────────────────────────────────

async function loadUsers() {
  try {
    const res = await apiFetch("/admin/users");
    const data = await res.json();
    const users = data.users || [];
    document.getElementById("user-count-label").textContent = users.length + " usuário(s)";
    const tbody = document.getElementById("user-table-body");
    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">Nenhum usuário</td></tr>`;
      return;
    }
    tbody.innerHTML = users.map(u => `
      <tr>
        <td>
          <div style="font-weight:600">${esc(u.username)}</div>
          <div style="font-size:.75rem;color:var(--text-muted)">${esc(u.full_name || "")}</div>
        </td>
        <td style="font-size:.82rem;color:var(--text-muted)">${esc(u.email)}</td>
        <td style="font-size:.82rem">${esc(u.institution || "—")}</td>
        <td style="text-align:center">
          ${u.is_verified ? `<span class="badge-verified">✓</span>` : `<span class="badge-unverified">—</span>`}
        </td>
        <td style="text-align:center">
          ${u.is_admin ? `<span class="badge-verified">Admin</span>` : "—"}
        </td>
        <td>
          <div class="action-cell">
            ${u.is_verified
              ? `<button class="btn btn-sm btn-ghost" onclick="verifyUser(${u.id}, false)">Remover</button>`
              : `<button class="btn btn-sm btn-primary" onclick="verifyUser(${u.id}, true)">Verificar</button>`}
            ${u.is_admin
              ? `<button class="btn btn-sm btn-ghost" onclick="setAdmin(${u.id}, false)">Remover Admin</button>`
              : `<button class="btn btn-sm btn-outline" onclick="setAdmin(${u.id}, true)">Tornar Admin</button>`}
            <button class="btn btn-sm btn-danger" onclick="confirmDelete('user', ${u.id}, '${esc(u.username).replace(/'/g,"\\'")}')">🗑 Excluir</button>
          </div>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    document.getElementById("user-table-body").innerHTML =
      `<tr><td colspan="6" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

async function verifyUser(id, verified) {
  const alertEl = document.getElementById("admin-alert-user");
  try {
    const res = await apiFetch(`/admin/users/${id}/verify`, {
      method: "POST",
      body: JSON.stringify({ verified }),
    });
    if (res.ok) {
      showAlert(alertEl, verified ? "Usuário verificado!" : "Verificação removida.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadUsers();
    } else {
      const d = await res.json();
      showAlert(alertEl, d.error || "Erro", "error");
    }
  } catch {
    showAlert(alertEl, "Erro de conexão", "error");
  }
}

async function setAdmin(id, isAdmin) {
  const alertEl = document.getElementById("admin-alert-user");
  try {
    const res = await apiFetch(`/admin/users/${id}/admin`, {
      method: "POST",
      body: JSON.stringify({ admin: isAdmin }),
    });
    if (res.ok) {
      showAlert(alertEl, isAdmin ? "Admin concedido!" : "Admin removido.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadUsers();
    } else {
      const d = await res.json();
      showAlert(alertEl, d.error || "Erro", "error");
    }
  } catch {
    showAlert(alertEl, "Erro de conexão", "error");
  }
}

async function deleteUser(id) {
  const alertEl = document.getElementById("admin-alert-user");
  try {
    const res = await apiFetch(`/admin/users/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Conta excluída com sucesso.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadUsers();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir conta", "error");
    }
  } catch {
    showAlert(alertEl, "Erro de conexão", "error");
  }
}

// ── Forum Posts ───────────────────────────────────────────────────────────────

async function loadForumPosts() {
  try {
    const res = await apiFetch("/admin/posts");
    const data = await res.json();
    const posts = data.posts || [];
    document.getElementById("forum-count-label").textContent =
      (data.total || posts.length) + " publicação(ões)";
    const tbody = document.getElementById("forum-table-body");
    if (!posts.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">Nenhuma publicação no fórum</td></tr>`;
      return;
    }
    tbody.innerHTML = posts.map(p => `
      <tr>
        <td>
          <div style="font-weight:600;max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
               title="${esc(p.title)}">${esc(p.title)}</div>
        </td>
        <td><span class="badge badge-muted">${esc(p.category || "—")}</span></td>
        <td style="font-size:.82rem">${esc(p.username)}</td>
        <td style="text-align:center;font-size:.85rem">${p.comment_count || 0}</td>
        <td style="font-size:.78rem;color:var(--text-muted)">${fmtDate(p.created_at)}</td>
        <td>
          <div class="action-cell">
            <a href="/gl/forum/${p.id}" class="btn btn-sm btn-outline" target="_blank">Ver →</a>
            <button class="btn btn-sm btn-danger" onclick="confirmDelete('post', ${p.id}, '${esc(p.title).replace(/'/g,"\\'")}')">🗑 Excluir</button>
          </div>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    document.getElementById("forum-table-body").innerHTML =
      `<tr><td colspan="6" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

async function deletePost(id) {
  const alertEl = document.getElementById("admin-alert-forum");
  try {
    const res = await apiFetch(`/admin/posts/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Publicação excluída com sucesso.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadForumPosts();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir", "error");
    }
  } catch {
    showAlert(alertEl, "Erro de conexão", "error");
  }
}

// ── Admin Preprints ───────────────────────────────────────────────────────────

async function loadAdminPreprints() {
  try {
    const res = await apiFetch("/admin/preprints");
    const data = await res.json();
    const preprints = data.preprints || [];
    document.getElementById("preprint-count-label").textContent =
      (data.total || preprints.length) + " pré-publicação(ões)";
    const tbody = document.getElementById("preprint-table-body");
    if (!preprints.length) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:24px">Nenhuma pré-publicação</td></tr>`;
      return;
    }
    const statusLabel = { draft: "Rascunho", submitted: "Submetido", under_review: "Em revisão", published: "Publicado" };
    tbody.innerHTML = preprints.map(p => `
      <tr>
        <td>
          <div style="font-weight:600;max-width:240px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
               title="${esc(p.title)}">${esc(p.title)}</div>
        </td>
        <td><span class="badge badge-muted">${esc(p.type || "—")}</span></td>
        <td style="font-size:.82rem">${esc(p.username)}</td>
        <td style="text-align:center">${p.review_count || 0}</td>
        <td><span class="badge-${p.status === 'published' ? 'verified' : 'unverified'}">${statusLabel[p.status] || p.status}</span></td>
        <td>
          <div class="action-cell">
            <a href="/gl/preprint/${p.id}" class="btn btn-sm btn-outline" target="_blank">Ver →</a>
            <button class="btn btn-sm btn-danger" onclick="confirmDelete('preprint', ${p.id}, '${esc(p.title).replace(/'/g,"\\'")}')">🗑 Excluir</button>
          </div>
        </td>
      </tr>
    `).join("");
  } catch (e) {
    document.getElementById("preprint-table-body").innerHTML =
      `<tr><td colspan="6" style="color:var(--danger)">${e.message}</td></tr>`;
  }
}

async function adminDeletePreprint(id) {
  const alertEl = document.getElementById("admin-alert-preprint");
  try {
    const res = await apiFetch(`/admin/preprints/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showAlert(alertEl, "Pré-publicação excluída com sucesso.", "success");
      setTimeout(() => hideAlert(alertEl), 3000);
      loadAdminPreprints();
    } else {
      showAlert(alertEl, data.error || "Erro ao excluir", "error");
    }
  } catch {
    showAlert(alertEl, "Erro de conexão", "error");
  }
}

// ── Confirm modal ─────────────────────────────────────────────────────────────

function confirmDelete(type, id, label) {
  const modal = document.getElementById("confirm-modal");
  const titles = { inst: "Excluir Instituição", post: "Excluir Publicação", user: "Excluir Conta de Usuário", preprint: "Excluir Pré-publicação" };
  document.getElementById("confirm-title").textContent = titles[type] || "Confirmar exclusão";
  document.getElementById("confirm-body").textContent =
    `Tem certeza que deseja excluir "${label}"? Esta ação removerá todos os dados relacionados e não pode ser desfeita.`;

  document.getElementById("confirm-ok-btn").onclick = () => {
    closeConfirm();
    if (type === "inst") deleteInstitution(id);
    else if (type === "user") deleteUser(id);
    else if (type === "preprint") adminDeletePreprint(id);
    else deletePost(id);
  };

  modal.style.display = "flex";
}

function closeConfirm() {
  document.getElementById("confirm-modal").style.display = "none";
}

// Close modal on backdrop click
document.addEventListener("click", e => {
  const modal = document.getElementById("confirm-modal");
  if (modal && e.target === modal) closeConfirm();
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtDate(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}
