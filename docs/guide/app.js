/* CogMyra Guide — app.js (v3)
   Wires up the new HTML ids and talks to your Cloudflare Worker.
   - Click Send or press Enter to send a message
   - “New Chat” creates a fresh session
   - Health shows model + prompt hash from proxy headers
*/

//// ---- Config ----
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;

// Must match your Worker secret FRONTEND_APP_KEY
const APP_KEY = "abc123";

// Session: one per browser tab unless you press “New Chat”
let SESSION_ID = localStorage.getItem("cm.sessionId") || `cm-${Date.now()}`;
localStorage.setItem("cm.sessionId", SESSION_ID);

//// ---- DOM ----
const el = {
  feed: document.getElementById("feed"),
  input: document.getElementById("composer-input"),
  send: document.getElementById("send-btn"),
  threads: document.getElementById("threads"),
  newChat: document.getElementById("new-chat"),
  clearHistory: document.getElementById("clear-history"),
  healthDot: document.getElementById("health-dot"),
  healthText: document.getElementById("health-text"),
};

//// ---- Utilities ----
function bubble(role, text, opts = {}) {
  const div = document.createElement("div");
  div.className = `msg ${role}${opts.error ? " error" : ""}`;
  div.textContent = text;
  el.feed.appendChild(div);
  el.feed.scrollTop = el.feed.scrollHeight;
  return div;
}

function setHealth(status, text) {
  el.healthText.textContent = text;
  el.healthDot.classList.remove("dot-ok", "dot-bad", "dot-muted");
  el.healthDot.classList.add(
    status === "ok" ? "dot-ok" : status === "bad" ? "dot-bad" : "dot-muted"
  );
}

function saveThreadPreview(latestUserText = "") {
  try {
    const list = JSON.parse(localStorage.getItem("cm.threads") || "[]");
    const idx = list.findIndex((t) => t.id === SESSION_ID);
    const preview = latestUserText || list[idx]?.preview || "New conversation";
    const entry = { id: SESSION_ID, ts: Date.now(), preview };
    if (idx >= 0) list[idx] = entry; else list.unshift(entry);
    localStorage.setItem("cm.threads", JSON.stringify(list.slice(0, 30)));
    renderThreads();
  } catch {}
}

function renderThreads() {
  const list = JSON.parse(localStorage.getItem("cm.threads") || "[]");
  el.threads.innerHTML = "";
  list.forEach(({ id, preview }) => {
    const item = document.createElement("button");
    item.className = "thread";
    item.textContent = preview || id;
    item.onclick = () => {
      SESSION_ID = id;
      localStorage.setItem("cm.sessionId", SESSION_ID);
      // soft reset the UI for now (no persistence of feed bubbles)
      el.feed.innerHTML = "";
      bubble("assistant", "Picked thread: " + (preview || id));
    };
    el.threads.appendChild(item);
  });
}

function headers() {
  return {
    "content-type": "application/json",
    "x-app-key": APP_KEY,
  };
}

//// ---- Health check (on load & every 60s) ----
async function checkHealth() {
  setHealth("muted", "Checking…");
  try {
    const res = await fetch(HEALTH_URL, { headers: headers() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // Read exposed headers to confirm the proxy is applying your config
    const hModel = res.headers.get("X-CogMyra-Model");
    const hPrompt = res.headers.get("X-CogMyra-Prompt-Hash");
    const extras = [];
    if (hModel) extras.push(hModel);
    if (hPrompt) extras.push(hPrompt.slice(0, 8) + "…");
    setHealth("ok", extras.length ? `Healthy • ${extras.join(" • ")}` : "Healthy");
    return data;
  } catch (err) {
    console.error("[health] fail:", err);
    setHealth("bad", "Health check failed");
  }
}

//// ---- Send message ----
async function sendMessage() {
  const text = el.input.value.trim();
  if (!text) return;

  // UI: add user bubble
  bubble("user", text);
  saveThreadPreview(text);
  el.input.value = "";
  el.input.focus();
  el.send.disabled = true;

  try {
    const body = {
      sessionId: SESSION_ID,
      messages: [{ role: "user", content: text }],
      // You can pass a model here to override, but proxy already enforces one.
      // model: "gpt-4o-mini-2024-07-18"
    };

    const res = await fetch(CHAT_URL, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify(body),
    });

    // Auth / errors
    if (res.status === 401) {
      bubble("assistant", "Unauthorized — check your APP_KEY vs FRONTEND_APP_KEY.", { error: true });
      return;
    }
    if (!res.ok) {
      const raw = await res.text().catch(() => "");
      bubble("assistant", `Error ${res.status}: ${raw || "Request failed"}`, { error: true });
      return;
    }

    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content || "(no content)";
    bubble("assistant", content);
  } catch (err) {
    console.error("[chat] error:", err);
    bubble("assistant", "Network error. See console for details.", { error: true });
  } finally {
    el.send.disabled = false;
  }
}

//// ---- Events ----
el.send.addEventListener("click", sendMessage);
el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

el.newChat?.addEventListener("click", () => {
  SESSION_ID = `cm-${Date.now()}`;
  localStorage.setItem("cm.sessionId", SESSION_ID);
  el.feed.innerHTML = "";
  bubble("assistant", "New chat started.");
  saveThreadPreview("");
});

el.clearHistory?.addEventListener("click", () => {
  localStorage.removeItem("cm.threads");
  renderThreads();
  bubble("assistant", "History cleared.");
});

//// ---- Boot ----
renderThreads();
checkHealth();
setInterval(checkHealth, 60_000);
