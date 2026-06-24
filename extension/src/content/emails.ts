/**
 * Find a contact email on a careers / company page (for cold outreach when there
 * is no ATS). The extraction + ranking are pure and unit-tested; the DOM scan is
 * a thin wrapper over mailto links + page text.
 */

const EMAIL_RE = /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/gi;

/** Words that make an address a likely hiring/contact inbox. */
const PREFERRED = [
  "careers",
  "jobs",
  "recruit",
  "talent",
  "hr",
  "people",
  "hiring",
  "work",
  "join",
  "hello",
  "contact",
  "team",
];

/** Addresses that are almost never a person to email. */
const BLOCKED = ["noreply", "no-reply", "donotreply", "example.com", "sentry", "wixpress", "mailer"];

export function extractEmails(text: string): string[] {
  const found = text.match(EMAIL_RE) ?? [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of found) {
    const e = raw.toLowerCase();
    if (seen.has(e)) continue;
    if (BLOCKED.some((b) => e.includes(b))) continue;
    seen.add(e);
    out.push(e);
  }
  return out;
}

/** Pure: pick the best contact email (prefers careers/jobs/hr-style inboxes). */
export function pickBestEmail(emails: string[]): string | undefined {
  if (!emails.length) return undefined;
  const score = (e: string) => {
    const local = e.split("@")[0];
    return PREFERRED.reduce((s, w) => {
      if (w === "hr") {
        const isWholeHrWord = local === "hr" || /(^|[-_.]+)hr([-_.]+|\d+$|$)/.test(local);
        return isWholeHrWord ? s + 1 : s;
      }
      return local.includes(w) ? s + 1 : s;
    }, 0);
  };
  return [...emails].sort((a, b) => score(b) - score(a))[0];
}

/** Pure: split an LLM "Subject: …\n\n body" reply into parts. */
export function parseSubjectBody(text: string): { subject: string; body: string } {
  const m = text.match(/^\s*subject:\s*(.+?)\r?\n([\s\S]*)$/i);
  if (m) return { subject: m[1].trim(), body: m[2].trim() };
  return { subject: "", body: text.trim() };
}

export function findPageEmails(): string[] {
  const fromLinks = Array.from(
    document.querySelectorAll<HTMLAnchorElement>("a[href^='mailto:']")
  ).map((a) => a.href.replace(/^mailto:/i, "").split("?")[0]);
  const fromText = extractEmails(document.body?.innerText ?? "");
  return extractEmails([...fromLinks, ...fromText].join(" "));
}
