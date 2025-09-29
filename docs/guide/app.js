// ==== CONFIG ====
// Your Cloudflare Worker base URL
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;

// This MUST match the Worker secret FRONTEND_APP_KEY
const APP_KEY = "abc123";

// Common headers we send on every request (includes x-app-key!)
const COMMON_HEADERS = {
  "content-type": "application/json",
  "x-app-key": APP_KEY,
};

// ==== ELEMENTS ====
const els = {
  history:  document.getElementById("history"),
  messages: document.getElementById("messages"),
  input:    document.getElementById("input"),
  send:     document.getElementById("send"),
  newThread:document.getElementById("newThread"),
};

// ==== MINI STORE (local history) ====
const store = {
  key: "cm.guide.threads",
  all() { try { return JSON.parse(localStorage.getItem(this.key) || "[]"); } catch { return []; } },
  save(list) { localStorage.setItem(this.key, JSON.stringify(list)); },
  upsert(thread) {
    const list = this.all();
    const i = list.findIndex(t => t.id === thread.id);
    if (i >= 0) list[i] = thread; else list.unshift(thread);
    this.save(list);
  },
};

let current = null; // {id, title, messages:[{role,content,ts}]}

// ==== UI HELPERS ====
function el(tag, attrs={}, ...children){
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k,v]) => {
    if (k === "class") n.className = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v != null) n.setAttribute(k, v);
  });
  children.forEach(c => n.append(c));
  return n;
}

function bubble(role, text){
  return el("div", { class: `bubble ${role === "user" ? "user" : "ai"}` }, text);
}

function renderThread(thread){
  els.messages.innerHTML = "";
  thread.messages.forEach(m => els.messages.append(bubble(m.role, m.content)));
  els.messages.scrollTop = els.messages.scrollHeight;
}

function pickTitleFromFirstUserMsg(text) {
  const t = text.trim();
  if (!t) return "New chat";
  return t.length > 60 ? t.slice(0, 57) + "…" : t;
}

// ==== NETWORK HELPERS ====
async function safeJson(res){
  // If not OK, try to read text so errors are clear in the console.
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${text || res.statusText}`);
  }
  return res.json();
}

async function healthCheck(){
  try {
    const res = await fetch(HEALTH_URL, { method: "GET", headers: COMMON_HEADERS });
    const data = await safeJson(res);
    console.log("health:", data);
  } catch (e) {
    console.error("health failed:", e);
  }
}

// ==== ACTIONS ====
async function send(){
  const text = (els.input.value || "").trim();
  if (!text) return;

  // Start (or update) thread
  if (!current) {
    current = { id: crypto.randomUUID(), title: pickTitleFromFirstUserMsg(text), messages: [] };
    store.upsert(current);
    drawHistory();
  }
  current.messages.push({ role: "user", content: text, ts: Date.now() });
  renderThread(current);
  els.input.value = "";

  try {
    const res = await fetch(CHAT_URL, {
      method: "POST",
      headers: COMMON_HEADERS, // <— sends x-app-key and content-type
      body: JSON.stringify({ messages: current.messages }),
    });
    const data = await safeJson(res);

    const ai = data?.choices?.[0]?.message?.content || "(no response)";
    current.messages.push({ role: "assistant", content: ai, ts: Date.now() });
    store.upsert(current);
    renderThread(current);
  } catch (err) {
    console.error("chat failed:", err);
    current.messages.push({ role: "assistant", content: `Error: ${err.message}`, ts: Date.now() });
    renderThread(current);
  }
}

function drawHistory(){
  const list = store.all();
  const box = els.history.querySelector(".scroll");
  box.innerHTML = "";
  list.forEach(t => {
    const item = el("div", { class: "item", onclick(){ current = t; renderThread(current); } },
      el("div", {}, t.title || "Untitled"),
      el("small", {}, new Date(t.messages?.[0]?.ts || Date.now()).toLocaleString())
    );
    box.append(item);
  });
}

// ==== WIRE UP ====
window.addEventListener("DOMContentLoaded", () => {
  drawHistory();
  els.send.addEventListener("click", send);
  els.input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) send(); });
  els.newThread.addEventListener("click", () => { current = null; els.messages.innerHTML = ""; });
  healthCheck();
});
