const BASE = "/gl";
const API_BASE = BASE + "/api";

function getToken() {
  return localStorage.getItem("gl_token");
}
function getUser() {
  const raw = localStorage.getItem("gl_user");
  try { return raw ? JSON.parse(raw) : null; } catch { return null; }
}
function setAuth(token, user) {
  localStorage.setItem("gl_token", token);
  localStorage.setItem("gl_user", JSON.stringify(user));
}
function clearAuth() {
  localStorage.removeItem("gl_token");
  localStorage.removeItem("gl_user");
}
function requireAuth() {
  if (!getToken()) {
    window.location.href = BASE + "/login";
    return false;
  }
  return true;
}
function requireGuest() {
  if (getToken()) {
    window.location.href = BASE + "/dashboard";
    return false;
  }
  return true;
}

async function apiFetch(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearAuth();
    window.location.href = BASE + "/login";
    throw new Error("Não autorizado");
  }
  return res;
}

function showAlert(el, message, type = "error") {
  el.textContent = message;
  el.className = `alert alert-${type} show`;
}
function hideAlert(el) {
  el.className = "alert";
  el.textContent = "";
}

function formatDate(ts) {
  const d = new Date(ts);
  return d.toLocaleDateString("pt-BR", { month: "short", day: "numeric", year: "numeric" });
}
function formatDateTime(ts) {
  const d = new Date(ts);
  return d.toLocaleDateString("pt-BR", { month: "short", day: "numeric" }) +
    " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}
function timeAgo(ts) {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "agora mesmo";
  if (m < 60) return `${m}min atrás`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h atrás`;
  const d = Math.floor(h / 24);
  return `${d}d atrás`;
}

function renderNavbar(activePage) {
  const user = getUser();
  const initials = user ? (user.avatar_initials || user.username.slice(0, 2).toUpperCase()) : "";
  const pages = [
    { href: BASE + "/dashboard", label: "Painel" },
    { href: BASE + "/search", label: "Busca de Genes" },
    { href: BASE + "/parcerias", label: "Parcerias" },
    { href: BASE + "/forum", label: "Fórum" },
    { href: BASE + "/preprints", label: "Pré-publicações" },
    { href: BASE + "/chat", label: "Chat" },
    { href: BASE + "/institucional", label: "Instituições" },
    { href: BASE + "/canais", label: "Canais" },
    { href: BASE + "/recursos", label: "Recursos" },
  ];
  const navLinks = pages.map(p =>
    `<a href="${p.href}" class="${activePage === p.href ? "active" : ""}">${p.label}</a>`
  ).join("");
  return `
    <nav class="navbar">
      <div class="navbar-brand">
        <div class="logo-icon">GL</div>
        GeneLink
      </div>
      <div class="navbar-nav">${navLinks}</div>
      <div class="navbar-right">
        ${user && user.is_admin ? `<a href="${BASE}/admin" style="color:rgba(255,255,255,.7);font-size:.78rem;border:1px solid rgba(255,255,255,.25);border-radius:4px;padding:3px 8px;">Admin</a>` : ""}
        <a href="${BASE}/profile" style="color:rgba(255,255,255,.82);font-size:.85rem;display:flex;align-items:center;gap:4px">
          ${user && user.is_verified ? `<span style="color:#90caf9;font-size:.75rem" title="Pesquisador Verificado">✓</span>` : ""}
          ${user ? user.username : ""}
        </a>
        <div class="avatar" title="Perfil" onclick="window.location='${BASE}/profile'">${initials}</div>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(255,255,255,.3);color:rgba(255,255,255,.82);" onclick="logout()">Sair</button>
      </div>
    </nav>`;
}

async function logout() {
  clearAuth();
  try {
    await fetch(API_BASE + "/logout", { method: "POST" });
  } catch (_) {}
  window.location.href = BASE + "/login";
}

function injectNavbar(activePage) {
  const nav = document.getElementById("navbar-placeholder");
  if (nav) nav.outerHTML = renderNavbar(activePage);
}
