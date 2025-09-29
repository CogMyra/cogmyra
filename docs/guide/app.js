// --- Config ---
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;
const APP_KEY    = "abc123"; // must match FRONTEND_APP_KEY in your Worker

// --- DOM ---
const feedEl     = document.querySelector(".feed");
const inputEl    = document.querySelector(".composer input");
const sendBtn    = document.querySelector(".composer button.primary");

// --- Simple state (persisted) ---
const STORAGE_KEY = "cogmyra.thread.v1";
let thread = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");

// --- Helpers ---
function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(thread)); }

function bubble(role, text = "") {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  feedEl.appendChild(el);
  feedEl.scrollTop = feedEl.scrollHeight;
  return el;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// Typewriter: strict per-char
async function typewriter(el, text, delay = 15) {
  el.textContent = "";
  for (let i = 0; i < text.length; i++) {
    el.textContent += text[i];
    // keep scrolled to bottom while we type
    feedEl.scrollTop = feedEl.scrollHeight;
    await sleep(delay);
  }
}

async function sendChat(userText) {
  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-app-key": APP_KEY
    },
    body: JSON.stringify({ messages: [{ role: "user", content: userText }] })
  });

  if (!res.ok) {
    const err = await res.text().catch(()=>"");
    throw new Error(`HTTP ${res.status} ${res.statusText} ${err}`);
  }

  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content || "(no content)";
  return content;
}

// --- Wire UI ---
async function handleSend() {
  const userText = inputEl.value.trim();
  if (!userText) return;

  // Add user bubble immediately
  const u = bubble("user", userText);
  thread.push({ role: "user", content: userText });
  save();

  inputEl.value = "";
  inputEl.focus();

  // Placeholder assistant bubble we will type into
  const a = bubble("assistant", "…");

  try {
    const reply = await sendChat(userText);

    // typewriter effect into assistant bubble
    await typewriter(a, reply, 12);

    thread.push({ role: "assistant", content: reply });
    save();
  } catch (e) {
    a.classList.add("error");
    a.textContent = `Error: ${e.message}`;
    thread.push({ role: "assistant", content: a.textContent, error: true });
    save();
  }
}

// Enter key
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

// Click send
sendBtn.addEventListener("click", handleSend);

// --- Boot: render any stored thread & a greeting once ---
(function boot() {
  if (thread.length === 0) {
    bubble("assistant", "Hello, I’m CogMyra.");
    return;
  }
  for (const m of thread) {
    bubble(m.role, m.content);
  }
})();
