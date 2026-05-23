// Supabase Auth — Login social (Google, GitHub)
// As credenciais são carregadas do backend via /gl/api/supabase-config
// Para ativar: adicione SUPABASE_URL e SUPABASE_ANON_KEY nos secrets do Replit

let supabaseClient = null;

async function initSupabase() {
  try {
    const res = await fetch("/gl/api/supabase-config");
    if (!res.ok) return;
    const config = await res.json();
    if (!config.url || !config.anon_key) return;

    supabaseClient = supabase.createClient(config.url, config.anon_key);

    // Exibe os botões de login social
    document.getElementById("social-login").style.display = "block";

    // Verifica se voltou de um redirect OAuth
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (session) {
      await handleSupabaseSession(session);
    }
  } catch (e) {
    // Supabase não configurado — botões permanecem ocultos
  }
}

async function loginComGoogle() {
  if (!supabaseClient) return;
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin + "/gl/login" }
  });
  if (error) alert("Erro ao entrar com Google: " + error.message);
}

async function loginComGitHub() {
  if (!supabaseClient) return;
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "github",
    options: { redirectTo: window.location.origin + "/gl/login" }
  });
  if (error) alert("Erro ao entrar com GitHub: " + error.message);
}

async function handleSupabaseSession(session) {
  try {
    const res = await fetch("/gl/api/supabase-auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        access_token: session.access_token,
        user: session.user
      })
    });
    const data = await res.json();
    if (res.ok && data.token) {
      setAuth(data.token, data.user);
      window.location.href = "/gl/dashboard";
    } else {
      alert(data.error || "Falha ao autenticar com Supabase");
    }
  } catch {
    alert("Erro ao processar login social.");
  }
}

document.addEventListener("DOMContentLoaded", initSupabase);
