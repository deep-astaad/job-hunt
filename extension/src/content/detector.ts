import type { FieldDescriptor, FieldKind, SelectOption } from "@/shared/types";
import { withSignature } from "./signature";

const HANDLE_ATTR = "data-appfill-id";
let counter = 0;

/** Runtime registry: descriptor id -> the live element it represents. */
const registry = new Map<string, HTMLElement>();

export function getElement(fieldId: string): HTMLElement | undefined {
  return registry.get(fieldId);
}

export function clearRegistry(): void {
  registry.clear();
}

/** Scan the current document for fillable controls. */
export function detectFields(root: ParentNode = document): FieldDescriptor[] {
  const out: FieldDescriptor[] = [];
  const seenRadioGroups = new Set<string>();

  const controls = root.querySelectorAll<HTMLElement>(
    "input, textarea, select, [contenteditable='true'], [role='combobox']"
  );

  for (const el of Array.from(controls)) {
    const kind = kindOf(el);
    if (!kind || !isVisible(el)) continue;

    // Collapse radio groups into a single descriptor with options.
    if (kind === "radio") {
      const groupName = (el as HTMLInputElement).name;
      if (groupName) {
        if (seenRadioGroups.has(groupName)) continue;
        seenRadioGroups.add(groupName);
      }
    }

    const descriptor = describeElement(el);
    if (descriptor) out.push(descriptor);
  }
  return out;
}

/**
 * Build a FieldDescriptor for a single element (used by both the batch scan and
 * the on-focus suggestion flow). Returns undefined if the element isn't a
 * fillable, visible control.
 */
export function describeElement(el: HTMLElement): FieldDescriptor | undefined {
  const kind = kindOf(el);
  if (!kind || !isVisible(el)) return undefined;
  const id = assignHandle(el);
  return withSignature({
    id,
    kind,
    label: labelFor(el),
    name: (el as HTMLInputElement).name || undefined,
    domId: el.id || undefined,
    placeholder: (el as HTMLInputElement).placeholder || undefined,
    autocomplete: el.getAttribute("autocomplete")?.toLowerCase() || undefined,
    ariaLabel: el.getAttribute("aria-label") || undefined,
    required:
      el.hasAttribute("required") || el.getAttribute("aria-required") === "true",
    sectionHeading: sectionHeadingFor(el),
    options: optionsFor(el, kind),
    groupName: (el as HTMLInputElement).name || undefined,
    maxLength: maxLengthOf(el),
    existingValue: currentValue(el, kind),
  });
}

function assignHandle(el: HTMLElement): string {
  let id = el.getAttribute(HANDLE_ATTR);
  if (!id) {
    id = `af${counter++}`;
    el.setAttribute(HANDLE_ATTR, id);
  }
  registry.set(id, el);
  return id;
}

function kindOf(el: HTMLElement): FieldKind | undefined {
  const tag = el.tagName.toLowerCase();
  if (el.getAttribute("role") === "combobox") return "combobox";
  if (el.getAttribute("contenteditable") === "true") return "contenteditable";
  if (tag === "textarea") return "textarea";
  if (tag === "select") return "select";
  if (tag === "input") {
    const type = ((el as HTMLInputElement).type || "text").toLowerCase();
    switch (type) {
      case "email":
        return "email";
      case "tel":
        return "tel";
      case "url":
        return "url";
      case "number":
        return "number";
      case "date":
        return "date";
      case "radio":
        return "radio";
      case "checkbox":
        return "checkbox";
      case "file":
        return "file";
      case "hidden":
      case "submit":
      case "button":
      case "reset":
      case "image":
        return undefined;
      default:
        return "text";
    }
  }
  return undefined;
}

/** Resolve the human-readable label for a control via several strategies. */
export function labelFor(el: HTMLElement): string | undefined {
  // 1. aria-labelledby
  const labelledby = el.getAttribute("aria-labelledby");
  if (labelledby) {
    const text = labelledby
      .split(/\s+/)
      .map((id) => document.getElementById(id)?.textContent?.trim())
      .filter(Boolean)
      .join(" ");
    if (text) return clean(text);
  }
  // 2. <label for=id>
  if (el.id) {
    const lbl = document.querySelector(`label[for="${cssEscape(el.id)}"]`);
    if (lbl?.textContent?.trim()) return clean(lbl.textContent);
  }
  // 3. wrapping <label>
  const wrap = el.closest("label");
  if (wrap?.textContent?.trim()) return clean(wrap.textContent);
  // 4. aria-label
  const aria = el.getAttribute("aria-label");
  if (aria?.trim()) return clean(aria);
  // 5. preceding label-ish sibling / nearby text
  const near = nearbyText(el);
  if (near) return clean(near);
  return undefined;
}

function nearbyText(el: HTMLElement): string | undefined {
  // Walk up a couple of wrappers looking for a leading text node / heading.
  let node: Element | null = el;
  for (let depth = 0; depth < 3 && node; depth++) {
    const prev = node.previousElementSibling;
    if (prev && /^(label|span|div|p|legend)$/i.test(prev.tagName)) {
      const t = prev.textContent?.trim();
      if (t && t.length < 120) return t;
    }
    node = node.parentElement;
  }
  return undefined;
}

function sectionHeadingFor(el: HTMLElement): string | undefined {
  const fieldset = el.closest("fieldset");
  const legend = fieldset?.querySelector("legend");
  if (legend?.textContent?.trim()) return clean(legend.textContent);
  const section = el.closest("section, [role='group']");
  const heading = section?.querySelector("h1, h2, h3, h4, [role='heading']");
  if (heading?.textContent?.trim()) return clean(heading.textContent);
  return undefined;
}

function optionsFor(el: HTMLElement, kind: FieldKind): SelectOption[] | undefined {
  if (kind === "select") {
    return Array.from((el as HTMLSelectElement).options).map((o) => ({
      value: o.value,
      label: o.textContent?.trim() ?? o.value,
    }));
  }
  if (kind === "radio") {
    const name = (el as HTMLInputElement).name;
    if (!name) return undefined;
    const inputs = document.querySelectorAll<HTMLInputElement>(
      `input[type="radio"][name="${cssEscape(name)}"]`
    );
    return Array.from(inputs).map((i) => ({
      value: i.value,
      label: labelFor(i) ?? i.value,
    }));
  }
  return undefined;
}

function maxLengthOf(el: HTMLElement): number | undefined {
  const ml = el.getAttribute("maxlength");
  if (ml && Number(ml) > 0) return Number(ml);
  return undefined;
}

function currentValue(el: HTMLElement, kind: FieldKind): string | undefined {
  if (kind === "contenteditable") return el.textContent?.trim() || undefined;
  if (kind === "checkbox" || kind === "radio") return undefined;
  if (kind === "file") return undefined;
  const v = (el as HTMLInputElement).value;
  return v?.trim() || undefined;
}

function isVisible(el: HTMLElement): boolean {
  if (el.hasAttribute("disabled")) return false;
  if ((el as HTMLInputElement).type === "hidden") return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = el.getBoundingClientRect();
  // file inputs are often visually hidden but still fillable — keep them.
  if ((el as HTMLInputElement).type === "file") return true;
  return rect.width > 0 && rect.height > 0;
}

function clean(s: string): string {
  return s.replace(/\s+/g, " ").replace(/\*+$/, "").trim();
}

function cssEscape(s: string): string {
  if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(s);
  return s.replace(/["\\]/g, "\\$&");
}
