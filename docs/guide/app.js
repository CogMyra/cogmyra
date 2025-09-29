// =================== CONFIG ===================
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;

// This must equal your Wrangler secret FRONTEND_APP_KEY
const APP_KEY = "abc123";

// Shared headers
const COMMON_HEADERS = {
  "content-type": "application/json",
  "x-app-key": APP_KEY,
};

// =================== ELEMENTS ===================
const els = {
  history:  document.getElementById("history"),
  messages: document.getElementById("messages"),
  input:    document.getElementById("input"),
  send:     document.getElementById("send"),
  check:    document.getElementById("check"),
  health:   document.getElementById("health"),
};

// Minimal local “threads”
const store = {
  key: "cm.guide.threads",
  all() { try { return JSON.parse(localStorage.getItem(this.key) || "[]"); } catch { return []; } },
  save(list) { localStorage.setItem(this.key, JSON.stringify(list)); },
  upsert(thread) {
    const list = this.all();
    const i = list.findIndex(t => t.id === thread.id);
    if (i >= 0) list[i] = thread; else list.unshift(thread);
    this.save(list);
  }
};

let current = null; // {id,title,messages:[{role,content,ts}]}

// =================== UI HELPERS ===================
function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k,v]) => {
    if (k === "class") n.className = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  });
  children.forEach(c => n.append(c));
  return n;
}

function renderThreadList() {
  const list = store.all();
  const wrap = els.history.querySelector(".scroll");
  if (!wrap) return;
  wrap.innerHTML = "";
  list.forEach(t => {
    const btn = el("button", { class: "btn block", onclick: () => openThread(t.id) }, t.title || "Chat");
    wrap.append(btn);
  });
}

function openThread(id) {
  const t = store.all().find(x => x.id === id);
  if (!t) return;
  current = t;
  drawMessages();
}

function newThread() {
  current = { id: "t_" + Math.random().toString(36).slice(2), title: "New Chat", messages: [] };
  store.upsert(current);
  renderThreadList();
  drawMessages();
}

function drawMessages() {
  const m = els.messages;
  m.innerHTML = "";
  if (!current) return;
  current.messages.forEach(msg => {
    const bubble = el("div", { class: "bubble " + (msg.role === "user" ? "user" : "ai") }, msg.content);
    m.append(bubble);
  });
  m.scrollTop = m.scrollHeight;
}

function showError(text) {
  const bubble = el("div", { class: "bubble ai" }, `⚠️ ${text}`);
  els.messages.append(bubble);
  els.messages.scrollTop = els.messages.scrollHeight;
}

// =================== NETWORK ===================

// Health check (button at bottom-left)
async function checkHealth() {
  els.health.textContent = "Checking…";
  try {
    const r = await fetch(HEALTH_URL, { headers: COMMON_HEADERS, mode: "cors", method: "GET" });
    const txt = await r.text(); // show raw so CORS/status are obvious
    els.health.textContent = `Health ${r.status}: ${txt}`;
    console.log("[health] status:", r.status, "raw:", txt);
  } catch (e) {
    els.health.textContent = "Health error";
    console.error("[health] error:", e);
  }
}

// Main chat call — no AbortController, detailed error reporting
async function sendToAPI(messages) {
  // Defensive JSON build
  const body = JSON.stringify({ messages });

  let resp;
  try {
    resp = await fetch(CHAT_URL, {
      method: "POST",
      mode: "cors",
      headers: COMMON_HEADERS,
      body
    });
  } catch (e) {
    // Network-layer error (DNS, CORS cancellation, offline, etc.)
    console.error("[chat] fetch threw:", e);
    throw new Error("Failed to reach API (network/CORS). See console.");
  }

  // Read body as text first so we can log non-JSON error payloads
  const raw = await resp.text();
  console.log("[chat] status:", resp.status, "raw:", raw);

  if (!resp.ok) {
    // Our Worker returns JSON on 401 with providedLength; show it if present
    try {
      const j = JSON.parse(raw);
      const reason = j.reason ? ` (${j.reason})` : "";
      const pl = typeof j.providedLength === "number" ? `, providedLength=${j.providedLength}` : "";
      throw new Error(`API ${resp.status}: ${j.error || "error"}${reason}${pl}`);
    } catch {
      throw new Error(`API ${resp.status}: ${raw || "Unknown error"}`);
    }
  }

  // Parse OpenAI-like JSON
  try {
    const data = JSON.parse(raw);
    const content = data?.choices?.[0]?.message?.content ?? "(no content)";
    return content;
  } catch (e) {
    console.error("[chat] JSON parse error:", e, "raw:", raw);
    throw new Error("Invalid JSON from API (see console).");
  }
}

// =================== EVENTS ===================
async function onSend() {
  const text = (els.input.value || "").trim();
  if (!text) return;
  if (!current) newThread();

  current.messages.push({ role: "user", content: text, ts: Date.now() });
  store.upsert(current);
  els.input.value = "";
  drawMessages();

  try {
    const reply = await sendToAPI(current.messages);
    current.messages.push({ role: "assistant", content: reply, ts: Date.now() });
    store.upsert(current);
    drawMessages();
  } catch (e) {
    showError(String(e.message || e));
  }
}

function wireUI() {
  // Build left pane if not present
  if (!els.history.querySelector(".scroll")) {
    const pane = document.createElement("div");
    pane.className = "history panel";
    els.history.appendChild(pane);
  }
  if (!document.getElementById("new-thread-btn")) {
    const header = el("div", { style: "padding:12px; border-bottom:1px solid #24304b;" }, el("h3", {}, "History"));
    const scroll = el("div", { class: "scroll" });
    els.history.innerHTML = "";
    els.history.append(header, scroll, el("button", { id: "new-thread-btn", class: "btn block", onclick: newThread }, "+ New Chat"));
  }

  els.send.addEventListener("click", onSend);
  els.input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }});
  if (els.check) els.check.addEventListener("click", checkHealth);

  // Initial state
  renderThreadList();
  if (!store.all().length) newThread();
}

document.addEventListener("DOMContentLoaded", wireUI);
