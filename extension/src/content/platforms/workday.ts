import type { PlatformAdapter } from "./index";

/**
 * Workday renders many "selects" as a button that opens a popup listbox, keyed
 * by data-automation-id. Best-effort: click to open, then click the option whose
 * text matches. Workday is notoriously inconsistent, so this returns false when
 * it can't confidently complete (the caller then flags the field for review).
 */
export const workdayAdapter: PlatformAdapter = {
  id: "workday",
  async fillCustom(el: Element, value: string): Promise<boolean> {
    const want = value.trim().toLowerCase();
    const trigger = el.closest<HTMLElement>(
      "[data-automation-id], button, [role='button'], [role='combobox']"
    );
    if (!trigger) return false;

    trigger.click();
    const listbox = await waitFor(
      () =>
        document.querySelector<HTMLElement>(
          "[role='listbox'], [data-automation-id='activeListContainer']"
        ),
      1500
    );
    if (!listbox) return false;

    const option = Array.from(
      listbox.querySelectorAll<HTMLElement>("[role='option'], li, div")
    ).find((o) => {
      const t = (o.textContent ?? "").trim().toLowerCase();
      return t === want || t.includes(want);
    });
    if (!option) return false;
    option.click();
    return true;
  },
};

function waitFor<T>(fn: () => T | null, timeoutMs: number): Promise<T | null> {
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = () => {
      const v = fn();
      if (v) return resolve(v);
      if (Date.now() - start > timeoutMs) return resolve(null);
      requestAnimationFrame(tick);
    };
    tick();
  });
}
