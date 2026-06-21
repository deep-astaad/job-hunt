import type { DetectedPlatform, FieldDescriptor } from "@/shared/types";
import type { CanonicalKey } from "@/profile/schema";

/**
 * Identify the ATS hosting the current form. Used to (a) tag learned memory so
 * answers reuse within the same platform, (b) pick a fill adapter for custom
 * widgets, (c) apply platform-specific field hints, and (d) drive the multi-page
 * flow runner via next/submit selectors. Detection is best-effort by hostname +
 * DOM markers.
 */
export function detectPlatform(): DetectedPlatform {
  const host = location.hostname;
  const html = document.documentElement;

  const has = (sel: string) => Boolean(document.querySelector(sel));

  if (/greenhouse\.io$/.test(host) || has("#grnhse_app, [id^='greenhouse'], #application_form"))
    return { id: "greenhouse", label: "Greenhouse" };
  if (/lever\.co$/.test(host) || has(".application-form[action*='lever'], [data-qa='application-form']"))
    return { id: "lever", label: "Lever" };
  if (/myworkdayjobs\.com$/.test(host) || /wd\d+\.myworkday/.test(host) || has("[data-automation-id]"))
    return { id: "workday", label: "Workday" };
  if (/ashbyhq\.com$/.test(host) || has("[class*='ashby'], [class*='_form_']"))
    return { id: "ashby", label: "Ashby" };
  if (/jobs\.smartrecruiters\.com$/.test(host) || /smartrecruiters\.com$/.test(host))
    return { id: "smartrecruiters", label: "SmartRecruiters" };
  if (/icims\.com$/.test(host)) return { id: "icims", label: "iCIMS" };
  if (
    /(^|\.)linkedin\.com$/.test(host) &&
    has(".jobs-easy-apply-modal, [data-test-modal][role='dialog'], .jobs-easy-apply-content")
  )
    return { id: "linkedin", label: "LinkedIn Easy Apply" };
  if (/successfactors\.com$/.test(host) || /sapsf/.test(host))
    return { id: "successfactors", label: "SuccessFactors" };
  if (html.getAttribute("data-ats")) {
    const id = html.getAttribute("data-ats")!;
    return { id, label: id };
  }
  return { id: "generic", label: "Generic" };
}

/** A platform-specific hint: if `match` appears in a field's id/name/label,
 * resolve it to `key`. Lets us map oddly-named or unlabeled ATS fields. */
export interface FieldHint {
  match: string; // lowercase substring
  key: CanonicalKey;
}

/** Registered platform adapters customize fill, mapping, and flow navigation. */
export interface PlatformAdapter {
  id: string;
  /**
   * Attempt to fill a custom widget. Return true if it handled the element.
   * Falls back to the generic filler when it returns false.
   */
  fillCustom?(el: Element, value: string): Promise<boolean> | boolean;
  /** Platform-specific field-identifier → canonical-key hints. */
  fieldHints?: FieldHint[];
  /** Selectors for the "Next/Continue" control in a multi-page flow. */
  nextSelectors?: string[];
  /** Selectors for the final "Submit/Apply" control. */
  submitSelectors?: string[];
}

const adapters: Record<string, PlatformAdapter> = {};

export function registerAdapter(a: PlatformAdapter): void {
  adapters[a.id] = a;
}

export function getAdapter(platformId: string): PlatformAdapter | undefined {
  return adapters[platformId];
}

/**
 * Resolve a field to a canonical key using the platform's hints (id/name/label
 * substring match). Returns undefined when no adapter or no hint matches.
 */
export function platformFieldHint(
  field: FieldDescriptor,
  platformId: string
): CanonicalKey | undefined {
  const hints = adapters[platformId]?.fieldHints;
  if (!hints?.length) return undefined;
  // Match against id/name/automation-id only — labels are handled by the generic
  // synonym mapper, and matching them here risks false positives (e.g. "Company
  // name" → fullName). The data-automation-id (Workday) is folded into `domId`
  // by the detector via the element id; we include name + autocomplete too.
  const idName = `${field.name ?? ""} ${field.domId ?? ""} ${
    field.autocomplete ?? ""
  }`.toLowerCase();
  for (const h of hints) {
    if (idName.includes(h.match)) return h.key;
  }
  return undefined;
}
