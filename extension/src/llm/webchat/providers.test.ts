import { describe, it, expect } from "vitest";
import {
  WEB_CHAT_PROVIDERS,
  getProvider,
  detectProviderByHost,
  webChatTarget,
  QUERY_PARAM_MAX,
} from "./providers";
import { messagesToPrompt } from "../promptText";

describe("web chat provider registry", () => {
  it("ships the four expected providers with required fields", () => {
    const ids = WEB_CHAT_PROVIDERS.map((p) => p.id).sort();
    expect(ids).toEqual(["chatgpt", "claude", "gemini", "kimi"]);
    for (const p of WEB_CHAT_PROVIDERS) {
      expect(p.label).toBeTruthy();
      expect(p.homeUrl.startsWith("https://")).toBe(true);
      expect(p.composerSelectors.length).toBeGreaterThan(0);
      expect(p.responseSelectors.length).toBeGreaterThan(0);
    }
  });

  it("detects providers by host", () => {
    expect(detectProviderByHost("claude.ai")?.id).toBe("claude");
    expect(detectProviderByHost("chatgpt.com")?.id).toBe("chatgpt");
    expect(detectProviderByHost("chat.openai.com")?.id).toBe("chatgpt");
    expect(detectProviderByHost("gemini.google.com")?.id).toBe("gemini");
    expect(detectProviderByHost("www.kimi.com")?.id).toBe("kimi");
    expect(detectProviderByHost("example.com")).toBeUndefined();
  });

  it("uses the query param for short prompts when supported", () => {
    const chatgpt = getProvider("chatgpt")!;
    const t = webChatTarget(chatgpt, "hello world");
    expect(t.prefilledViaUrl).toBe(true);
    expect(t.url).toContain("q=hello");
  });

  it("falls back to home URL for long prompts", () => {
    const chatgpt = getProvider("chatgpt")!;
    const long = "x".repeat(QUERY_PARAM_MAX + 1);
    const t = webChatTarget(chatgpt, long);
    expect(t.prefilledViaUrl).toBe(false);
    expect(t.url).toBe(chatgpt.homeUrl);
  });

  it("never uses a query param for providers without one", () => {
    const claude = getProvider("claude")!;
    const t = webChatTarget(claude, "hi");
    expect(t.prefilledViaUrl).toBe(false);
    expect(t.url).toBe(claude.homeUrl);
  });
});

describe("messagesToPrompt", () => {
  it("flattens system + user into a single instruction prompt", () => {
    const prompt = messagesToPrompt([
      { role: "system", content: "Be concise." },
      { role: "user", content: "Write a cover letter." },
    ]);
    expect(prompt).toContain("Be concise.");
    expect(prompt).toContain("Write a cover letter.");
    expect(prompt).toContain("ONLY the requested text");
  });
});
