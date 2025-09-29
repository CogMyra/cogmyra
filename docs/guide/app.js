// ---------- Config ----------
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;
// This must equal your Wrangler secret FRONTEND_APP_KEY
const APP_KEY    = "abc123";

// ---------- DOM ----------
const feed        = document.getElementById("feed");
const input       = document.getElementById("input");
const sendBtn     = document.getElementById("send");
const newBtn      = document.getElementById("new-chat");
const threadsEl   = document.getElementById("threads");
const pingBtn     = document.getElementById("ping");
const dotSmall    = document.getElementById("dot");
const healthLabel = document.getElementById("health-label");
const topDot      = document.getElementById("health-dot");
const topText     = document.getElementById("health-text");
const modelBadge  = document.getElementById("model-badge");

// ---------- State ----------
let sessionId = crypto.randomUUID();
let threads = JSON.parse(localStorage.getItem("cm_threads") || "[]");

// ---------- Helpers ----------
function el(tag, cls, text="") {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}
function pushThreadPreview(prompt) {
  const title = prompt.length > 40 ? prompt.slice(0, 40) + "…" : prompt;
  threads.unshift({ id: sessionId, title, ts: Date.now() });
  threads = threads.slice(0, 30);
  localStorage.setItem("cm_threads", JSON.stringify(threads));
  renderThreads();
}
function renderThreads() {
  threadsEl.innerHTML = "";
  for (const t of threads) {
    const a = el("button", "thread", t.title);
    a.onclick = () => loadThread(t.id);
    threadsEl.appendChild(a);
  }
}
function loadThread(id) {
  sessionId = id;
  const saved = JSON.parse(localStorage.getItem("cm_msgs_" + id) || "[]");
  feed.innerHTML = "";
  for (const m of saved) {
    const bubble = el("div", `msg ${m.role}`);
    bubble.textContent = m.content;
    feed.appendChild(bubble);
  }
  feed.scrollTop = feed.scrollHeight;
}
function saveMessage(role, content) {
  const key = "cm_msgs_" + sessionId;
  const arr = JSON.parse(localStorage.getItem(key) || "[]");
  arr.push({ role, content });
  localStorage.setItem(key, JSON.stringify(arr));
}

// Typewriter render
async function typewriterAppend(text) {
  const bubble = el("div", "msg assistant");
  feed.appendChild(bubble);
  feed.scrollTop = feed.scrollHeight;

  for (const ch of text) {
    bubble.textContent += ch;
    await new Promise(r => setTimeout(r, 8)); // smooth typing
    if (bubble === null) break;
    feed.scrollTop = feed.scrollHeight;
  }
}

// Update health/model UI
function setHealth(ok, modelText) {
  const color = ok ? "#22c55e" : "#ef4444";
  dotSmall.style.background = color;
  topDot.style.background = color;
  healthLabel.textContent = ok ? "Healthy" : "Error";
  topText.textContent = ok ? "Healthy" : "Error";
  if (modelText) modelBadge.textContent = `Model: ${modelText}`;
}

// ---------- Network ----------
async function pingHealth() {
  try {
    const r = await fetch(HEALTH_URL, {
      headers: { "x-app-key": APP_KEY }
    });
    const json = await r.json();
    setHealth(true, json.model || "");
    return json.model || "";
  } catch (e) {
    setHealth(false);
    console.error(e);
    return "";
  }
}

async function sendChat(userText) {
  // Add user bubble
  const u = el("div", "msg user", userText);
  feed.appendChild(u);
  feed.scrollTop = feed.scrollHeight;

  saveMessage("user", userText);

  // POST to proxy (model decided by proxy; we don't set one here)
  const resp = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-app-key": APP_KEY
    },
    body: JSON.stringify({ messages: [{ role: "user", content: userText }] })
  });

  // Read exposed headers for proof
  const headerModel = resp.headers.get("X-CogMyra-Model");
  const headerHash  = resp.headers.get("X-CogMyra-Prompt-Hash");
  if (headerModel) modelBadge.textContent = `Model: ${headerModel}`;
  if (headerModel) setHealth(true, headerModel);

  let data;
  try { data = await resp.json(); } catch { data = {}; }

  if (!resp.ok || !data?.choices?.[0]?.message?.content) {
    const err = el("div", "msg error", "Error talking to CogMyra.");
    feed.appendChild(err);
    setHealth(false, headerModel || "");
    return;
  }

  const content = data.choices[0].message.content;

  // Typewriter the reply
  await typewriterAppend(content);
  saveMessage("assistant", content);

  // After first message, add to history rail
  if (!threads.find(t => t.id === sessionId)) {
    pushThreadPreview(userText);
  }
}

// ---------- Events ----------
sendBtn.onclick = async () => {
  const txt = (input.value || "").trim();
  if (!txt) return;
  input.value = "";
  await sendChat(txt);
};
input.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});
newBtn.onclick = () => {
  sessionId = crypto.randomUUID();
  feed.innerHTML = "";
  input.focus();
};
pingBtn.onclick = () => pingHealth();

// ---------- Boot ----------
renderThreads();
loadThread(sessionId);
(async () => {
  // Show an initial hello
  const hello = el("div", "msg assistant", "Hello, I’m CogMyra.");
  feed.appendChild(hello);

  // Check health/model on load and set badge
  const model = await pingHealth();
  if (!model) modelBadge.textContent = "Model: (unknown)";
})();
