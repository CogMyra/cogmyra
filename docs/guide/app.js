// ==== CONFIG ====
// Point this to your Worker / API that calls your CogMyra GPT.
// If you kept my earlier health endpoint, set both below to your domain.
const API_BASE   = "https://api.cogmyra.com";       // <— change if needed
const CHAT_URL   = `${API_BASE}/api/chat`;          // POST  {threadId?, email?, age?, speak?, speed?, message}
// Optional health check (GET -> {ok:true})
const HEALTH_URL = `${API_BASE}/api/health`;

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

// --- UI helpers ---
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

function renderHistory(){
  els.history.innerHTML = '';
  const list = store.all();
  for (const t of list) {
    const first = t.messages?.find(m => m.role === 'user')?.content || 'New chat';
    const when = new Date(t.updated || Date.now()).toLocaleString();
    els.history.append(
      el('div', {class:'item', onclick: () => loadThread(t.id)},
        first.length > 60 ? first.slice(0, 60) + '…' : first,
        el('small', {}, when)
      )
    );
  }
}

function renderMessages(){
  els.messages.innerHTML = '';
  if (!current) return;
  for (const m of current.messages) {
    els.messages.append(
      el('div', {},
        el('div', {class:'meta'}, m.role === 'user' ? 'You' : 'CogMyra'),
        el('div', {class:'bubble ' + (m.role === 'user' ? 'me' : '')}, m.content)
      )
    );
  }
  els.messages.scrollTop = els.messages.scrollHeight;
}

function newThread(){
  current = { id: crypto.randomUUID(), title:'', messages:[], updated: Date.now() };
  store.upsert(current);
  renderHistory();
  renderMessages();
}

function loadThread(id){
  const t = store.all().find(x => x.id === id);
  if (!t) return;
  current = t;
  renderHistory();
  renderMessages();
}

// --- Speech synthesis ---
function speakText(text) {
  if (!els.speak.checked) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = Number(els.speed.value) || 1.0;
  window.speechSynthesis.speak(u);
}

// --- Networking ---
async function sendMessage() {
  const text = els.input.value.trim();
  if (!text) return;
  if (!current) newThread();

  // optimistic UI
  current.messages.push({ role:'user', content:text, ts:Date.now() });
  current.updated = Date.now();
  store.upsert(current);
  renderHistory();
  renderMessages();
  els.input.value = '';

  try {
    const payload = {
      threadId: current.id,
      email: els.email.value || undefined,
      age: els.age.value === 'auto' ? undefined : els.age.value,
      speak: !!els.speak.checked,
      speed: Number(els.speed.value) || 1.0,
      message: text
    };

    const res = await fetch(CHAT_URL, {
      method: 'POST',
      headers: { 'Content-Type':'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    // Support either {message: "..."} or stream text/plain
    let assistantText = '';
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      const data = await res.json();
      assistantText = data.message || data.reply || JSON.stringify(data);
    } else {
      assistantText = await res.text();
    }

    current.messages.push({ role:'assistant', content:assistantText, ts:Date.now() });
    current.updated = Date.now();
    store.upsert(current);
    renderHistory();
    renderMessages();
    speakText(assistantText);

  } catch (err) {
    const msg = `Error contacting API. ${err.message}`;
    current.messages.push({ role:'assistant', content: msg, ts:Date.now() });
    current.updated = Date.now();
    store.upsert(current);
    renderMessages();
  }
}

async function checkHealth(){
  try {
    const r = await fetch(HEALTH_URL, { cache:'no-store' });
    const ok = r.ok ? 'ok' : `down (HTTP ${r.status})`;
    els.health.textContent = `API: ${ok}`;
  } catch {
    els.health.textContent = 'API: unreachable';
  }
}

// --- Wire events ---
els.send.addEventListener('click', sendMessage);
els.input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
els.newThread.addEventListener('click', newThread);

els.speakBtn.addEventListener('click', async () => {
  // simple microphone capture -> inserts transcript into box (optional later)
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    alert('Speech recognition is not supported in this browser.');
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new SR(); rec.lang = 'en-US'; rec.interimResults = false; rec.maxAlternatives = 1;
  rec.onresult = (e) => { els.input.value = e.results[0][0].transcript; };
  rec.onerror = () => {}; rec.onend = () => {};
  rec.start();
});

// --- Boot ---
renderHistory();
if (store.all().length) loadThread(store.all()[0].id); else newThread();
checkHealth();
