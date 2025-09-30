// Cloudflare Worker — CogMyra RAG Proxy (verbatim answers + inline [file,chunk] cites)

interface Env {
  OPENAI_API_KEY: string;     // wrangler secret put OPENAI_API_KEY
  FRONTEND_APP_KEY: string;   // wrangler secret put FRONTEND_APP_KEY  (e.g. abc123)
  INDEX_URL: string;          // wrangler secret put INDEX_URL         (raw JSON index URL)
  SYSTEM_PROMPT?: string;     // optional: wrangler secret put SYSTEM_PROMPT
  MODEL?: string;             // optional: wrangler secret put MODEL (default: gpt-5)
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
  indexUrl?: string | null;
  loadError?: string | null;
} = {
  index: undefined,
  indexLoadedAt: null,
  indexUrl: null,
  loadError: null,
};

const ALLOW_ORIGIN = [
  "http://localhost:5500",
  "https://cogmyra.com",
  "https://www.cogmyra.com",
];

function cors(origin: string | null): Headers {
  const h = new Headers();
  const allow =
    origin && ALLOW_ORIGIN.includes(origin) ? origin : ALLOW_ORIGIN[1];
  h.set("access-control-allow-origin", allow);
  h.set(
    "access-control-allow-headers",
    "Content-Type, Authorization, x-app-key"
  );
  h.set("access-control-allow-methods", "GET, POST, OPTIONS");
  h.set("access-control-expose-headers", "X-CogMyra-Model, X-CogMyra-Prompt-Hash");
  return h;
}

function sha256Hex(s: string) {
  const data = new TextEncoder().encode(s);
  // @ts-ignore
  return crypto.subtle.digest("SHA-256", data).then((buf: ArrayBuffer) => {
    const b = new Uint8Array(buf);
    return [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  });
}

async function fetchIndex(url: string): Promise<RagIndex> {
  const res = await fetch(url, { cf: { cacheTtl: 300, cacheEverything: true } });
  if (!res.ok) throw new Error(`Failed to fetch index: ${res.status} ${res.statusText}`);
  return res.json<RagIndex>();
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
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`OpenAI embed error: ${r.status} ${r.statusText}\n${t}`);
  }
  const j = await r.json();
  return j.data[0].embedding;
}

function rank(envIndex: RagIndex, qEmb: number[], k = 3) {
  const scored = envIndex.records.map((rec) => ({
    rec,
    score: cosSim(qEmb, rec.embedding),
  }));
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, Math.min(k, scored.length));
}

function buildSystemPrompt(env: Env) {
  const base = env.SYSTEM_PROMPT?.trim() || "";
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

FORMAT:
- If the first chunk contains a heading, keep it on its own line.
- Then the exact sentences/lines from the chunks, in order of relevance, with cites.
`.trim();
  return base ? `${base}\n\n${hardRule}` : hardRule;
}

function userPromptFrom(messages: Array<{ role: string; content: string }>) {
  // Pass through last user message only for retrieval focus
  const last = [...messages].reverse().find((m) => m.role === "user")?.content ?? "";
  return last;
}

async function callChat(env: Env, sys: string, user: string, context: string) {
  const model = env.MODEL || "gpt-5";
  const body = {
    model,
    // IMPORTANT: don't send temperature when model only supports default
    messages: [
      { role: "system", content: sys },
      {
        role: "user",
        content: `${user}

Use ONLY this context (do not quote anything not present):

${context}`.trim(),
      },
    ],
  };
  const r = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "content-type": "application/json",
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

function citeTag(file: string, chunkIndex: number) {
  return `[file: ${file}, chunk: ${chunkIndex}]`;
}

function buildRagContext(top: Array<{ rec: RagRecord; score: number }>) {
  // Put each chunk with a small header line we also allow to be echoed
  // The model will quote **only** the lines it needs
  return top
    .map(({ rec }) => {
      const head = `## ${rec.file} — chunk ${rec.chunkIndex}`;
      // append a cite tag to the end of the chunk content for strict grounding
      return `${head}\n${rec.text}\n${citeTag(rec.file, rec.chunkIndex)}`;
    })
    .join("\n\n---\n\n");
}

function jsonResponse(obj: any, origin: string | null, extra: HeadersInit = {}) {
  const h = cors(origin);
  h.set("content-type", "application/json; charset=utf-8");
  for (const [k, v] of Object.entries(extra)) h.set(k, String(v));
  return new Response(JSON.stringify(obj), { status: 200, headers: h });
}

function textError(e: unknown, origin: string | null, status = 500) {
  const h = cors(origin);
  h.set("content-type", "text/plain; charset=utf-8");
  return new Response(typeof e === "string" ? e : String(e), { status, headers: h });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const origin = request.headers.get("origin");

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors(origin) });
    }

    // simple app-key gate
    const appKey = request.headers.get("x-app-key");
    if (!appKey || appKey !== env.FRONTEND_APP_KEY) {
      return textError("Forbidden: bad or missing x-app-key", origin, 403);
    }

    try {
      if (url.pathname === "/api/health") {
        // (re)load index on health
        const indexUrl = env.INDEX_URL;
        if (STATE.indexUrl !== indexUrl) {
          STATE.index = undefined;
          STATE.indexLoadedAt = null;
          STATE.loadError = null;
          STATE.indexUrl = indexUrl;
        }
        if (!STATE.index) {
          try {
            STATE.index = await fetchIndex(indexUrl);
            STATE.indexLoadedAt = new Date().toISOString();
            STATE.loadError = null;
          } catch (e) {
            STATE.loadError = (e as Error).message || String(e);
          }
        }
        const sys = buildSystemPrompt(env);
        const promptHash = await sha256Hex(sys);
        const h = cors(origin);
        h.set("X-CogMyra-Model", env.MODEL || "gpt-5");
        h.set("X-CogMyra-Prompt-Hash", promptHash);
        return new Response(
          JSON.stringify({
            ok: true,
            now: new Date().toISOString(),
            model: env.MODEL || "gpt-5",
            promptHash,
            rag: {
              indexUrl: env.INDEX_URL,
              loaded: !!STATE.index && !STATE.loadError,
              lastLoaded: STATE.indexLoadedAt,
              count: STATE.index?.count ?? 0,
              dims: STATE.index?.dims ?? null,
              embedModel: "text-embedding-3-large",
              error: STATE.loadError ?? null,
            },
          }),
          { status: 200, headers: h }
        );
      }

      if (url.pathname === "/api/chat") {
        if (request.method !== "POST") {
          return textError("Method Not Allowed", origin, 405);
        }
        const body = await request.json().catch(() => ({}));
        const messages: Array<{ role: string; content: string }> = body?.messages ?? [];

        // ensure index
        if (!STATE.index) {
          STATE.index = await fetchIndex(env.INDEX_URL);
          STATE.indexLoadedAt = new Date().toISOString();
        }

        const userQ = userPromptFrom(messages);
        const qEmb = await embedQuery(env, userQ);
        const top = rank(STATE.index!, qEmb, 3);

        const ragUsed = top.length > 0;
        const ragChars = top.reduce((s, t) => s + t.rec.text.length, 0);
        const ragCitations = top.map((t) => ({
          file: t.rec.file,
          chunk: t.rec.chunkIndex,
          score: t.score,
        }));

        const context = buildRagContext(top);
        const sys = buildSystemPrompt(env);
        const promptHash = await sha256Hex(sys);

        const openai = await callChat(env, sys, userQ, context);

        const h = cors(origin);
        h.set("X-CogMyra-Model", env.MODEL || "gpt-5");
        h.set("X-CogMyra-Prompt-Hash", promptHash);

        // surface RAG info alongside OpenAI payload
        const merged = {
          ...openai,
          model: openai.model || env.MODEL || "gpt-5",
          ragUsed,
          ragChars,
          ragCitations,
        };
        return new Response(JSON.stringify(merged), {
          status: 200,
          headers: h,
        });
      }

      return textError("Not Found", origin, 404);
    } catch (e) {
      return textError(`Proxy error: ${e instanceof Error ? e.message : String(e)}`, origin, 500);
    }
  },
} satisfies ExportedHandler<Env>;
