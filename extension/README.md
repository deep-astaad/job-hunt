# AppFill — Job Application Autofiller (Chrome Extension)

A Manifest V3 Chrome extension that autofills job-application forms on **any
platform** using your resume, and **learns from your submissions** so repeat ATS
forms (e.g. Workday) pre-fill from what you entered last time.

It is **self-contained** — your profile, resume file, learned answers, and OpenAI
key all live in your browser. It does not depend on the job-hunt Django backend.

## How it works

1. **Resume artifacts** (set up in the options page):
   - A **binary resume** (PDF/DOCX) stored in IndexedDB → attached to file-upload
     fields.
   - A **markdown resume** → an LLM-readable source you can paste in. "Extract
     profile with AI" parses it into the master resume (or fill it by hand — no
     LLM required).
   - A **master resume (YAML)** → the single source of truth for everything
     AppFill knows about you (contact, summary, work history, education, skills,
     links, eligibility). Autofill and all generation derive from it; it's
     human-editable, and **"Download / print PDF"** renders it to a clean
     printable resume.
2. **Hybrid field mapping** (content script): for each detected field it tries, in
   order — learned **memory** (per-domain → per-platform → global), a deterministic
   **dictionary** (labels/autocomplete → profile), then an **LLM fallback** for
   whatever's left (optional).
3. **Passive by default** — AppFill does **not** auto-fill on load. When you focus a
   field it shows an inline suggestion ("AppFill: <value> · Fill") you can accept,
   with an optional **✨ AI** action for fields it can't map deterministically.
   Whole-form **auto-fill on page load** is opt-in (globally in options, or per-site
   from the popup); when on, filled fields are highlighted and low-confidence/AI
   values are badged "review". It **never submits** for you.
4. **Learning**: when you submit, every field's signature → value is captured into
   memory and reused on future forms.
5. **LLM content** (optional toggles): cover letters and screening-question answers
   from the popup, grounded in your profile.

### Power features

- **Manual input that learns** — if a field isn't in your profile, the focus bubble
  lets you type a value; it fills, **remembers it** for next time, and offers to
  **save it to your profile** when it maps to a known field.
- **Inline generation** — focusing a big text box (cover letter / "why this
  company?") offers **✨ Generate**, grounded in your profile + the page's job.
- **Pre-submit check** — the popup’s **Check before submitting** flags empty
  required fields, fields you have data for but left blank, and a rough
  experience-vs-JD gap, as an on-page checklist that jumps you to each field.
- **Work history & education** — the popup’s **Fill work history & education**
  populates repeating ATS rows (company, title, dates, description / school,
  degree, field) from your master resume, clicking “Add another” as needed.
- **Guided multi-page fill** — for ATS wizards (Workday, Greenhouse, …), the
  popup’s **Guided multi-page fill** fills the page, then an on-page bar lets you
  review and click **Next →** to advance and re-fill each step. It survives full
  page reloads and **hard-stops at the final Submit** — you submit.
- **Tailored resume per job** — the popup’s **Tailor resume for this job** shows a
  deterministic JD match score and (with an LLM) generates a JD-focused resume from
  your master, opened as a printable PDF. Upload multiple **resume variants** with
  labels/tags (e.g. “Backend”, “ML”) and AppFill attaches the best match per posting.
- **Bring your own LLM (no API key)** — set LLM mode to **Web chat** (options §3)
  to generate via a logged-in **Claude / ChatGPT / Gemini / Kimi** tab instead of
  an API key. AppFill opens the chat with your prompt (also copied to clipboard),
  and the answer returns to the field automatically — or paste it back. It never
  auto-sends; you drive the chat.
- **Right-click menu** — "AppFill: fill this field" / "fill this form".
- **Keyboard shortcut** — `Ctrl/Cmd+Shift+L` fills the current form (rebind at
  `chrome://extensions/shortcuts`).
- **Toolbar badge** — shows how many fillable fields AppFill sees on the page.
- **Backup** — export/import everything (profile, resume, learned answers, settings)
  as a JSON file from the options page.

## Develop

```bash
cd extension
npm install
npm run dev        # Vite dev server with HMR for popup/options
npm run build      # type-check + production build into dist/
npm test           # vitest unit tests
```

Load the unpacked extension: open `chrome://extensions`, enable Developer mode,
"Load unpacked", and select `extension/dist` (after `npm run build`).

## Privacy

All data is local. The only external call is to your configured OpenAI-compatible
endpoint, and only when an LLM feature runs. Turn LLM features off (options →
section 3) to keep everything on-device — deterministic + learned autofill still
works.

## Layout

- `src/content/` — detector, signature, mapper, resolver, filler, highlight,
  capture, platform adapters.
- `src/background/service-worker.ts` — LLM calls, memory persistence, resume bytes.
- `src/storage/` — settings, profile, memory (chrome.storage), resume (IndexedDB).
- `src/llm/` — OpenAI-compatible client (ports the repo's `llm.py` retry pattern)
  + prompts.
- `src/popup/`, `src/options/` — React UIs.
