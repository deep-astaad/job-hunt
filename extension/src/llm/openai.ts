/**
 * Minimal OpenAI-compatible chat client for the background worker. Ports the
 * retry + key-pool behavior from the job-hunt repo's `llm.py`: accept a
 * comma-separated key pool, pick one at random per attempt, retry up to 3 times.
 * Any OpenAI-compatible base URL works (OpenAI, DeepSeek, local vLLM/Ollama).
 */

export interface LlmConfig {
  apiKey: string; // may be a single key or comma-separated pool
  baseUrl: string;
  model: string;
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatOptions {
  temperature?: number;
  jsonMode?: boolean;
  timeoutMs?: number;
}

function keyPool(apiKey: string): string[] {
  return apiKey
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean);
}

export async function chatCompletion(
  cfg: LlmConfig,
  messages: ChatMessage[],
  opts: ChatOptions = {}
): Promise<string> {
  const keys = keyPool(cfg.apiKey);
  if (!keys.length) throw new Error("No OpenAI API key configured.");
  const baseUrl = cfg.baseUrl.replace(/\/$/, "");
  const url = `${baseUrl}/chat/completions`;

  let lastErr: unknown;
  for (let attempt = 0; attempt < 3; attempt++) {
    const apiKey = keys[Math.floor(Math.random() * keys.length)];
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 60000);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: cfg.model,
          messages,
          temperature: opts.temperature ?? 0.2,
          ...(opts.jsonMode
            ? { response_format: { type: "json_object" } }
            : {}),
        }),
        signal: controller.signal,
      });
      clearTimeout(timer);
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`OpenAI ${res.status}: ${body.slice(0, 200)}`);
      }
      const data = await res.json();
      const content = data?.choices?.[0]?.message?.content;
      if (typeof content !== "string") throw new Error("Empty completion");
      return content;
    } catch (err) {
      clearTimeout(timer);
      lastErr = err;
      if (attempt < 2) await sleep(800);
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("LLM call failed");
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
