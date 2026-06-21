/**
 * Editable outreach template library. Templates use {placeholders} filled from
 * the contact + sender profile, so the user gets a usable message with no LLM
 * (and the LLM can polish it when enabled). Seeded with sensible defaults on
 * first use; fully editable in the options page.
 */

export interface OutreachTemplate {
  id: string;
  name: string;
  /** Body with {name} {firstName} {company} {role} {myName} {myTitle} placeholders. */
  body: string;
}

export interface TemplateVars {
  name?: string;
  firstName?: string;
  company?: string;
  role?: string;
  myName?: string;
  myTitle?: string;
}

const KEY = "appfill:templates";

export const DEFAULT_TEMPLATES: OutreachTemplate[] = [
  {
    id: "cold_intro",
    name: "Cold intro",
    body:
      "Hi {firstName}, I came across your work at {company} and really admire what your team is building. I'm a {myTitle} exploring roles in this space — would you be open to a quick chat? Thanks, {myName}",
  },
  {
    id: "referral_ask",
    name: "Referral ask",
    body:
      "Hi {firstName}, I just applied for the {role} role at {company} and noticed you're on the team. If it feels right, I'd be grateful for a referral — happy to share more on my background. Either way, thanks for your time! {myName}",
  },
  {
    id: "recruiter_followup",
    name: "Recruiter follow-up",
    body:
      "Hi {firstName}, following up on my application for {role} at {company}. I'm very interested and think my background is a strong fit. Happy to share anything that would help — thank you! {myName}",
  },
];

/** Pure: substitute {placeholders}; unknown/empty ones collapse cleanly. */
export function renderTemplate(body: string, vars: TemplateVars): string {
  return body
    .replace(/\{(\w+)\}/g, (_, k: string) => {
      const v = (vars as Record<string, string | undefined>)[k];
      return v ? v : "";
    })
    .replace(/\s{2,}/g, " ")
    .trim();
}

export async function getTemplates(): Promise<OutreachTemplate[]> {
  const raw = await chrome.storage.local.get(KEY);
  const list = raw[KEY] as OutreachTemplate[] | undefined;
  return list && list.length ? list : DEFAULT_TEMPLATES;
}

export async function saveTemplates(list: OutreachTemplate[]): Promise<void> {
  await chrome.storage.local.set({ [KEY]: list });
}

export function newTemplateId(): string {
  return `tpl_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
}
