const postId = window.location.pathname.split("/").pop();

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  injectNavbar("/forum");
  await loadPost();
});

async function loadPost() {
  const el = document.getElementById("post-container");
  try {
    const res = await fetch(`/gl/api/posts/${postId}`);
    if (res.status === 404) {
      el.innerHTML = `<div class="empty-state"><h3>Publicação não encontrada</h3></div>`;
      return;
    }
    const post = await res.json();
    const user = getUser();
    const isAuthor = user && user.id === post.author_id;

    document.title = `${post.title} · Fórum GeneLink`;

    document.getElementById("post-title").textContent = post.title;
    document.getElementById("post-author-initials").textContent = post.avatar_initials || "?";
    document.getElementById("post-author").textContent = post.username;
    document.getElementById("post-institution").textContent = post.institution || "";
    document.getElementById("post-date").textContent = formatDateTime(post.created_at);
    document.getElementById("post-category").textContent = post.category;
    document.getElementById("post-content-body").textContent = post.content;

    if (isAuthor) {
      document.getElementById("delete-btn").style.display = "inline-flex";
    }

    renderComments(post.comments || []);
  } catch {
    el.innerHTML = `<p style="color:var(--danger)">Falha ao carregar publicação.</p>`;
  }
}

function renderComments(comments) {
  const el = document.getElementById("comments-list");
  document.getElementById("comment-count").textContent =
    `${comments.length} comentário${comments.length !== 1 ? "s" : ""}`;
  if (!comments.length) {
    el.innerHTML = `<div class="empty-state" style="padding:32px"><h3>Nenhum comentário ainda</h3><p style="font-size:.85rem;margin-top:6px">Seja o primeiro a comentar.</p></div>`;
    return;
  }
  el.innerHTML = comments.map((c) => `
    <div style="padding:14px 20px;border-bottom:1px solid var(--border);display:flex;gap:12px">
      <div class="avatar-sm" style="width:32px;height:32px;font-size:.8rem;flex-shrink:0">${escHtml(c.avatar_initials || "?")}</div>
      <div style="flex:1">
        <div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">
          <strong style="font-size:.875rem">${escHtml(c.username)}</strong>
          ${c.institution ? `<span style="font-size:.78rem;color:var(--text-muted)">${escHtml(c.institution)}</span>` : ""}
          <span style="font-size:.78rem;color:var(--text-light);margin-left:auto">${timeAgo(c.created_at)}</span>
        </div>
        <div style="font-size:.9rem;line-height:1.6;white-space:pre-wrap">${escHtml(c.content)}</div>
      </div>
    </div>`).join("");
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("comment-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl = document.getElementById("comment-alert");
    const btn = document.getElementById("submit-comment-btn");
    const content = document.getElementById("comment-content").value.trim();
    if (!content) { showAlert(alertEl, "O comentário não pode estar vazio.", "error"); return; }

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Publicando…`;
    hideAlert(alertEl);

    try {
      const res = await apiFetch(`/posts/${postId}/comments`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      const data = await res.json();
      if (!res.ok) { showAlert(alertEl, data.error || "Falha ao publicar comentário", "error"); return; }
      document.getElementById("comment-content").value = "";
      await loadPost();
    } catch {
      showAlert(alertEl, "Requisição falhou.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Publicar Comentário";
    }
  });
});

async function deletePost() {
  if (!confirm("Tem certeza que deseja excluir esta publicação? Esta ação não pode ser desfeita.")) return;
  try {
    const res = await apiFetch(`/posts/${postId}`, { method: "DELETE" });
    if (res.ok) window.location.href = "/gl/forum";
    else {
      const d = await res.json();
      alert(d.error || "Falha ao excluir");
    }
  } catch { alert("Requisição de exclusão falhou."); }
}

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
