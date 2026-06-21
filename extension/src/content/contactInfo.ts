/**
 * Extract a contact draft from the current page — primarily LinkedIn profiles,
 * with a generic fallback (og:title / h1). Best-effort DOM scraping; the small
 * pure helper (splitHeadline) is unit-tested.
 */
import type { ContactDraft } from "@/storage/contacts";

/** Split a LinkedIn-style headline "Role at Company" into parts. Pure. */
export function splitHeadline(headline: string): { role?: string; company?: string } {
  const h = headline.trim();
  if (!h) return {};
  const m = h.match(/^(.*?)\s+(?:at|@|·)\s+(.+)$/i);
  if (m) return { role: m[1].trim(), company: m[2].trim() };
  return { role: h };
}

function text(sel: string): string | undefined {
  const el = document.querySelector<HTMLElement>(sel);
  const t = el?.innerText?.trim() || el?.textContent?.trim();
  return t || undefined;
}

function meta(name: string): string | undefined {
  const el =
    document.querySelector<HTMLMetaElement>(`meta[property="${name}"]`) ||
    document.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  return el?.content?.trim() || undefined;
}

export function extractContactInfo(): ContactDraft {
  const isLinkedIn = /(^|\.)linkedin\.com$/.test(location.hostname);
  if (isLinkedIn) {
    const name =
      text("h1.text-heading-xlarge") || text("main h1") || text("h1");
    const headline =
      text(".text-body-medium.break-words") ||
      text("[data-generated-suggestion-target]") ||
      "";
    const { role, company } = splitHeadline(headline);
    const exp = text("[aria-label='Current company'], .pv-text-details__right-panel");
    return {
      name,
      role,
      company: company || exp,
      profileUrl: location.href.split("?")[0],
      context: headline || undefined,
    };
  }
  // Generic fallback.
  const title = meta("og:title") || text("h1") || document.title;
  const { role, company } = splitHeadline(title ?? "");
  return {
    name: title,
    role,
    company: company || meta("og:site_name"),
    profileUrl: location.href.split("?")[0],
  };
}
