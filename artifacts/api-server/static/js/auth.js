document.addEventListener("DOMContentLoaded", () => {
  if (new URLSearchParams(window.location.search).get("clear") === "1") {
    clearAuth();
    history.replaceState(null, "", "/gl/login");
  }

  // Se já está logado, mostra banner em vez de redirecionar
  if (getToken()) {
    const user = getUser();
    const name = user ? (user.full_name || user.username || "sua conta") : "sua conta";
    const header = document.querySelector(".auth-header");
    if (header) {
      const banner = document.createElement("div");
      banner.style.cssText = [
        "background:#fef9c3",
        "border-bottom:1px solid #fde68a",
        "padding:10px 20px",
        "display:flex",
        "align-items:center",
        "justify-content:space-between",
        "gap:10px",
        "font-size:.83rem",
        "color:#854d0e",
        "flex-wrap:wrap",
      ].join(";");
      banner.innerHTML =
        `<span>⚠️ Você está logado como <strong>${name}</strong></span>` +
        `<div style="display:flex;gap:8px">` +
          `<button onclick="window.location.href='/gl/dashboard'" ` +
            `style="background:#1d4ed8;color:#fff;border:none;border-radius:6px;` +
            `padding:4px 12px;font-size:.78rem;cursor:pointer;font-weight:600">` +
            `Ir ao Painel →</button>` +
          `<button id="btn-sair-testar" ` +
            `style="background:#dc2626;color:#fff;border:none;border-radius:6px;` +
            `padding:4px 12px;font-size:.78rem;cursor:pointer;font-weight:600">` +
            `Sair e Testar</button>` +
        `</div>`;
      header.insertAdjacentElement("afterend", banner);

      document.getElementById("btn-sair-testar").addEventListener("click", async () => {
        clearAuth();
        if (typeof firebaseSignOut === "function") await firebaseSignOut();
        window.location.reload();
      });
    }
  }

  setupTabs();
  setupForms();
  setupAvailabilityChecks();
});

function setupTabs() {
  const loginTab     = document.getElementById("tab-login");
  const registerTab  = document.getElementById("tab-register");
  const loginForm    = document.getElementById("login-section");
  const registerForm = document.getElementById("register-section");
  if (!loginTab || !registerTab) return;
  loginTab.addEventListener("click", () => {
    loginTab.classList.add("active");
    registerTab.classList.remove("active");
    loginForm.style.display = "block";
    registerForm.style.display = "none";
  });
  registerTab.addEventListener("click", () => {
    registerTab.classList.add("active");
    loginTab.classList.remove("active");
    registerForm.style.display = "block";
    loginForm.style.display = "none";
  });
}

// ── Availability checks ───────────────────────────────────────────────────────

let _usernameTimer = null, _emailTimer = null;
let _usernameTaken = false, _emailTaken = false;

function setFieldStatus(inputId, statusId, state, msg) {
  const input  = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  if (!input || !status) return;
  input.style.borderColor =
    state === "ok"    ? "var(--success, #1a9b82)" :
    state === "error" ? "var(--danger,  #c0392b)" : "";
  status.textContent  = msg;
  status.style.color  =
    state === "ok"    ? "var(--success, #1a9b82)" :
    state === "error" ? "var(--danger,  #c0392b)" : "var(--text-muted)";
  status.style.display = msg ? "block" : "none";
}

function setupAvailabilityChecks() {
  const usernameInput = document.getElementById("reg-username");
  const emailInput    = document.getElementById("reg-email");
  if (usernameInput) {
    usernameInput.addEventListener("input", () => {
      clearTimeout(_usernameTimer);
      const val = usernameInput.value.trim();
      if (val.length < 3) { setFieldStatus("reg-username","username-status","",""); _usernameTaken = false; return; }
      setFieldStatus("reg-username","username-status","muted","Verificando…");
      _usernameTimer = setTimeout(async () => {
        try {
          const res  = await fetch(`/gl/api/check-availability?username=${encodeURIComponent(val)}`);
          const data = await res.json();
          if (data.username_taken) { _usernameTaken = true;  setFieldStatus("reg-username","username-status","error","❌ Nome de usuário já está em uso"); }
          else                     { _usernameTaken = false; setFieldStatus("reg-username","username-status","ok","✓ Nome de usuário disponível"); }
        } catch { setFieldStatus("reg-username","username-status","",""); _usernameTaken = false; }
      }, 500);
    });
  }
  if (emailInput) {
    emailInput.addEventListener("input", () => {
      clearTimeout(_emailTimer);
      const val = emailInput.value.trim();
      if (!val.includes("@")) { setFieldStatus("reg-email","email-status","",""); _emailTaken = false; return; }
      setFieldStatus("reg-email","email-status","muted","Verificando…");
      _emailTimer = setTimeout(async () => {
        try {
          const res  = await fetch(`/gl/api/check-availability?email=${encodeURIComponent(val.toLowerCase())}`);
          const data = await res.json();
          if (data.email_taken) { _emailTaken = true;  setFieldStatus("reg-email","email-status","error","❌ Este e-mail já está cadastrado"); }
          else                  { _emailTaken = false; setFieldStatus("reg-email","email-status","ok","✓ E-mail disponível"); }
        } catch { setFieldStatus("reg-email","email-status","",""); _emailTaken = false; }
      }, 500);
    });
  }
}

// ── Forms ─────────────────────────────────────────────────────────────────────

function setupForms() {

  // ── LOGIN ──────────────────────────────────────────────────────────────────
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl  = document.getElementById("login-alert");
    const btn      = document.getElementById("login-btn");
    const email    = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    if (!email || !password) { showAlert(alertEl, "Por favor, insira seu e-mail e senha.", "error"); return; }
    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Entrando…`;
    hideAlert(alertEl);

    try {
      // 1. Tenta Firebase se disponível — e-mail verificado ou não
      const fbAuth = typeof getFirebaseAuth === "function" ? getFirebaseAuth() : null;
      if (fbAuth && typeof loginWithEmail === "function") {
        try {
          const fbUser = await loginWithEmail(email, password);
          if (fbUser) {
            // Autenticou no Firebase → usa token Firebase (cria conta no DB se não existir)
            const idToken = await fbUser.getIdToken();
            const res = await fetch("/gl/api/firebase-auth", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ id_token: idToken, email: fbUser.email, display_name: fbUser.displayName || "" }),
            });
            const data = await res.json();
            if (!res.ok) { showAlert(alertEl, data.error || "Falha no login", "error"); return; }
            setAuth(data.token, data.user);
            window.location.href = "/gl/dashboard";
            return;
          }
        } catch (fbErr) {
          const code = fbErr.code || "";
          if (code === "auth/too-many-requests") {
            showAlert(alertEl, "Muitas tentativas. Tente novamente mais tarde.", "error"); return;
          }
          // Conta criada apenas com Google — não tem senha definida
          if (code === "auth/invalid-credential" || code === "auth/wrong-password" || code === "auth/user-not-found") {
            // Tenta fallback via API (o backend chama Firebase REST para verificar)
            // Se também falhar, mostramos mensagem orientando a usar Google
          }
          // Outros erros Firebase → cai no fallback da API abaixo
        }
      }

      // 2. Fallback: login direto na API (contas existentes, ou Firebase sem verificação)
      const res  = await fetch("/gl/api/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        // Show error + reset-password link inline
        alertEl.innerHTML =
          `❌ ${data.error || "Email ou senha incorretos"} &nbsp;—&nbsp; ` +
          `<a href="#" id="inline-forgot" style="color:inherit;font-weight:600;text-decoration:underline">Redefinir senha</a>`;
        alertEl.className = "alert alert-error show";
        document.getElementById("inline-forgot")?.addEventListener("click", e => {
          e.preventDefault();
          document.getElementById("forgot-pwd-link")?.click();
        });
        return;
      }
      setAuth(data.token, data.user);
      window.location.href = "/gl/dashboard";

    } catch {
      showAlert(alertEl, "Erro de conexão. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Entrar como Pesquisador";
    }
  });

  // ── CADASTRO ───────────────────────────────────────────────────────────────
  document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl       = document.getElementById("register-alert");
    const btn           = document.getElementById("register-btn");
    const full_name     = document.getElementById("reg-fullname").value.trim();
    const username      = document.getElementById("reg-username").value.trim();
    const email         = document.getElementById("reg-email").value.trim();
    const password      = document.getElementById("reg-password").value;
    const institution   = document.getElementById("reg-institution").value.trim();
    const research_area = document.getElementById("reg-area").value.trim();

    if (!username || !email || !password) { showAlert(alertEl, "Usuário, e-mail e senha são obrigatórios.", "error"); return; }
    if (password.length < 8) { showAlert(alertEl, "A senha deve ter pelo menos 8 caracteres.", "error"); return; }
    if (_usernameTaken) { setFieldStatus("reg-username","username-status","error","❌ Nome de usuário já está em uso"); showAlert(alertEl,"Nome de usuário já está em uso.","error"); return; }
    if (_emailTaken)    { setFieldStatus("reg-email","email-status","error","❌ Este e-mail já está cadastrado");      showAlert(alertEl,"E-mail já cadastrado.","error"); return; }

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Criando conta…`;
    hideAlert(alertEl);

    try {
      const fbAuth = typeof getFirebaseAuth === "function" ? getFirebaseAuth() : null;
      if (fbAuth && typeof registerWithEmail === "function") {
        try {
          await registerWithEmail(email, password);
        } catch (fbErr) {
          const code = fbErr.code || "";
          if (code === "auth/weak-password") { showAlert(alertEl, "Senha fraca. Use pelo menos 8 caracteres.", "error"); return; }
          if (code === "auth/email-already-in-use") {
            // Email exists in Firebase (partial previous registration) — try logging in directly
            showAlert(alertEl, "⏳ Este e-mail já existe — tentando entrar automaticamente…", "info");
            try {
              const fbUser = await loginWithEmail(email, password);
              if (fbUser) {
                const idToken = await fbUser.getIdToken();
                const res = await fetch("/gl/api/firebase-auth", {
                  method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ id_token: idToken, email: fbUser.email, display_name: fbUser.displayName || "" }),
                });
                const data = await res.json();
                if (res.ok && data.token) {
                  setAuth(data.token, data.user);
                  window.location.href = "/gl/dashboard";
                  return;
                }
              }
            } catch (_) {}
            // Auto-login failed — try backend fallback
            try {
              const res = await fetch("/gl/api/login", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
              });
              const data = await res.json();
              if (res.ok && data.token) {
                setAuth(data.token, data.user);
                window.location.href = "/gl/dashboard";
                return;
              }
            } catch (_) {}
            // Both failed — tell user to reset password
            alertEl.innerHTML =
              `❌ Este e-mail já está cadastrado mas a senha não confere. ` +
              `<a href="#" onclick="document.getElementById('tab-login').click();setTimeout(()=>document.getElementById('forgot-pwd-link')?.click(),200);return false" ` +
              `style="color:inherit;font-weight:600;text-decoration:underline">Redefinir senha agora →</a>`;
            alertEl.className = "alert alert-error show";
            return;
          }
          // Other Firebase errors — fall through to direct API register below
        }

        // Try to register in DB. Even if this fails the user can still log in
        // because the backend /api/login has a Firebase fallback that creates
        // the DB record on first login.
        try {
          await fetch("/gl/api/register", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ full_name, username, email, password, institution, research_area }),
          });
        } catch (_) { /* network error — login will self-heal via Firebase fallback */ }

        [document.getElementById("tab-login"), document.getElementById("tab-register"), document.getElementById("tab-inst")]
          .forEach(t => t && t.classList.remove("active"));
        document.getElementById("tab-login").classList.add("active");
        document.getElementById("login-section").style.display = "block";
        document.getElementById("register-section").style.display = "none";
        showAlert(document.getElementById("login-alert"),
          "✅ Conta criada! Você já pode entrar com seu e-mail e senha.", "success");
        return;
      }

      // Fallback: cadastro direto na API
      const res  = await fetch("/gl/api/register", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name, username, email, password, institution, research_area }),
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 409) {
          const errLower = (data.error || "").toLowerCase();
          if (errLower.includes("username")) { _usernameTaken = true; setFieldStatus("reg-username","username-status","error","❌ Nome de usuário já está em uso"); }
          else if (errLower.includes("email")) { _emailTaken = true; setFieldStatus("reg-email","email-status","error","❌ Este e-mail já está cadastrado"); }
        }
        showAlert(alertEl, data.error || "Falha no cadastro", "error"); return;
      }
      setAuth(data.token, data.user);
      window.location.href = "/gl/dashboard";

    } catch {
      showAlert(alertEl, "Erro de conexão. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Criar Conta de Pesquisador";
    }
  });
}
