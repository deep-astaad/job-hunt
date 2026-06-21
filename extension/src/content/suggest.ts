import { describeElement } from "./detector";
import { resolveSingle } from "./resolver";
import { fillField } from "./filler";
import { fetchResumeFile } from "./resume";
import { getProfile } from "@/storage/profile";
import { getSettings, type Settings } from "@/storage/settings";
import type { CandidateProfile } from "@/profile/schema";
import type { FieldDescriptor, FieldResolution } from "@/shared/types";
import { sendToBackground, type Message } from "@/shared/messages";

/**
 * On-focus suggestion UX (the default interaction). When the user focuses an
 * empty field, AppFill offers to fill it with a recommended value — like the
 * browser's own autofill bubble, but driven by your profile + learned answers.
 * Nothing is filled until the user clicks "Fill". An optional "✨ AI" action
 * asks the LLM for fields we can't map deterministically.
 */
let profile: CandidateProfile;
let settings: Settings;
let domain = location.hostname;
let platformId = "generic";

let host: HTMLElement | null = null;
let shadow: ShadowRoot | null = null;
let currentField: FieldDescriptor | null = null;
let currentEl: HTMLElement | null = null;

export async function installSuggestions(domainArg: string, platform: string) {
  domain = domainArg;
  platformId = platform;
  profile = await getProfile();
  settings = await getSettings();

  chrome.storage.onChanged.addListener(async () => {
    profile = await getProfile();
    settings = await getSettings();
  });

  document.addEventListener("focusin", onFocus, true);
  document.addEventListener("scroll", reposition, true);
  window.addEventListener("resize", reposition);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });
}

async function onFocus(e: FocusEvent) {
  if (!settings.suggestOnFocus) return hide();
  const el = e.target as HTMLElement | null;
  if (!el || !isFocusableField(el)) return hide();

  const field = describeElement(el);
  if (!field) return hide();
  // Don't nag on fields the user has already filled.
  if (field.existingValue && field.existingValue.trim()) return hide();

  const resolution = await resolveSingle(field, profile, domain, platformId);
  currentField = field;
  currentEl = el;

  if (resolution) {
    render(el, resolution);
  } else if (canUseLlm()) {
    renderAiOnly(el, field);
  } else {
    hide();
  }
}

function isFocusableField(el: HTMLElement): boolean {
  const tag = el.tagName.toLowerCase();
  if (tag === "textarea" || tag === "select") return true;
  if (el.getAttribute("contenteditable") === "true") return true;
  if (el.getAttribute("role") === "combobox") return true;
  if (tag === "input") {
    const type = ((el as HTMLInputElement).type || "text").toLowerCase();
    return !["hidden", "submit", "button", "reset", "checkbox", "radio"].includes(type);
  }
  return false;
}

function canUseLlm(): boolean {
  return Boolean(settings.llmFieldMappingEnabled && settings.openaiApiKey);
}

// --- rendering (isolated in a shadow root so host-page CSS can't touch it) ---
function ensureHost(): ShadowRoot {
  if (shadow) return shadow;
  host = document.createElement("div");
  host.style.position = "absolute";
  host.style.zIndex = "2147483647";
  host.style.top = "0";
  host.style.left = "0";
  shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = `
    .box { position:absolute; font:13px/1.4 system-ui,sans-serif; background:#111827;
      color:#fff; border-radius:10px; padding:8px 10px; box-shadow:0 6px 24px rgba(0,0,0,.25);
      display:flex; align-items:center; gap:8px; max-width:320px; }
    .mark { font-weight:700; color:#93c5fd; }
    .val { max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; opacity:.9; }
    button { font:600 12px system-ui,sans-serif; border:none; border-radius:7px; padding:5px 9px; cursor:pointer; }
    .fill { background:#2563eb; color:#fff; }
    .ai { background:#374151; color:#e5e7eb; }
    .x { background:transparent; color:#9ca3af; padding:4px 6px; }
  `;
  shadow.appendChild(style);
  document.body.appendChild(host);
  return shadow;
}

function render(anchor: HTMLElement, resolution: FieldResolution) {
  const sh = ensureHost();
  clearBox(sh);
  const box = document.createElement("div");
  box.className = "box";

  const mark = document.createElement("span");
  mark.className = "mark";
  mark.textContent = "AppFill";
  box.appendChild(mark);

  if (resolution.isResumeFile) {
    box.appendChild(text("Attach your resume?"));
  } else {
    const v = document.createElement("span");
    v.className = "val";
    v.textContent = resolution.value ?? "";
    v.title = resolution.value ?? "";
    box.appendChild(v);
  }

  const fill = button("fill", "Fill", async () => {
    await applyResolution(resolution);
    hide();
  });
  box.appendChild(fill);

  if (canUseLlm() && !resolution.isResumeFile) {
    box.appendChild(button("ai", "✨ AI", () => askAi()));
  }
  box.appendChild(button("x", "✕", hide));

  sh.appendChild(box);
  position(box, anchor);
}

function renderAiOnly(anchor: HTMLElement, _field: FieldDescriptor) {
  const sh = ensureHost();
  clearBox(sh);
  const box = document.createElement("div");
  box.className = "box";
  const mark = document.createElement("span");
  mark.className = "mark";
  mark.textContent = "AppFill";
  box.appendChild(mark);
  box.appendChild(text("Ask AI to fill this?"));
  box.appendChild(button("ai", "✨ Fill with AI", () => askAi()));
  box.appendChild(button("x", "✕", hide));
  sh.appendChild(box);
  position(box, anchor);
}

async function applyResolution(resolution: FieldResolution) {
  if (!currentField) return;
  if (resolution.isResumeFile) {
    const file = await fetchResumeFile();
    if (file) await fillField(currentField, "", platformId, file);
    return;
  }
  if (resolution.value) await fillField(currentField, resolution.value, platformId);
}

async function askAi() {
  if (!currentField) return;
  const sh = ensureHost();
  const box = sh.querySelector(".box");
  if (box) box.textContent = "Asking AI…";
  try {
    const resp = await sendToBackground({
      type: "LLM_MAP_FIELDS",
      fields: [currentField],
      profile,
    } satisfies Message);
    if (resp.ok && "resolutions" in resp && resp.resolutions[0]?.value) {
      await fillField(currentField, resp.resolutions[0].value, platformId);
    }
  } catch {
    /* ignore */
  }
  hide();
}

function position(box: HTMLElement, anchor: HTMLElement) {
  const r = anchor.getBoundingClientRect();
  // Place just below the field; flip above if near the viewport bottom.
  const below = r.bottom + 6 + window.scrollY;
  const aboveFlip = window.innerHeight - r.bottom < 60;
  box.style.left = `${r.left + window.scrollX}px`;
  box.style.top = aboveFlip
    ? `${r.top + window.scrollY - 44}px`
    : `${below}px`;
}

function reposition() {
  if (!currentEl || !shadow) return;
  const box = shadow.querySelector<HTMLElement>(".box");
  if (box) position(box, currentEl);
}

function hide() {
  if (shadow) clearBox(shadow);
  currentField = null;
  currentEl = null;
}

function clearBox(sh: ShadowRoot) {
  sh.querySelectorAll(".box").forEach((b) => b.remove());
}

function button(cls: string, label: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = cls;
  b.textContent = label;
  // mousedown (not click) so we act before the field's blur tears the box down.
  b.addEventListener("mousedown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick();
  });
  return b;
}

function text(s: string): HTMLSpanElement {
  const span = document.createElement("span");
  span.textContent = s;
  span.style.opacity = "0.9";
  return span;
}
