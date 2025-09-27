// Minimal browser client for CogMyra API
// Usage:
//   const api = createCogMyra({ baseUrl: "https://cogmyra-api.onrender.com", apiKey: "<SERVER_API_KEY>" });
//   await api.chat({ sessionId: "s1", model: "gpt-4o-mini", messages: [{ role: "user", content: "hi" }] });
//   await api.chatStream({ ... , onDelta: (t) => console.log(t) })

type Role = "user" | "assistant" | "system";

export interface Message {
  role: Role;
  content: string;
}

export interface ChatArgs {
  sessionId: string;
  model: string;
  messages: Message[];
  temperature?: number;
  signal?: AbortSignal;
}

export interface ChatResponse {
  reply: string;
  version: string;
  latency_ms: number;
  usage?: Record<string, any>;
  request_id?: string | null;
  error?: { code: string; message: string };
}

export interface ChatStreamArgs extends ChatArgs {
  onDelta?: (text: string) => void;
  onDone?: (final: {
    reply: string;
    latency_ms: number;
    usage?: Record<string, any>;
    version: string;
    request_id?: string | null;
  }) => void;
  onError?: (err: any) => void;
}

/** Factory */
export function createCogMyra(opts: { baseUrl: string; apiKey: string }) {
  const base = opts.baseUrl.replace(/\/+$/, "");
  const key = opts.apiKey;

  async function chat(args: ChatArgs): Promise<ChatResponse> {
    const body: any = {
      sessionId: args.sessionId,
      model: args.model,
      messages: args.messages,
    };
    if (typeof args.temperature === "number") {
      // API handles stripping temp for models that don’t support it
      body.temperature = args.temperature;
    }

    const res = await fetch(`${base}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": key,
      },
      body: JSON.stringify(body),
      signal: args.signal,
    });

    const json = (await res.json()) as ChatResponse | { error: any };
    if (!res.ok || "error" in json) {
      const errObj =
        "error" in json
          ? json.error
          : { code: `HTTP_${res.status}`, message: res.statusText };
      throw new Error(
        `Chat failed: ${errObj.code ?? "ERR"} - ${errObj.message ?? "Unknown"}`
      );
    }
    return json as ChatResponse;
  }

  /** SSE streaming reader for /api/chat/stream */
  async function chatStream(args: ChatStreamArgs): Promise<void> {
    const body: any = {
      sessionId: args.sessionId,
      model: args.model,
      messages: args.messages,
    };
    if (typeof args.temperature === "number") {
      body.temperature = args.temperature;
    }

    const res = await fetch(`${base}/api/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": key,
      },
      body: JSON.stringify(body),
      signal: args.signal,
    });

    if (!res.ok || !res.body) {
      let msg = `HTTP ${res.status} ${res.statusText}`;
      try {
        const j = await res.json();
        if (j?.error?.message) msg = j.error.message;
      } catch {}
      throw new Error(`Stream failed: ${msg}`);
    }

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += dec.decode(value, { stream: true });

        // Parse SSE lines
        let idx: number;
        // Split on double-newline boundaries to handle event chunks
        while ((idx = buffer.indexOf("\n\n")) >= 0) {
          const chunk = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 2);

          if (!chunk) continue;

          // Extract possible "event:" and "data:" lines
          let event: string | null = null;
          let dataLine = "";
          for (const line of chunk.split("\n")) {
            const t = line.trim();
            if (t.startsWith("event:")) event = t.slice(6).trim();
            if (t.startsWith("data:")) dataLine += t.slice(5).trim();
          }

          if (!dataLine) continue;

          try {
            const payload = JSON.parse(dataLine);
            if (event === "error" || payload?.error) {
              const msg =
                payload?.error?.message ??
                payload?.message ??
                "Stream error";
              throw new Error(msg);
            }
            if (event === "done" || payload?.final) {
              args.onDone?.({
                reply: String(payload.reply ?? ""),
                latency_ms: Number(payload.latency_ms ?? 0),
                usage: payload.usage ?? {},
                version: String(payload.version ?? ""),
                request_id: payload.request_id ?? null,
              });
            } else if (typeof payload.delta === "string") {
              args.onDelta?.(payload.delta);
            }
          } catch (e) {
            args.onError?.(e);
            throw e;
          }
        }
      }
    } catch (e: any) {
      if (e?.name === "AbortError") return; // silent on abort
      args.onError?.(e);
      throw e;
    } finally {
      // flush any remaining buffered text (ignore)
    }
  }

  return { chat, chatStream };
}

export type CogMyraClient = ReturnType<typeof createCogMyra>;
