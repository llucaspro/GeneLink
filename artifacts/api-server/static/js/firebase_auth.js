// Firebase Auth — Login social (Google) + Email/Senha com verificação
// Credenciais carregadas do backend via /gl/api/firebase-config

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendEmailVerification,
  onAuthStateChanged,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

let firebaseApp = null;
let firebaseAuth = null;

async function initFirebase() {
  try {
    const res = await fetch("/gl/api/firebase-config");
    if (!res.ok) return;
    const config = await res.json();
    if (!config.apiKey) return;

    firebaseApp = initializeApp(config);
    firebaseAuth = getAuth(firebaseApp);

    // Exibe o botão de login social SOMENTE na aba de pesquisador (não instituição)
    window._firebaseReady = true;
    const instSection = document.getElementById("inst-section");
    const socialDiv = document.getElementById("social-login");
    if (socialDiv && instSection && instSection.style.display !== "block") {
      socialDiv.style.display = "block";
    }

    // Verifica se há sessão ativa (retorno de popup)
    onAuthStateChanged(firebaseAuth, async (fbUser) => {
      if (fbUser && !window._handlingFirebaseAuth) {
        window._handlingFirebaseAuth = true;
        await handleFirebaseUser(fbUser);
      }
    });
  } catch (e) {
    // Firebase não configurado — botões sociais permanecem ocultos
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

async function handleFirebaseUser(fbUser) {
  try {
    const idToken = await fbUser.getIdToken();
    const res = await fetch("/gl/api/firebase-auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_token: idToken,
        display_name: fbUser.displayName || "",
        email: fbUser.email || "",
      }),
    });
    const data = await res.json();
    if (res.ok && data.token) {
      setAuth(data.token, data.user);
      window.location.href = "/gl/dashboard";
    } else {
      alert(data.error || "Falha ao autenticar com Firebase");
    }
  } catch (e) {
    alert("Erro ao processar login social.");
  }
}

// Cadastro com e-mail/senha + verificação via Firebase
async function registerWithEmail(email, password) {
  if (!firebaseAuth) return null;
  const cred = await createUserWithEmailAndPassword(firebaseAuth, email, password);
  await sendEmailVerification(cred.user);
  return cred.user;
}

// Login com e-mail/senha via Firebase
async function loginWithEmail(email, password) {
  if (!firebaseAuth) return null;
  const cred = await signInWithEmailAndPassword(firebaseAuth, email, password);
  return cred.user;
}

// Expõe funções globalmente para uso nos templates
window.loginComGoogle = loginComGoogle;
window.registerWithEmail = registerWithEmail;
window.loginWithEmail = loginWithEmail;
window.getFirebaseAuth = () => firebaseAuth;

document.addEventListener("DOMContentLoaded", initFirebase);
