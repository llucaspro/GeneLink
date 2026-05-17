let searchTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  requireAuth();
  injectNavbar("/institucional");
  loadInstitutions();
});

function onSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadInstitutions, 350);
}

async function loadInstitutions() {
  const q = document.getElementById("search-input").value.trim();
  const verified = document.getElementById("verified-filter").checked ? "1" : "0";
  const el = document.getElementById("inst-list");
  const empty = document.getElementById("empty-state");
  el.innerHTML = `<div class="loading-state"><div class="spinner spinner-dark"></div></div>`;
  empty.style.display = "none";

  try {
    const params = new URLSearchParams({ page: 1, verified });
    if (q) params.set("q", q);
    const res = await apiFetch(`/institutions?${params}`);
    const data = await res.json();
    const insts = data.institutions || [];
    document.getElementById("total-label").textContent = `${data.total || 0} resultado(s)`;

    if (!insts.length) {
      el.innerHTML = "";
      empty.style.display = "block";
      return;
    }

    el.innerHTML = insts.map(i => renderInstCard(i)).join("");
  } catch (e) {
    el.innerHTML = `<div style="color:var(--danger);padding:12px">Erro ao carregar: ${e.message}</div>`;
  }
}

function renderInstCard(inst) {
  const verifiedBadge = inst.is_verified
    ? `<span class="verified-seal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Verificada</span>`
    : "";
  const loc = [inst.city, inst.state].filter(Boolean).join(", ");
  return `
    <div class="inst-card">
      <div class="inst-logo">${inst.logo_initials || inst.name.slice(0, 2).toUpperCase()}</div>
      <div class="inst-name">
        ${inst.name}
        ${verifiedBadge}
      </div>
      <div class="inst-meta">
        <span class="type-badge">${inst.type || "Instituição"}</span>
        ${loc ? " · " + loc : ""}
      </div>
      <div class="inst-desc">${inst.description || "Plataforma de pesquisa científica."}</div>
      <div class="inst-footer">
        <span style="font-size:.78rem;color:var(--text-muted)">${inst.member_count || 0} membro(s)</span>
        <a href="/gl/instituicao/${inst.id}" class="btn btn-sm btn-outline">Ver →</a>
      </div>
    </div>
  `;
}

function openModal() {
  document.getElementById("modal-overlay").classList.add("open");
}

function closeModal(e) {
  if (!e || e.target === document.getElementById("modal-overlay") || e.currentTarget === document.querySelector("button[onclick='closeModal()']")) {
    document.getElementById("modal-overlay").classList.remove("open");
  }
}

async function submitInstitution(e) {
  e.preventDefault();
  const alertEl = document.getElementById("modal-alert");
  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> Cadastrando…`;
  hideAlert(alertEl);

  const payload = {
    name: document.getElementById("inst-name").value.trim(),
    short_name: document.getElementById("inst-short").value.trim(),
    type: document.getElementById("inst-type").value,
    cnpj: document.getElementById("inst-cnpj").value.trim(),
    city: document.getElementById("inst-city").value.trim(),
    state: document.getElementById("inst-state").value.trim(),
    website: document.getElementById("inst-website").value.trim(),
    email_domain: document.getElementById("inst-domain").value.trim(),
    description: document.getElementById("inst-desc").value.trim(),
  };

  try {
    const res = await apiFetch("/institutions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      showAlert(alertEl, data.error || "Erro ao cadastrar", "error");
      return;
    }
    document.getElementById("modal-overlay").classList.remove("open");
    document.getElementById("inst-form").reset();
    loadInstitutions();
    window.location.href = "/gl/instituicao/" + data.id;
  } catch {
    showAlert(alertEl, "Erro de conexão. Tente novamente.", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "Cadastrar";
  }
}
