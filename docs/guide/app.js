// ==== CONFIG ====
// Point this to your Worker / API that calls your CogMyra GPT.
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;

// This must match the Worker secret you set.
const APP_KEY = "abc123";

// Reusable headers for all requests from the guide.
const COMMON_HEADERS = {
  "content-type": "application/json",
  "x-app-key": APP_KEY,
};

// ==== ELEMENTS ====
const els = {
  history:  document.getElementById('history'),
  messages: document.getElementById('messages'),
  email:    document.getElementById('email'),
  age:      document.getElementById('age'),
  speak:    document.getElementById('speak'),
  speed:    document.getElementById('speed'),
  input:    document.getElementById('input'),
  send:     document.getElementById('send'),
  speakBtn: document.getElementById('speakBtn'),
  newThread:document.getElementById('newThread'),
  health:   document.getElementById('health'),
};

// ==== LOCAL STORAGE ====
const store = {
  key: 'cm.guide.threads',
  all() {
    try { return JSON.parse(localStorage.getItem(this.key) || '[]'); }
    catch { return []; }
  },
  save(list) { localStorage.setItem(this.key, JSON.stringify(list)); },
  upsert(thread) {
    const list = this.all();
    const i = list.findIndex(t => t.id === thread.id);
    if (i >= 0) list[i] = thread; else list.unshift(thread);
    this.save(list);
  },
};

let current = null;     // {id, title, messages:[{role,content,ts}]}
let speaking = false;

// ==== UI HELPERS ====
function el(tag, attrs={}, ...children){
  const n = document.createElement(tag);
  Object.entries(attrs).forEach(([k,v]) => {
    if (k === 'class') n.className = v;
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else if (v != null) n.setAttribute(k, v);
  });
  children.forEach(c => n.append(c));
  return n;
}

function renderThreadList(){
  els.history.innerHTML = "";
  store.all().forEach(t => {
    const btn = el("button", {
      class:"thread-btn",
      onclick: () => loadThread(t.id)
    }, t.title || "(untitled)");
    els.history.append(btn);
  });
}

function renderMessages(){
  els.messages.innerHTML = "";
  current.messages.forEach(m => {
    const bubble = el("div", {class:`bubble ${m.role}`}, m.content);
    els.messages.append(bubble);
  });
  els.messages.scrollTop = els.messages.scrollHeight;
}

function loadThread(id){
  const thread = store.all().find(t => t.id === id);
  if (!thread) return;
  current = thread;
  renderMessages();
}

function newThread(){
  current = { id: Date.now().toString(), title:"New Chat", messages:[] };
  store.upsert(current);
  renderThreadList();
  renderMessages();
}

// ==== NETWORK ====
async function checkHealth(){
  try {
    const res = await fetch(HEALTH_URL, { headers: COMMON_HEADERS });
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    els.health.textContent = "✅ Online: " + data.now;
  } catch(e){
    els.health.textContent = "❌ Offline";
  }
}

async function sendMessage(){
  if (!current) newThread();
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = "";

  current.messages.push({role:"user", content:text, ts:Date.now()});
  renderMessages();
  store.upsert(current);

  try {
    const res = await fetch(CHAT_URL, {
      method:"POST",
      headers: COMMON_HEADERS,
      body: JSON.stringify({ messages: current.messages })
    });
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    const reply = data.choices?.[0]?.message?.content || "(no reply)";
    current.messages.push({role:"assistant", content:reply, ts:Date.now()});
    renderMessages();
    store.upsert(current);
  } catch(e){
    current.messages.push({role:"assistant", content:"[Error: "+e.message+"]", ts:Date.now()});
    renderMessages();
  }
}

// ==== INIT ====
els.send.onclick = sendMessage;
els.newThread.onclick = newThread;
checkHealth();
renderThreadList();
