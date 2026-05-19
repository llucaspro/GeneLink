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

// ── Researcher Navbar ─────────────────────────────────────────────────────────

function renderNavbar(activePage) {
  const user = getUser();
  const initials = user ? (user.avatar_initials || user.username.slice(0, 2).toUpperCase()) : "";
  const pages = [
    { href: BASE + "/dashboard",    label: "Painel",           icon: "🏠" },
    { href: BASE + "/search",       label: "Busca de Genes",   icon: "🔬" },
    { href: BASE + "/parcerias",    label: "Parcerias",        icon: "🤝" },
    { href: BASE + "/forum",        label: "Fórum",            icon: "💬" },
    { href: BASE + "/preprints",    label: "Pré-publicações",  icon: "📄" },
    { href: BASE + "/chat",         label: "Chat",             icon: "✉️"  },
    { href: BASE + "/dm",           label: "Mensagens",        icon: "💌", badge: true },
    { href: BASE + "/institucional",label: "Instituições",     icon: "🏛️" },
    { href: BASE + "/canais",       label: "Canais",           icon: "📡" },
    { href: BASE + "/user-search", label: "Pesquisadores",     icon: "👥" },
    { href: BASE + "/recursos",     label: "Recursos",         icon: "📚" },
  ];
  if (user && user.is_admin) {
    pages.push({ href: BASE + "/admin", label: "Admin", icon: "⚙️" });
  }
  const navLinks = pages.map(p =>
    `<a href="${p.href}" class="${activePage === p.href ? "active" : ""}">${p.label}</a>`
  ).join("");
  const drawerItems = pages.map(p =>
    `<a href="${p.href}" class="gl-drawer-item${activePage === p.href ? " active" : ""}">
      <span class="gl-drawer-icon">${p.icon}</span>
      <span>${p.label}</span>
      ${p.badge ? `<span id="dm-nav-badge" style="display:none;background:var(--accent);color:#fff;border-radius:20px;font-size:.65rem;font-weight:700;padding:1px 6px;margin-left:auto">0</span>` : ""}
    </a>`
  ).join("");

  return `
    <!-- Overlay + Drawer -->
    <div class="gl-drawer-overlay" id="gl-drawer-overlay" onclick="_glCloseDrawer()"></div>
    <div class="gl-drawer" id="gl-drawer">
      <div class="gl-drawer-header">
        <div class="gl-drawer-brand">
          <div class="logo-icon" style="width:32px;height:32px;font-size:.9rem">GL</div>
          <span>GeneLink</span>
        </div>
        <button class="gl-drawer-close" onclick="_glCloseDrawer()" aria-label="Fechar menu">✕</button>
      </div>
      ${user ? `<div class="gl-drawer-user">
        <div class="avatar" style="width:38px;height:38px;font-size:.9rem;flex-shrink:0">${initials}</div>
        <div>
          <div style="font-weight:700;font-size:.9rem">${user.full_name || user.username}</div>
          <div style="font-size:.75rem;opacity:.65">@${user.username}${user.is_verified ? ' · ✓ Verificado' : ''}</div>
        </div>
      </div>` : ""}
      <nav class="gl-drawer-nav">${drawerItems}</nav>
      <div class="gl-drawer-footer">
        <button class="gl-drawer-signout" onclick="logout()">↩ Sair da conta</button>
      </div>
    </div>

    <nav class="navbar">
      <button class="gl-menu-btn" onclick="_glOpenDrawer()" aria-label="Abrir menu">
        <span></span><span></span><span></span>
      </button>
      <div class="navbar-brand" onclick="window.location='${BASE}/dashboard'" style="cursor:pointer">
        <div class="logo-icon">GL</div>
        GeneLink
      </div>
      <div class="navbar-nav">${navLinks}</div>
      <div class="navbar-right">
        <a href="${BASE}/profile" style="color:rgba(255,255,255,.82);font-size:.85rem;display:flex;align-items:center;gap:4px">
          ${user && user.is_verified ? `<span style="color:#90caf9;font-size:.75rem" title="Pesquisador Verificado">✓</span>` : ""}
          ${user ? user.username : ""}
        </a>
        <div class="avatar" title="Perfil" onclick="window.location='${BASE}/profile'">${initials}</div>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(255,255,255,.3);color:rgba(255,255,255,.82);" onclick="logout()">Sair</button>
      </div>
    </nav>`;
}

function _glOpenDrawer() {
  document.getElementById("gl-drawer").classList.add("open");
  document.getElementById("gl-drawer-overlay").classList.add("open");
  document.body.style.overflow = "hidden";
}
function _glCloseDrawer() {
  document.getElementById("gl-drawer").classList.remove("open");
  document.getElementById("gl-drawer-overlay").classList.remove("open");
  document.body.style.overflow = "";
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

// ── Institutional Navbar ──────────────────────────────────────────────────────

function renderInstNavbar(activePage) {
  const inst = JSON.parse(localStorage.getItem('gl_inst') || 'null');
  const initials = inst
    ? (inst.logo_initials || inst.short_name?.[0] || inst.name?.[0] || 'GL')
    : 'GL';
  const name = inst ? inst.name : 'Instituição';

  const pages = [
    { href: BASE + "/inst-dashboard",  label: "Painel",              icon: "🏠" },
    { href: BASE + "/inst-candidates", label: "Candidatos",          icon: "👥" },
    { href: BASE + "/parcerias",       label: "Mural de Parcerias",  icon: "📢" },
  ];

  const drawerItems = pages.map(p =>
    `<a href="${p.href}" class="gl-drawer-item${activePage === p.href ? " active" : ""}">
      <span class="gl-drawer-icon">${p.icon}</span>
      <span>${p.label}</span>
    </a>`
  ).join("");

  const navLinks = pages.map(p =>
    `<a href="${p.href}" class="${activePage === p.href ? "active" : ""}">${p.label}</a>`
  ).join("");

  return `
    <div class="gl-drawer-overlay" id="gl-drawer-overlay" onclick="_glCloseDrawer()"></div>
    <div class="gl-drawer" id="gl-drawer">
      <div class="gl-drawer-header">
        <div class="gl-drawer-brand">
          <div class="logo-icon" style="width:32px;height:32px;font-size:.9rem">GL</div>
          <span>GeneLink</span>
        </div>
        <button class="gl-drawer-close" onclick="_glCloseDrawer()" aria-label="Fechar menu">✕</button>
      </div>
      ${inst ? `<div class="gl-drawer-user">
        <div class="avatar" style="width:38px;height:38px;font-size:.88rem;flex-shrink:0;background:#1a9b82">${initials}</div>
        <div>
          <div style="font-weight:700;font-size:.9rem">${name}</div>
          <div style="font-size:.75rem;opacity:.65">Conta Institucional · ✅ Verificada</div>
        </div>
      </div>` : ""}
      <nav class="gl-drawer-nav">${drawerItems}</nav>
      <div class="gl-drawer-footer">
        <button class="gl-drawer-signout" onclick="instLogoutNav()">↩ Sair da conta</button>
      </div>
    </div>

    <nav class="navbar">
      <button class="gl-menu-btn" onclick="_glOpenDrawer()" aria-label="Abrir menu">
        <span></span><span></span><span></span>
      </button>
      <div class="navbar-brand" onclick="window.location='${BASE}/inst-dashboard'" style="cursor:pointer">
        <div class="logo-icon">GL</div>
        GeneLink
      </div>
      <div class="navbar-nav">${navLinks}</div>
      <div class="navbar-right">
        <span style="color:rgba(255,255,255,.82);font-size:.85rem">${name}</span>
        <div class="avatar" style="background:#1a9b82;border-color:rgba(255,255,255,.3)" title="${name}">${initials}</div>
        <button class="btn btn-ghost btn-sm" style="border-color:rgba(255,255,255,.3);color:rgba(255,255,255,.82);" onclick="instLogoutNav()">Sair</button>
      </div>
    </nav>`;
}

function injectInstNavbar(activePage) {
  const nav = document.getElementById("navbar-placeholder");
  if (nav) nav.outerHTML = renderInstNavbar(activePage);
}

function instLogoutNav() {
  fetch('/gl/api/institutions/logout', { method: 'POST' }).catch(() => {});
  localStorage.removeItem('gl_inst_token');
  localStorage.removeItem('gl_inst');
  window.location.href = BASE + '/login#instituicao';
}
