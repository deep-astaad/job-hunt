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
  // popup -> background: produce a JD-focused resume (subset/reordered profile)
  | {
      type: "LLM_TAILOR_RESUME";
      profile: CandidateProfile;
      job?: JobContext;
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
  // extension origin, which the page-scoped content script can't read directly).
  // jobText, when present, lets the background auto-pick the best resume variant.
  | { type: "GET_RESUME_FILE"; jobText?: string }
  // content/popup -> background: start a BYO-LLM web-chat handoff. Background
  // opens the provider tab and records the prompt + return target.
  | {
      type: "WEBCHAT_HANDOFF";
      providerId: string;
      prompt: string;
      /** Fill the answer back into this field on the originating tab. */
      fieldHandle?: string;
    }
  // provider content -> background: the captured answer to relay back.
  | { type: "WEBCHAT_RESULT"; id: string; text: string }
  // background -> origin content: fill a field with a returned web-chat answer.
  | { type: "FILL_RESULT"; fieldHandle: string; text: string }
  // popup -> content: scrape the job posting on the page for grounding.
  | { type: "GET_JOB_CONTEXT" }
  // popup -> content: start / stop the guided multi-page "Fill & Next" flow.
  | { type: "FLOW_START" }
  | { type: "FLOW_STOP" }
  // popup -> content: fill repeating work-history / education sections.
  | { type: "FILL_WORK_HISTORY" }
  // popup -> content: run the pre-submit validation pass and show the checklist.
  | { type: "VALIDATE_FORM" }
  // content -> background: an application was submitted; log it (opt-in).
  | {
      type: "APPLICATION_SUBMITTED";
      record: {
        company?: string;
        role?: string;
        url?: string;
        platform: string;
      };
    };

export type MessageResponse =
  | { ok: true; resolutions: FieldResolution[] }
  | { ok: true; text: string }
  | { ok: true; url: string }
  | { ok: true; job: JobContext }
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
