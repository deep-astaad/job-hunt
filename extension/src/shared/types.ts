import type { CanonicalKey } from "@/profile/schema";

/** A control kind we know how to fill. */
export type FieldKind =
  | "text"
  | "email"
  | "tel"
  | "url"
  | "number"
  | "date"
  | "textarea"
  | "select"
  | "radio"
  | "checkbox"
  | "file"
  | "contenteditable"
  | "combobox";

export interface SelectOption {
  value: string;
  label: string;
}

/**
 * Everything the engine learns about a single form control. `id` is a runtime
 * handle (assigned by the detector) used to address the element back in the DOM.
 */
export interface FieldDescriptor {
  id: string;
  kind: FieldKind;
  label?: string;
  name?: string;
  domId?: string;
  placeholder?: string;
  autocomplete?: string;
  ariaLabel?: string;
  required?: boolean;
  sectionHeading?: string;
  options?: SelectOption[]; // for select / radio groups
  groupName?: string; // radio group name
  maxLength?: number;
  /** Stable signature used as the learning-memory key. */
  signature: string;
  /** Current value already present in the field (don't overwrite if non-empty). */
  existingValue?: string;
}

export type ValueSource = "deterministic" | "memory" | "memory-global" | "llm";

export interface FieldResolution {
  fieldId: string;
  canonicalKey?: CanonicalKey;
  value?: string;
  /** 0..1 — low values are flagged for review and badged in the UI. */
  confidence: number;
  source: ValueSource;
  /** True for file inputs that should receive the stored resume binary. */
  isResumeFile?: boolean;
}

export interface DetectedPlatform {
  id: string; // "greenhouse" | "lever" | "workday" | "ashby" | "generic" | ...
  label: string;
}
