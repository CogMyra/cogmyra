// ===== Config =====
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;
const APP_KEY    = "abc123"; // must match your Worker FRONTEND_APP_KEY

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

// ===== Local storage model =====
// threads: { [threadId]: { id, title, createdAt, messages: [{role,content}] } }
const LS_KEY = "cogmyra_guide_threads_v1";
let threads = loadThreads();
let activeId = null;

// ===== Storage helpers =====
function loadThreads() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    return obj && typeof obj === "object" ? obj : {};
  } catch { return {}; }
}
function saveThreads() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(threads)); }
  catch (e) { console.warn("failed to save threads", e); }
}
function createThread(title = "New Chat") {
  const id = crypto.randomUUID();
  threads[id] = {
    id,
    title,
    createdAt: Date.now(),
    messages: [{ role: "assistant", content: "New chat started. How can I help?" }]
  };
  saveThreads();
  return id;
}
function setActive(id) {
  activeId = id;
  renderThreads();
  renderFeed();
  inputEl.focus();
}
function current() {
  if (!activeId || !threads[activeId]) {
    const id = createThread("New Chat");
    setActive(id);
  }
  return threads[activeId];
}

// ===== UI helpers =====
function clear(el){ while(el.firstChild) el.removeChild(el.firstChild); }
function bubble(role, text, kind="") {
  const d = document.createElement("div");
  d.className = `msg ${role}${kind ? " " + kind : ""}`;
  d.textContent = text;
  feedEl.appendChild(d);
  feedEl.scrollTop = feedEl.scrollHeight;
  return d;
}
function renderFeed() {
  clear(feedEl);
  const t = current();
  for (const m of t.messages) bubble(m.role, m.content, m.kind || "");
}
function renderThreads() {
  clear(threadsEl);
  // sort newest first
  const arr = Object.values(threads).sort((a,b)=>b.createdAt-a.createdAt);
  for (const t of arr) {
    const d = document.createElement("div");
    d.className = "thread";
    d.textContent = t.title || "Untitled";
    if (t.id === activeId) d.style.borderColor = "#33507a";
    d.addEventListener("click", ()=> setActive(t.id));
    threadsEl.appendChild(d);
  }
}
function updateTitleFromFirstUserMessage(t) {
  const firstUser = t.messages.find(m=>m.role==="user");
  if (firstUser) {
    const newTitle = firstUser.content.slice(0, 40);
    if (newTitle && newTitle !== t.title) {
      t.title = newTitle;
      saveThreads();
      renderThreads();
    }
  }
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
    const r = await fetch(HEALTH_URL, { headers: { "x-app-key": APP_KEY } });
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
  const body = { messages: [{ role: "user", content: userText }] };
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
  try { data = await r.json(); }
  catch { throw new Error(`Bad JSON from proxy (status ${r.status})`); }

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

  const t = current();

  inputEl.value = "";
  disableComposer(true);

  // push + render user
  t.messages.push({ role: "user", content: text });
  saveThreads();
  renderFeed();
  updateTitleFromFirstUserMessage(t);

  // typing stub (optional)
  const stub = { role: "assistant", content: "…" , kind: "pending" };
  t.messages.push(stub);
  saveThreads();
  renderFeed();

  try {
    const { text: reply, model } = await postChat(text);
    // replace stub
    const idx = t.messages.indexOf(stub);
    if (idx !== -1) t.messages.splice(idx, 1, { role: "assistant", content: reply });
    else t.messages.push({ role: "assistant", content: reply });
    saveThreads();
    renderFeed();
    if (model) modelTag.textContent = `· ${model}`;
  } catch (e) {
    console.error("[chat] error:", e);
    const idx = t.messages.indexOf(stub);
    if (idx !== -1) t.messages.splice(idx, 1, { role: "assistant", content: "Sorry—request failed. Check console/logs.", kind: "error" });
    else t.messages.push({ role: "assistant", content: "Sorry—request failed. Check console/logs.", kind: "error" });
    saveThreads();
    renderFeed();
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
  const id = createThread("New Chat");
  setActive(id);
}

// ===== Wire up =====
sendBtn.addEventListener("click", handleSend);
inputEl.addEventListener("keydown", handleEnterToSend);
newChat.addEventListener("click", handleNewChat);
pingBtn.addEventListener("click", pingHealth);

// ===== Initial paint =====
if (!Object.keys(threads).length) {
  const id = createThread("Welcome");
  setActive(id);
} else {
  // keep last-open thread selected (latest by createdAt)
  const latest = Object.values(threads).sort((a,b)=>b.createdAt-a.createdAt)[0];
  setActive(latest.id);
}
pingHealth();
inputEl.focus();
