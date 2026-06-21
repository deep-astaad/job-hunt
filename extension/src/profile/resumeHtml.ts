/**
 * Render a CandidateProfile (the master resume) to a clean, printable HTML
 * document. The options page opens this in a new tab and the user prints it to
 * PDF (browser-native, no dependency). Kept pure so it is unit-testable.
 */
import type { CandidateProfile } from "./schema";

function esc(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function dateRange(start?: string, end?: string, current?: boolean): string {
  const e = current ? "Present" : end;
  return [start, e].filter(Boolean).join(" – ");
}

export function profileToResumeHtml(p: CandidateProfile): string {
  const c = p.contact;
  const name =
    c.fullName || [c.firstName, c.lastName].filter(Boolean).join(" ") || "Your Name";
  const contactLine = [
    c.email,
    c.phone,
    [c.city, c.country].filter(Boolean).join(", "),
    p.links.linkedin,
    p.links.github,
    p.links.portfolio || p.links.website,
  ]
    .filter(Boolean)
    .map(esc)
    .join(" · ");

  const experience = (p.workExperience ?? [])
    .map((w) => {
      const bullets = (w.bullets ?? [])
        .filter(Boolean)
        .map((b) => `<li>${esc(b)}</li>`)
        .join("");
      return `
      <div class="entry">
        <div class="entry-head">
          <span class="role">${esc(w.title)}${w.company ? ` · ${esc(w.company)}` : ""}</span>
          <span class="dates">${esc(dateRange(w.startDate, w.endDate, w.current))}</span>
        </div>
        ${w.location ? `<div class="loc">${esc(w.location)}</div>` : ""}
        ${bullets ? `<ul>${bullets}</ul>` : ""}
      </div>`;
    })
    .join("");

  const education = (p.education ?? [])
    .map((e) => {
      const line = [e.degree, e.field].filter(Boolean).join(", ");
      return `
      <div class="entry">
        <div class="entry-head">
          <span class="role">${esc(e.school)}</span>
          <span class="dates">${esc(dateRange(e.startDate, e.endDate))}</span>
        </div>
        ${line ? `<div class="loc">${esc(line)}${e.gpa ? ` · GPA ${esc(e.gpa)}` : ""}</div>` : ""}
      </div>`;
    })
    .join("");

  const skills = (p.skills ?? []).length
    ? `<section><h2>Skills</h2><p class="skills">${p.skills.map(esc).join(" · ")}</p></section>`
    : "";

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>${esc(name)} — Resume</title>
<style>
  @page { margin: 18mm 16mm; }
  * { box-sizing: border-box; }
  body { font: 13px/1.45 "Helvetica Neue", Arial, sans-serif; color: #1f2937; max-width: 760px; margin: 0 auto; padding: 28px; }
  h1 { font-size: 26px; margin: 0 0 2px; }
  .headline { color: #374151; font-size: 14px; margin: 0 0 6px; }
  .contact { color: #4b5563; font-size: 12px; margin: 0 0 16px; }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: #2563eb; border-bottom: 1px solid #e5e7eb; padding-bottom: 3px; margin: 18px 0 8px; }
  .summary { margin: 0 0 4px; white-space: pre-wrap; }
  .entry { margin: 0 0 10px; }
  .entry-head { display: flex; justify-content: space-between; gap: 12px; }
  .role { font-weight: 600; }
  .dates { color: #6b7280; font-size: 12px; white-space: nowrap; }
  .loc { color: #6b7280; font-size: 12px; }
  ul { margin: 4px 0 0; padding-left: 18px; }
  li { margin: 1px 0; }
  .skills { margin: 0; }
  @media print { body { padding: 0; } }
</style>
</head>
<body>
  <h1>${esc(name)}</h1>
  ${p.headline ? `<p class="headline">${esc(p.headline)}</p>` : ""}
  ${contactLine ? `<p class="contact">${contactLine}</p>` : ""}
  ${p.summary ? `<section><h2>Summary</h2><p class="summary">${esc(p.summary)}</p></section>` : ""}
  ${experience ? `<section><h2>Experience</h2>${experience}</section>` : ""}
  ${education ? `<section><h2>Education</h2>${education}</section>` : ""}
  ${skills}
</body>
</html>`;
}
