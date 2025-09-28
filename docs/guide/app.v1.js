// Minimal, dependency-free Guide wiring.
// Safe if some elements are missing (guards everywhere).

// ---------- tiny DOM helpers
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// ---------- state helpers
const LS = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
};

// ---------- elements (optional; all guarded)
const el = {
  sendBtn: $("#sendBtn"),
  userInput: $("#userInput"),
  reply: $("#reply"),
  logsPre: $("#logsPre") || $("#logs") || $("#logsJson"),
  temp: $("#temperature"),
  tempLabel: $("#tempLabel"),
  model: $("#model"),
  apiBaseInput: $("#apiBase"),    // optional override
  apiKeyInput: $("#apiKey"),      // where user types the key
  streamToggle: $("#stream"),     // checkbox for streaming
};

// ---------- defaults
const DEFAULTS = {
  apiBase: "https://cogmyra-api.onrender.com",
  model: "gpt-4o-mini",
  sessionId: LS.get("cm.sessionId") || (crypto?.randomUUID?.() ?? String(Date.now())),
};
LS.set("cm.sessionId", DEFAULTS.sessionId);

// hydrate UI (if controls exist)
if (el.apiBaseInput && !el.apiBaseInput.value) el.apiBaseInput.value = LS.get("cm.apiBase", DEFAULTS.apiBase);
if (el.model && !el.model.value) el.model.value = LS.get("cm.model", DEFAULTS.model);
if (el.temp && el.tempLabel) el.tempLabel.textContent = (el.temp.value ?? 1.0);
if (el.apiKeyInput && !el.apiKeyInput.value) el.apiKeyInput.value = LS.get("cm.apiKey", "");

// ---------- util: current config
function cfg() {
  const apiBase = (el.apiBaseInput && el.apiBaseInput.value?.trim()) || DEFAULTS.apiBase;
  const model = (el.model && el.model.value) || DEFAULTS.model;
  const temperature = el.temp ? Number(el.temp.value || 1.0) : 1.0;
  const stream = el.streamToggle ? !!el.streamToggle.checked : false;
  const apiKey = (el.apiKeyInput && el.apiKeyInput.value?.trim()) || LS.get("cm.apiKey", "");
  return { apiBase, model, temperature, stream, apiKey };
}

// persist some UI changes
["change","input"].forEach(evt => {
  el.apiBaseInput && el.apiBaseInput.addEventListener(evt, () => LS.set("cm.apiBase", el.apiBaseInput.value.trim()));
  el.model && el.model.addEventListener(evt, () => LS.set("cm.model", el.model.value));
  el.apiKeyInput && el.apiKeyInput.addEventListener(evt, () => LS.set("cm.apiKey", el.apiKeyInput.value.trim()));
  el.temp && el.temp.addEventListener(evt, () => { if (el.tempLabel) el.tempLabel.textContent = el.temp.value; });
});

// ---------- logging
function log(obj) {
  const arr = LS.get("cm.logs", []);
  arr.push({ t: new Date().toISOString(), ...obj });
  LS.set("cm.logs", arr);
  if (el.logsPre) el.logsPre.textContent = JSON.stringify(arr, null, 2);
}

// ---------- render helpers
function setReply(html) {
  if (el.reply) el.reply.innerHTML = html;
}
function metaLine({ version, latency_ms, usage, request_id }) {
  const tokens = usage?.total_tokens ?? "-";
  return `<div style="opacity:.7;font-size:.9em;margin-top:.5rem;">(${latency_ms ?? "–"} ms · tokens ${tokens} · ${version ?? "api"}) · <code>${request_id ?? ""}</code></div>`;
}

// ---------- main send
async function sendMessage() {
  const ui = cfg();
  if (!ui.apiKey) {
    setReply(`<em>Enter your API key to send.</em>`);
    return;
  }
  const userText = (el.userInput && el.userInput.value.trim()) || "Hello from CogMyra Guide";
  if (!userText) return;

  setReply("Sending…");

  const body = {
    sessionId: DEFAULTS.sessionId,
    model: ui.model,
    temperature: ui.temperature,
    messages: [{ role: "user", content: userText }],
    ...(ui.stream ? { stream: true } : {}),
  };
  const url = `${ui.apiBase.replace(/\/+$/,"")}/api/chat`;
  const headers = {
    "content-type": "application/json",
    "x-api-key": ui.apiKey, // IMPORTANT: exact header name your API expects
  };

  try {
    if (ui.stream) {
      // Streaming: server may send full JSON or incremental chunks.
      const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (!res.body) {
        // fallback: if no stream body, just parse JSON
        const j = await res.json();
        setReply(`${(j.reply ?? "").replace(/\n/g,"<br>")}${metaLine(j)}`);
        log({ type:"chat", mode:"stream-fallback-json", ok:true, request: body, response: j });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      setReply("");
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        if (el.reply) el.reply.textContent = acc; // raw stream view
      }
      log({ type:"chat", mode:"stream", ok:true, request: body, responseRaw: acc });
    } else {
      // Non-streaming JSON
      const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
      const j = await res.json();
      if (!res.ok) throw new Error(j?.detail || `HTTP ${res.status}`);
      setReply(`${(j.reply ?? "").replace(/\n/g,"<br>")}${metaLine(j)}`);
      log({ type:"chat", mode:"json", ok:true, request: body, response: j });
    }
  } catch (err) {
    setReply(`<span style="color:#ff6868;">Error:</span> ${String(err?.message || err)}`);
    log({ type:"chat", ok:false, error:String(err?.message || err) });
  }
}

// ---------- wire UI
if (el.sendBtn) el.sendBtn.addEventListener("click", sendMessage);
if (el.userInput) el.userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

// initial logs render
log({ type:"boot", sessionId: DEFAULTS.sessionId, apiBase: cfg().apiBase, model: cfg().model });
