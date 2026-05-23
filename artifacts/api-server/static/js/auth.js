document.addEventListener("DOMContentLoaded", () => {
  requireGuest();
  setupTabs();
  setupForms();
});

function setupTabs() {
  const loginTab = document.getElementById("tab-login");
  const registerTab = document.getElementById("tab-register");
  const loginForm = document.getElementById("login-section");
  const registerForm = document.getElementById("register-section");

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

function setupForms() {
  // ── Login com e-mail ───────────────────────────────────────────────────────
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
      // Tenta login via Firebase se disponível
      const fbAuth = typeof getFirebaseAuth === "function" ? getFirebaseAuth() : null;
      if (fbAuth && typeof loginWithEmail === "function") {
        try {
          const fbUser = await loginWithEmail(email, password);
          if (!fbUser.emailVerified) {
            showAlert(alertEl, "E-mail não verificado. Verifique sua caixa de entrada e clique no link enviado.", "error");
            return;
          }
          const idToken = await fbUser.getIdToken();
          // Sincroniza com o backend
          const res = await fetch("/api/firebase-auth", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_token: idToken, email: fbUser.email, display_name: fbUser.displayName || "" }),
          });
          const data = await res.json();
          if (!res.ok) {
            showAlert(alertEl, data.error || "Falha no login", "error");
            return;
          }
          setAuth(data.token, data.user);
          window.location.href = "/dashboard";
          return;
        } catch (fbErr) {
          // Trata erros do Firebase
          const code = fbErr.code || "";
          if (code === "auth/user-not-found" || code === "auth/wrong-password" || code === "auth/invalid-credential") {
            showAlert(alertEl, "E-mail ou senha incorretos.", "error");
            return;
          }
          if (code === "auth/too-many-requests") {
            showAlert(alertEl, "Muitas tentativas. Tente novamente mais tarde.", "error");
            return;
          }
          // Se Firebase não reconhece, cai no login direto abaixo
        }
      }

      // Fallback: login direto na API (usuários sem Firebase)
      const res = await fetch("/api/login", {
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
      window.location.href = "/dashboard";
    } catch {
      showAlert(alertEl, "Erro de conexão. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Entrar";
    }
  });

  // ── Cadastro com e-mail ────────────────────────────────────────────────────
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

    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> Criando conta…`;
    hideAlert(alertEl);

    try {
      const fbAuth = typeof getFirebaseAuth === "function" ? getFirebaseAuth() : null;

      if (fbAuth && typeof registerWithEmail === "function") {
        // Cria no Firebase (envia e-mail de verificação automaticamente)
        try {
          await registerWithEmail(email, password);
          // Cria o usuário no banco de dados local
          await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ full_name, username, email, password, institution, research_area }),
          });
          // Exibe aviso de verificação e muda para a aba de login
          const notice = document.getElementById("verify-email-notice");
          if (notice) { notice.style.display = "block"; notice.classList.add("show"); }
          document.getElementById("tab-login").click();
          showAlert(document.getElementById("login-alert"), "Conta criada! Verifique seu e-mail antes de entrar.", "success");
          return;
        } catch (fbErr) {
          const code = fbErr.code || "";
          if (code === "auth/email-already-in-use") {
            showAlert(alertEl, "Este e-mail já está cadastrado.", "error");
            return;
          }
          if (code === "auth/weak-password") {
            showAlert(alertEl, "Senha fraca. Use pelo menos 8 caracteres.", "error");
            return;
          }
          // Qualquer outro erro do Firebase — cai no registro direto
        }
      }

      // Fallback: registro direto na API
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name, username, email, password, institution, research_area }),
      });
      const data = await res.json();
      if (!res.ok) {
        showAlert(alertEl, data.error || "Falha no cadastro", "error");
        return;
      }
      setAuth(data.token, data.user);
      window.location.href = "/dashboard";
    } catch {
      showAlert(alertEl, "Erro de conexão. Tente novamente.", "error");
    } finally {
      btn.disabled = false;
      btn.innerHTML = "Criar Conta";
    }
  });
}
