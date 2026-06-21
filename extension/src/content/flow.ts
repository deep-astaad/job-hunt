/**
 * Multi-page "Fill & Next" flow runner. Drives an ATS wizard one page at a time:
 * fill the current page, let the user review, click the platform's Next on
 * confirm, then re-fill the new page. It hard-stops at the final Submit — AppFill
 * never submits for you.
 *
 * Flow state is persisted (storage/flow.ts) so the runner resumes after a full
 * page reload between steps. Navigation selectors come from the platform adapter
 * (see content/platforms/*).
 */
import { getAdapter } from "./platforms";
import { getFlow, setFlow, clearFlow } from "@/storage/flow";

interface FlowDeps {
  fill: () => Promise<{ fieldCount: number; filledCount: number }>;
  platformId: string;
  domain: string;
}

let deps: FlowDeps | null = null;
let host: HTMLElement | null = null;
let shadow: ShadowRoot | null = null;

export function installFlow(d: FlowDeps): void {
  deps = d;
  // Resume an in-progress flow on the next page (SPA or reload).
  void (async () => {
    const flow = await getFlow();
    if (flow && flow.domain === d.domain) {
      // Let the new page settle before filling.
      setTimeout(() => void runStep(), 900);
    }
  })();
}

export async function startFlow(): Promise<void> {
  if (!deps) return;
  await setFlow({ active: true, domain: deps.domain, step: 1, startedAt: Date.now() });
  await runStep();
}

export async function stopFlow(): Promise<void> {
  await clearFlow();
  teardown();
}

async function runStep(): Promise<void> {
  if (!deps) return;
  const flow = await getFlow();
  if (!flow) return teardown();
  const { filledCount } = await deps.fill();
  renderBar(flow.step, filledCount);
}

async function advance(): Promise<void> {
  if (!deps) return;
  const next = findButton(getAdapter(deps.platformId)?.nextSelectors);
  if (!next) {
    message("No “Next” button found — fill the last fields and submit yourself.");
    return;
  }
  const flow = await getFlow();
  const step = (flow?.step ?? 1) + 1;
  await setFlow({
    active: true,
    domain: deps.domain,
    step,
    startedAt: flow?.startedAt ?? Date.now(),
  });
  message("Advancing…");
  next.click();
  // SPA route changes don't reload, so wait for the DOM to change, then re-fill.
  await waitForNavigation();
  await runStep();
}

/** Resolve once the page looks different (new step rendered) or after a timeout. */
function waitForNavigation(): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      obs.disconnect();
      // small debounce for late-rendering fields
      setTimeout(resolve, 600);
    };
    const obs = new MutationObserver(() => done());
    obs.observe(document.body, { childList: true, subtree: true });
    setTimeout(done, 4000); // hard cap (covers full reloads handled by resume)
  });
}

// ----------------------------------------------------------- control bar ------

function ensure(): ShadowRoot {
  if (shadow) return shadow;
  host = document.createElement("div");
  host.style.cssText =
    "position:fixed;z-index:2147483646;left:16px;bottom:16px;font:13px system-ui,sans-serif;";
  shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = `
    .bar{background:#0f172a;color:#fff;border-radius:12px;padding:11px 13px;display:flex;
      gap:10px;align-items:center;box-shadow:0 8px 30px rgba(0,0,0,.35);max-width:380px;}
    .t{font-weight:700;color:#93c5fd;white-space:nowrap;}
    .m{opacity:.92;}
    button{font:600 12px system-ui;border:none;border-radius:8px;padding:7px 11px;cursor:pointer;}
    .next{background:#2563eb;color:#fff;}
    .ghost{background:#334155;color:#e5e7eb;}
    .stop{background:transparent;color:#f87171;}
  `;
  shadow.appendChild(style);
  document.documentElement.appendChild(host);
  return shadow;
}

function renderBar(step: number, filledCount: number): void {
  const sh = ensure();
  sh.querySelectorAll(".bar").forEach((b) => b.remove());
  const bar = document.createElement("div");
  bar.className = "bar";
  const hasNext = Boolean(findButton(getAdapter(deps?.platformId ?? "")?.nextSelectors));
  const hasSubmit = Boolean(
    findButton(getAdapter(deps?.platformId ?? "")?.submitSelectors)
  );

  bar.appendChild(span("t", `AppFill flow · step ${step}`));
  bar.appendChild(
    span("m", `${filledCount} filled.` + (hasNext ? " Review, then:" : ""))
  );

  if (hasNext) {
    bar.appendChild(btn("next", "Next →", () => void advance()));
    bar.appendChild(btn("ghost", "Fill again", () => void runStep()));
  } else if (hasSubmit) {
    bar.appendChild(span("m", "Final step — review and submit yourself."));
  } else {
    bar.appendChild(btn("ghost", "Fill again", () => void runStep()));
  }
  bar.appendChild(btn("stop", "Stop", () => void stopFlow()));
  sh.appendChild(bar);
}

function message(text: string): void {
  const sh = ensure();
  const m = sh.querySelector<HTMLElement>(".bar .m");
  if (m) m.textContent = text;
}

function teardown(): void {
  host?.remove();
  host = null;
  shadow = null;
}

function findButton(selectors?: string[]): HTMLButtonElement | null {
  if (!selectors) return null;
  for (const sel of selectors) {
    const el = document.querySelector<HTMLButtonElement>(sel);
    if (el && isVisible(el) && !el.disabled) return el;
  }
  return null;
}

function isVisible(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

function span(cls: string, text: string): HTMLSpanElement {
  const s = document.createElement("span");
  s.className = cls;
  s.textContent = text;
  return s;
}

function btn(cls: string, label: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = cls;
  b.textContent = label;
  b.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick();
  });
  return b;
}
