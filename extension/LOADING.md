# Loading AppFill into Chrome — Complete Guide

This walks you from a fresh checkout to a working, configured extension you can
use on real job applications. Works in **Chrome**, **Edge**, **Brave**, and any
Chromium browser (the steps are identical; only the `chrome://` URL prefix
differs — Edge uses `edge://extensions`, Brave uses `brave://extensions`).

---

## 0. Prerequisites

- **Node.js 18+** and **npm** (you have Node 24 / npm 11 — fine).
  Check: `node --version`
- A Chromium browser (Chrome/Edge/Brave).
- (Optional) An OpenAI-compatible API key — only needed for the AI features
  (field-mapping fallback, cover letters, screening answers, markdown→profile
  extraction). Plain deterministic + learned autofill works with **no key**.

---

## 1. Build the extension

The browser loads the compiled output in `dist/`, not the source. Build it once:

```bash
cd /home/neovara/job-hunt/extension
npm install      # first time only
npm run build
```

You should see Vite print a list of files and `✓ built in …`. This creates the
`extension/dist/` folder containing `manifest.json`, the service worker, the
content script, the popup/options pages, and icons.

> If `npm run build` errors, fix that first — a broken build won't load. Run
> `npm test` to sanity-check the core logic (should be 19 passing tests).

---

### Option B: build a distributable zip

To produce a versioned, shareable artifact instead of loading the raw `dist/`:

```bash
npm run package      # runs the build, then zips dist/ → release/appfill-<version>.zip
```

This writes `extension/release/appfill-<version>.zip` with `manifest.json` at the
zip root.

> **Important:** Chrome cannot install a raw `.zip` directly — "Load unpacked"
> needs an unpacked folder, and drag-and-drop install only ever worked for signed
> `.crx` files. So the zip is for **distribution / Chrome Web Store upload**. To
> run it locally, **unzip it first**, then load the unzipped folder via the steps
> below (point "Load unpacked" at the unzipped folder instead of `dist/`).
>
> The zip *is* exactly what you upload at the Chrome Web Store Developer Dashboard
> if you ever publish.

---

## 2. Open the Extensions page

1. Open Chrome.
2. Go to **`chrome://extensions`** (type it in the address bar and press Enter).
   - Or: **⋮ menu → Extensions → Manage Extensions**.

---

## 3. Enable Developer mode

In the **top-right corner** of the Extensions page, toggle **Developer mode**
**ON**. Three buttons appear: *Load unpacked*, *Pack extension*, *Update*.

---

## 4. Load the extension

1. Click **Load unpacked**.
2. In the file picker, navigate to and select the **`dist`** folder:
   `/home/neovara/job-hunt/extension/dist`
   (Select the `dist` folder itself — not `extension/`, not a file inside it.)
3. Click **Open / Select**.

The **AppFill** card now appears on the page. If you see a red **Errors**
button, click it to see what's wrong (usually a stale build — re-run
`npm run build` and reload).

---

## 5. Pin it to the toolbar (recommended)

1. Click the **puzzle-piece icon** (Extensions) in the Chrome toolbar.
2. Find **AppFill** and click the **pin icon** so its icon stays visible.

Clicking the icon opens the **popup**.

---

## 6. First-time setup (do this before using it)

Open the **options page**: right-click the AppFill icon → **Options**, or popup →
**“Edit profile & settings →”**.

1. **Section 1 · Resume**
   - **Resume file**: upload your PDF/DOCX. This is the file attached to
     “Upload your resume” fields on applications.
   - **Resume markdown**: paste a markdown version of your resume. This is the
     text the autofiller and AI features read.
2. **Section 3 · LLM** (optional but needed for AI)
   - Paste your **API key** (single, or comma-separated for a key pool).
   - **Base URL** defaults to OpenAI; change it for DeepSeek / local vLLM / Ollama.
   - **Model** defaults to `gpt-4o-mini`.
   - Toggle which AI features you want on.
3. **Section 2 · Profile**
   - Click **“Extract profile with AI”** to parse your markdown into structured
     fields (needs the key from step 2) — **or** fill First name / Email / etc.
     by hand. Edit the **Advanced JSON** box for links, work history, education.
   - Click **Save profile**.
4. **Section 4 · Fill behavior** — leave **Auto-fill on page load** on, or turn it
   off to fill only via the popup button. Adjust the low-confidence threshold if
   you want more/fewer “review” badges.

> With no API key, skip step 2's AI parts: fill the profile fields manually and
> AppFill still does deterministic + learned autofill. Nothing leaves your device.

---

## 7. Use it

1. Open a real job application (Greenhouse, Lever, Workday, Ashby, or any form).
2. If auto-fill is on, fields populate on load:
   - **Green outline** = confident fill.
   - **Amber dashed + “review” / “AI · review” badge** = low-confidence or AI
     guess — check these before submitting.
3. Or click the AppFill icon → **“Fill this form”** to fill on demand.
4. Click **“Generate cover letter → clipboard”** to draft one (needs a key).
5. **Review everything, then submit yourself** — AppFill never submits for you.
6. When you submit, AppFill **remembers** your answers. Next time a similar form
   (same platform first, then anywhere) pre-fills from what you entered.

---

## 8. Updating after code changes

The extension does **not** auto-update from source. After editing `src/`:

```bash
npm run build
```

Then on `chrome://extensions`, click the **↻ reload icon** on the AppFill card
(or the **Update** button at the top). Reload the job-application tab too.

> Faster dev loop: `npm run dev` runs Vite with HMR, so the popup/options pages
> hot-reload. Content-script changes may still need a tab refresh + extension
> reload. For day-to-day use, `npm run build` + reload is simplest.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| “Load unpacked” greyed out | Turn on **Developer mode** (top-right). |
| Card shows **Errors** | Re-run `npm run build`; click Errors to read details; reload the card. |
| Popup says “Open a job application page…” | The content script only runs on pages with form fields; reload the tab after installing. |
| Nothing fills | Check a profile is saved (options → section 2) and auto-fill/per-site toggle is on; click **Fill this form** manually. |
| Resume not attaching | Some ATS use custom upload widgets — the field is flagged; attach manually. Confirm a resume file is uploaded in options. |
| AI features error | Verify API key, base URL, and model in options → section 3; check the key has quota. |
| Workday dropdowns not filling | Workday’s custom widgets are best-effort; review amber-badged fields and pick manually. |
| Want to disable on one site | Popup → uncheck **“Auto-fill on this site”** (stored as a per-site override). |

---

## 10. Privacy reminder

Everything is stored **locally** in your browser (profile, resume, learned
answers, API key). The only network call is to your configured OpenAI-compatible
endpoint, and only when an AI feature runs. Turn AI features off in options to keep
all data on-device.
