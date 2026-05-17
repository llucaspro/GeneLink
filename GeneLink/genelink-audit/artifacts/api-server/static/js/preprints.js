// ── Pré-publicações (Preprints) ───────────────────────────────────────────────

const PREPRINT_TYPES = ["Hipótese", "Artigo Preliminar", "Revisão", "Experimento"];
const STATUS_LABELS = {
  draft: "Rascunho",
  submitted: "Submetido",
  under_review: "Em revisão",
  published: "Publicado",
};
const STATUS_COLORS = {
  draft: "badge-unverified",
  submitted: "badge-unverified",
  under_review: "badge-unverified",
  published: "badge-verified",
};

let currentFilter = { type: "", status: "submitted" };
let myPreprintsCache = [];

document.addEventListener("DOMContentLoaded", async () => {
  requireAuth();
  injectNavbar("/gl/preprints");
  setupFilters();
  await loadPreprints();
  await loadMyPreprints();
});

// ── Filters ───────────────────────────────────────────────────────────────────

function setupFilters() {
  const typeSelect = document.getElementById("filter-type");
  const statusSelect = document.getElementById("filter-status");
  if (typeSelect) typeSelect.addEventListener("change", () => { currentFilter.type = typeSelect.value; loadPreprints(); });
  if (statusSelect) statusSelect.addEventListener("change", () => { currentFilter.status = statusSelect.value; loadPreprints(); });
}

// ── Load preprints list ───────────────────────────────────────────────────────

async function loadPreprints() {
  const container = document.getElementById("preprints-list");
  if (!container) return;
  container.innerHTML = `<div class="loading-state"><div class="spinner spinner-dark"></div><p>Carregando pré-publicações...</p></div>`;

  try {
    const params = new URLSearchParams();
    if (currentFilter.type) params.set("type", currentFilter.type);
    if (currentFilter.status) params.set("status", currentFilter.status);

    const res = await apiFetch(`/preprints?${params}`);
    const data = await res.json();
    const preprints = data.preprints || [];

    const totalEl = document.getElementById("total-count");
    if (totalEl) totalEl.textContent = `${data.total || preprints.length} resultado(s)`;

    if (!preprints.length) {
      container.innerHTML = `
        <div class="empty-state" style="text-align:center;padding:60px 20px;color:var(--text-muted)">
          <div style="font-size:3rem;margin-bottom:12px">🔬</div>
          <h3>Nenhuma pré-publicação encontrada</h3>
          <p style="margin-top:8px">Seja o primeiro a compartilhar sua pesquisa!</p>
        </div>`;
      return;
    }

    container.innerHTML = preprints.map(p => renderPreprintCard(p)).join("");
  } catch (e) {
    container.innerHTML = `<div style="color:var(--danger);padding:20px">${e.message}</div>`;
  }
}

function renderPreprintCard(p) {
  const abstract = (p.abstract || "").slice(0, 200) + ((p.abstract || "").length > 200 ? "..." : "");
  const keywords = p.keywords ? p.keywords.split(",").map(k => `<span class="keyword-tag">${esc(k.trim())}</span>`).join("") : "";
  return `
    <div class="preprint-card card" onclick="window.location='/gl/preprint/${p.id}'" style="cursor:pointer;margin-bottom:16px">
      <div class="card-body" style="padding:20px 24px">
        <div style="display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:10px">
          <span class="type-badge type-${slugify(p.type)}">${esc(p.type)}</span>
          <span class="${STATUS_COLORS[p.status] || 'badge-unverified'}" style="border-radius:20px;padding:2px 10px;font-size:.72rem;font-weight:700">${STATUS_LABELS[p.status] || p.status}</span>
        </div>
        <h3 style="font-size:1.05rem;font-weight:700;margin-bottom:8px;line-height:1.4">${esc(p.title)}</h3>
        <p style="font-size:.87rem;color:var(--text-muted);line-height:1.6;margin-bottom:12px">${esc(abstract)}</p>
        ${keywords ? `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px">${keywords}</div>` : ""}
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
          <div style="display:flex;align-items:center;gap:8px">
            <div class="avatar avatar-sm">${esc(p.author_initials || "?")}</div>
            <div>
              <div style="font-size:.83rem;font-weight:600">${esc(p.author_username)}</div>
              ${p.author_institution ? `<div style="font-size:.74rem;color:var(--text-muted)">${esc(p.author_institution)}</div>` : ""}
            </div>
          </div>
          <div style="display:flex;gap:16px;font-size:.78rem;color:var(--text-muted)">
            <span>💬 ${p.review_count || 0} revisão(ões)</span>
            <span>${timeAgo(p.created_at)}</span>
          </div>
        </div>
      </div>
    </div>`;
}

// ── My preprints ──────────────────────────────────────────────────────────────

async function loadMyPreprints() {
  const container = document.getElementById("my-preprints-list");
  if (!container) return;
  try {
    const res = await apiFetch("/preprints/mine");
    const data = await res.json();
    myPreprintsCache = data.preprints || [];
    if (!myPreprintsCache.length) {
      container.innerHTML = `<p style="color:var(--text-muted);font-size:.87rem;text-align:center;padding:20px 0">Você ainda não publicou nada.</p>`;
      return;
    }
    container.innerHTML = myPreprintsCache.map(p => `
      <div class="my-preprint-item" style="border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:10px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
          <a href="/gl/preprint/${p.id}" style="font-weight:600;font-size:.9rem;color:var(--primary);text-decoration:none">${esc(p.title)}</a>
          <span class="${STATUS_COLORS[p.status] || 'badge-unverified'}" style="border-radius:20px;padding:2px 8px;font-size:.7rem;font-weight:700;white-space:nowrap">${STATUS_LABELS[p.status] || p.status}</span>
        </div>
        <div style="display:flex;gap:10px;margin-top:8px;flex-wrap:wrap">
          <span style="font-size:.75rem;color:var(--text-muted)">${esc(p.type)}</span>
          <span style="font-size:.75rem;color:var(--text-muted)">💬 ${p.review_count || 0}</span>
          <span style="font-size:.75rem;color:var(--text-muted)">${timeAgo(p.created_at)}</span>
        </div>
        <div style="display:flex;gap:6px;margin-top:10px">
          <a href="/gl/preprint/${p.id}" class="btn btn-sm btn-outline">Ver</a>
          <button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteMyPreprint(${p.id})">Excluir</button>
        </div>
      </div>
    `).join("");
  } catch (e) {
    container.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`;
  }
}

async function deleteMyPreprint(id) {
  if (!confirm("Excluir esta pré-publicação? Esta ação não pode ser desfeita.")) return;
  try {
    const res = await apiFetch(`/preprints/${id}`, { method: "DELETE" });
    if (res.ok) {
      await loadMyPreprints();
      await loadPreprints();
    } else {
      const d = await res.json();
      alert(d.error || "Erro ao excluir");
    }
  } catch {
    alert("Erro de conexão");
  }
}

// ── Create preprint form ──────────────────────────────────────────────────────

function openCreateModal() {
  document.getElementById("create-modal").style.display = "flex";
  document.getElementById("create-form").reset();
  document.getElementById("create-alert").className = "alert";
  populateTypeSelect();
}

function closeCreateModal() {
  document.getElementById("create-modal").style.display = "none";
}

function populateTypeSelect() {
  const sel = document.getElementById("new-type");
  if (!sel || sel.options.length > 1) return;
  PREPRINT_TYPES.forEach(t => {
    const opt = document.createElement("option");
    opt.value = t; opt.textContent = t;
    sel.appendChild(opt);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("create-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl = document.getElementById("create-alert");
    const btn = document.getElementById("create-submit-btn");
    const title = document.getElementById("new-title").value.trim();
    const abstract = document.getElementById("new-abstract").value.trim();
    const content = document.getElementById("new-content").value.trim();
    const type = document.getElementById("new-type").value;
    const keywords = document.getElementById("new-keywords").value.trim();
    const status = document.getElementById("new-status").value;

    btn.disabled = true; btn.textContent = "Publicando...";
    try {
      const res = await apiFetch("/preprints", {
        method: "POST",
        body: JSON.stringify({ title, abstract, content, type, keywords, status }),
      });
      const data = await res.json();
      if (res.ok) {
        closeCreateModal();
        await loadPreprints();
        await loadMyPreprints();
      } else {
        showAlert(alertEl, data.error || "Erro ao publicar", "error");
      }
    } catch {
      showAlert(alertEl, "Erro de conexão", "error");
    } finally {
      btn.disabled = false; btn.textContent = "Publicar";
    }
  });
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function slugify(s) {
  return (s || "").toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
}
