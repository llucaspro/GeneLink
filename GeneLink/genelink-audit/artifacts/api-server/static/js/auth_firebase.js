/**
 * GeneLink — Firebase Auth client (replaces auth.js JWT flow)
 *
 * Dependências (adicione ao seu HTML antes deste script):
 *   <script type="module">
 *     import { initializeApp } from "https://www.gstatic.com/firebasejs/10.x.x/firebase-app.js";
 *     import { getAuth, ... } from "https://www.gstatic.com/firebasejs/10.x.x/firebase-auth.js";
 *   </script>
 *
 * Ou via npm: npm install firebase
 *
 * CONFIGURAÇÃO: copie o objeto firebaseConfig do Firebase Console
 * (Project Settings > Your apps > Web app).
 */

// ─── Configuração Firebase ────────────────────────────────────────────────────
// Substitua pelos valores do seu projeto no Firebase Console
const FIREBASE_CONFIG = {
  apiKey: "COLE_AQUI_SUA_API_KEY",
  authDomain: "COLE_AQUI.firebaseapp.com",
  projectId: "COLE_AQUI_SEU_PROJECT_ID",
  storageBucket: "COLE_AQUI.appspot.com",
  messagingSenderId: "COLE_AQUI",
  appId: "COLE_AQUI_SEU_APP_ID",
};

// ─── Inicialização ────────────────────────────────────────────────────────────
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  onAuthStateChanged,
  GoogleAuthProvider,
  signInWithPopup,
  sendPasswordResetEmail,
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

const firebaseApp = initializeApp(FIREBASE_CONFIG);
const auth = getAuth(firebaseApp);

const API_BASE = "/gl/api";

// ─── Funções utilitárias ──────────────────────────────────────────────────────

/**
 * Retorna o Firebase ID token do usuário logado.
 * Sempre use esta função para pegar o token (ele é renovado automaticamente).
 */
async function getIdToken() {
  const user = auth.currentUser;
  if (!user) throw new Error("Usuário não autenticado");
  return user.getIdToken(/* forceRefresh= */ false);
}

/**
 * Faz uma requisição autenticada para a API do GeneLink.
 */
async function apiRequest(path, options = {}) {
  const token = await getIdToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// ─── Registro ─────────────────────────────────────────────────────────────────

/**
 * Registra um novo usuário pesquisador.
 * 1. Cria o usuário no Firebase Auth
 * 2. Envia os dados de perfil para o banco PostgreSQL
 */
async function register({ email, password, username, fullName, institution, researchArea }) {
  // 1. Cria no Firebase
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  const idToken = await userCredential.user.getIdToken();

  // 2. Registra no banco PostgreSQL
  const res = await fetch(`${API_BASE}/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
    },
    body: JSON.stringify({
      username,
      full_name: fullName,
      institution,
      research_area: researchArea,
      email,
    }),
  });

  if (!res.ok) {
    // Rollback: remove o usuário do Firebase se o registro no DB falhou
    await userCredential.user.delete().catch(() => {});
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || "Erro ao registrar usuário");
  }

  const data = await res.json();
  localStorage.setItem("gl_user", JSON.stringify(data.user));
  return data.user;
}

// ─── Login ────────────────────────────────────────────────────────────────────

/**
 * Login com email/senha via Firebase.
 * Após autenticação, sincroniza com o banco PostgreSQL.
 */
async function login(email, password) {
  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  const idToken = await userCredential.user.getIdToken();

  const res = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    if (err.needs_registration) {
      // Usuário existe no Firebase mas não no banco — redireciona para completar cadastro
      window.location.href = "/gl/register?complete=1";
      return null;
    }
    throw new Error(err.error || "Erro ao fazer login");
  }

  const data = await res.json();
  localStorage.setItem("gl_user", JSON.stringify(data.user));
  return data.user;
}

// ─── Login com Google ─────────────────────────────────────────────────────────

async function loginWithGoogle() {
  const provider = new GoogleAuthProvider();
  const userCredential = await signInWithPopup(auth, provider);
  const idToken = await userCredential.user.getIdToken();

  const res = await fetch(`${API_BASE}/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${idToken}`,
    },
  });

  const data = await res.json();
  if (res.status === 404 && data.needs_registration) {
    // Novo usuário do Google — precisa completar cadastro
    sessionStorage.setItem("gl_firebase_token", idToken);
    sessionStorage.setItem("gl_google_email", userCredential.user.email || "");
    window.location.href = "/gl/register?google=1";
    return null;
  }
  if (!res.ok) throw new Error(data.error || "Erro ao autenticar com Google");
  localStorage.setItem("gl_user", JSON.stringify(data.user));
  return data.user;
}

// ─── Logout ───────────────────────────────────────────────────────────────────

async function logout() {
  await fetch(`${API_BASE}/logout`, { method: "POST" }).catch(() => {});
  await signOut(auth);
  localStorage.removeItem("gl_user");
  window.location.href = "/gl/login";
}

// ─── Recuperar senha ──────────────────────────────────────────────────────────

async function forgotPassword(email) {
  await sendPasswordResetEmail(auth, email);
}

// ─── Observer de autenticação ─────────────────────────────────────────────────

/**
 * Observa mudanças no estado de autenticação.
 * Use para proteger páginas client-side.
 */
function onAuthChanged(callback) {
  return onAuthStateChanged(auth, callback);
}

// ─── Usuário atual do localStorage ────────────────────────────────────────────

function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem("gl_user"));
  } catch {
    return null;
  }
}

// ─── Exporta ──────────────────────────────────────────────────────────────────

export {
  auth,
  register,
  login,
  loginWithGoogle,
  logout,
  forgotPassword,
  onAuthChanged,
  getCurrentUser,
  getIdToken,
  apiRequest,
};
