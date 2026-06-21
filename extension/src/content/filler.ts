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
  resumeFile?: File
): Promise<boolean> {
  const el = getElement(field.id);
  if (!el) return false;

  // Don't clobber a value the user already typed.
  if (field.existingValue && field.existingValue.trim()) return false;

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
  const want = value.trim().toLowerCase();
  const match = Array.from(el.options).find(
    (o) =>
      o.value.toLowerCase() === want ||
      (o.textContent ?? "").trim().toLowerCase() === want ||
      (o.textContent ?? "").trim().toLowerCase().includes(want)
  );
  if (!match) return false;
  el.value = match.value;
  fireInputEvents(el);
  return true;
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
  // Generic best-effort: focus, type, dispatch — works for many combobox impls.
  el.focus();
  setNativeValue(el as unknown as HTMLInputElement, value);
  fireInputEvents(el);
  return false; // not certain; caller flags as low confidence
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
