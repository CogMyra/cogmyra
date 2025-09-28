/* CogMyra — simple chat client for the Guide page
   Place at: docs/guide/chat.v1.js
   ------------------------------------------------------------------ */

(function () {
  // ====== CONFIG — update BASE_URL if your API lives elsewhere ======
  const BASE_URL = 'https://cogmyra.com/api'; // e.g. 'https://api.cogmyra.com' or '/api'
  const CHAT_PATH = '/chat';                   // POST {input, session_id?, model?}
  const HEALTH_PATH = '/health';               // GET -> {ok: true} or text
  const MODEL = 'cogmyra-gpt';                 // your model name on the server
  const API_KEY = null;                        // only if your public endpoint expects a key
  // =================================================================

  const $messages = document.getElementById('cm-chat-messages');
  const $input    = document.getElementById('cm-chat-input');
  const $send     = document.getElementById('cm-chat-send');
  const $health   = document.getElementById('health-status');

  // lightweight session id so your backend can keep context per browser
  const sessionId = (() => {
    const k = 'cm.session.v1';
    let v = localStorage.getItem(k);
    if (!v) { v = crypto.randomUUID(); localStorage.setItem(k, v); }
    return v;
  })();

  // --------- helpers ----------
  const el = (tag, attrs = {}, text = '') => {
    const n = document.createElement(tag);
    Object.assign(n, attrs);
    if (text) n.textContent = text;
    return n;
  };

  const addMsg = (role, text) => {
    const row = el('div', {
      style: `
        display:flex; gap:10px; margin:10px 0; align-items:flex-start;
      `
    });
    const bubble = el('div', {
      style: `
        background:${role === 'user' ? '#1b2640' : '#0f1626'};
        border:1px solid #2b3446;
        border-radius:12px; padding:10px 12px; max-width: 100%;
        white-space:pre-wrap; line-height:1.5;
      `
    }, text);
    const tag = el('div', {
      style: `
        font-size:.75rem; opacity:.7; width:54px; flex:0 0 54px;
        text-align:right; user-select:none;
      `
    }, role === 'user' ? 'You' : 'CogMyra');

    row.append(tag, bubble);
    $messages.append(row);
    $messages.scrollTop = $messages.scrollHeight;
  };

  const setBusy = (busy) => {
    $send.disabled = busy;
    $send.textContent = busy ? '…' : 'Send';
  };

  // --------- health check ----------
  (async () => {
    try {
      const r = await fetch(BASE_URL + HEALTH_PATH, { cache: 'no-store' });
      if (!r.ok) throw new Error(`${r.status}`);
      let statusText = 'ok';
      try {
        const ct = r.headers.get('content-type') || '';
        statusText = ct.includes('application/json') ? (await r.json()).status || 'ok' : (await r.text() || 'ok');
      } catch { /* ignore parse issues */ }
      $health.textContent = `API: ${statusText}`;
    } catch (e) {
      $health.textContent = `API: error (${e.message})`;
    }
  })();

  // --------- send logic ----------
  async function sendMessage() {
    const text = ($input.value || '').trim();
    if (!text) return;
    addMsg('user', text);
    $input.value = '';
    setBusy(true);

    try {
      const body = {
        input: text,
        session_id: sessionId,
        model: MODEL
      };
      const headers = { 'Content-Type': 'application/json' };
      if (API_KEY) headers['Authorization'] = `Bearer ${API_KEY}`;

      const resp = await fetch(BASE_URL + CHAT_PATH, {
        method: 'POST',
        headers,
        body: JSON.stringify(body)
      });

      if (!resp.ok) {
        const errTxt = await resp.text().catch(() => '');
        throw new Error(`${resp.status} ${resp.statusText}${errTxt ? ` — ${errTxt.slice(0,200)}` : ''}`);
      }

      // Support either JSON {output:"..."} or NDJSON/event-stream lines "data: {delta:...}"
      const ct = resp.headers.get('content-type') || '';
      if (ct.includes('application/json')) {
        const j = await resp.json();
        addMsg('assistant', j.output || j.message || j.reply || JSON.stringify(j));
      } else {
        // stream as text
        const reader = resp.body.getReader();
        let acc = '';
        const decoder = new TextDecoder();
        // create placeholder
        const row = el('div', { style: 'display:flex; gap:10px; margin:10px 0;' });
        const tag = el('div', { style: 'font-size:.75rem; opacity:.7; width:54px; flex:0 0 54px; text-align:right;' }, 'CogMyra');
        const bubble = el('div', {
          style: 'background:#0f1626;border:1px solid #2b3446;border-radius:12px;padding:10px 12px;white-space:pre-wrap;'
        }, '');
        row.append(tag, bubble);
        $messages.append(row);

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          acc += decoder.decode(value, { stream: true });

          // try to parse as SSE/NDJSON
          for (const line of acc.split(/\r?\n/)) {
            if (!line.trim()) continue;
            if (line.startsWith('data:')) {
              try {
                const payload = JSON.parse(line.slice(5).trim());
                if (payload.delta) bubble.textContent += payload.delta;
                if (payload.output) bubble.textContent = payload.output;
              } catch { /* ignore */ }
            } else {
              // plain text chunk
              bubble.textContent += line + '\n';
            }
            $messages.scrollTop = $messages.scrollHeight;
          }
          acc = '';
        }
      }
    } catch (err) {
      addMsg('assistant', `⚠️ ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  $send.addEventListener('click', sendMessage);
  $input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
})();
