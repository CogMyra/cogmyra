// Cloudflare Worker — CogMyra RAG Proxy (R2-backed index)

interface Env {
  OPENAI_API_KEY: string;        // wrangler secret put OPENAI_API_KEY
  FRONTEND_APP_KEY: string;      // wrangler secret put FRONTEND_APP_KEY
  SYSTEM_PROMPT?: string;        // optional: wrangler secret put SYSTEM_PROMPT
  MODEL?: string;                // optional: wrangler secret put MODEL (default: gpt-5)
  VECTOR_BUCKET: R2Bucket;       // bound in wrangler.jsonc as "VECTOR_BUCKET"
}

type RagRecord = {
  id: string;
  file: string;
  chunkIndex: number;
  text: string;
  embedding: number[];
};

type RagIndex = {
  created: string;
  model: string;
  dims: number;
  count: number;
  records: RagRecord[];
};

const STATE: {
  index?: RagIndex;
  indexLoadedAt?: string | null;
  loadError?: string | null;
} = {
  index: undefined,
  indexLoadedAt: null,
  loadError: null,
};

const ALLOW_ORIGIN = ['http://localhost:5500', 'https://cogmyra.com', 'https://www.cogmyra.com'];

function cors(origin: string | null): Headers {
  const h = new Headers();
  const allow = origin && ALLOW_ORIGIN.includes(origin) ? origin : 'https://cogmyra.com';
  h.set('access-control-allow-origin', allow);
  h.set('access-control-allow-headers', 'Content-Type, Authorization, x-app-key');
  h.set('access-control-allow-methods', 'GET, POST, OPTIONS');
  h.set('access-control-expose-headers', 'X-CogMyra-Model, X-CogMyra-Prompt-Hash');
  return h;
}

async function sha256Hex(s: string) {
  const data = new TextEncoder().encode(s);
  // @ts-ignore
  const buf = await crypto.subtle.digest('SHA-256', data);
  const b = new Uint8Array(buf);
  return [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
}

async function fetchIndexFromR2(env: Env): Promise<RagIndex> {
  const obj = await env.VECTOR_BUCKET.get('index.json');
  if (!obj) throw new Error('R2 missing object: index.json');
  const text = await obj.text();
  try {
    return JSON.parse(text) as RagIndex;
  } catch (e) {
    throw new Error(`R2 index.json is not valid JSON: ${(e as Error).message}`);
  }
}

async function ensureIndex(env: Env): Promise<void> {
  if (STATE.index) return;
  try {
    STATE.index = await fetchIndexFromR2(env);
    STATE.indexLoadedAt = new Date().toISOString();
    STATE.loadError = null;
  } catch (e) {
    STATE.loadError = (e as Error).message || String(e);
    STATE.index = undefined;
  }
}

function dot(a: number[], b: number[]) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * b[i];
  return s;
}
function norm(a: number[]) {
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i] * a[i];
  return Math.sqrt(s);
}
function cosSim(a: number[], b: number[]) {
  const d = dot(a, b);
  const n = norm(a) * norm(b);
  return n ? d / n : 0;
}

async function embedQuery(env: Env, text: string): Promise<number[]> {
  const r = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: "text-embedding-3-large",
      input: text,
    }),
  });

  const raw = await r.text();
  if (!r.ok) throw new Error(`OpenAI embed error: ${r.status} ${r.statusText}\n${raw}`);

  let j: any;
  try { j = JSON.parse(raw); }
  catch { throw new Error(`OpenAI embed returned non-JSON (first 200 chars): ${raw.slice(0, 200)}`); }

  const emb = j?.data?.[0]?.embedding;
  if (!Array.isArray(emb)) {
    throw new Error(`OpenAI embed missing data[0].embedding. Response (first 2000 chars): ${JSON.stringify(j).slice(0, 2000)}`);
  }
  return emb as number[];
}

function rank(envIndex: RagIndex, qEmb: number[], k = 3) {
  const scored: Array<{ rec: RagRecord; score: number }> = [];

  for (const rec of envIndex.records) {
    const emb = (rec as any)?.embedding;
    if (!Array.isArray(emb)) continue;
    if (emb.length !== qEmb.length) continue;

    scored.push({ rec, score: cosSim(qEmb, emb) });
  }

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, Math.min(k, scored.length));
}

// Strict mode ONLY when we actually have retrieved chunks.
function buildSystemPrompt(env: Env, strict: boolean) {
  const base = (env.SYSTEM_PROMPT?.trim() || '').trim();

  if (!strict) {
    return base || 'You are CogMyra, a helpful educational assistant. Be clear, direct, and practical.';
  }

  const hardRule = `
You are a strict retrieval assistant.

RULES:
- Answer using ONLY the retrieved chunks.
- Do not add meta text (no "Goal", "Plan", "Check", "Next step", "Sources").
- Preserve wording; lightly normalize capitalization/punctuation only if needed.
- Whenever you include content from a chunk, append an inline cite exactly like:
  [file: <file>, chunk: <chunkIndex>]
- If multiple chunks contribute, keep their cites near the lines they support.
- If the user asks beyond the retrieved chunks, say:
  "Not in retrieved chunks." and stop.
`.trim();

  return base ? `${base}\n\n${hardRule}` : hardRule;
}

function userPromptFrom(messages: Array<{ role: string; content: string }>) {
  return [...messages].reverse().find((m) => m.role === 'user')?.content ?? '';
}

function citeTag(file: string, chunkIndex: number) {
  return `[file: ${file}, chunk: ${chunkIndex}]`;
}

function buildRagContext(top: Array<{ rec: RagRecord; score: number }>) {
  return top
    .map(({ rec }) => {
      const head = `## ${rec.file} — chunk ${rec.chunkIndex}`;
      return `${head}\n${rec.text}\n${citeTag(rec.file, rec.chunkIndex)}`;
    })
    .join('\n\n---\n\n');
}

async function callChat(env: Env, sys: string, user: string, context: string) {
  const model = env.MODEL || 'gpt-5';
  const content = context
    ? `${user}\n\nUse ONLY this context (do not quote anything not present):\n\n${context}`
    : user;

  const body = {
    model,
    messages: [
      { role: 'system', content: sys },
      { role: 'user', content },
    ],
  };

  const r = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${env.OPENAI_API_KEY}`,
    },
    body: JSON.stringify(body),
  });

  if (!r.ok) {
    const t = await r.text();
    throw new Error(`OpenAI error ${r.status}: ${t}`);
  }
  return r.json();
}

function textError(e: unknown, origin: string | null, status = 500) {
  const h = cors(origin);
  h.set('content-type', 'text/plain; charset=utf-8');
  return new Response(typeof e === 'string' ? e : String(e), { status, headers: h });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get('origin');

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: cors(origin) });
    }

    const appKey = request.headers.get('x-app-key');
    if (!appKey || appKey !== env.FRONTEND_APP_KEY) {
      return textError('Forbidden: bad or missing x-app-key', origin, 403);
    }

    try {
      if (url.pathname === '/api/health') {
        await ensureIndex(env);

        const sys = buildSystemPrompt(env, false);
        const promptHash = await sha256Hex(sys);

        const h = cors(origin);
        h.set('content-type', 'application/json; charset=utf-8');
        h.set('X-CogMyra-Model', env.MODEL || 'gpt-5');
        h.set('X-CogMyra-Prompt-Hash', promptHash);

        return new Response(
          JSON.stringify({
            ok: true,
            now: new Date().toISOString(),
            model: env.MODEL || 'gpt-5',
            promptHash,
            rag: {
              indexSource: 'r2://VECTOR_BUCKET/index.json',
              loaded: !!STATE.index && !STATE.loadError,
              lastLoaded: STATE.indexLoadedAt,
              count: STATE.index?.count ?? 0,
              dims: STATE.index?.dims ?? null,
              embedModel: 'text-embedding-3-large',
              error: STATE.loadError ?? null,
            },
          }),
          { status: 200, headers: h },
        );
      }

      if (url.pathname === '/api/chat') {
        if (request.method !== 'POST') {
          return textError('Method Not Allowed', origin, 405);
        }

        const t0 = Date.now();
        const body = await request.json().catch(() => ({}));
        const messages: Array<{ role: string; content: string }> = body?.messages ?? [];
        const userQ = userPromptFrom(messages);

        await ensureIndex(env);

        let ragUsed = false;
        let ragChars = 0;
        let ragCitations: Array<{ file: string; chunk: number; score: number }> = [];
        let context = '';

        if (STATE.index && !STATE.loadError) {
          const qEmb = await embedQuery(env, userQ);
          const top = rank(STATE.index, qEmb, 3);

          ragUsed = top.length > 0;
          ragChars = top.reduce((s, t) => s + t.rec.text.length, 0);
          ragCitations = top.map((t) => ({
            file: t.rec.file,
            chunk: t.rec.chunkIndex,
            score: t.score,
          }));
          if (ragUsed) context = buildRagContext(top);
        }

        const sys = buildSystemPrompt(env, ragUsed);
        const promptHash = await sha256Hex(sys);

        const openai = await callChat(env, sys, userQ, context);

        const h = cors(origin);
        h.set('content-type', 'application/json; charset=utf-8');
        h.set('X-CogMyra-Model', env.MODEL || 'gpt-5');
        h.set('X-CogMyra-Prompt-Hash', promptHash);

        console.log(JSON.stringify({
          event_type: 'chat_response_sent',
          ts: new Date().toISOString(),
          path: url.pathname,
          status: 200,
          latency_ms: Date.now() - t0,
          rag_used: ragUsed,
          rag_chars: ragChars,
          rag_error: STATE.loadError ?? null,
        }));

        const merged = {
          ...openai,
          model: (openai as any).model || env.MODEL || 'gpt-5',
          ragUsed,
          ragChars,
          ragCitations,
          ragIndexSource: 'r2://VECTOR_BUCKET/index.json',
          ragLoadError: STATE.loadError ?? null,
        };

        return new Response(JSON.stringify(merged), { status: 200, headers: h });
      }

      return textError('Not Found', origin, 404);
    } catch (e) {
      return textError(`Proxy error: ${e instanceof Error ? e.message : String(e)}`, origin, 500);
    }
  },
} satisfies ExportedHandler<Env>;
