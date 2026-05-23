// Firebase Auth — Login social (Google, GitHub) + Email/Senha com verificação
// Credenciais carregadas do backend via /api/firebase-config

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  GithubAuthProvider,
  signInWithPopup,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendEmailVerification,
  onAuthStateChanged,
  signOut,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

let firebaseApp = null;
let firebaseAuth = null;

async function initFirebase() {
  try {
    const res = await fetch("/api/firebase-config");
    if (!res.ok) return;
    const config = await res.json();
    if (!config.apiKey) return;

    firebaseApp = initializeApp(config);
    firebaseAuth = getAuth(firebaseApp);

    // Exibe os botões de login social
    const socialDiv = document.getElementById("social-login");
    if (socialDiv) socialDiv.style.display = "block";

    // Verifica se já há uma sessão ativa (retorno de popup)
    onAuthStateChanged(firebaseAuth, async (fbUser) => {
      if (fbUser && !window._handlingFirebaseAuth) {
        window._handlingFirebaseAuth = true;
        await handleFirebaseUser(fbUser);
      }
    });
  } catch (e) {
    // Firebase não configurado — botões permanecem ocultos
  }
}

async function loginComGoogle() {
  if (!firebaseAuth) return;
  try {
    const provider = new GoogleAuthProvider();
    const result = await signInWithPopup(firebaseAuth, provider);
    await handleFirebaseUser(result.user);
  } catch (e) {
    if (e.code !== "auth/popup-closed-by-user") {
      alert("Erro ao entrar com Google: " + (e.message || e));
    }
  }
}

async function loginComGitHub() {
  if (!firebaseAuth) return;
  try {
    const provider = new GithubAuthProvider();
    const result = await signInWithPopup(firebaseAuth, provider);
    await handleFirebaseUser(result.user);
  } catch (e) {
    if (e.code !== "auth/popup-closed-by-user") {
      alert("Erro ao entrar com GitHub: " + (e.message || e));
    }
  }
}

async function handleFirebaseUser(fbUser) {
  try {
    const idToken = await fbUser.getIdToken();
    const res = await fetch("/api/firebase-auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_token: idToken,
        display_name: fbUser.displayName || "",
        email: fbUser.email || "",
        photo_url: fbUser.photoURL || "",
      }),
    });
    const data = await res.json();
    if (res.ok && data.token) {
      setAuth(data.token, data.user);
      window.location.href = "/dashboard";
    } else {
      alert(data.error || "Falha ao autenticar com Firebase");
    }
  } catch (e) {
    alert("Erro ao processar login social.");
  }
}

// Cadastro com e-mail/senha + verificação de e-mail via Firebase
async function registerWithEmail(email, password, extraData) {
  if (!firebaseAuth) {
    // Fallback para registro direto na API (sem Firebase configurado)
    return null;
  }
  try {
    const cred = await createUserWithEmailAndPassword(firebaseAuth, email, password);
    await sendEmailVerification(cred.user);
    return cred.user;
  } catch (e) {
    throw e;
  }
}

// Login com e-mail/senha via Firebase
async function loginWithEmail(email, password) {
  if (!firebaseAuth) return null;
  try {
    const cred = await signInWithEmailAndPassword(firebaseAuth, email, password);
    return cred.user;
  } catch (e) {
    throw e;
  }
}

// Expõe funções globalmente para uso nos templates
window.loginComGoogle = loginComGoogle;
window.loginComGitHub = loginComGitHub;
window.registerWithEmail = registerWithEmail;
window.loginWithEmail = loginWithEmail;
window.getFirebaseAuth = () => firebaseAuth;

document.addEventListener("DOMContentLoaded", initFirebase);
