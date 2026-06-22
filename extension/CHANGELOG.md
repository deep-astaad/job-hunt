# AppFill Changelog

## 0.3.0 — 2026-06-22

### Master resume & canonical answers
- **Master resume in YAML** — the single source of truth for everything AppFill
  knows about you (contact, summary, work history, education, skills, links,
  eligibility). Human-editable, diff-friendly; autofill and all generation
  derive from it. **"Download / print PDF"** renders it to a clean printable
  resume. (#63)
- **Canonical application answers** — sponsorship, work authorization,
  relocation, notice period, available start date, desired salary, and
  voluntary EEO (gender, race, veteran, disability) now fill deterministically
  everywhere. Set once in the structured **Application preferences** panel. (#47)

### Generation — bring your own LLM, no API key required
- **Web-chat handoff** — set LLM mode to **Web chat** (options §3) and
  generation hands the prompt to a logged-in **Claude / ChatGPT / Gemini /
  Kimi** tab. The answer returns to the field automatically (best-effort) or
  paste it back; it **never auto-sends** — you drive the chat. Works with **no
  API key configured**. (#62)
- **JD-aware generation** — cover letters, screening answers, and tailored
  resumes are now grounded in the **actual job posting on the page**, scraped
  from schema.org JobPosting JSON-LD, meta tags, or a heuristic text scan. (#50)
- **Per-job tailored resume** — the popup's **"Tailor resume for this job"**
  shows a deterministic **match score** and matched skills, then generates a
  JD-focused resume (truthful selection/emphasis, no fabrication) as a
  printable PDF. (#51)
- **Named resume variants** — upload multiple resumes with labels/tags (e.g.
  "Backend", "ML"); AppFill **auto-picks the best match** per posting and
  attaches it to file-upload fields. (#51)

### Multi-page flow runner
- **Guided "Fill & Next"** — for ATS wizards (Workday, Greenhouse, …), the
  popup's **"Guided multi-page fill"** fills the page, then an on-page bar
  lets you review and click **Next →** to advance and re-fill each step. It
  survives full page reloads and **hard-stops at the final Submit** — you
  submit. (#45)

### Platform adapters — deterministic wins more often
- First-class adapters for **Greenhouse, Lever, Ashby, iCIMS,
  SmartRecruiters, and LinkedIn Easy Apply** (joining the existing Workday
  adapter). Each provides platform-specific field-id→canonical-key hints and
  next/submit selectors for the flow runner. (#46)

### Quality of life
- **Pre-submit validation checklist** — the popup's **"Check before
  submitting"** flags empty required fields, fields you have data for but left
  blank, and a rough experience-vs-JD gap. Clicking an item jumps to the
  field. (#49)
- **Work history & education autofill** — the popup's **"Fill work history &
  education"** populates repeating ATS rows (company, title, dates,
  description / school, degree, field, GPA) from your master resume, clicking
  "Add another" as needed. (#52)
- **Opt-in application log** — optionally POST each submission to a
  user-configured backend. **Off by default** — AppFill stays fully
  self-contained, zero network, until you enable it. (#48)

### Networking suite
- **Contact capture** (CRM-lite) — one-click save of {name, role, company,
  profileUrl, context} from LinkedIn / company pages via the popup, with
  list/search/delete in options. Included in backup. (#54)
- **LinkedIn connection-note composer** — draft a personalized <300-char
  connect note grounded in your profile + the contact, by angle (alum / same
  stack / hiring manager / shared interest / referral). Fills LinkedIn's "Add
  a note" box. (#53)
- **Recruiter & referral outreach templates** — editable template library
  (cold intro, referral ask, recruiter follow-up) with `{placeholders}` filled
  from the page's contact + job. Usable with **no LLM** (filled as-is) or
  polished by the LLM. (#55)
- **Follow-up reminders** — contacts past the cadence (configurable, default
 7 days) surface in the popup with a one-click pre-drafted follow-up. (#56)
- **Cold-email drafting** — for companies without an ATS, detect the contact
  address, draft a tailored intro grounded in the posting, and open your mail
  client with the email + resume-attach reminder. (#57)

---

## 0.2.0 — 2026-06-21

- **On-focus suggestions** — when you focus a field, AppFill offers a value
  from memory or your profile, with an inline ✎ edit box that **learns** the
  value for next time and optionally saves it to your profile.
- **Passive by default** — whole-form auto-fill is opt-in (global or per-site
  from the popup). The toolbar badge shows fillable-field count.
- **Inline content generation** — focusing a big text box offers **✨
  Generate** for cover letters / screening answers.
- **Right-click menu + keyboard shortcut** (`Ctrl/Cmd+Shift+L`).
- **Backup** — export/import everything as a JSON file.

## 0.1.0 — 2026-06-21

- Initial release: hybrid field mapping (memory → deterministic → LLM),
  submission learning, markdown resume → profile extraction, Workday adapter,
  popup + options pages.
