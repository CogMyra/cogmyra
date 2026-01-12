/**
 * Minimal API worker for CogMyra — step 3d (/api/profile)
 * Requires a D1 binding named CMG_DB and a secret FRONTEND_APP_KEY
 * Route: api.cogmyra.com/*
 */

const ALLOW_ORIGIN = [
  "http://localhost:5500",
  "https://cogmyra.com",
  "https://www.cogmyra.com",
];

// ---------- helpers ----------
function cors(origin) {
  const h = new Headers();
  const allow = origin && ALLOW_ORIGIN.includes(origin) ? origin : ALLOW_ORIGIN[1];
  h.set("access-control-allow-origin", allow);
  h.set("access-control-allow-headers", "Content-Type, Authorization, x-app-key");
  h.set("access-control-allow-methods", "GET, POST, OPTIONS");
  h.set("access-control-expose-headers", "X-CogMyra-Model, X-CogMyra-Prompt-Hash");
  return h;
}

function json(body, { status = 200, headers } = {}) {
  const h = headers ? new Headers(headers) : new Headers();
  if (!h.has("content-type")) h.set("content-type", "application/json;charset=UTF-8");
  return new Response(JSON.stringify(body), { status, headers: h });
}

function text(msg, { status = 200, headers } = {}) {
  const h = headers ? new Headers(headers) : new Headers();
  if (!h.has("content-type")) h.set("content-type", "text/plain; charset=utf-8");
  return new Response(msg, { status, headers: h });
}

function parseCookies(header) {
  const out = {};
  if (!header) return out;
  header.split(";").forEach((p) => {
    const [k, v] = p.split("=").map(s => (s || "").trim());
    if (k) out[k] = decodeURIComponent(v || "");
  });
  return out;
}

// Tiny UUIDv4 (not crypto-strong, good enough for anon id)
function uuid4() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// Ensure a cmg_uid cookie; returns {uid, setCookie?:string}
function ensureUidCookie(request) {
  const cookies = parseCookies(request.headers.get("cookie") || "");
  let uid = cookies.cmg_uid;
  let setCookie;
  if (!uid) {
    uid = uuid4();
    // cookie: 400 days, secure, sameSite=Lax
    const maxAge = 60 * 60 * 24 * 400;
    setCookie = `cmg_uid=${encodeURIComponent(uid)}; Max-Age=${maxAge}; Path=/; SameSite=Lax; Secure`;
  }
  return { uid, setCookie };
}

// --------- SQL helpers (D1) ----------
async function getOrCreateUser(db, id) {
  // Create if missing
  await db.prepare(
    `INSERT INTO users (id) VALUES (?) ON CONFLICT(id) DO NOTHING`
  ).bind(id).run();

  const row = await db.prepare(`SELECT id, email, display_name, anon, created_at
                                FROM users WHERE id = ?`).bind(id).first();
  return row;
}

async function upsertUser(db, id, { email, display_name, anon }) {
  // Upsert by id; only provided fields update
  await db.prepare(`
    INSERT INTO users (id, email, display_name, anon)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      email = COALESCE(excluded.email, email),
      display_name = COALESCE(excluded.display_name, display_name),
      anon = COALESCE(excluded.anon, anon)
  `).bind(id, email ?? null, display_name ?? null, typeof anon === "number" ? anon : null).run();

  return getOrCreateUser(db, id);
}

// ---------- request router ----------
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("origin");
    const baseHeaders = cors(origin);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: baseHeaders });
    }

    // Simple app-key gate (matches your existing endpoints)
    const appKey = request.headers.get("x-app-key");
    if (!appKey || appKey !== env.FRONTEND_APP_KEY) {
      return text("Forbidden: bad or missing x-app-key", { status: 403, headers: baseHeaders });
    }

    try {
      if (url.pathname === "/api/health") {
        return json({ ok: true, now: new Date().toISOString() }, { headers: baseHeaders });
      }

      // -------- /api/profile --------
      if (url.pathname === "/api/profile") {
        const { uid, setCookie } = ensureUidCookie(request);
        let result;

        if (request.method === "GET") {
          result = await getOrCreateUser(env.CMG_DB, uid);
        } else if (request.method === "POST") {
          const body = await request.json().catch(() => ({}));
          // normalize anon to 0/1 if provided
          if (typeof body.anon === "boolean") body.anon = body.anon ? 1 : 0;
          result = await upsertUser(env.CMG_DB, uid, body || {});
        } else {
          return text("Method Not Allowed", { status: 405, headers: baseHeaders });
        }

        const headers = new Headers(baseHeaders);
        if (setCookie) headers.set("set-cookie", setCookie);
        return json({ ok: true, user: result }, { headers });
      }

      // Placeholder for next steps:
      // - /api/modes (GET)
      // - /api/events (POST)
      // - /api/metrics/summary (GET)
      return text("Not Found", { status: 404, headers: baseHeaders });
    } catch (e) {
      const headers = new Headers(baseHeaders);
      return text(`Server error: ${e instanceof Error ? e.message : String(e)}`, { status: 500, headers });
    }
  }
};
