// GeneLink — Private DMs

document.addEventListener("DOMContentLoaded", async () => {
  if (!requireAuth()) return;
  injectNavbar("/gl/dm");
  await loadConversations();

  // Abre conversa pela URL (?conv=ID)
  const params = new URLSearchParams(window.location.search);
  const convId = params.get("conv");
  if (convId) openConversation(parseInt(convId, 10));

  // Polling de mensagens não lidas no badge
  pollUnread();
});

let _activeConvId = null;
let _pollTimer    = null;
let _lastMsgId    = 0;
let _otherUsername = "";

// ── Conversas ────────────────────────────────────────────────────────────────

async function loadConversations() {
  try {
    const res  = await apiFetch("/dm/conversations");
    const data = await res.json();
    renderConvList(data.conversations || []);
  } catch {
    document.getElementById("dm-conv-list").innerHTML =
      '<div class="dm-empty-conv">Erro ao carregar conversas.</div>';
  }
}

function renderConvList(convs) {
  const list = document.getElementById("dm-conv-list");
  if (!convs.length) {
    list.innerHTML = `<div class="dm-empty-conv">
      Nenhuma conversa ainda.<br>
      Acesse o perfil de um pesquisador e clique em <strong>Enviar Mensagem</strong>.
    </div>`;
    return;
  }
  list.innerHTML = convs.map(c => {
    const initials = (c.other_initials || c.other_username.slice(0,2)).toUpperCase();
    const preview  = c.last_message
      ? (c.last_message.length > 38 ? c.last_message.slice(0, 38) + "…" : c.last_message)
      : "Conversa iniciada";
    const badge = c.unread > 0
      ? `<span class="dm-badge">${c.unread}</span>` : "";
    return `<div class="dm-conv-item${_activeConvId === c.id ? " active" : ""}"
                 onclick="openConversation(${c.id})"
                 id="conv-item-${c.id}">
      <div class="dm-conv-avatar">${initials}</div>
      <div class="dm-conv-info">
        <div class="dm-conv-name">@${c.other_username}</div>
        <div class="dm-conv-preview">${escHtml(preview)}</div>
      </div>
      ${badge}
    </div>`;
  }).join("");
}

// ── Abrir conversa ────────────────────────────────────────────────────────────

async function openConversation(convId) {
  _activeConvId = convId;
  _lastMsgId    = 0;
  _otherUsername = "";

  // Atualiza URL sem recarregar
  history.replaceState(null, "", `/gl/dm?conv=${convId}`);

  // Destaca item ativo
  document.querySelectorAll(".dm-conv-item").forEach(el => el.classList.remove("active"));
  const item = document.getElementById(`conv-item-${convId}`);
  if (item) item.classList.add("active");

  // Mostra área de chat
  document.getElementById("dm-welcome").style.display    = "none";
  document.getElementById("dm-header").style.display     = "flex";
  document.getElementById("dm-messages").style.display   = "flex";
  document.getElementById("dm-input-bar").style.display  = "flex";
  document.getElementById("dm-messages").innerHTML = '<div class="dm-loading">Carregando…</div>';

  // Busca mensagens
  await loadMessages(convId, true);

  // Inicia polling
  clearInterval(_pollTimer);
  _pollTimer = setInterval(() => pollMessages(convId), 3000);
}

async function loadMessages(convId, initial = false) {
  try {
    const url = initial
      ? `/dm/conversations/${convId}/messages`
      : `/dm/conversations/${convId}/messages?after=${_lastMsgId}`;
    const res  = await apiFetch(url);
    const data = await res.json();
    const msgs = data.messages || [];

    if (initial) {
      // Popula cabeçalho
      const first = msgs.find(m => !m.is_mine) || msgs[0];
      if (first) {
        setHeader(first.username, first.avatar_initials || first.username.slice(0,2));
      } else {
        // Sem mensagens ainda — tenta obter info da conversa
        const item = document.getElementById(`conv-item-${convId}`);
        if (item) {
          const name = item.querySelector(".dm-conv-name")?.textContent || "";
          const init = item.querySelector(".dm-conv-avatar")?.textContent || "";
          setHeader(name.replace("@",""), init);
        }
      }
      renderAllMessages(msgs, convId);
    } else {
      appendMessages(msgs, convId);
    }

    if (msgs.length) _lastMsgId = msgs[msgs.length - 1].id;

    // Remove badge da conversa ativa
    const item = document.getElementById(`conv-item-${convId}`);
    if (item) {
      const badge = item.querySelector(".dm-badge");
      if (badge) badge.remove();
    }
  } catch (e) {
    if (initial) {
      document.getElementById("dm-messages").innerHTML =
        '<div class="dm-loading">Erro ao carregar mensagens.</div>';
    }
  }
}

function setHeader(username, initials) {
  _otherUsername = username;
  document.getElementById("dm-hd-av").textContent   = (initials || username.slice(0,2)).toUpperCase();
  document.getElementById("dm-hd-name").textContent = `@${username}`;
  document.getElementById("dm-hd-sub").textContent  = "Pesquisador GeneLink";
  document.getElementById("dm-profile-link").href   = `/gl/user/${username}`;
}

function renderAllMessages(msgs, convId) {
  const box = document.getElementById("dm-messages");
  if (!msgs.length) {
    box.innerHTML = `<div class="dm-empty-conv" style="margin:auto">
      Nenhuma mensagem ainda. Diga olá! 👋
    </div>`;
    return;
  }
  box.innerHTML = msgs.map(m => msgHtml(m)).join("");
  box.scrollTop = box.scrollHeight;
}

function appendMessages(msgs, convId) {
  if (!msgs.length) return;
  const box = document.getElementById("dm-messages");
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;

  // Remove estado "nenhuma mensagem ainda" se existir
  const empty = box.querySelector(".dm-empty-conv");
  if (empty) empty.remove();

  msgs.forEach(m => {
    box.insertAdjacentHTML("beforeend", msgHtml(m));
  });
  if (atBottom) box.scrollTop = box.scrollHeight;

  // Atualiza preview na sidebar
  const lastMsg = msgs[msgs.length - 1];
  const item = document.getElementById(`conv-item-${convId}`);
  if (item && lastMsg) {
    const preview = item.querySelector(".dm-conv-preview");
    if (preview) preview.textContent =
      lastMsg.content.length > 38 ? lastMsg.content.slice(0,38) + "…" : lastMsg.content;
  }
}

function msgHtml(m) {
  const cls    = m.is_mine ? "mine" : "them";
  const wrapCls= m.is_mine ? "mine" : "";
  const init   = (m.avatar_initials || m.username.slice(0,2)).toUpperCase();
  const time   = m.created_at ? formatDateTime(m.created_at) : "";
  const flag   = m.is_flagged && m.is_mine
    ? `<div class="dm-flagged-note">⚠ Mensagem em análise pela moderação</div>` : "";
  return `<div class="dm-bubble-wrap ${wrapCls}">
    ${!m.is_mine ? `<div class="dm-bubble-av">${init}</div>` : ""}
    <div>
      <div class="dm-bubble ${cls}">${escHtml(m.content)}</div>
      <div class="dm-bubble-time">${time}</div>
      ${flag}
    </div>
  </div>`;
}

// ── Enviar mensagem ───────────────────────────────────────────────────────────

const sendBtn  = document.getElementById("dm-send-btn");
const inputEl  = document.getElementById("dm-input");

if (sendBtn) sendBtn.addEventListener("click", sendMessage);
if (inputEl) {
  inputEl.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  // Auto-resize textarea
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
  });
}

async function sendMessage() {
  const content = inputEl.value.trim();
  if (!content || !_activeConvId) return;

  sendBtn.disabled = true;
  inputEl.value    = "";
  inputEl.style.height = "auto";

  try {
    const res  = await apiFetch(`/dm/conversations/${_activeConvId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    const data = await res.json();
    if (!res.ok) { alert(data.error || "Erro ao enviar"); return; }
    appendMessages([{ ...data, is_mine: true }], _activeConvId);
    _lastMsgId = data.id;
  } catch {
    alert("Erro ao enviar mensagem.");
  } finally {
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

// ── Polling ───────────────────────────────────────────────────────────────────

async function pollMessages(convId) {
  if (_activeConvId !== convId) return;
  await loadMessages(convId, false);
}

async function pollUnread() {
  const updateBadge = async () => {
    try {
      const res  = await apiFetch("/dm/unread");
      const data = await res.json();
      const n = data.unread || 0;
      const badge = document.getElementById("dm-unread-badge");
      if (badge) {
        badge.textContent = n;
        badge.style.display = n > 0 ? "inline-block" : "none";
      }
      // Atualiza badge do link na navbar
      const navBadge = document.getElementById("dm-nav-badge");
      if (navBadge) {
        navBadge.textContent = n;
        navBadge.style.display = n > 0 ? "inline-flex" : "none";
      }
    } catch {}
  };
  updateBadge();
  setInterval(updateBadge, 15000);
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br>");
}
