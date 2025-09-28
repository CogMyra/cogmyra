// ==== CONFIG ====
// Point this to your Worker / API that calls your CogMyra GPT.
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev"; 
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;

// App key must match the Worker secret (currently set to "abc123")
const APP_KEY = "abc123";

function authHeaders() {
  return {
    "content-type": "application/json",
    "x-app-key": APP_KEY,
  };
}

// ==== STATE ====
let threadId = null;

// ==== HELPERS ====
async function checkHealth() {
  try {
    const res = await fetch(HEALTH_URL, { headers: authHeaders() });
    const data = await res.json();
    console.log("Health OK:", data);
  } catch (err) {
    console.error("Health check failed", err);
  }
}

async function sendMessage(message) {
  const payload = {
    threadId,
    messages: [{ role: "user", content: message }],
  };

  const res = await fetch(CHAT_URL, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Chat request failed: ${res.status}`);
  }

  const data = await res.json();
  threadId = data.id || threadId; // update threadId if provided
  return data.choices?.[0]?.message?.content || "(no response)";
}

// ==== UI HOOKUP ====
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const output = document.getElementById("chat-output");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userText = input.value.trim();
    if (!userText) return;

    // show user message
    const userDiv = document.createElement("div");
    userDiv.className = "msg user";
    userDiv.textContent = userText;
    output.appendChild(userDiv);
    input.value = "";

    try {
      const reply = await sendMessage(userText);
      const botDiv = document.createElement("div");
      botDiv.className = "msg bot";
      botDiv.textContent = reply;
      output.appendChild(botDiv);
    } catch (err) {
      const errDiv = document.createElement("div");
      errDiv.className = "msg error";
      errDiv.textContent = "Error: " + err.message;
      output.appendChild(errDiv);
    }

    output.scrollTop = output.scrollHeight;
  });

  // initial health check
  checkHealth();
});
