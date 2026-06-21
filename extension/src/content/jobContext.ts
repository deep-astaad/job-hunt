/**
 * Extract the job context (title, company, description) from the current page so
 * generation (cover letters, screening answers) is grounded in the ACTUAL
 * posting, not just the page title.
 *
 * Strategy, best signal first:
 *   1. schema.org JobPosting JSON-LD (most ATS + job boards emit it),
 *   2. Open Graph / meta tags,
 *   3. a heuristic scan of the largest job-like text block.
 *
 * The JSON-LD parsing is pure and unit-tested; DOM scraping is best-effort.
 */
import type { JobContext } from "@/shared/messages";

/** Cap description length so prompts stay reasonable. */
export const MAX_DESCRIPTION = 4000;

export function extractJobContext(): JobContext {
  const fromLd = fromJsonLd();
  const title =
    fromLd?.title ||
    metaContent(["og:title"]) ||
    document.querySelector("h1")?.textContent?.trim() ||
    document.title;
  const company =
    fromLd?.company ||
    metaContent(["og:site_name"]) ||
    undefined;
  const description =
    fromLd?.description || metaContent(["og:description"]) || scanDescription();

  return {
    title: clean(title),
    company: company ? clean(company) : undefined,
    description: description
      ? truncate(normalizeBlock(description), MAX_DESCRIPTION)
      : undefined,
    url: location.href,
  };
}

function fromJsonLd(): { title?: string; company?: string; description?: string } | undefined {
  const blocks = document.querySelectorAll<HTMLScriptElement>(
    'script[type="application/ld+json"]'
  );
  for (const b of Array.from(blocks)) {
    const job = parseJsonLdJob(b.textContent ?? "");
    if (job) return job;
  }
  return undefined;
}

/**
 * Pure: parse a JobPosting out of a JSON-LD string. Handles a single object, an
 * array, or an @graph wrapper. Returns undefined if no JobPosting is present.
 */
export function parseJsonLdJob(
  jsonText: string
): { title?: string; company?: string; description?: string } | undefined {
  let data: unknown;
  try {
    data = JSON.parse(jsonText);
  } catch {
    return undefined;
  }
  const candidates = flatten(data);
  const posting = candidates.find((c) => isJobPosting(c));
  if (!posting) return undefined;
  const p = posting as Record<string, any>;
  const company =
    typeof p.hiringOrganization === "string"
      ? p.hiringOrganization
      : p.hiringOrganization?.name;
  return {
    title: typeof p.title === "string" ? p.title : undefined,
    company: typeof company === "string" ? company : undefined,
    description:
      typeof p.description === "string" ? stripHtml(p.description) : undefined,
  };
}

function flatten(data: unknown): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  const visit = (v: unknown) => {
    if (Array.isArray(v)) v.forEach(visit);
    else if (v && typeof v === "object") {
      const o = v as Record<string, unknown>;
      out.push(o);
      if (Array.isArray(o["@graph"])) (o["@graph"] as unknown[]).forEach(visit);
    }
  };
  visit(data);
  return out;
}

function isJobPosting(o: Record<string, unknown>): boolean {
  const t = o["@type"];
  if (typeof t === "string") return t === "JobPosting";
  if (Array.isArray(t)) return t.includes("JobPosting");
  return false;
}

function scanDescription(): string | undefined {
  const selectors = [
    '[class*="job-description"]',
    '[class*="jobDescription"]',
    '[data-testid*="description"]',
    "#job-description",
    '[class*="description"]',
    "article",
    "main",
  ];
  let best = "";
  for (const sel of selectors) {
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(sel))) {
      const text = el.innerText?.trim() ?? "";
      if (text.length > best.length) best = text;
    }
    if (best.length > 400) break; // good enough, stop early
  }
  return best.length > 120 ? best : undefined;
}

function metaContent(names: string[]): string | undefined {
  for (const n of names) {
    const el =
      document.querySelector<HTMLMetaElement>(`meta[property="${n}"]`) ||
      document.querySelector<HTMLMetaElement>(`meta[name="${n}"]`);
    const c = el?.content?.trim();
    if (c) return c;
  }
  return undefined;
}

export function stripHtml(html: string): string {
  return html
    .replace(/<\s*br\s*\/?\s*>/gi, "\n")
    .replace(/<\/(p|li|div|h[1-6])\s*>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "…" : s;
}

function clean(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/** Collapse runs of spaces/tabs but keep newlines (paragraph structure). */
function normalizeBlock(s: string): string {
  return s
    .replace(/[ \t]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
