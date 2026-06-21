import type { FieldDescriptor } from "@/shared/types";
import { getElement } from "./detector";
import { getAdapter } from "./platforms";

/**
 * Set a value on a control in a framework-safe way. React/Vue/Angular track an
 * internal value and ignore a plain `el.value = x`, so we call the *native*
 * setter and dispatch input/change/blur to make the framework register it.
 */
export async function fillField(
  field: FieldDescriptor,
  value: string,
  platformId: string,
  resumeFile?: File,
  force = false
): Promise<boolean> {
  const el = getElement(field.id);
  if (!el) return false;

  // Don't clobber a value the user already typed — UNLESS this is a user-
  // initiated fill (force). Native <select>/radio always report a current
  // value, so without force an explicit "Fill" click would be a no-op.
  if (!force && field.existingValue && field.existingValue.trim()) return false;

  switch (field.kind) {
    case "file":
      return resumeFile ? attachFile(el as HTMLInputElement, resumeFile) : false;
    case "select":
      return fillSelect(el as HTMLSelectElement, value);
    case "radio":
      return fillRadio(field, value);
    case "checkbox":
      return fillCheckbox(el as HTMLInputElement, value);
    case "contenteditable":
      return fillContentEditable(el, value);
    case "combobox":
      return fillCombobox(el, value, platformId);
    default:
      return fillTextLike(el as HTMLInputElement | HTMLTextAreaElement, value, field);
  }
}

function fillTextLike(
  el: HTMLInputElement | HTMLTextAreaElement,
  value: string,
  field: FieldDescriptor
): boolean {
  const v = field.maxLength ? value.slice(0, field.maxLength) : value;
  setNativeValue(el, v);
  fireInputEvents(el);
  return true;
}

function fillSelect(el: HTMLSelectElement, value: string): boolean {
  const opts = Array.from(el.options).map((o) => ({
    value: o.value,
    label: (o.textContent ?? o.value).trim(),
  }));
  const match = bestOption(value, opts);
  if (!match) return false;
  el.value = match.value;
  fireInputEvents(el);
  return true;
}

/**
 * Pick the option that best matches a desired value: exact (value or label) →
 * startsWith → word/contains → yes/no synonyms. Case-insensitive. Shared by the
 * select filler and the resolver (so a suggestion can show the real option text).
 */
export function bestOption<T extends { value: string; label: string }>(
  value: string,
  options: T[]
): T | undefined {
  const want = value.trim().toLowerCase();
  if (!want) return undefined;
  const norm = (s: string) => s.trim().toLowerCase();
  const real = options.filter((o) => o.value !== "" || norm(o.label) !== "");

  const exact = real.find((o) => norm(o.value) === want || norm(o.label) === want);
  if (exact) return exact;
  const starts = real.find((o) => norm(o.label).startsWith(want) || want.startsWith(norm(o.label)));
  if (starts) return starts;
  const contains = real.find((o) => norm(o.label).includes(want) || want.includes(norm(o.label)));
  if (contains) return contains;

  // yes/no normalization (eligibility-style dropdowns)
  const yes = /^(yes|true)$/.test(want);
  const no = /^(no|false)$/.test(want);
  if (yes || no) {
    return real.find((o) => {
      const l = norm(o.label);
      return yes ? l.startsWith("yes") : l.startsWith("no");
    });
  }
  return undefined;
}

function fillRadio(field: FieldDescriptor, value: string): boolean {
  const want = value.trim().toLowerCase();
  const opt = field.options?.find(
    (o) =>
      o.value.toLowerCase() === want ||
      o.label.trim().toLowerCase() === want ||
      o.label.trim().toLowerCase().includes(want)
  );
  if (!opt || !field.groupName) return false;
  const input = document.querySelector<HTMLInputElement>(
    `input[type="radio"][name="${cssEscape(field.groupName)}"][value="${cssEscape(opt.value)}"]`
  );
  if (!input) return false;
  input.checked = true;
  input.click();
  fireInputEvents(input);
  return true;
}

function fillCheckbox(el: HTMLInputElement, value: string): boolean {
  const truthy = /^(yes|true|on|checked|1)$/i.test(value.trim());
  if (el.checked !== truthy) el.click();
  return true;
}

function fillContentEditable(el: HTMLElement, value: string): boolean {
  el.focus();
  el.textContent = value;
  fireInputEvents(el);
  return true;
}

async function fillCombobox(
  el: HTMLElement,
  value: string,
  platformId: string
): Promise<boolean> {
  // Let a platform adapter handle bespoke widgets (Workday/Ashby) first.
  const adapter = getAdapter(platformId);
  if (adapter?.fillCustom) {
    const handled = await adapter.fillCustom(el, value);
    if (handled) return true;
  }
  return typeAndSelect(el, value);
}

/**
 * Type into a searchable dropdown and click the matching option. Handles the
 * common "type to filter, pick from a popup list" pattern used by react-select,
 * Ashby, headless-ui comboboxes, etc. Returns true only when an option was
 * actually selected.
 */
export async function typeAndSelect(
  el: HTMLElement,
  value: string
): Promise<boolean> {
  const input = findTextInput(el);
  const target = input ?? el;
  target.focus();
  target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  target.click?.();

  if (input) {
    setNativeValue(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    // Some widgets only filter in response to keyboard events.
    const last = value.slice(-1) || "a";
    for (const type of ["keydown", "keyup"]) {
      input.dispatchEvent(
        new KeyboardEvent(type, { key: last, bubbles: true })
      );
    }
  }

  const option = await waitForOption(value, 1500);
  if (option) {
    option.scrollIntoView?.({ block: "nearest" });
    option.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    option.click();
    target.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  // Last resort: commit the typed value with Enter (some widgets accept it).
  if (input) {
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    input.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
  }
  return false;
}

function findTextInput(el: HTMLElement): HTMLInputElement | null {
  if (el.tagName === "INPUT") return el as HTMLInputElement;
  const inside = el.querySelector<HTMLInputElement>("input");
  if (inside) return inside;
  // react-select renders the input as a sibling within the control container.
  const container = el.closest<HTMLElement>(
    "[class*='select'], [class*='combobox'], [role='combobox']"
  );
  return container?.querySelector<HTMLInputElement>("input") ?? null;
}

const OPTION_SELECTORS =
  "[role='option'], [class*='option'], li[role], li, [data-automation-id='promptOption']";

function waitForOption(
  value: string,
  timeoutMs: number
): Promise<HTMLElement | null> {
  const want = value.trim().toLowerCase();
  const pick = (): HTMLElement | null => {
    const nodes = Array.from(
      document.querySelectorAll<HTMLElement>(OPTION_SELECTORS)
    ).filter((n) => n.offsetParent !== null && (n.textContent ?? "").trim());
    const byText = (pred: (t: string) => boolean) =>
      nodes.find((n) => pred((n.textContent ?? "").trim().toLowerCase()));
    return (
      byText((t) => t === want) ??
      byText((t) => t.startsWith(want)) ??
      byText((t) => t.includes(want)) ??
      null
    );
  };
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = () => {
      const found = pick();
      if (found) return resolve(found);
      if (Date.now() - start > timeoutMs) return resolve(null);
      setTimeout(tick, 80);
    };
    tick();
  });
}

function attachFile(el: HTMLInputElement, file: File): boolean {
  try {
    const dt = new DataTransfer();
    dt.items.add(file);
    el.files = dt.files;
    fireInputEvents(el);
    return true;
  } catch {
    return false; // some ATS use custom upload widgets; flagged for manual attach
  }
}

/** Call the prototype's native value setter so React's tracker sees the change. */
function setNativeValue(el: HTMLElement, value: string): void {
  const proto =
    el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (setter) setter.call(el, value);
  else (el as HTMLInputElement).value = value;
}

function fireInputEvents(el: HTMLElement): void {
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: true }));
}

function cssEscape(s: string): string {
  if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(s);
  return s.replace(/["\\]/g, "\\$&");
}
