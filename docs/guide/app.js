// ---------- Config ----------
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;
// must match your Wrangler secret FRONTEND_APP_KEY
const APP_KEY    = "abc123";

// ---------- State ----------
let threads = JSON.parse(localStorage.getItem("cm_threads") || "[]");
let activeThreadId = localStorage.getItem("cm_active") || null;

// ---------- DOM ----------
const feed   = document.querySelector("#feed");
const input  = document.querySelector("#input");
const form   = document.querySelector("#composer");
const ping   = document.querySelector("#ping");
const healthDot  = document.querySelector("#health-dot");
const healthText = document.querySelector("#health-text");
const newChatBtn = document.querySelector("#new-chat");
const threadsEl  = document.querySelector("#threads");

// ---------- Utilities ----------
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function saveThreads() {
  localStorage.setItem("cm_threads", JSON.stringify(threads));
  localStorage.setItem("cm_active", activeThreadId || "");
}

function getActiveThread() {
  let t = threads.find(t => t.id === activeThreadId);
  if (!t) {
    t = { id: crypto.randomUUID(), title: "New chat", msgs: [] };
    threads.unshift(t);
    activeThreadId = t.id;
    saveThreads();
  }
  return t;
}

function renderThreads() {
  threadsEl.innerHTML = "";
  threads.forEach(t => {
    const btn = document.createElement("button");
    btn.className = "thread";
    btn.textContent = t.title || "Chat";
    btn.onclick = () => {
      activeThreadId = t.id; saveThreads(); renderFeed();
    };
    threadsEl.appendChild(btn);
  });
}

function renderFeed() {
  const t = getActiveThread();
  feed.innerHTML = "";
  t.msgs.forEach(m => addMsgToFeed(m.role, m.content));
  feed.scrollTop = feed.scrollHeight;
}

function addMsgToFeed(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  feed.appendChild(div);
  return div;
}

async function typewriter(el, fullText, speed = 12) {
  el.textContent = "";
  for (let i = 0; i < fullText.length; i++) {
    el.textContent += fullText[i];
    // slightly faster for whitespace for nicer feel
    await sleep(fullText[i].trim() ? speed : Math.max(1, speed/2));
    feed.scrollTop = feed.scrollHeight;
  }
}

// ---------- Network ----------
async function pingHealth() {
  try {
    const res = await fetch(HEALTH_URL, { headers: { "x-app-key": APP_KEY } });
    const data = await res.json();
    healthDot.className = "dot dot-ok";
    healthText.textContent = "Healthy";
    // optional: show model/prompt hash in tooltip
    const model = res.headers.get("X-CogMyra-Model");
    const hash  = res.headers.get("X-CogMyra-Prompt-Hash");
    if (model || hash) healthText.title = `Model: ${model}\nPrompt: ${hash}`;
  } catch (e) {
    healthDot.className = "dot dot-bad";
    healthText.textContent = "Error";
  }
}

async function sendToLLM(messages) {
  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-app-key": APP_KEY
    },
    body: JSON.stringify({ messages })
  });
  if (!res.ok) throw new Error(`chat ${res.status}`);
  const data = await res.json();
  return data.choices?.[0]?.message?.content || "(no content)";
}

// ---------- Actions ----------
newChatBtn.onclick = () => {
  activeThreadId = null;
  renderFeed(); renderThreads();
};

ping.onclick = () => pingHealth();

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = (input.value || "").trim();
  if (!text) return;

  const thread = getActiveThread();
  // user bubble
  addMsgToFeed("user", text);
  thread.msgs.push({ role: "user", content: text });
  input.value = "";
  saveThreads();

  try {
    // call proxy
    const answer = await sendToLLM(thread.msgs);
    // assistant bubble (typewriter)
    const bubble = addMsgToFeed("assistant", "");
    await typewriter(bubble, answer, 12);

    // store
    thread.msgs.push({ role: "assistant", content: answer });
    // first AI message becomes thread title (simple)
    if (!thread.title || thread.title === "New chat") thread.title = text.slice(0, 32);
    saveThreads(); renderThreads();
  } catch (err) {
    const b = addMsgToFeed("assistant", "Sorry, something went wrong.");
    b.classList.add("error");
  }
});

// ---------- Boot ----------
renderThreads();
renderFeed();
pingHealth();

// greeting if empty
(() => {
  const t = getActiveThread();
  if (t.msgs.length === 0) {
    const hello = "Hello, I’m CogMyra.";
    addMsgToFeed("assistant", hello);
    t.msgs.push({ role: "assistant", content: hello });
    saveThreads();
  }
})();
