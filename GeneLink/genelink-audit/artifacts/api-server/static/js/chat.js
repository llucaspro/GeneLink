// ── Chat via HTTP Polling ────────────────────────────────────────────────────

let currentUser = null;
let lastMessageId = 0;
let pollInterval = null;
let sending = false;

document.addEventListener("DOMContentLoaded", () => {
  if (!requireAuth()) return;
  injectNavbar("/gl/chat");
  currentUser = getUser();
  loadHistory();
  startPolling();

  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg || sending) return;
    sending = true;
    input.disabled = true;
    try {
      const res = await apiFetch("/chat/messages", {
        method: "POST",
        body: JSON.stringify({ message: msg }),
      });
      if (res.ok) {
        input.value = "";
        await poll();
      } else {
        const err = await res.json().catch(() => ({}));
        showBanner(err.error || "Erro ao enviar mensagem", "error");
      }
    } catch {
      showBanner("Erro de conexão", "error");
    } finally {
      sending = false;
      input.disabled = false;
      input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.dispatchEvent(new Event("submit"));
    }
  });
});

async function loadHistory() {
  setStatus("Carregando…", "muted");
  try {
    const res = await apiFetch("/chat/messages");
    if (!res.ok) throw new Error();
    const data = await res.json();
    const messages = data.messages || [];
    const container = document.getElementById("chat-messages");
    container.innerHTML = "";
    if (!messages.length) {
      container.innerHTML = `<div class="empty-state" style="flex:1">
        <div class="empty-state-icon">💬</div>
        <h3>Nenhuma mensagem ainda</h3>
        <p style="font-size:.85rem;margin-top:6px">Seja o primeiro a iniciar a conversa!</p>
      </div>`;
    } else {
      messages.forEach((m) => appendMessage(m));
      scrollToBottom();
      lastMessageId = messages[messages.length - 1].id;
    }
    setStatus("● Ao vivo", "success");
  } catch {
    setStatus("Erro ao carregar", "error");
  }
}

function startPolling() {
  pollInterval = setInterval(poll, 2000);
}

async function poll() {
  try {
    const res = await apiFetch(`/chat/messages?after=${lastMessageId}`);
    if (!res.ok) return;
    const data = await res.json();
    const messages = data.messages || [];
    if (!messages.length) return;
    const container = document.getElementById("chat-messages");
    const emptyState = container.querySelector(".empty-state");
    if (emptyState) container.innerHTML = "";
    const atBottom = isAtBottom();
    messages.forEach((m) => appendMessage(m));
    if (atBottom) scrollToBottom();
    lastMessageId = messages[messages.length - 1].id;
  } catch {
    // silently ignore transient poll errors
  }
}

function appendMessage(msg) {
  const container = document.getElementById("chat-messages");
  const isMine = currentUser && msg.username === currentUser.username;
  const initials = (msg.avatar_initials || msg.username.slice(0, 2)).toUpperCase();
  const div = document.createElement("div");
  div.className = "chat-msg";
  div.dataset.id = msg.id;
  if (isMine) div.style.flexDirection = "row-reverse";
  div.innerHTML = `
    <div class="avatar-sm" style="width:32px;height:32px;font-size:.78rem;flex-shrink:0;${isMine ? "background:var(--accent)" : ""}">${escHtml(initials)}</div>
    <div class="chat-msg-content" style="${isMine ? "text-align:right" : ""}">
      <div class="chat-msg-header" style="${isMine ? "flex-direction:row-reverse" : ""}">
        <span class="chat-username">${escHtml(msg.username)}</span>
        <span class="chat-time">${formatTime(msg.created_at)}</span>
      </div>
      <div class="chat-text" style="${isMine
        ? "background:var(--primary);color:#fff;padding:7px 12px;border-radius:12px 4px 12px 12px;display:inline-block;text-align:left"
        : "background:var(--surface-alt);padding:7px 12px;border-radius:4px 12px 12px 12px;display:inline-block"
      }">${escHtml(msg.message)}</div>
    </div>`;
  container.appendChild(div);
}

function isAtBottom() {
  const c = document.getElementById("chat-messages");
  return c.scrollHeight - c.scrollTop - c.clientHeight < 80;
}

function scrollToBottom() {
  const c = document.getElementById("chat-messages");
  c.scrollTop = c.scrollHeight;
}

function setStatus(text, type) {
  const el = document.getElementById("connection-status");
  if (!el) return;
  const colors = { success: "var(--success)", warning: "var(--warning)", error: "var(--danger)", muted: "var(--text-muted)" };
  el.textContent = text;
  el.style.color = colors[type] || "var(--text-muted)";
}

function showBanner(msg, type) {
  const el = document.getElementById("chat-banner");
  if (!el) return;
  el.textContent = msg;
  el.className = `alert alert-${type} show`;
  setTimeout(() => { el.className = "alert"; }, 4000);
}

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function escHtml(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
