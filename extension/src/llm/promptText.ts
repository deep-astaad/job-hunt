/**
 * Flatten the structured chat messages we'd send to an API into a single plain
 * prompt suitable for pasting into a web chat UI (the BYO-LLM path). The system
 * message becomes an instruction preamble; the user message follows.
 */
import type { ChatMessage } from "@/llm/openai";

export function messagesToPrompt(messages: ChatMessage[]): string {
  const system = messages
    .filter((m) => m.role === "system")
    .map((m) => m.content.trim())
    .filter(Boolean)
    .join("\n\n");
  const user = messages
    .filter((m) => m.role === "user")
    .map((m) => m.content.trim())
    .filter(Boolean)
    .join("\n\n");

  const parts: string[] = [];
  if (system) parts.push(system);
  if (user) parts.push(user);
  parts.push(
    "Reply with ONLY the requested text — no preamble, notes, or markdown fences."
  );
  return parts.join("\n\n");
}
