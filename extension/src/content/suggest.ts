import { describeElement } from "./detector";
import { resolveSingle } from "./resolver";
import { mapFieldDeterministic } from "./mapper";
import { fillField } from "./filler";
import { fetchResumeFile } from "./resume";
import { getProfile, updateProfileField } from "@/storage/profile";
import { remember } from "@/storage/memory";
import { getSettings, type Settings } from "@/storage/settings";
import {
  type CandidateProfile,
  type CanonicalKey,
  isStorableKey,
} from "@/profile/schema";
import type { FieldDescriptor, FieldResolution } from "@/shared/types";
import { sendToBackground, type Message, type JobContext } from "@/shared/messages";
import { buildCoverLetterMessages, buildScreeningMessages } from "@/llm/prompts";
import { messagesToPrompt } from "@/llm/promptText";
import { getProvider } from "@/llm/webchat/providers";
import { extractJobContext } from "./jobContext";

/**
 * On-focus assistant. When you focus a field, AppFill offers — in order of
 * usefulness — a remembered/profile value to fill, an AI fill, inline content
 * generation (for textareas), or a manual input box that *learns* the value for
 * next time and optionally saves it to your profile. Nothing fills until you act.
 */
let profile: CandidateProfile;
let settings: Settings;
let domain = location.hostname;
let platformId = "generic";

let host: HTMLElement | null = null;
let shadow: ShadowRoot | null = null;
let field: FieldDescriptor | null = null;
let anchorEl: HTMLElement | null = null;
let canonicalKey: CanonicalKey | undefined;

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
  const el = e.target as HTMLElement | null;
  // Ignore focus moving into our own UI (shadow events retarget to the host).
  if (!el || el === host) return;
  if (!settings.suggestOnFocus) return hide();
  if (!isFocusableField(el)) return hide();

  const f = describeElement(el);
  if (!f) return hide();
  const isOption = f.kind === "select" || f.kind === "combobox";
  if (!isOption && f.existingValue && f.existingValue.trim()) return hide();

  field = f;
  anchorEl = el;
  canonicalKey = mapFieldDeterministic(f)?.key;

  const resolution = await resolveSingle(f, profile, domain, platformId);
  if (resolution) renderSuggestion(resolution);
  else renderNoValue();
}

/** Fill whatever field is currently focused (driven by context menu / shortcut). */
export async function fillFocused(): Promise<void> {
  const el = document.activeElement as HTMLElement | null;
  if (!el || !isFocusableField(el)) return;
  const f = describeElement(el);
  if (!f) return;
  field = f;
  anchorEl = el;
  canonicalKey = mapFieldDeterministic(f)?.key;
  const r = await resolveSingle(f, profile, domain, platformId);
  if (r) {
    const ok = await applyResolution(r);
    if (!ok) renderSuggestion(r);
  } else if (canUseLlm()) {
    await askAi();
  } else {
    renderNoValue();
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

// Direct-API field mapping needs a key; web chat can't do structured mapping.
const canUseLlm = () =>
  Boolean(
    settings.llmMode === "direct" &&
      settings.llmFieldMappingEnabled &&
      settings.openaiApiKey
  );
// Generation works either via the API (direct) or web-chat handoff (no key).
const generationAvailable = () =>
  settings.llmMode === "webchat" ||
  (settings.llmMode === "direct" && Boolean(settings.openaiApiKey));
const canGenerate = () =>
  generationAvailable() &&
  (settings.coverLetterEnabled ||
    settings.screeningAnswersEnabled ||
    settings.fieldTailoringEnabled);

// ---------------------------------------------------------------- rendering --
function renderSuggestion(resolution: FieldResolution) {
  const box = startBox();
  if (resolution.isResumeFile) {
    box.appendChild(text("Attach your resume?"));
  } else {
    box.appendChild(valueChip(resolution.value ?? ""));
  }
  box.appendChild(
    button("fill", "Fill", async () => {
      const ok = await applyResolution(resolution);
      if (ok) flashSavedHint();
      else message("Couldn't auto-select — pick it manually", true);
    })
  );
  if (!resolution.isResumeFile) {
    box.appendChild(button("ghost", "✎", () => renderInput(resolution.value ?? "")));
    if (canUseLlm()) box.appendChild(button("ghost", "✨", askAi));
  }
  box.appendChild(closeBtn());
  finishBox(box);
}

function renderNoValue() {
  const box = startBox();
  const isTextarea = field?.kind === "textarea" || field?.kind === "contenteditable";
  box.appendChild(text(isTextarea ? "No saved value" : "Not in your profile"));
  box.appendChild(button("fill", "Enter value", () => renderInput("")));
  if (canUseLlm()) box.appendChild(button("ghost", "✨ AI", askAi));
  if (isTextarea && canGenerate())
    box.appendChild(button("ghost", "✨ Generate", generateIntoField));
  box.appendChild(closeBtn());
  finishBox(box);
}

/** Manual input: type a value, fill it, learn it, optionally save to profile. */
function renderInput(prefill: string) {
  const box = startBox();
  const input = document.createElement("input");
  input.className = "in";
  input.value = prefill;
  input.placeholder = "Type a value…";
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") void commitManual(input.value);
    if (e.key === "Escape") hide();
  });
  box.appendChild(input);
  box.appendChild(button("fill", "Fill & save", () => void commitManual(input.value)));
  box.appendChild(closeBtn());
  finishBox(box);
  setTimeout(() => input.focus(), 0);
}

async function commitManual(value: string) {
  const v = value.trim();
  if (!field || !v) return hide();
  const ok = await fillField(field, v, platformId, undefined, true);
  if (!ok) return message("Couldn't fill — pick it manually", true);
  // Learn it for next time (per-domain → platform → global).
  await remember([{ signature: field.signature, value: v }], domain, platformId);
  // Offer to persist structured fields to the profile too.
  if (canonicalKey && isStorableKey(canonicalKey)) {
    const key = canonicalKey;
    const box = startBox();
    box.appendChild(text("Saved ✓ Add to your profile?"));
    box.appendChild(
      button("fill", "Save to profile", async () => {
        await updateProfileField(key, v);
        profile = await getProfile();
        message("Added to profile ✓");
        setTimeout(hide, 900);
      })
    );
    box.appendChild(closeBtn());
    finishBox(box);
  } else {
    message("Saved — will reuse next time ✓");
    setTimeout(hide, 1100);
  }
}

async function askAi() {
  if (!field) return;
  message("Asking AI…");
  try {
    const resp = await sendToBackground({
      type: "LLM_MAP_FIELDS",
      fields: [field],
      profile,
    } satisfies Message);
    const value =
      resp.ok && "resolutions" in resp ? resp.resolutions[0]?.value : undefined;
    if (!value) return renderInput("");
    const ok = await fillField(field, value, platformId, undefined, true);
    if (ok) {
      await remember([{ signature: field.signature, value }], domain, platformId);
      message(`✓ ${value}`);
      setTimeout(hide, 900);
    } else {
      renderInput(value); // let the user adjust & fill manually
    }
  } catch {
    message("AI request failed", true);
  }
}

async function generateIntoField() {
  if (!field) return;
  const label = (field.label ?? "").toLowerCase();
  const kind: "cover_letter" | "screening_answer" =
    /cover letter|motivation/.test(label) ? "cover_letter" : "screening_answer";

  if (settings.llmMode === "webchat") {
    return generateViaWebchat(kind);
  }

  message("Generating…");
  try {
    const resp = await sendToBackground({
      type: "LLM_GENERATE",
      kind,
      profile,
      job: jobContext(),
      prompt: field.label ?? "",
      maxLength: field.maxLength,
    } satisfies Message);
    if (resp.ok && "text" in resp) {
      await fillField(field, resp.text, platformId, undefined, true);
      message("Generated ✓ review before submitting", true);
    } else if (!resp.ok) {
      message(resp.error, true);
    }
  } catch {
    message("Generation failed", true);
  }
}

function jobContext(): JobContext {
  return extractJobContext();
}

/**
 * BYO-LLM path: build the prompt, hand it to the configured web chat (opened by
 * the background worker), and wait for the answer. The answer returns
 * automatically when possible; the paste-back box is the reliable fallback.
 */
async function generateViaWebchat(kind: "cover_letter" | "screening_answer") {
  if (!field) return;
  const messages =
    kind === "cover_letter"
      ? buildCoverLetterMessages(profile, jobContext())
      : buildScreeningMessages(
          profile,
          field.label ?? "",
          jobContext(),
          field.maxLength
        );
  const prompt = messagesToPrompt(messages);
  const provider = getProvider(settings.webchatProvider);
  const label = provider?.label ?? "your LLM";

  try {
    await navigator.clipboard.writeText(prompt);
  } catch {
    /* clipboard may be blocked; auto-inject / manual paste still works */
  }

  const resp = await sendToBackground({
    type: "WEBCHAT_HANDOFF",
    providerId: settings.webchatProvider,
    prompt,
    fieldHandle: field.id,
  } satisfies Message);
  if (!resp.ok) return message(resp.error, true);

  renderPasteBack(label);
}

/** Waiting UI: answer auto-returns, or the user pastes it here to fill. */
function renderPasteBack(providerLabel: string) {
  const box = startBox();
  box.appendChild(
    text(`Opened ${providerLabel}. Answer will return here — or paste it:`)
  );
  const ta = document.createElement("textarea");
  ta.className = "ta";
  ta.placeholder = "Paste the answer…";
  ta.addEventListener("keydown", (e) => e.stopPropagation());
  box.appendChild(ta);
  box.appendChild(
    button("fill", "Fill", async () => {
      const v = ta.value.trim();
      if (!v || !field) return;
      await fillField(field, v, platformId, undefined, true);
      message("Filled ✓ review before submitting", true);
    })
  );
  box.appendChild(closeBtn());
  finishBox(box);
}

async function applyResolution(resolution: FieldResolution): Promise<boolean> {
  if (!field) return false;
  if (resolution.isResumeFile) {
    const file = await fetchResumeFile();
    return file ? fillField(field, "", platformId, file, true) : false;
  }
  if (resolution.value)
    return fillField(field, resolution.value, platformId, undefined, true);
  return false;
}

function flashSavedHint() {
  // Successful suggestion fill — nothing to learn (already known), just close.
  hide();
}

// --------------------------------------------------------------- box plumbing -
function ensureHost(): ShadowRoot {
  if (shadow) return shadow;
  host = document.createElement("div");
  host.style.cssText = "position:absolute;z-index:2147483647;top:0;left:0;";
  shadow = host.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = `
    .box{position:absolute;font:13px/1.4 system-ui,sans-serif;background:#111827;color:#fff;
      border-radius:10px;padding:7px 9px;box-shadow:0 6px 24px rgba(0,0,0,.28);
      display:flex;align-items:center;gap:7px;max-width:360px;}
    .mark{font-weight:700;color:#93c5fd;white-space:nowrap;}
    .val{max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
      background:#1f2937;border-radius:6px;padding:3px 7px;opacity:.95;}
    .msg{opacity:.92;}
    .in{font:13px system-ui,sans-serif;border:1px solid #374151;background:#0b1220;color:#fff;
      border-radius:7px;padding:5px 8px;min-width:150px;outline:none;}
    .in:focus{border-color:#3b82f6;}
    .ta{font:13px system-ui,sans-serif;border:1px solid #374151;background:#0b1220;color:#fff;
      border-radius:7px;padding:6px 8px;min-width:230px;min-height:64px;outline:none;resize:vertical;}
    .ta:focus{border-color:#3b82f6;}
    button{font:600 12px system-ui,sans-serif;border:none;border-radius:7px;padding:5px 9px;cursor:pointer;}
    .fill{background:#2563eb;color:#fff;}
    .ghost{background:#374151;color:#e5e7eb;}
    .x{background:transparent;color:#9ca3af;padding:4px 6px;}
  `;
  shadow.appendChild(style);
  document.body.appendChild(host);
  return shadow;
}

function startBox(): HTMLDivElement {
  const sh = ensureHost();
  sh.querySelectorAll(".box").forEach((b) => b.remove());
  const box = document.createElement("div");
  box.className = "box";
  const mark = document.createElement("span");
  mark.className = "mark";
  mark.textContent = "AppFill";
  box.appendChild(mark);
  return box;
}

function finishBox(box: HTMLDivElement) {
  ensureHost().appendChild(box);
  if (anchorEl) position(box, anchorEl);
}

function message(msg: string, keep = false) {
  const box = startBox();
  box.appendChild(text(msg, "msg"));
  if (keep) box.appendChild(closeBtn());
  finishBox(box);
}

function valueChip(s: string): HTMLSpanElement {
  const v = document.createElement("span");
  v.className = "val";
  v.textContent = s;
  v.title = s;
  return v;
}

function text(s: string, cls = "msg"): HTMLSpanElement {
  const span = document.createElement("span");
  span.className = cls;
  span.textContent = s;
  return span;
}

function closeBtn(): HTMLButtonElement {
  return button("x", "✕", hide);
}

function button(cls: string, label: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = cls;
  b.textContent = label;
  // mousedown (not click) so we act before the field's blur tears the box down,
  // except we still preventDefault to keep page focus where it is.
  b.addEventListener("mousedown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onClick();
  });
  return b;
}

function position(box: HTMLElement, anchor: HTMLElement) {
  const r = anchor.getBoundingClientRect();
  const flipUp = window.innerHeight - r.bottom < 60;
  box.style.left = `${r.left + window.scrollX}px`;
  box.style.top = flipUp
    ? `${r.top + window.scrollY - 44}px`
    : `${r.bottom + 6 + window.scrollY}px`;
}

function reposition() {
  if (!anchorEl || !shadow) return;
  const box = shadow.querySelector<HTMLElement>(".box");
  if (box) position(box, anchorEl);
}

function hide() {
  if (shadow) shadow.querySelectorAll(".box").forEach((b) => b.remove());
  field = null;
  anchorEl = null;
  canonicalKey = undefined;
}
