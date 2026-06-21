import type { DetectedPlatform } from "@/shared/types";

/**
 * Identify the ATS hosting the current form. Used to (a) tag learned memory so
 * answers reuse within the same platform, and (b) pick a fill adapter for
 * custom widgets. Detection is best-effort by hostname + DOM markers.
 */
export function detectPlatform(): DetectedPlatform {
  const host = location.hostname;
  const html = document.documentElement;

  const has = (sel: string) => Boolean(document.querySelector(sel));

  if (/greenhouse\.io$/.test(host) || has("#grnhse_app, [id^='greenhouse']"))
    return { id: "greenhouse", label: "Greenhouse" };
  if (/lever\.co$/.test(host) || has(".application-form[action*='lever']"))
    return { id: "lever", label: "Lever" };
  if (/myworkdayjobs\.com$/.test(host) || has("[data-automation-id]"))
    return { id: "workday", label: "Workday" };
  if (/ashbyhq\.com$/.test(host) || has("[class*='ashby']"))
    return { id: "ashby", label: "Ashby" };
  if (/icims\.com$/.test(host)) return { id: "icims", label: "iCIMS" };
  if (/wd\d+\.myworkday/.test(host)) return { id: "workday", label: "Workday" };
  if (/successfactors\.com$/.test(host) || /sapsf/.test(host))
    return { id: "successfactors", label: "SuccessFactors" };
  if (html.getAttribute("data-ats")) {
    const id = html.getAttribute("data-ats")!;
    return { id, label: id };
  }
  return { id: "generic", label: "Generic" };
}

/** Registered fill adapters can override how a given control is filled. */
export interface PlatformAdapter {
  id: string;
  /**
   * Attempt to fill a custom widget. Return true if it handled the element.
   * Falls back to the generic filler when it returns false.
   */
  fillCustom?(el: Element, value: string): Promise<boolean> | boolean;
}

const adapters: Record<string, PlatformAdapter> = {};

export function registerAdapter(a: PlatformAdapter): void {
  adapters[a.id] = a;
}

export function getAdapter(platformId: string): PlatformAdapter | undefined {
  return adapters[platformId];
}
