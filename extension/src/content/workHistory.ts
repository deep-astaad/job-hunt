/**
 * Auto-fill repeating work-history / education sections from the structured
 * profile. Many ATSs make you re-enter each job (company, title, dates,
 * description) and each degree as repeating rows behind an "Add another" button.
 *
 * The field CLASSIFIERS (label/name → sub-field) are pure and unit-tested; the
 * DOM grouping + "Add another" clicking is best-effort and defensive.
 */
import type { CandidateProfile, WorkExperience, Education } from "@/profile/schema";
import { labelFor } from "./detector";
import { normalizeText } from "./signature";

export type ExperienceField =
  | "company"
  | "title"
  | "location"
  | "startDate"
  | "endDate"
  | "description";

export type EducationField =
  | "school"
  | "degree"
  | "field"
  | "startDate"
  | "endDate"
  | "gpa";

/** Classify a work-experience sub-field from its label/name text. Pure. */
export function classifyExperienceField(text: string): ExperienceField | undefined {
  const t = normalizeText(text);
  if (!t) return undefined;
  if (/\b(end date|to date|end|until)\b/.test(t)) return "endDate";
  if (/\b(start date|from date|start|from)\b/.test(t)) return "startDate";
  if (/\b(company|employer|organization|organisation)\b/.test(t)) return "company";
  if (/\b(job title|title|position|role)\b/.test(t)) return "title";
  if (/\b(description|responsibilities|duties|summary|achievements)\b/.test(t))
    return "description";
  if (/\b(location|city)\b/.test(t)) return "location";
  return undefined;
}

/** Classify an education sub-field from its label/name text. Pure. */
export function classifyEducationField(text: string): EducationField | undefined {
  const t = normalizeText(text);
  if (!t) return undefined;
  if (/\b(end date|to date|graduation|end|until)\b/.test(t)) return "endDate";
  if (/\b(start date|from date|start|from)\b/.test(t)) return "startDate";
  if (/\b(school|university|college|institution)\b/.test(t)) return "school";
  if (/\b(field of study|major|field|discipline)\b/.test(t)) return "field";
  if (/\b(degree|qualification)\b/.test(t)) return "degree";
  if (/\b(gpa|grade)\b/.test(t)) return "gpa";
  return undefined;
}

/** Number of "Add another" clicks needed to host all entries. Pure. */
export function rowsToAdd(entries: number, existingRows: number, max = 10): number {
  return Math.max(0, Math.min(entries, max) - existingRows);
}

const EXPERIENCE_WORDS = ["experience", "employment", "work history", "work experience"];
const EDUCATION_WORDS = ["education", "academic"];

export async function fillWorkHistory(profile: CandidateProfile): Promise<number> {
  let filled = 0;
  filled += await fillRepeating<WorkExperience, ExperienceField>(
    profile.workExperience ?? [],
    "company",
    classifyExperienceField,
    experienceValue,
    EXPERIENCE_WORDS
  );
  filled += await fillRepeating<Education, EducationField>(
    profile.education ?? [],
    "school",
    classifyEducationField,
    educationValue,
    EDUCATION_WORDS
  );
  return filled;
}

function experienceValue(e: WorkExperience, key: ExperienceField): string | undefined {
  switch (key) {
    case "company":
      return e.company;
    case "title":
      return e.title;
    case "location":
      return e.location;
    case "startDate":
      return e.startDate;
    case "endDate":
      return e.current ? "Present" : e.endDate;
    case "description":
      return e.bullets?.length ? e.bullets.map((b) => `• ${b}`).join("\n") : undefined;
  }
}

function educationValue(e: Education, key: EducationField): string | undefined {
  switch (key) {
    case "school":
      return e.school;
    case "degree":
      return e.degree;
    case "field":
      return e.field;
    case "startDate":
      return e.startDate;
    case "endDate":
      return e.endDate;
    case "gpa":
      return e.gpa;
  }
}

async function fillRepeating<E, K extends string>(
  entries: E[],
  anchorKey: K,
  classify: (text: string) => K | undefined,
  valueOf: (entry: E, key: K) => string | undefined,
  sectionWords: string[]
): Promise<number> {
  if (!entries.length) return 0;

  let rows = findRows(anchorKey, classify);
  if (rows.length && entries.length > rows.length) {
    const addBtn = findAddButton(sectionWords);
    if (addBtn) {
      const need = rowsToAdd(entries.length, rows.length);
      for (let i = 0; i < need; i++) {
        addBtn.click();
        await sleep(250);
      }
      rows = findRows(anchorKey, classify);
    }
  }
  if (!rows.length) return 0;

  let filled = 0;
  for (let i = 0; i < Math.min(entries.length, rows.length); i++) {
    filled += fillRow(rows[i], entries[i], classify, valueOf);
  }
  return filled;
}

interface Row {
  container: HTMLElement;
  inputs: HTMLElement[];
}

/** Group inputs into rows anchored on a field that classifies to `anchorKey`. */
function findRows<K extends string>(
  anchorKey: K,
  classify: (text: string) => K | undefined
): Row[] {
  const controls = Array.from(
    document.querySelectorAll<HTMLElement>("input, textarea, select, [contenteditable='true']")
  );
  const anchors = controls.filter((el) => classify(fieldText(el)) === anchorKey);
  const rows: Row[] = [];
  const seen = new Set<HTMLElement>();
  for (const anchor of anchors) {
    const container = rowContainer(anchor);
    if (!container || seen.has(container)) continue;
    seen.add(container);
    rows.push({
      container,
      inputs: Array.from(
        container.querySelectorAll<HTMLElement>(
          "input, textarea, select, [contenteditable='true']"
        )
      ),
    });
  }
  return rows;
}

/** Walk up until we find an ancestor that scopes a single entry (small subtree
 *  containing the anchor plus a few sibling fields). */
function rowContainer(anchor: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = anchor.parentElement;
  let best: HTMLElement | null = null;
  for (let depth = 0; depth < 6 && node; depth++) {
    const count = node.querySelectorAll(
      "input, textarea, select, [contenteditable='true']"
    ).length;
    if (count >= 2 && count <= 10) best = node;
    if (count > 10) break;
    node = node.parentElement;
  }
  return best ?? anchor.parentElement;
}

function fillRow<E, K extends string>(
  row: Row,
  entry: E,
  classify: (text: string) => K | undefined,
  valueOf: (entry: E, key: K) => string | undefined
): number {
  let filled = 0;
  const used = new Set<K>();
  for (const el of row.inputs) {
    const key = classify(fieldText(el));
    if (!key || used.has(key)) continue;
    const value = valueOf(entry, key);
    if (value == null || value === "") continue;
    if (setValue(el, value)) {
      used.add(key);
      filled++;
    }
  }
  return filled;
}

function fieldText(el: HTMLElement): string {
  return [
    labelFor(el),
    el.getAttribute("name"),
    el.id,
    (el as HTMLInputElement).placeholder,
    el.getAttribute("aria-label"),
  ]
    .filter(Boolean)
    .join(" ");
}

function findAddButton(sectionWords: string[]): HTMLElement | null {
  const buttons = Array.from(
    document.querySelectorAll<HTMLElement>("button, a, [role='button']")
  );
  for (const b of buttons) {
    const t = (b.textContent || "").trim().toLowerCase();
    if (!/\badd\b/.test(t)) continue;
    if (sectionWords.some((w) => t.includes(w)) || /another|more/.test(t)) return b;
  }
  return null;
}

function setValue(el: HTMLElement, value: string): boolean {
  if (el instanceof HTMLSelectElement) {
    const want = value.trim().toLowerCase();
    const opt = Array.from(el.options).find(
      (o) => o.text.trim().toLowerCase() === want || o.value.toLowerCase() === want
    );
    if (!opt) return false;
    el.value = opt.value;
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
    if (el.value.trim()) return false; // don't overwrite existing input
    const proto = Object.getPrototypeOf(el);
    Object.getOwnPropertyDescriptor(proto, "value")?.set?.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }
  if (el.getAttribute("contenteditable") === "true") {
    if (el.textContent?.trim()) return false;
    el.textContent = value;
    el.dispatchEvent(new InputEvent("input", { bubbles: true }));
    return true;
  }
  return false;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
