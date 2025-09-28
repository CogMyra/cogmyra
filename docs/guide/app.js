// /public/guide/app.js
// Minimal, dependency-free wiring for the Guide page.
// - Sends chat to your API
// - Shows reply + (latency · tokens · version)
// - Pretty-prints full JSON logs
// - Supports temperature slider, model select, and API base picker
// - Gracefully no-ops if some elements are missing

// ---------- tiny DOM helpers
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

// ---------- localStorage helpers
const LS = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem(key);
      return v === null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {}
  },
};

// ---------- elements (all optional; we guard if missing)
const el = {
  sendBtn: $("#sendBtn"),
  refreshBtn: $("#refreshLogs"),
  userInput: $("#userInput"),
  reply: $("#reply"),
  logsPre: $("#logsPre") || $("#logs") || $("#logsJson"),
  temp: $("#temperature"),
  tempLabel: $("#tempLabel"),
  model: $("#model"),
  apiBaseInput: $("#apiBase"),
  apiStatus: $("#apiStatus") || $("#healthBadge") || $("#apiBadge"),
};

// ---------- config
const DEFAULT_API_BASE = "https://cogmyra-api.onrender.com";
const DEFAULT_MODEL = "gpt-4.1";
const SESSION_ID = "guide";

// ---------- utils
function getApiBase() {
  const fromInput =
    el.apiBaseInput && el.apiBaseInput.value.trim()
      ? el.apiBaseInput.value.trim()
      : null;
  return fromInput || LS.get("apiBase", DEFAULT_API_BASE);
}

function setApiBase(val) {
  if (el.apiBaseInput) el.apiBaseInput.value = val;
  LS.set("apiBase", val);
}

function setStatusBadge(text, ok = true) {
  if (!el.apiStatus) return;
  el.apiStatus.textContent = text;
  // simple coloring without css framework
  el.apiStatus.style.padding = "2px 6px";
  el.apiStatus.style.borderRadius = "12px";
  el.apiStatus.style.fontSize = "12px";
  el.apiStatus.style.fontFamily = "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial";
  el.apiStatus.style.display = "inline-block";
  el.apiStatus.style.background = ok ? "#e8f5e9" : "#ffebee";
  el.apiStatus.style.color = ok ? "#1b5e20" : "#b71c1c";
  el.apiStatus.style.border = `1px solid ${ok ? "#c8e6c9" : "#ffcdd2"}`;
}

function pretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function setReply(text) {
  if (!el.reply) return;
  el.reply.textContent = text;
}

function setLogs(obj) {
  if (!el.logsPre) return;
  el.logsPre.textContent = pretty(obj);
}

// temperature label sync
function syncTempLabel() {
  if (!el.temp || !el.tempLabel) return;
  el.tempLabel.textContent = Number(el.temp.value).toFixed(2);
}

// ---------- API calls
async function checkHealth() {
  const base = getApiBase();
  try {
    const r = await fetch(`${base}/api/health`, { credentials: "include" });
    const json = await r.json();
    const ok = r.ok && (json.ok === "true" || json.status === "ok");
    const version = json.version || json.build || "unknown";
    setStatusBadge(`API ${ok ? "OK" : "DOWN"} · ${version}`, ok);
    setLogs(json);
  } catch (e) {
    setStatusBadge("API DOWN", false);
    setLogs({ error: String(e), apiBase: base });
  }
}

async function sendChat() {
  const base = getApiBase();
  const model = el.model?.value || LS.get("model", DEFAULT_MODEL);
  const temperatureRaw = el.temp ? Number(el.temp.value) : null;
  // only include temperature if present (so backend can treat missing vs explicit)
  const maybeTemp =
    typeof temperatureRaw === "number" && !Number.isNaN(temperatureRaw)
      ? temperatureRaw
      : undefined;

  const content = el.userInput?.value?.trim() || "";

  if (!content) {
    setReply("(enter a prompt first)");
    return;
  }

  const body = {
    sessionId: SESSION_ID,
    model,
    messages: [{ role: "user", content }],
  };
  if (maybeTemp !== undefined) body.temperature = maybeTemp;

  setReply("…sending…");

  try {
    const res = await fetch(`${base}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });

    const data = await res.json();
    setLogs(data);

    const extra = [];
    if (typeof data.latency_ms === "number") extra.push(`⏱ ${data.latency_ms} ms`);
    if (data.usage && data.usage.total_tokens != null)
      extra.push(`🔢 ${data.usage.total_tokens} tokens`);
    if (data.version) extra.push(`🔁 ${data.version}`);

    const suffix = extra.length ? `\n\n(${extra.join(" · ")})` : "";

    setReply((data.reply || "(no reply)") + suffix);
  } catch (e) {
    setReply("(request failed)");
    setLogs({ error: String(e), apiBase: base });
    setStatusBadge("API DOWN", false);
  }
}

// ---------- wiring
function wireButtons() {
  el.sendBtn?.addEventListener("click", sendChat);
  el.refreshBtn?.addEventListener("click", checkHealth);
}

function wireTemp() {
  if (!el.temp) return;
  // restore saved temp if any
  const saved = LS.get("temperature");
  if (saved != null) {
    el.temp.value = String(saved);
  }
  syncTempLabel();
  el.temp.addEventListener("input", () => {
    LS.set("temperature", Number(el.temp.value));
    syncTempLabel();
  });
}

function wireModel() {
  if (!el.model) return;
  // restore saved model
  const saved = LS.get("model", DEFAULT_MODEL);
  el.model.value = saved;
  el.model.addEventListener("change", () => {
    LS.set("model", el.model.value);
  });
}

function wireApiPicker() {
  const saved = LS.get("apiBase", DEFAULT_API_BASE);
  setApiBase(saved);
  el.apiBaseInput?.addEventListener("change", () => {
    const v = el.apiBaseInput.value.trim();
    if (v) setApiBase(v);
    // ping health on change
    checkHealth();
  });
}

// ---------- init
function init() {
  wireButtons();
  wireTemp();
  wireModel();
  wireApiPicker();

  // initial health check (also fills logs with health JSON)
  checkHealth();
}

document.addEventListener("DOMContentLoaded", init);
