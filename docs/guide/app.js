// ============ Config ============
const API_BASE   = "https://cogmyra-proxy.cogmyra.workers.dev";
const CHAT_URL   = `${API_BASE}/api/chat`;
const HEALTH_URL = `${API_BASE}/api/health`;

// This must equal your Wrangler secret FRONTEND_APP_KEY
const APP_KEY = "abc123";

// ============ Elements ============
const feed   = document.getElementById("feed");
const input  = document.getElementById("composer-input");
const send   = document.getElementById("send-btn");
const threads = document.getElementById("threads");

// ============ Helpers ============
function appendMessage(role, text, cls = "") {
  const div = document.createElement("div");
  div.className = `msg ${role} ${cls}`.trim();
  div.textContent = text;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
  return div;
}

// ============ Events ============
send.addEventListener("click", async () => {
  const text = input.value.trim();
  if (!text) return;
  
  // Show user message
  appendMessage("user", text);
  input.value = "";

  // Show placeholder for CogMyra reply
  const msgDiv = appendMessage("assistant", "…");

  try {
    const res = await fetch(CHAT_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-app-key": APP_KEY
      },
      body: JSON.stringify({
        messages: [{ role: "user", content: text }]
      })
    });

    if (!res.ok) {
      msgDiv.textContent = `Error: ${res.status}`;
      msgDiv.classList.add("error");
      return;
    }

    const data = await res.json();
    const reply = data.choices?.[0]?.message?.content || "(no reply)";
    msgDiv.textContent = reply;

  } catch (err) {
    msgDiv.textContent = `Network error: ${err.message}`;
    msgDiv.classList.add("error");
  }
});

// Allow pressing Enter to send
input.addEventListener("keypress", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send.click();
  }
});
