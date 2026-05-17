document.addEventListener("DOMContentLoaded", () => {
  if (new URLSearchParams(window.location.search).get("clear") === "1") {
    clearAuth();
    history.replaceState(null, "", "/gl/login");
  }
  requireGuest();
  setupTabs();
  setupForms();
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
