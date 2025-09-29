// ===== Config =====
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;
// Must match your Wrangler secret FRONTEND_APP_KEY
const APP_KEY    = "abc123";

// ===== DOM =====
const feedEl    = document.getElementById("feed");
const inputEl   = document.getElementById("composerInput");
const sendBtn   = document.getElementById("sendBtn");
const newChat   = document.getElementById("newChatBtn");
const pingBtn   = document.getElementById("pingBtn");
const healthDot = document.getElementById("healthDot");
const healthTxt = document.getElementById("healthText");
const modelTag  = document.getElementById("modelTag");
const threadsEl = document.getElementById("threads");

// Simple in-page “thread” memory (optional)
let threadId = crypto.randomUUID();
let history = [];

function addThreadCard(title) {
  const d = document.createElement("div");
  d.className = "thread";
  d.textContent = title;
  threadsEl.prepend(d);
}

// ===== UI helpers =====
function bubble(role, text, kind="") {
  const d = document.createElement("div");
  d.className = `msg ${role}${kind ? " " + kind : ""}`;
  d.textContent = text;
  feedEl.appendChild(d);
  feedEl.scrollTop = feedEl.scrollHeight;
  return d;
}
function setHealth(status, msg, model) {
  healthDot.classList.remove("dot-ok", "dot-bad", "dot-muted");
  if (status === "ok") healthDot.classList.add("dot-ok");
  else if (status === "bad") healthDot.classList.add("dot-bad");
  else healthDot.classList.add("dot-muted");
  healthTxt.textContent = msg;
  modelTag.textContent = model ? `· ${model}` : "";
}
function disableComposer(disabled) {
  sendBtn.disabled = disabled;
  inputEl.disabled = disabled;
}

// ===== Network =====
async function pingHealth() {
  try {
    const r = await fetch(HEALTH_URL, {
      headers: { "x-app-key": APP_KEY }
    });
    const modelHeader = r.headers.get("X-CogMyra-Model") || "";
    const json = await r.json().catch(() => ({}));
    const model = json.model || modelHeader || "";
    if (r.ok) setHealth("ok", "Healthy", model);
    else setHealth("bad", `Health ${r.status}`, model);
  } catch (e) {
    setHealth("bad", "Health error", "");
    console.error("[health] error:", e);
  }
}

async function postChat(userText) {
  const body = {
    // Your Worker injects SYSTEM_PROMPT + MODEL; messages can be simple.
    messages: [{ role: "user", content: userText }],
  };

  const r = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-app-key": APP_KEY,
    },
    body: JSON.stringify(body),
  });

  const modelHeader = r.headers.get("X-CogMyra-Model") || "";
  let data;
  try {
    data = await r.json();
  } catch {
    throw new Error(`Bad JSON from proxy (status ${r.status})`);
  }

  // Try to surface model + prompt hash in console for verification
  if (modelHeader) console.log("[proxy] model:", modelHeader);
  if (data.promptHash) console.log("[proxy] prompt hash:", data.promptHash);

  if (!r.ok) {
    const raw = typeof data === "object" ? JSON.stringify(data) : String(data);
    throw new Error(`Proxy error ${r.status}: ${raw}`);
  }

  const msg = data?.choices?.[0]?.message?.content ?? "";
  if (!msg) throw new Error("No assistant content in response");
  return { text: msg, model: data.model || modelHeader || "" };
}

// ===== Handlers =====
async function handleSend() {
  const text = inputEl.value.trim();
  if (!text) return;

  // Start a new “thread title” on first message
  if (history.length === 0) addThreadCard(text.slice(0, 40));

  inputEl.value = "";
  disableComposer(true);
  const userB = bubble("user", text);
  history.push({ role: "user", content: text });

  let assistantB;
  try {
    const { text: reply, model } = await postChat(text);
    assistantB = bubble("assistant", reply);
    history.push({ role: "assistant", content: reply });
    // keep health line fresh w/ model
    if (model) modelTag.textContent = `· ${model}`;
  } catch (e) {
    console.error("[chat] error:", e);
    assistantB = bubble("assistant", "Sorry—request failed. Check console/logs.", "error");
  } finally {
    disableComposer(false);
    inputEl.focus();
  }
}

function handleEnterToSend(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
}

function handleNewChat() {
  // reset in-page state
  history = [];
  threadId = crypto.randomUUID();
  feedEl.innerHTML = "";
  bubble("assistant", "New chat started. How can I help?");
  inputEl.focus();
}

// ===== Wire up =====
sendBtn.addEventListener("click", handleSend);
inputEl.addEventListener("keydown", handleEnterToSend);
newChat.addEventListener("click", handleNewChat);
pingBtn.addEventListener("click", pingHealth);

// Initial
pingHealth();
inputEl.focus();
