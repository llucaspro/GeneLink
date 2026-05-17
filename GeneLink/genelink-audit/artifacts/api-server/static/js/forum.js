let currentPage = 1;
let currentCategory = "";

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  injectNavbar("/forum");
  await loadCategories();
  await loadPosts();

  document.getElementById("filter-category").addEventListener("change", async (e) => {
    currentCategory = e.target.value;
    currentPage = 1;
    await loadPosts();
  });
});

async function loadCategories() {
  try {
    const res = await fetch("/gl/api/categories");
    const cats = await res.json();
    const sel = document.getElementById("filter-category");
    cats.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      sel.appendChild(opt);
    });
  } catch {}
}

async function loadPosts() {
  const el = document.getElementById("posts-list");
  el.innerHTML = `<div class="loading-state"><div class="spinner spinner-dark"></div></div>`;
  try {
    const qs = new URLSearchParams({ page: currentPage });
    if (currentCategory) qs.set("category", currentCategory);
    const res = await fetch(`/gl/api/posts?${qs}`);
    const data = await res.json();
    const posts = data.posts || [];
    if (!posts.length) {
      el.innerHTML = `<div class="empty-state">
        <div class="empty-state-icon">📋</div>
        <h3>Nenhuma publicação ainda</h3>
        <p style="font-size:.85rem;margin-top:8px">Seja o primeiro a iniciar uma discussão nesta comunidade.</p>
      </div>`;
      return;
    }
    el.innerHTML = posts.map((p) => `
      <div class="post-item" onclick="window.location='/forum/${p.id}'">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
          <div>
            <div class="post-title">${escHtml(p.title)}</div>
            <div class="post-excerpt">${escHtml(p.content)}</div>
            <div class="post-meta">
              <span class="badge badge-primary">${escHtml(p.category)}</span>
              <span class="user-chip">
                <span class="avatar-sm">${escHtml(p.avatar_initials || "?")}</span>
                <strong>${escHtml(p.username)}</strong>
                ${p.institution ? `<span style="color:var(--text-light)">· ${escHtml(p.institution)}</span>` : ""}
              </span>
              <span>${timeAgo(p.created_at)}</span>
            </div>
          </div>
          <div style="text-align:right;flex-shrink:0">
            <div style="font-size:.85rem;font-weight:600;color:var(--text)">${p.comment_count}</div>
            <div style="font-size:.75rem;color:var(--text-muted)">comentário${p.comment_count !== 1 ? "s" : ""}</div>
          </div>
        </div>
      </div>`).join("");
  } catch {
    el.innerHTML = `<p style="padding:20px;color:var(--text-muted)">Falha ao carregar publicações.</p>`;
  }
}

function openNewPostModal() {
  document.getElementById("new-post-modal").style.display = "flex";
}
function closeNewPostModal() {
  document.getElementById("new-post-modal").style.display = "none";
  document.getElementById("new-post-form").reset();
  hideAlert(document.getElementById("post-alert"));
}

async function loadModalCategories() {
  try {
    const res = await fetch("/gl/api/categories");
    const cats = await res.json();
    const sel = document.getElementById("post-category");
    sel.innerHTML = cats.map((c) => `<option value="${c}">${c}</option>`).join("");
  } catch {}
}

document.addEventListener("DOMContentLoaded", () => {
  loadModalCategories();
  document.getElementById("new-post-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl = document.getElementById("post-alert");
    const btn = document.getElementById("submit-post-btn");
    const title = document.getElementById("post-title").value.trim();
    const content = document.getElementById("post-content").value.trim();
    const category = document.getElementById("post-category").value;

    if (!title || !content) {
      showAlert(alertEl, "Título e conteúdo são obrigatórios.", "error");
      return;
    }

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Publicando…`;
    hideAlert(alertEl);

    try {
      const res = await apiFetch("/posts", {
        method: "POST",
        body: JSON.stringify({ title, content, category }),
      });
      const data = await res.json();
      if (!res.ok) {
        showAlert(alertEl, data.error || "Falha ao criar publicação", "error");
        return;
      }
      closeNewPostModal();
      window.location.href = `/forum/${data.id}`;
    } catch {
      showAlert(alertEl, "Requisição falhou. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Publicar";
    }
  });

  window.addEventListener("click", (e) => {
    if (e.target === document.getElementById("new-post-modal")) closeNewPostModal();
  });
});

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
