/**
 * Pre-submit validation. Before the user submits, surface problems: empty
 * required fields, fields they have data for but left blank, and a rough
 * experience-vs-JD mismatch. Clicking an issue jumps to the field.
 *
 * The issue logic is pure and unit-tested; the DOM scan + panel are thin.
 */
import {
  type CandidateProfile,
  type CanonicalKey,
  resolveCanonicalValue,
} from "@/profile/schema";
import { detectFields, getElement } from "./detector";
import { mapFieldDeterministic } from "./mapper";

export interface ValField {
  id: string;
  label?: string;
  required: boolean;
  value?: string;
  canonicalKey?: CanonicalKey;
}

export interface ValIssue {
  fieldId?: string;
  severity: "error" | "warn";
  message: string;
}

const WORD_TO_NUM: Record<string, number> = {
  one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10
};

/** Parse a rough "required years of experience" from a job description. */
export function parseRequiredYears(jobText: string): number | undefined {
  const normalized = jobText.toLowerCase();
  const rangeMatch = normalized.match(/(\d{1,2})\s*(?:-\s*\d{1,2})?\s*\+?\s*(?:years|yrs)\b/);
  if (rangeMatch) {
    return Number(rangeMatch[1]);
  }
  const words = Object.keys(WORD_TO_NUM).join("|");
  const wordMatch = normalized.match(new RegExp(`\\b(${words})\\s*(?:-\\s*(?:\\d{1,2}|${words}))?\\s*\\+?\\s*(?:years|yrs)\\b`));
  if (wordMatch) {
    return WORD_TO_NUM[wordMatch[1]];
  }
  return undefined;
}

const SENSITIVE: CanonicalKey[] = [
  "gender",
  "raceEthnicity",
  "veteranStatus",
  "disabilityStatus",
];

/** Pure: build the issue list from classified fields + profile + job text. */
export function collectIssues(
  fields: ValField[],
  profile: CandidateProfile,
  jobText: string
): ValIssue[] {
  const issues: ValIssue[] = [];

  for (const f of fields) {
    const empty = !f.value || !f.value.trim();
    const name = f.label || f.canonicalKey || "field";
    if (empty && f.required) {
      issues.push({ fieldId: f.id, severity: "error", message: `Required field empty: ${name}` });
      continue;
    }
    if (
      empty &&
      f.canonicalKey &&
      !SENSITIVE.includes(f.canonicalKey) &&
      f.canonicalKey !== "coverLetter" &&
      f.canonicalKey !== "resumeFile"
    ) {
      const have = resolveCanonicalValue(profile, f.canonicalKey);
      if (have) {
        issues.push({
          fieldId: f.id,
          severity: "warn",
          message: `You have “${name}” in your profile but it's blank here`,
        });
      }
    }
  }

  const req = parseRequiredYears(jobText);
  const have = profile.yearsOfExperience;
  if (req != null && have != null && have + 0.5 < req) {
    issues.push({
      severity: "warn",
      message: `Job suggests ~${req} yrs experience; your profile lists ${have}`,
    });
  }

  return issues;
}

/** Scan the live form, classify fields, and return issues + a jump map. */
export function runValidation(
  profile: CandidateProfile,
  platformId: string,
  jobText: string
): ValIssue[] {
  const fields = detectFields();
  const valFields: ValField[] = fields.map((f) => ({
    id: f.id,
    label: f.label,
    required: Boolean(f.required),
    value: f.existingValue,
    canonicalKey: mapFieldDeterministic(f, platformId)?.key,
  }));
  return collectIssues(valFields, profile, jobText);
}

export function jumpToField(fieldId: string): void {
  const el = getElement(fieldId);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  (el as HTMLElement).focus?.();
  const prev = el.style.outline;
  el.style.outline = "3px solid #f59e0b";
  setTimeout(() => (el.style.outline = prev), 1600);
}

let panelHost: HTMLElement | null = null;

/** Render the issue checklist panel (top-right). Clicking an item jumps to it. */
export function renderValidationPanel(issues: ValIssue[]): void {
  panelHost?.remove();
  const host = document.createElement("div");
  host.style.cssText =
    "position:fixed;z-index:2147483646;right:16px;top:16px;font:13px system-ui,sans-serif;";
  const sh = host.attachShadow({ mode: "open" });
  const errors = issues.filter((i) => i.severity === "error").length;
  const rows = issues
    .map(
      (i, idx) => `
      <div class="row ${i.severity}" data-i="${idx}">
        <span class="dot"></span>
        <span class="msg">${escapeHtml(i.message)}</span>
        ${i.fieldId ? '<button class="jump" data-i="' + idx + '">go</button>' : ""}
      </div>`
    )
    .join("");
  sh.innerHTML = `
    <style>
      .card{background:#0f172a;color:#fff;border-radius:12px;padding:12px 13px;max-width:340px;
        box-shadow:0 8px 30px rgba(0,0,0,.4);}
      .t{font-weight:700;margin-bottom:8px;display:flex;gap:8px;align-items:center;}
      .ok{color:#34d399;} .bad{color:#f87171;}
      .row{display:flex;gap:8px;align-items:flex-start;padding:5px 0;border-top:1px solid #1e293b;}
      .msg{flex:1;opacity:.95;line-height:1.35;}
      .dot{width:8px;height:8px;border-radius:50%;margin-top:5px;flex:none;}
      .error .dot{background:#f87171;} .warn .dot{background:#fbbf24;}
      .jump{background:#2563eb;color:#fff;border:none;border-radius:6px;padding:3px 8px;cursor:pointer;font:600 11px system-ui;}
      .x{background:transparent;color:#9ca3af;border:none;cursor:pointer;margin-left:auto;}
      .head{display:flex;align-items:center;}
    </style>
    <div class="card">
      <div class="t head">
        <span class="${errors ? "bad" : "ok"}">AppFill check</span>
        <button class="x" title="Close">✕</button>
      </div>
      ${
        issues.length
          ? `<div style="font-size:12px;opacity:.8;margin-bottom:4px;">${errors} blocking, ${
              issues.length - errors
            } to review</div>${rows}`
          : `<div class="ok">No issues found — looks ready to submit. 🎉</div>`
      }
    </div>`;
  sh.querySelector(".x")?.addEventListener("click", () => host.remove());
  sh.querySelectorAll<HTMLButtonElement>(".jump").forEach((b) => {
    b.addEventListener("click", () => {
      const i = Number(b.dataset.i);
      const issue = issues[i];
      if (issue?.fieldId) jumpToField(issue.fieldId);
    });
  });
  document.documentElement.appendChild(host);
  panelHost = host;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
