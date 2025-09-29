/* CogMyra Guide — frontend (GPT-5 safe)
   - Uses your Cloudflare proxy (/api/chat, /api/health)
   - NO temperature sent (GPT-5 rejects non-default values)
   - Typewriter output, simple history, “Checking…” health badge
*/

const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;
// Must match your Wrangler FRONTEND_APP_KEY
const APP_KEY    = "abc123";

/* ---------- DOM ---------- */
const feedEl     = document.querySelector(".feed");
const inputEl    = document.querySelector(".composer input");
const sendBtn    = document.querySelector(".composer button.primary");
const threadsEl  = document.querySelector(".threads");
const newChatBtn = document.querySelector(".topbar .primary");
const healthDot  = document.querySelector(".dot");
const healthLbl  = document.querySelector(".health-line");
const topbar     = document.querySelector(".topbar");

/* ---------- State ---------- */
let threadId = null;
const LS_THREADS = "cm_threads_v1";

/* ---------- Helpers ---------- */
function nowId() {
  return "t-" + Date.now().toString(36);
}
function saveThread(id, messages) {
  const all = JSON.parse(localStorage.getItem(LS_THREADS) || "{}");
  all[id] = { id, ts: Date.now(), messages };
  localStorage.setItem(LS_THREADS, JSON.stringify(all));
  renderThreads();
}
function loadThread(id) {
  const all = JSON.parse(localStorage.getItem(LS_THREADS) || "{}");
  return all[id] || null;
}
function listThreads() {
  const all = JSON.parse(localStorage.getItem(LS_THREADS) || "{}");
  return Object.values(all).sort((a,b)=>b.ts-a.ts);
}
function truncate(text, n=80){ return text.length>n? text.slice(0,n)+"…": text; }

/* ---------- UI builders ---------- */
function bubble(role, text, extraClass="") {
  const div = document.createElement("div");
  div.className = `msg ${role} ${extraClass}`.trim();
  div.textContent = text;
  return div;
}
function addBubble(role, text) {
  const el = bubble(role, text);
  feedEl.appendChild(el);
  feedEl.scrollTop = feedEl.scrollHeight;
  return el;
}
async function typewriter(el, text, delay=18) {
  el.textContent = "";
  for (const ch of text) {
    el.textContent += ch;
    // Keep view scrolled while typing
    feedEl.scrollTop = feedEl.scrollHeight;
    await new Promise(r => setTimeout(r, delay));
  }
}

/* ---------- Health badge ---------- */
async function checkHealth() {
  // Show temporary “Checking…”
  if (topbar && !topbar.dataset.healthOnce) {
    const s = document.createElement("span");
    s.style.marginLeft = "8px";
    s.style.fontSize = "12px";
    s.style.opacity = "0.85";
    s.textContent = " • Checking…";
    topbar.appendChild(s);
  }
  try {
    const res = await fetch(HEALTH_URL, {
      headers: { "x-app-key": APP_KEY }
    });
    const data = await res.json();
    if (healthDot) healthDot.className = "dot dot-ok";
    if (healthLbl) healthLbl.title = `Model: ${data.model || "unknown"}`;
    if (topbar && !topbar.dataset.healthOnce) {
      const ok = document.createElement("span");
      ok.style.marginLeft = "8px";
      ok.style.fontSize = "12px";
      ok.style.opacity = "0.85";
      ok.textContent = ` • ${data.model || "model"}`;
      topbar.appendChild(ok);
      topbar.dataset.healthOnce = "1";
    }
  } catch (e) {
    if (healthDot) healthDot.className = "dot dot-bad";
    if (topbar && !topbar.dataset.healthOnce) {
      const bad = document.createElement("span");
      bad.style.marginLeft = "8px";
      bad.style.fontSize = "12px";
      bad.style.opacity = "0.85";
      bad.textContent = " • Proxy error";
      topbar.appendChild(bad);
      topbar.dataset.healthOnce = "1";
    }
  }
}

/* ---------- Threads rail ---------- */
function renderThreads() {
  if (!threadsEl) return;
  threadsEl.innerHTML = "";
  for (const t of listThreads()) {
    const firstUser = (t.messages || []).find(m => m.role === "user");
    const btn = document.createElement("button");
    btn.className = "thread";
    btn.textContent = truncate(firstUser?.content || "New chat");
    btn.onclick = () => {
      threadId = t.id;
      drawThread(t.messages || []);
    };
    threadsEl.appendChild(btn);
  }
}
function drawThread(messages) {
  feedEl.innerHTML = "";
  for (const m of messages) {
    feedEl.appendChild(bubble(m.role, m.content));
  }
  feedEl.scrollTop = feedEl.scrollHeight;
}

/* ---------- Message gathering ---------- */
function currentMessages() {
  const nodes = [...feedEl.querySelectorAll(".msg")];
  return nodes.map(n => {
    const role = n.classList.contains("user") ? "user" : "assistant";
    return { role, content: n.textContent || "" };
  });
}

/* ---------- Chat send (NO temperature) ---------- */
async function sendMessage() {
  const text = (inputEl.value || "").trim();
  if (!text) return;

  // Ensure a thread
  if (!threadId) threadId = nowId();

  // User bubble
  const userEl = addBubble("user", text);

  // Placeholder assistant bubble (we'll type into it)
  const botEl = addBubble("assistant", "…");

  // Clear composer
  inputEl.value = "";
  inputEl.focus();

  try {
    const messages = [...currentMessages(), { role: "user", content: text }];

    const res = await fetch(CHAT_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-app-key": APP_KEY,
      },
      // IMPORTANT: no temperature for GPT-5
      body: JSON.stringify({ messages })
    });

    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content || "(no content)";
    await typewriter(botEl, content, 16);

    // Persist
    saveThread(threadId, currentMessages());
  } catch (err) {
    botEl.classList.add("error");
    botEl.textContent = "Error talking to CogMyra proxy.";
  }
}

/* ---------- Wire events ---------- */
function wireUI() {
  // Enter to send
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  sendBtn.addEventListener("click", sendMessage);

  // New chat
  if (newChatBtn) {
    newChatBtn.onclick = () => {
      threadId = nowId();
      feedEl.innerHTML = "";
      const hello = addBubble("assistant", "Hello, I’m CogMyra.");
      typewriter(hello, "Hello, I’m CogMyra.", 10); // quick intro
      saveThread(threadId, currentMessages());
    };
  }

  // Load latest or start fresh
  const latest = listThreads()[0];
  if (latest) {
    threadId = latest.id;
    drawThread(latest.messages || []);
  } else {
    threadId = nowId();
    const hello = addBubble("assistant", "Hello, I’m CogMyra.");
    typewriter(hello, "Hello, I’m CogMyra.", 10);
    saveThread(threadId, currentMessages());
  }

  renderThreads();
  checkHealth();
}

/* ---------- Boot ---------- */
document.addEventListener("DOMContentLoaded", wireUI);
