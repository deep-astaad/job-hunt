/**
 * Master-resume YAML <-> CandidateProfile.
 *
 * The "master resume" is just the CandidateProfile rendered as human-editable
 * YAML — a single source of truth the user can read, diff, and hand-edit, and
 * that downstream features (tailored resume, PDF, autofill) derive from.
 *
 * We deliberately ship our OWN small YAML codec rather than a dependency: the
 * extension is self-contained, and we only need the narrow subset our schema
 * uses (nested maps, scalar lists, lists of maps, and block-scalar text for
 * multi-line fields like the summary). Both the emitter and parser live here so
 * they round-trip each other; `yaml.test.ts` guards that contract.
 */
import {
  type CandidateProfile,
  type WorkExperience,
  type Education,
  emptyProfile,
} from "./schema";

// ----------------------------------------------------------------- emit ------

export function profileToYaml(p: CandidateProfile): string {
  const lines: string[] = [];
  lines.push("# AppFill master resume — edit freely, then Save.");
  lines.push("# This is the single source of truth for autofill & generation.");
  lines.push("");

  emitMap(lines, "contact", p.contact, 0);
  emitScalar(lines, "headline", p.headline, 0);
  emitBlock(lines, "summary", p.summary, 0);
  emitScalar(lines, "yearsOfExperience", p.yearsOfExperience, 0);
  emitScalar(lines, "currentCompany", p.currentCompany, 0);
  emitScalar(lines, "currentTitle", p.currentTitle, 0);
  emitScalarList(lines, "skills", p.skills, 0);
  emitMap(lines, "links", p.links, 0);
  emitMap(lines, "eligibility", p.eligibility, 0);

  if (p.workExperience?.length) {
    lines.push("workExperience:");
    for (const w of p.workExperience) emitWork(lines, w);
  }
  if (p.education?.length) {
    lines.push("education:");
    for (const e of p.education) emitEducation(lines, e);
  }
  return lines.join("\n") + "\n";
}

function emitWork(lines: string[], w: WorkExperience): void {
  const pad = "  ";
  let first = true;
  const item = (key: string, val: unknown) => {
    if (val == null || val === "") return;
    const prefix = first ? "- " : "  ";
    first = false;
    lines.push(`${pad}${prefix}${key}: ${scalar(val)}`);
  };
  item("company", w.company);
  item("title", w.title);
  item("location", w.location);
  item("startDate", w.startDate);
  item("endDate", w.endDate);
  if (w.current != null) item("current", w.current);
  if (w.bullets?.length) {
    if (first) {
      lines.push(`${pad}- bullets:`);
      first = false;
    } else {
      lines.push(`${pad}  bullets:`);
    }
    for (const b of w.bullets) lines.push(`${pad}    - ${scalar(b)}`);
  }
  if (first) lines.push(`${pad}- {}`); // empty entry, keep it valid
}

function emitEducation(lines: string[], e: Education): void {
  const pad = "  ";
  let first = true;
  const item = (key: string, val: unknown) => {
    if (val == null || val === "") return;
    const prefix = first ? "- " : "  ";
    first = false;
    lines.push(`${pad}${prefix}${key}: ${scalar(val)}`);
  };
  item("school", e.school);
  item("degree", e.degree);
  item("field", e.field);
  item("startDate", e.startDate);
  item("endDate", e.endDate);
  item("gpa", e.gpa);
  if (first) lines.push(`${pad}- {}`);
}

function emitMap(
  lines: string[],
  key: string,
  obj: object | undefined,
  indent: number
): void {
  if (!obj) return;
  const entries = Object.entries(obj).filter(
    ([, v]) => v != null && v !== ""
  );
  if (!entries.length) return;
  const pad = "  ".repeat(indent);
  lines.push(`${pad}${key}:`);
  for (const [k, v] of entries) {
    lines.push(`${pad}  ${k}: ${scalar(v)}`);
  }
}

function emitScalar(
  lines: string[],
  key: string,
  val: unknown,
  indent: number
): void {
  if (val == null || val === "") return;
  lines.push(`${"  ".repeat(indent)}${key}: ${scalar(val)}`);
}

function emitScalarList(
  lines: string[],
  key: string,
  list: string[] | undefined,
  indent: number
): void {
  if (!list?.length) return;
  const pad = "  ".repeat(indent);
  lines.push(`${pad}${key}:`);
  for (const item of list) lines.push(`${pad}  - ${scalar(item)}`);
}

/** Multi-line text as a YAML block scalar (|) so the user can edit it freely. */
function emitBlock(
  lines: string[],
  key: string,
  val: string | undefined,
  indent: number
): void {
  if (val == null || val === "") return;
  const pad = "  ".repeat(indent);
  if (!val.includes("\n")) {
    lines.push(`${pad}${key}: ${scalar(val)}`);
    return;
  }
  lines.push(`${pad}${key}: |`);
  for (const line of val.split("\n")) lines.push(`${pad}  ${line}`);
}

function scalar(v: unknown): string {
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return String(v);
  const s = String(v);
  // Quote when the value could be misread as YAML syntax.
  if (
    s === "" ||
    /^[-?:,\[\]{}#&*!|>'"%@`]/.test(s) ||
    /:\s/.test(s) ||
    /\s#/.test(s) ||
    /^\s|\s$/.test(s) ||
    /^(true|false|null|yes|no|~)$/i.test(s) ||
    /^[\d.+-]+$/.test(s)
  ) {
    return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  return s;
}

// ----------------------------------------------------------------- parse -----

interface Line {
  indent: number;
  raw: string; // content after indentation, comments stripped
}

/**
 * Parse the master-resume YAML back into a CandidateProfile. This is a focused
 * parser for the subset we emit (plus typical hand edits). Unknown keys are
 * ignored so the profile shape stays stable.
 */
export function yamlToProfile(text: string): CandidateProfile {
  const tree = parseYaml(text);
  const p = emptyProfile();
  if (!tree || typeof tree !== "object") return p;
  const o = tree as Record<string, unknown>;

  if (isObj(o.contact)) p.contact = pickStrings(o.contact);
  p.headline = str(o.headline);
  p.summary = str(o.summary);
  p.yearsOfExperience = num(o.yearsOfExperience);
  p.currentCompany = str(o.currentCompany);
  p.currentTitle = str(o.currentTitle);
  p.skills = strList(o.skills);
  if (isObj(o.links)) p.links = pickStrings(o.links);
  if (isObj(o.eligibility)) p.eligibility = pickEligibility(o.eligibility);
  p.workExperience = asArray(o.workExperience).map(toWork).filter(hasAny);
  p.education = asArray(o.education).map(toEducation).filter(hasAny);
  return p;
}

function toWork(v: unknown): WorkExperience {
  const o = isObj(v) ? v : {};
  return {
    company: str(o.company) ?? "",
    title: str(o.title) ?? "",
    location: str(o.location),
    startDate: str(o.startDate),
    endDate: str(o.endDate),
    current: bool(o.current),
    bullets: strList(o.bullets),
  };
}

function toEducation(v: unknown): Education {
  const o = isObj(v) ? v : {};
  return {
    school: str(o.school) ?? "",
    degree: str(o.degree),
    field: str(o.field),
    startDate: str(o.startDate),
    endDate: str(o.endDate),
    gpa: str(o.gpa),
  };
}

// --- generic YAML -> JS for our subset -------------------------------------

/** Tokenize into non-empty, non-comment lines with their indent depth. */
function tokenize(text: string): Line[] {
  const out: Line[] = [];
  for (const rawLine of text.replace(/\t/g, "  ").split("\n")) {
    if (!rawLine.trim()) continue;
    const indent = rawLine.length - rawLine.replace(/^\s+/, "").length;
    const content = rawLine.slice(indent);
    if (content.startsWith("#")) continue;
    out.push({ indent, raw: content });
  }
  return out;
}

function parseYaml(text: string): unknown {
  const lines = tokenize(text);
  const [val] = parseBlock(lines, 0, 0);
  return val;
}

/**
 * Parse a block of sibling lines at >= baseIndent starting at index `i`.
 * Returns the parsed value and the index of the first unconsumed line.
 */
function parseBlock(lines: Line[], i: number, baseIndent: number): [unknown, number] {
  if (i >= lines.length) return [null, i];
  const indent = lines[i].indent;
  if (lines[i].raw.startsWith("- ") || lines[i].raw === "-") {
    return parseList(lines, i, indent);
  }
  return parseMap(lines, i, indent < baseIndent ? indent : indent);
}

function parseMap(lines: Line[], i: number, indent: number): [Record<string, unknown>, number] {
  const map: Record<string, unknown> = {};
  while (i < lines.length && lines[i].indent === indent && !lines[i].raw.startsWith("- ")) {
    const { key, value, isBlock, blockChar } = splitKey(lines[i].raw);
    i++;
    if (isBlock) {
      const [text, next] = parseBlockScalar(lines, i, indent, blockChar);
      map[key] = text;
      i = next;
    } else if (value !== "") {
      map[key] = parseScalar(value);
    } else if (i < lines.length && lines[i].indent > indent) {
      const [child, next] = parseBlock(lines, i, lines[i].indent);
      map[key] = child;
      i = next;
    } else {
      map[key] = null;
    }
  }
  return [map, i];
}

function parseList(lines: Line[], i: number, indent: number): [unknown[], number] {
  const list: unknown[] = [];
  while (i < lines.length && lines[i].indent === indent && (lines[i].raw.startsWith("- ") || lines[i].raw === "-")) {
    const rest = lines[i].raw === "-" ? "" : lines[i].raw.slice(2);
    if (rest === "" || rest === "{}") {
      // Either a nested block on following deeper lines, or an empty entry.
      if (rest === "{}") {
        list.push({});
        i++;
      } else if (i + 1 < lines.length && lines[i + 1].indent > indent) {
        const [child, next] = parseBlock(lines, i + 1, lines[i + 1].indent);
        list.push(child);
        i = next;
      } else {
        list.push(null);
        i++;
      }
      continue;
    }
    // Inline "- key: value" — treat the dash content as the first map entry,
    // then fold in any deeper-indented sibling keys.
    const { key, value, isBlock } = splitKey(rest);
    if (key && (value !== "" || isBlock || isMapContinuation(lines, i, indent))) {
      // Reconstruct a virtual map starting from this line at indent+2.
      const virtualIndent = indent + 2;
      const folded: Line[] = [{ indent: virtualIndent, raw: rest }];
      let j = i + 1;
      while (j < lines.length && lines[j].indent >= virtualIndent && !(lines[j].indent === indent)) {
        folded.push(lines[j]);
        j++;
      }
      const [map, _] = parseMap(normalizeIndent(folded, virtualIndent), 0, virtualIndent);
      void _;
      list.push(map);
      i = j;
    } else {
      list.push(parseScalar(rest));
      i++;
    }
  }
  return [list, i];
}

/** Does the list item have continuation map keys on following lines? */
function isMapContinuation(lines: Line[], i: number, indent: number): boolean {
  const j = i + 1;
  return j < lines.length && lines[j].indent > indent;
}

function normalizeIndent(lines: Line[], target: number): Line[] {
  // Re-key the first line (the dash content) to sit at `target`; others keep
  // their own indent which is already >= target.
  return lines.map((l, idx) => (idx === 0 ? { indent: target, raw: l.raw } : l));
}

function parseBlockScalar(
  lines: Line[],
  i: number,
  parentIndent: number,
  _char: string
): [string, number] {
  const collected: string[] = [];
  let contentIndent = -1;
  while (i < lines.length && lines[i].indent > parentIndent) {
    if (contentIndent < 0) contentIndent = lines[i].indent;
    collected.push(" ".repeat(Math.max(0, lines[i].indent - contentIndent)) + lines[i].raw);
    i++;
  }
  return [collected.join("\n"), i];
}

function splitKey(raw: string): {
  key: string;
  value: string;
  isBlock: boolean;
  blockChar: string;
} {
  const m = raw.match(/^([^:]+):(?:\s+(.*))?$/);
  if (!m) return { key: raw.trim(), value: "", isBlock: false, blockChar: "" };
  const key = m[1].trim();
  const value = (m[2] ?? "").trim();
  if (value === "|" || value === ">" || value === "|-" || value === ">-") {
    return { key, value: "", isBlock: true, blockChar: value[0] };
  }
  return { key, value, isBlock: false, blockChar: "" };
}

function parseScalar(s: string): unknown {
  const t = s.trim();
  if (t.startsWith('"') && t.endsWith('"') && t.length >= 2) {
    return t.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, "\\");
  }
  if (t.startsWith("'") && t.endsWith("'") && t.length >= 2) {
    return t.slice(1, -1).replace(/''/g, "'");
  }
  if (t === "true") return true;
  if (t === "false") return false;
  if (t === "null" || t === "~") return null;
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  return t;
}

// --- coercion helpers -------------------------------------------------------

function isObj(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v);
}
function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function str(v: unknown): string | undefined {
  if (v == null) return undefined;
  if (typeof v === "string") return v || undefined;
  return String(v);
}
function num(v: unknown): number | undefined {
  if (typeof v === "number") return v;
  if (typeof v === "string" && v.trim() && !Number.isNaN(Number(v))) return Number(v);
  return undefined;
}
function bool(v: unknown): boolean | undefined {
  if (typeof v === "boolean") return v;
  if (v === "true") return true;
  if (v === "false") return false;
  return undefined;
}
function strList(v: unknown): string[] {
  if (typeof v === "string") return v.split(",").map((s) => s.trim()).filter(Boolean);
  return asArray(v).map((x) => str(x)).filter((x): x is string => Boolean(x));
}
function pickStrings(o: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(o)) {
    const s = str(v);
    if (s != null) out[k] = s;
  }
  return out;
}
function pickEligibility(o: Record<string, unknown>): CandidateProfile["eligibility"] {
  return {
    workAuthorization: str(o.workAuthorization),
    requiresSponsorship: bool(o.requiresSponsorship),
    willingToRelocate: bool(o.willingToRelocate),
    noticePeriod: str(o.noticePeriod),
    availableStartDate: str(o.availableStartDate),
    desiredSalary: str(o.desiredSalary),
    gender: str(o.gender),
    raceEthnicity: str(o.raceEthnicity),
    veteranStatus: str(o.veteranStatus),
    disabilityStatus: str(o.disabilityStatus),
  };
}
function hasAny(o: object): boolean {
  return Object.values(o).some((v) => v != null && v !== "" && !(Array.isArray(v) && v.length === 0));
}
