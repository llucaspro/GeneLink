document.addEventListener("DOMContentLoaded", () => {
  if (new URLSearchParams(window.location.search).get("clear") === "1") {
    clearAuth();
    history.replaceState(null, "", "/gl/login");
  }
  requireGuest();
  setupTabs();
  setupForms();
  setupAvailabilityChecks();
});

function setupTabs() {
  const loginTab = document.getElementById("tab-login");
  const registerTab = document.getElementById("tab-register");
  const loginForm = document.getElementById("login-section");
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

// ── Availability checks (username + email) ──────────────────────────────────

let _usernameTimer = null;
let _emailTimer = null;
let _usernameTaken = false;
let _emailTaken = false;

function setFieldStatus(inputId, statusId, state, msg) {
  const input = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  if (!input || !status) return;

  input.style.borderColor = state === "ok"
    ? "var(--success, #1a9b82)"
    : state === "error"
    ? "var(--danger, #c0392b)"
    : "";
  status.textContent = msg;
  status.style.color = state === "ok"
    ? "var(--success, #1a9b82)"
    : state === "error"
    ? "var(--danger, #c0392b)"
    : "var(--text-muted)";
  status.style.display = msg ? "block" : "none";
}

function setupAvailabilityChecks() {
  const usernameInput = document.getElementById("reg-username");
  const emailInput = document.getElementById("reg-email");

  if (usernameInput) {
    usernameInput.addEventListener("input", () => {
      clearTimeout(_usernameTimer);
      const val = usernameInput.value.trim();
      if (val.length < 3) {
        setFieldStatus("reg-username", "username-status", "", "");
        _usernameTaken = false;
        return;
      }
      setFieldStatus("reg-username", "username-status", "muted", "Verificando…");
      _usernameTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/gl/api/check-availability?username=${encodeURIComponent(val)}`);
          const data = await res.json();
          if (data.username_taken) {
            _usernameTaken = true;
            setFieldStatus("reg-username", "username-status", "error", "❌ Nome de usuário já está em uso");
          } else {
            _usernameTaken = false;
            setFieldStatus("reg-username", "username-status", "ok", "✓ Nome de usuário disponível");
          }
        } catch {
          setFieldStatus("reg-username", "username-status", "", "");
          _usernameTaken = false;
        }
      }, 500);
    });
  }

  if (emailInput) {
    emailInput.addEventListener("input", () => {
      clearTimeout(_emailTimer);
      const val = emailInput.value.trim();
      if (!val.includes("@")) {
        setFieldStatus("reg-email", "email-status", "", "");
        _emailTaken = false;
        return;
      }
      setFieldStatus("reg-email", "email-status", "muted", "Verificando…");
      _emailTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/gl/api/check-availability?email=${encodeURIComponent(val.toLowerCase())}`);
          const data = await res.json();
          if (data.email_taken) {
            _emailTaken = true;
            setFieldStatus("reg-email", "email-status", "error", "❌ Este e-mail já está cadastrado");
          } else {
            _emailTaken = false;
            setFieldStatus("reg-email", "email-status", "ok", "✓ E-mail disponível");
          }
        } catch {
          setFieldStatus("reg-email", "email-status", "", "");
          _emailTaken = false;
        }
      }, 500);
    });
  }
}

// ── Forms ────────────────────────────────────────────────────────────────────

function setupForms() {
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl = document.getElementById("login-alert");
    const btn = document.getElementById("login-btn");
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    if (!email || !password) {
      showAlert(alertEl, "Por favor, insira seu e-mail e senha.", "error");
      return;
    }

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Entrando…`;
    hideAlert(alertEl);

    try {
      const res = await fetch("/gl/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        showAlert(alertEl, data.error || "Falha no login", "error");
        return;
      }
      setAuth(data.token, data.user);
      window.location.href = "/gl/dashboard";
    } catch {
      showAlert(alertEl, "Erro de conexão. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Entrar";
    }
  });

  document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const alertEl = document.getElementById("register-alert");
    const btn = document.getElementById("register-btn");
    const full_name = document.getElementById("reg-fullname").value.trim();
    const username = document.getElementById("reg-username").value.trim();
    const email = document.getElementById("reg-email").value.trim();
    const password = document.getElementById("reg-password").value;
    const institution = document.getElementById("reg-institution").value.trim();
    const research_area = document.getElementById("reg-area").value.trim();

    if (!username || !email || !password) {
      showAlert(alertEl, "Usuário, e-mail e senha são obrigatórios.", "error");
      return;
    }
    if (password.length < 8) {
      showAlert(alertEl, "A senha deve ter pelo menos 8 caracteres.", "error");
      return;
    }
    if (_usernameTaken) {
      setFieldStatus("reg-username", "username-status", "error", "❌ Nome de usuário já está em uso");
      showAlert(alertEl, "Nome de usuário já está em uso. Escolha outro.", "error");
      return;
    }
    if (_emailTaken) {
      setFieldStatus("reg-email", "email-status", "error", "❌ Este e-mail já está cadastrado");
      showAlert(alertEl, "Este e-mail já está cadastrado. Faça login ou use outro e-mail.", "error");
      return;
    }

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Criando conta…`;
    hideAlert(alertEl);

    try {
      const res = await fetch("/gl/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name, username, email, password, institution, research_area }),
      });
      const data = await res.json();
      if (!res.ok) {
        // Aplica feedback visual se for conflito de username/email
        if (res.status === 409) {
          const errLower = (data.error || "").toLowerCase();
          if (errLower.includes("username")) {
            _usernameTaken = true;
            setFieldStatus("reg-username", "username-status", "error", "❌ Nome de usuário já está em uso");
          } else if (errLower.includes("email")) {
            _emailTaken = true;
            setFieldStatus("reg-email", "email-status", "error", "❌ Este e-mail já está cadastrado");
          }
        }
        showAlert(alertEl, data.error || "Falha no cadastro", "error");
        return;
      }
      setAuth(data.token, data.user);
      window.location.href = "/gl/dashboard";
    } catch {
      showAlert(alertEl, "Erro de conexão. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Criar Conta";
    }
  });
}

// ── Firebase: sobrescreve o submit do login-form e register-form ──────────────
(function patchFormsForFirebase() {
  function waitReady(cb) {
    if (document.readyState !== 'loading') cb();
    else document.addEventListener('DOMContentLoaded', cb);
  }

  waitReady(() => {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');

    if (loginForm) {
      loginForm.addEventListener('submit', async function firebaseLoginHandler(e) {
        const fbAuth = typeof getFirebaseAuth === 'function' ? getFirebaseAuth() : null;
        if (!fbAuth) return; // sem Firebase: deixa o handler original agir

        e.preventDefault();
        e.stopImmediatePropagation();

        const alertEl = document.getElementById('login-alert');
        const btn = document.getElementById('login-btn');
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;

        if (!email || !password) {
          showAlert(alertEl, 'Por favor, insira seu e-mail e senha.', 'error'); return;
        }
        btn.disabled = true;
        btn.innerHTML = '<div class="spinner"></div> Entrando…';
        hideAlert(alertEl);

        try {
          if (typeof loginWithEmail === 'function') {
            const fbUser = await loginWithEmail(email, password);
            if (!fbUser) throw { code: 'auth/user-not-found' };
            if (!fbUser.emailVerified) {
              showAlert(alertEl, 'E-mail não verificado. Verifique sua caixa de entrada antes de entrar.', 'error');
              return;
            }
            const idToken = await fbUser.getIdToken();
            const res = await fetch('/gl/api/firebase-auth', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ id_token: idToken, email: fbUser.email, display_name: fbUser.displayName || '' }),
            });
            const data = await res.json();
            if (!res.ok) { showAlert(alertEl, data.error || 'Falha no login', 'error'); return; }
            setAuth(data.token, data.user);
            window.location.href = '/gl/dashboard';
            return;
          }
        } catch (fbErr) {
          const code = fbErr.code || '';
          if (code === 'auth/user-not-found' || code === 'auth/wrong-password' || code === 'auth/invalid-credential') {
            showAlert(alertEl, 'E-mail ou senha incorretos.', 'error'); return;
          }
          if (code === 'auth/too-many-requests') {
            showAlert(alertEl, 'Muitas tentativas. Tente mais tarde.', 'error'); return;
          }
          // fallback: deixa o handler original tentar
        } finally {
          btn.disabled = false;
          btn.innerHTML = 'Entrar como Pesquisador';
        }
      }, true); // capture: roda antes do handler original
    }

    if (registerForm) {
      registerForm.addEventListener('submit', async function firebaseRegisterHandler(e) {
        const fbAuth = typeof getFirebaseAuth === 'function' ? getFirebaseAuth() : null;
        if (!fbAuth) return;

        e.preventDefault();
        e.stopImmediatePropagation();

        const alertEl = document.getElementById('register-alert');
        const btn = document.getElementById('register-btn');
        const email = document.getElementById('reg-email').value.trim();
        const password = document.getElementById('reg-password').value;
        const username = document.getElementById('reg-username').value.trim();
        const full_name = document.getElementById('reg-fullname').value.trim();
        const institution = document.getElementById('reg-institution').value.trim();
        const research_area = document.getElementById('reg-area').value.trim();

        if (!username || !email || !password) {
          showAlert(alertEl, 'Usuário, e-mail e senha são obrigatórios.', 'error'); return;
        }
        if (password.length < 8) {
          showAlert(alertEl, 'A senha deve ter pelo menos 8 caracteres.', 'error'); return;
        }

        btn.disabled = true;
        btn.innerHTML = '<div class="spinner"></div> Criando conta…';
        hideAlert(alertEl);

        try {
          if (typeof registerWithEmail === 'function') {
            await registerWithEmail(email, password);
            // Cria o usuário no banco de dados local
            await fetch('/gl/api/register', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ full_name, username, email, password, institution, research_area }),
            });
            // Mostra aviso e muda para aba de login
            const tabLogin = document.getElementById('tab-login');
            const secLogin = document.getElementById('login-section');
            const secRegister = document.getElementById('register-section');
            if (tabLogin) {
              [document.getElementById('tab-login'), document.getElementById('tab-register'), document.getElementById('tab-inst')]
                .forEach(t => t && t.classList.remove('active'));
              tabLogin.classList.add('active');
              secLogin.style.display = 'block';
              secRegister.style.display = 'none';
            }
            showAlert(document.getElementById('login-alert'),
              '✅ Conta criada! Enviamos um e-mail de verificação. Confirme antes de entrar.', 'success');
            return;
          }
        } catch (fbErr) {
          const code = fbErr.code || '';
          if (code === 'auth/email-already-in-use') {
            showAlert(alertEl, 'Este e-mail já está cadastrado.', 'error'); return;
          }
          if (code === 'auth/weak-password') {
            showAlert(alertEl, 'Senha fraca. Use pelo menos 8 caracteres.', 'error'); return;
          }
        } finally {
          btn.disabled = false;
          btn.innerHTML = 'Criar Conta de Pesquisador';
        }
      }, true);
    }
  });
})();
