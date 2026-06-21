import type { FieldResolution } from "@/shared/types";
import { getElement } from "./detector";

/**
 * Visually mark what was filled so the user reviews before submitting. High
 * confidence = subtle green outline; low confidence / LLM-guessed = amber with a
 * small badge. Styles are injected once into the page.
 */
const STYLE_ID = "appfill-styles";

function ensureStyles(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .appfill-filled { outline: 2px solid rgba(34,197,94,0.7) !important; outline-offset: 1px; transition: outline-color .3s; }
    .appfill-review { outline: 2px dashed rgba(245,158,11,0.9) !important; outline-offset: 1px; }
    .appfill-badge {
      position: absolute; z-index: 2147483647; font: 600 10px/1.4 system-ui, sans-serif;
      background: #f59e0b; color: #1f2937; padding: 1px 5px; border-radius: 6px;
      pointer-events: none; transform: translateY(-50%);
    }
  `;
  document.documentElement.appendChild(style);
}

export function clearHighlights(): void {
  document
    .querySelectorAll(".appfill-filled, .appfill-review")
    .forEach((el) => el.classList.remove("appfill-filled", "appfill-review"));
  document.querySelectorAll(".appfill-badge").forEach((el) => el.remove());
}

export function highlight(
  resolutions: FieldResolution[],
  lowConfidenceThreshold: number
): void {
  ensureStyles();
  for (const r of resolutions) {
    const el = getElement(r.fieldId);
    if (!el) continue;
    const low = r.confidence < lowConfidenceThreshold || r.source === "llm";
    el.classList.add(low ? "appfill-review" : "appfill-filled");
    if (low) addBadge(el, r.source === "llm" ? "AI · review" : "review");
  }
}

function addBadge(el: HTMLElement, text: string): void {
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return;
  const badge = document.createElement("div");
  badge.className = "appfill-badge";
  badge.textContent = text;
  badge.style.left = `${window.scrollX + rect.right - 8}px`;
  badge.style.top = `${window.scrollY + rect.top}px`;
  document.body.appendChild(badge);
}
