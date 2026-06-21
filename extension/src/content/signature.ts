import type { FieldDescriptor, FieldKind } from "@/shared/types";

/**
 * Build a stable signature for a field, used as the learning-memory key.
 *
 * Goals:
 *  - Stable across companies on the same ATS (a Workday "Phone Device Type"
 *    field should key the same everywhere).
 *  - Distinct between genuinely different questions.
 *
 * Strategy: prefer the human label (what the question actually asks); fall back
 * to name/id. Normalize aggressively — lowercase, strip punctuation, collapse
 * whitespace, and remove volatile numeric/uuid fragments that ATSs inject into
 * name/id attributes.
 */
export function normalizeText(input: string | undefined): string {
  if (!input) return "";
  return input
    .toLowerCase()
    .replace(/[‘’“”]/g, "") // smart quotes
    .replace(/https?:\/\/\S+/g, "") // stray urls
    .replace(/[^a-z0-9]+/g, " ") // punctuation -> space
    .replace(/\b[0-9a-f]{8,}\b/g, " ") // uuid/hash fragments
    .replace(/\b\d{2,}\b/g, " ") // long digit runs (indices, ids)
    .replace(/\s+/g, " ")
    .trim();
}

export function computeSignature(
  parts: {
    label?: string;
    name?: string;
    domId?: string;
    placeholder?: string;
    ariaLabel?: string;
    kind: FieldKind;
  }
): string {
  const labelish =
    normalizeText(parts.label) ||
    normalizeText(parts.ariaLabel) ||
    normalizeText(parts.placeholder) ||
    normalizeText(parts.name) ||
    normalizeText(parts.domId);
  // Kind disambiguates e.g. a "country" text input vs a "country" select.
  const kindBucket = bucketKind(parts.kind);
  return `${kindBucket}::${labelish}`.trim();
}

/** Group equivalent kinds so a text vs email rename doesn't fragment memory. */
function bucketKind(kind: FieldKind): string {
  switch (kind) {
    case "text":
    case "email":
    case "tel":
    case "url":
    case "number":
    case "date":
    case "contenteditable":
      return "input";
    case "textarea":
      return "textarea";
    case "select":
    case "combobox":
      return "choice";
    case "radio":
    case "checkbox":
      return "option";
    case "file":
      return "file";
  }
}

export function withSignature(
  d: Omit<FieldDescriptor, "signature">
): FieldDescriptor {
  return { ...d, signature: computeSignature(d) };
}
