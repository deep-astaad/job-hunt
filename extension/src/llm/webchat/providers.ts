/**
 * Bring-your-own-LLM via web chat. Instead of an API key, the user hands a
 * generated prompt to a provider's web chat UI (Claude, ChatGPT, Gemini, Kimi)
 * and the answer comes back into the form.
 *
 * This module is the pure, testable core: the provider registry plus URL/target
 * construction. DOM injection/capture lives in the provider content script
 * (src/content/webchat.ts), keyed off these selectors.
 */

export interface WebChatProvider {
  id: string;
  label: string;
  /** Where to open a fresh chat. */
  homeUrl: string;
  /** Hostname patterns that identify this provider's pages. */
  hostMatch: RegExp;
  /**
   * Query param that pre-fills (and usually sends) a prompt, if the provider
   * supports it. Only used for short prompts — long ones overflow URL limits,
   * so we fall back to clipboard + auto-inject.
   */
  queryParam?: string;
  /** Composer element selectors, tried in order. */
  composerSelectors: string[];
  /** Send-button selectors, tried in order (Enter is the fallback). */
  sendSelectors: string[];
  /** Latest assistant-message selectors, tried in order. */
  responseSelectors: string[];
}

export const WEB_CHAT_PROVIDERS: WebChatProvider[] = [
  {
    id: "claude",
    label: "Claude",
    homeUrl: "https://claude.ai/new",
    hostMatch: /(^|\.)claude\.ai$/,
    composerSelectors: [
      'div[contenteditable="true"].ProseMirror',
      'div[contenteditable="true"]',
      '[data-testid="chat-input"]',
    ],
    sendSelectors: [
      'button[aria-label="Send message"]',
      'button[aria-label="Send Message"]',
      'button[type="submit"]',
    ],
    responseSelectors: [
      ".font-claude-message",
      '[data-testid="message-content"]',
      'div[data-is-streaming="false"]',
    ],
  },
  {
    id: "chatgpt",
    label: "ChatGPT",
    homeUrl: "https://chatgpt.com/",
    hostMatch: /(^|\.)(chatgpt\.com|chat\.openai\.com)$/,
    queryParam: "q",
    composerSelectors: [
      "#prompt-textarea",
      'div[contenteditable="true"]#prompt-textarea',
      'textarea[data-id]',
      "textarea",
    ],
    sendSelectors: [
      'button[data-testid="send-button"]',
      'button[aria-label*="Send"]',
    ],
    responseSelectors: [
      '[data-message-author-role="assistant"] .markdown',
      '[data-message-author-role="assistant"]',
    ],
  },
  {
    id: "gemini",
    label: "Gemini",
    homeUrl: "https://gemini.google.com/app",
    hostMatch: /(^|\.)gemini\.google\.com$/,
    composerSelectors: [
      "rich-textarea div[contenteditable='true']",
      "div[contenteditable='true']",
      "textarea",
    ],
    sendSelectors: [
      'button[aria-label*="Send"]',
      "button.send-button",
    ],
    responseSelectors: [
      "message-content .markdown",
      "message-content",
      ".model-response-text",
    ],
  },
  {
    id: "kimi",
    label: "Kimi",
    homeUrl: "https://www.kimi.com/",
    hostMatch: /(^|\.)(kimi\.com|kimi\.moonshot\.cn|moonshot\.cn)$/,
    composerSelectors: [
      "div[contenteditable='true']",
      "textarea",
      ".chat-input-editor",
    ],
    sendSelectors: [
      'button[aria-label*="Send"]',
      ".send-button",
    ],
    responseSelectors: [
      ".markdown",
      ".segment-assistant",
      ".chat-content-item-assistant",
    ],
  },
];

export function getProvider(id: string): WebChatProvider | undefined {
  return WEB_CHAT_PROVIDERS.find((p) => p.id === id);
}

export function detectProviderByHost(host: string): WebChatProvider | undefined {
  return WEB_CHAT_PROVIDERS.find((p) => p.hostMatch.test(host));
}

/** Below this prompt length we may pre-fill via the URL query param. */
export const QUERY_PARAM_MAX = 1800;

export interface WebChatTarget {
  url: string;
  /** True when the prompt is carried in the URL (no clipboard step needed). */
  prefilledViaUrl: boolean;
}

/**
 * Build the tab URL to open for a handoff. Short prompts can ride the provider's
 * query param (auto-prefills); longer ones open a blank chat and are injected by
 * the content script (with clipboard as the user-visible fallback).
 */
export function webChatTarget(
  provider: WebChatProvider,
  prompt: string
): WebChatTarget {
  if (provider.queryParam && prompt.length <= QUERY_PARAM_MAX) {
    const u = new URL(provider.homeUrl);
    u.searchParams.set(provider.queryParam, prompt);
    return { url: u.toString(), prefilledViaUrl: true };
  }
  return { url: provider.homeUrl, prefilledViaUrl: false };
}
