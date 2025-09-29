// ~/cogmyra-dev/docs/guide/app.js

/* ---------- Elements ---------- */
const form = document.querySelector("#chat-form");
const input = document.querySelector("#chat-input");
const feed = document.querySelector("#chat-feed");
const historyList = document.querySelector("#thread-history");

/* ---------- State ---------- */
let thread = [];
let threads = JSON.parse(localStorage.getItem("threads") || "[]");

/* ---------- Helpers ---------- */
function saveThread() {
  if (thread.length > 0) {
    threads.push([...thread]);
    localStorage.setItem("threads", JSON.stringify(threads));
    renderHistory();
  }
}

function renderHistory() {
  historyList.innerHTML = "";
  threads.forEach((t, i) => {
    const btn = document.createElement("button");
    btn.textContent = `Thread ${i + 1}`;
    btn.onclick = () => loadThread(i);
    historyList.appendChild(btn);
  });
}

function loadThread(i) {
  thread = threads[i] || [];
  feed.innerHTML = "";
  thread.forEach(msg => renderMessage(msg.role, msg.content, false));
}

function renderMessage(role, content, append = true) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;
  if (append) thread.push({ role, content });
}

/* ---------- Typewriter Effect ---------- */
async function typewriterEffect(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  feed.appendChild(div);
  feed.scrollTop = feed.scrollHeight;

  for (let i = 0; i < text.length; i++) {
    div.textContent += text[i];
    feed.scrollTop = feed.scrollHeight;
    await new Promise(r => setTimeout(r, 15)); // typing speed
  }
  thread.push({ role, content: text });
}

/* ---------- Chat Request ---------- */
async function sendMessage(userInput) {
  renderMessage("user", userInput);

  try {
    const resp = await fetch("https://cogmyra-proxy.cogmyra.workers.dev/api/chat", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-app-key": "abc123"
      },
      body: JSON.stringify({
        messages: [...thread, { role: "user", content: userInput }]
      })
    });

    const data = await resp.json();

    if (data.error) {
      renderMessage("assistant", `⚠️ Error: ${data.error.message || "Unknown"}`);
      console.error("Proxy error:", data);
      return;
    }

    const reply = data.choices?.[0]?.message?.content || "[No reply]";
    await typewriterEffect("assistant", reply);

  } catch (err) {
    console.error(err);
    renderMessage("assistant", "⚠️ Network error.");
  }
}

/* ---------- Form Submit ---------- */
form.addEventListener("submit", async e => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";

  await sendMessage(text);
  saveThread();
});

/* ---------- Init ---------- */
renderHistory();
