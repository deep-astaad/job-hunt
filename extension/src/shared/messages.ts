import type { FieldDescriptor, FieldResolution } from "./types";
import type { CandidateProfile } from "@/profile/schema";

/**
 * Typed messaging contract between content script, popup/options UI, and the
 * background service worker. The background worker is the only place that holds
 * the OpenAI key and makes network calls, so the content script asks it to do
 * LLM work rather than calling OpenAI from page context.
 */

export type JobContext = {
  title?: string;
  company?: string;
  description?: string;
  url?: string;
};

export type Message =
  // content -> background: map ambiguous fields with the LLM
  | {
      type: "LLM_MAP_FIELDS";
      fields: FieldDescriptor[];
      profile: CandidateProfile;
    }
  // content/popup -> background: generate prose
  | {
      type: "LLM_GENERATE";
      kind: "cover_letter" | "screening_answer" | "tailor_field";
      profile: CandidateProfile;
      job?: JobContext;
      prompt?: string; // the question / field label / constraint
      maxLength?: number;
    }
  // background -> content: extract structured profile from markdown
  | {
      type: "LLM_EXTRACT_PROFILE";
      markdown: string;
    }
  // popup/background -> content: run a whole-form fill pass now
  | { type: "FILL_NOW" }
  // background -> content: fill the currently focused field (context menu / shortcut)
  | { type: "FILL_FOCUSED" }
  // popup -> content: ask the content script for current page status
  | { type: "GET_STATUS" }
  // content -> background: report fillable-field count so the toolbar badge updates
  | { type: "PAGE_FILLABLE"; count: number }
  // content -> background: persist captured answers on submit
  | {
      type: "CAPTURE_SUBMISSION";
      domain: string;
      platform: string;
      entries: { signature: string; value: string }[];
    }
  // content -> background: fetch the stored resume (IndexedDB lives in the
  // extension origin, which the page-scoped content script can't read directly)
  | { type: "GET_RESUME_FILE" };

export type MessageResponse =
  | { ok: true; resolutions: FieldResolution[] }
  | { ok: true; text: string }
  | { ok: true; profile: CandidateProfile }
  | { ok: true; file?: { name: string; type: string; base64: string } }
  | {
      ok: true;
      status: {
        platform: string;
        fieldCount: number;
        filledCount: number;
        autofillEnabled: boolean;
      };
    }
  | { ok: true }
  | { ok: false; error: string };

export function sendToBackground(msg: Message): Promise<MessageResponse> {
  return chrome.runtime.sendMessage(msg);
}
