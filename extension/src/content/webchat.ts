/**
 * Provider-side of the BYO-LLM web-chat handoff. Runs only on the chat
 * providers' own pages (Claude / ChatGPT / Gemini / Kimi). When a handoff is
 * pending for this provider it:
 *   1. best-effort injects the prompt into the composer and submits it, and
 *   2. shows an AppFill banner with a one-click "Send answer back to my form"
 *      button (the reliable path), plus a best-effort auto-capture once the
 *      reply finishes streaming.
 *
 * Everything is wrapped so a selector miss degrades to the manual path: the user
 * can always copy the answer themselves.
 */
import {
  detectProviderByHost,
  type WebChatProvider,
} from "@/llm/webchat/providers";
import { getHandoff, markHandoffConsumed, type Handoff } from "@/storage/handoff";
import { getSettings } from "@/storage/settings";
import { sendToBackground } from "@/shared/messages";

const provider = detectProviderByHost(location.hostname);

if (provider) void run(provider);

async function run(p: WebChatProvider): Promise<void> {
  const handoff = await getHandoff();
  if (!handoff || handoff.providerId !== p.id) return;

  banner(p, handoff);

  if (!handoff.consumed) {
    const settings = await getSettings();
    if (settings.webchatAutoInject) {
      // Give the SPA a moment to mount its composer.
      const composer = await waitFor(() => firstMatch(p.composerSelectors), 8000);
      if (composer) {
        await markHandoffConsumed(handoff.id);
        void injectPrompt(p, handoff.prompt);
      }
    } else {
      await markHandoffConsumed(handoff.id);
      observeResponse(p);
    }
  } else {
    observeResponse(p);
  }
}

// ----------------------------------------------------------- prompt inject ---

async function injectPrompt(p: WebChatProvider, prompt: string): Promise<void> {
  const el = firstMatch(p.composerSelectors);
  if (!el) return; // user pastes manually
  el.focus();
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) {
    setNativeValue(el, prompt);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  } else {
    // contenteditable
    el.focus();
    document.execCommand("selectAll", false);
    document.execCommand("insertText", false, prompt);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  await sleep(400);
  const send = firstMatch(p.sendSelectors) as HTMLButtonElement | null;
  if (send && !send.disabled) {
    send.click();
  } else {
    el.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })
    );
  }
  observeResponse(p);
}

// ----------------------------------------------------------- capture ----------

let lastSent = "";

function latestResponseText(p: WebChatProvider): string {
  for (const sel of p.responseSelectors) {
    const nodes = document.querySelectorAll<HTMLElement>(sel);
    if (nodes.length) {
      const text = nodes[nodes.length - 1].innerText?.trim();
      if (text) return text;
    }
  }
  return "";
}

/** Best-effort: when the reply stops changing for ~2.5s, send it back once. */
function observeResponse(p: WebChatProvider): void {
  let timer: number | undefined;
  const obs = new MutationObserver(() => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      const text = latestResponseText(p);
      if (text && text.length > 12 && text !== lastSent) {
        lastSent = text;
        void sendResult(text);
        flashBanner("Answer sent back to your form ✓");
      }
    }, 2500);
  });
  obs.observe(document.body, { childList: true, subtree: true, characterData: true });
  // Stop watching after 3 minutes regardless.
  window.setTimeout(() => obs.disconnect(), 180_000);
}

async function sendResult(text: string): Promise<void> {
  const h = await getHandoff();
  if (!h) return;
  await sendToBackground({ type: "WEBCHAT_RESULT", id: h.id, text });
}

// ----------------------------------------------------------- banner UI --------

let bannerEl: HTMLElement | null = null;

function banner(p: WebChatProvider, _h: Handoff): void {
  const host = document.createElement("div");
  host.style.cssText =
    "position:fixed;z-index:2147483647;right:16px;bottom:16px;font:13px system-ui,sans-serif;";
  const shadow = host.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      .card{background:#111827;color:#fff;border-radius:12px;padding:12px 14px;max-width:300px;
        box-shadow:0 8px 30px rgba(0,0,0,.35);}
      .t{font-weight:700;color:#93c5fd;margin-bottom:4px;}
      .m{opacity:.92;margin-bottom:9px;line-height:1.4;}
      button{font:600 12px system-ui;border:none;border-radius:8px;padding:7px 11px;cursor:pointer;width:100%;}
      .send{background:#2563eb;color:#fff;}
      .x{background:transparent;color:#9ca3af;width:auto;padding:4px;position:absolute;top:6px;right:8px;}
      .wrap{position:relative;}
    </style>
    <div class="card wrap">
      <button class="x" title="Dismiss">✕</button>
      <div class="t">AppFill · ${p.label}</div>
      <div class="m">When ${p.label} finishes, click below to send the answer
        back to your application form.</div>
      <button class="send">Send answer back to my form ↩</button>
    </div>`;
  shadow.querySelector(".send")?.addEventListener("click", () => {
    const text = latestResponseText(p);
    if (!text) return flashBanner("Couldn't read the answer — copy it manually.");
    lastSent = text;
    void sendResult(text);
    flashBanner("Sent ✓ Switch back to your form.");
  });
  shadow.querySelector(".x")?.addEventListener("click", () => host.remove());
  document.documentElement.appendChild(host);
  bannerEl = host;
}

function flashBanner(text: string): void {
  const m = bannerEl?.shadowRoot?.querySelector<HTMLElement>(".m");
  if (m) m.textContent = text;
}

// ----------------------------------------------------------- helpers ----------

function firstMatch(selectors: string[]): HTMLElement | null {
  for (const sel of selectors) {
    const el = document.querySelector<HTMLElement>(sel);
    if (el && isVisible(el)) return el;
  }
  return null;
}

function isVisible(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

function setNativeValue(el: HTMLTextAreaElement | HTMLInputElement, value: string): void {
  const proto = Object.getPrototypeOf(el);
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  desc?.set?.call(el, value);
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function waitFor<T>(fn: () => T | null, timeoutMs: number): Promise<T | null> {
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = () => {
      const v = fn();
      if (v) return resolve(v);
      if (Date.now() - start > timeoutMs) return resolve(null);
      setTimeout(tick, 200);
    };
    tick();
  });
}
