// ==== CONFIG ====
// Point this to your Worker / API that calls your CogMyra GPT.
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;

// This must match the Worker secret you set.
const APP_KEY = "abc123";

// Reusable headers for all requests from the guide.
const COMMON_HEADERS = {
  "Content-Type": "application/json",
  "x-app-key": APP_KEY,
};

// ==== ELEMENTS ====
const els = {
  history:  document.getElementById('history'), 
  messages: document.getElementById('messages'),
  input:    document.getElementById('input'),
  send:     document.getElementById('send'),
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

// ==== RENDERING ====
function renderThread(thread) {
  els.messages.innerHTML = '';
  for (const m of thread.messages) {
    const div = document.createElement('div');
    div.className = `bubble ${m.role}`;
    div.textContent = m.content;
    els.messages.appendChild(div);
  }
}

function addMessage(role, content) {
  const msg = { role, content, ts: Date.now() };
  current.messages.push(msg);
  renderThread(current);
  store.upsert(current);
}

// ==== EVENTS ====
els.send.onclick = async () => {
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = '';
  addMessage("user", text);

  try {
    const res = await fetch(CHAT_URL, {
      method: "POST",
      headers: COMMON_HEADERS,
      body: JSON.stringify({
        messages: current.messages.map(m => ({ role: m.role, content: m.content }))
      })
    });

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`HTTP ${res.status}: ${txt}`);
    }

    const data = await res.json();
    const reply = data.choices?.[0]?.message?.content || "(no reply)";
    addMessage("assistant", reply);
  } catch (err) {
    console.error("Chat error:", err);
    addMessage("assistant", "⚠️ Error: " + err.message);
  }
};

els.newThread.onclick = () => {
  current = { id: String(Date.now()), title: "New Chat", messages: [] };
  renderThread(current);
  store.upsert(current);
};

// ==== INIT ====
function init() {
  const list = store.all();
  if (list.length) {
    current = list[0];
    renderThread(current);
  } else {
    els.newThread.click();
  }
}
init();
