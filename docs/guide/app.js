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

// ==== THREADS ====
function newThread() {
  current = { id: Date.now().toString(), title: "New Conversation", messages: [] };
  store.upsert(current);
  renderHistory();
  renderMessages();
}

function renderHistory() {
  const list = store.all();
  els.history.innerHTML = list.map(t =>
    `<div class="thread ${current && current.id === t.id ? 'active' : ''}" data-id="${t.id}">
      ${t.title}
    </div>`
  ).join('');
  [...els.history.querySelectorAll('.thread')].forEach(div => {
    div.onclick = () => {
      current = list.find(t => t.id === div.dataset.id);
      renderMessages();
      renderHistory();
    };
  });
}

function renderMessages() {
  if (!current) return;
  els.messages.innerHTML = current.messages.map(m =>
    `<div class="msg ${m.role}"><b>${m.role}:</b> ${m.content}</div>`
  ).join('');
}

// ==== API CALLS ====
async function checkHealth() {
  try {
    const res = await fetch(HEALTH_URL, { headers: COMMON_HEADERS });
    const data = await res.json();
    els.health.textContent = `✅ API OK @ ${data.now}`;
  } catch {
    els.health.textContent = "❌ API unreachable";
  }
}

async function sendMessage() {
  if (!current) newThread();
  const text = els.input.value.trim();
  if (!text) return;

  const userMsg = { role: "user", content: text, ts: Date.now() };
  current.messages.push(userMsg);
  renderMessages();
  store.upsert(current);
  els.input.value = "";

  try {
    const res = await fetch(CHAT_URL, {
      method: "POST",
      headers: COMMON_HEADERS,
      body: JSON.stringify({ messages: current.messages })
    });
    const data = await res.json();
    const reply = data.choices[0].message;
    const aiMsg = { role: "assistant", content: reply.content, ts: Date.now() };
    current.messages.push(aiMsg);
    renderMessages();
    store.upsert(current);
  } catch (err) {
    console.error("Chat error", err);
  }
}

// ==== EVENTS ====
els.send.onclick = sendMessage;
els.newThread.onclick = newThread;

// ==== INIT ====
checkHealth();
renderHistory();
