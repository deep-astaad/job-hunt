import { useEffect, useState } from "react";
import {
  getSettings,
  saveSettings,
  DEFAULT_SETTINGS,
  type Settings,
} from "@/storage/settings";
import { getProfile, saveProfile } from "@/storage/profile";
import {
  saveResumeFile,
  getResumeFile,
  deleteResumeFile,
} from "@/storage/resumeFile";
import { getAllMemory, deleteMemory, clearMemory } from "@/storage/memory";
import type { MemoryEntry } from "@/storage/memory";
import { type CandidateProfile, type EligibilityInfo } from "@/profile/schema";
import { extractProfileFromMarkdown } from "@/profile/markdownImport";
import { profileToYaml, yamlToProfile } from "@/profile/yaml";
import { profileToResumeHtml } from "@/profile/resumeHtml";
import { exportAll, importAll, type Backup } from "@/storage/backup";

export function Options() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [markdown, setMarkdown] = useState("");
  const [yamlText, setYamlText] = useState("");
  const [resumeName, setResumeName] = useState<string | null>(null);
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void (async () => {
      setSettings(await getSettings());
      const p = await getProfile();
      setMarkdown(p.rawMarkdown ?? "");
      setYamlText(profileToYaml(p));
      const rf = await getResumeFile();
      setResumeName(rf?.name ?? null);
      setMemory(await getAllMemory());
    })();
  }, []);

  function flash(m: string) {
    setMsg(m);
    setTimeout(() => setMsg(""), 3000);
  }

  async function patchSettings(patch: Partial<Settings>) {
    setSettings(await saveSettings(patch));
  }

  async function onExtract() {
    if (!markdown.trim()) return flash("Paste your resume markdown first.");
    setBusy(true);
    try {
      const extracted = await extractProfileFromMarkdown(markdown);
      setYamlText(profileToYaml(extracted));
      await saveProfile(extracted);
      flash("Profile extracted ✓ Review the master resume below.");
    } catch (e) {
      flash(e instanceof Error ? e.message : "Extraction failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onSaveProfile() {
    let parsed: CandidateProfile;
    try {
      parsed = yamlToProfile(yamlText);
    } catch {
      return flash("Master resume YAML is invalid — fix it before saving.");
    }
    const merged = { ...parsed, rawMarkdown: markdown };
    setYamlText(profileToYaml(merged));
    await saveProfile(merged);
    flash("Master resume saved ✓");
  }

  /** Open the rendered resume in a new tab for the user to print/save as PDF. */
  function onDownloadPdf() {
    let p: CandidateProfile;
    try {
      p = yamlToProfile(yamlText);
    } catch {
      return flash("Fix the master resume YAML first.");
    }
    const html = profileToResumeHtml(p);
    const w = window.open("", "_blank");
    if (!w) return flash("Allow pop-ups to open the printable resume.");
    w.document.write(html);
    w.document.close();
    setTimeout(() => w.print(), 350);
  }

  const parsedPreview = (() => {
    try {
      const p = yamlToProfile(yamlText);
      const name =
        p.contact.fullName ||
        [p.contact.firstName, p.contact.lastName].filter(Boolean).join(" ") ||
        "—";
      return `${name} · ${p.contact.email ?? "no email"} · ${p.skills.length} skills · ${p.workExperience.length} roles`;
    } catch {
      return "invalid YAML";
    }
  })();

  // Application preferences edit the eligibility block of the master resume.
  // They read from / write back to the YAML so it stays the single source of
  // truth; "Save" persists the whole document.
  const elig: EligibilityInfo = (() => {
    try {
      return yamlToProfile(yamlText).eligibility;
    } catch {
      return {};
    }
  })();

  function patchEligibility(patch: Partial<EligibilityInfo>) {
    let p: CandidateProfile;
    try {
      p = yamlToProfile(yamlText);
    } catch {
      return flash("Fix the master resume YAML first.");
    }
    p.eligibility = { ...p.eligibility, ...patch };
    setYamlText(profileToYaml(p));
  }

  function setEligText(k: keyof EligibilityInfo, v: string) {
    patchEligibility({ [k]: v || undefined } as Partial<EligibilityInfo>);
  }
  function setEligBool(k: keyof EligibilityInfo, v: string) {
    patchEligibility({
      [k]: v === "" ? undefined : v === "yes",
    } as Partial<EligibilityInfo>);
  }
  const yesNo = (b?: boolean) => (b == null ? "" : b ? "yes" : "no");

  async function onResumeUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await saveResumeFile(file);
    setResumeName(file.name);
    flash("Resume stored ✓ It will attach to upload fields.");
  }

  async function onDeleteResume() {
    await deleteResumeFile();
    setResumeName(null);
  }

  async function onExport() {
    const data = await exportAll();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `appfill-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function onImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const data = JSON.parse(await file.text()) as Backup;
      await importAll(data);
      // reload UI state
      setSettings(await getSettings());
      const p = await getProfile();
      setMarkdown(p.rawMarkdown ?? "");
      setYamlText(profileToYaml(p));
      const rf = await getResumeFile();
      setResumeName(rf?.name ?? null);
      setMemory(await getAllMemory());
      flash("Backup imported ✓");
    } catch (err) {
      flash(err instanceof Error ? err.message : "Import failed.");
    }
  }

  return (
    <div style={wrap}>
      <h1 style={{ fontSize: 20, margin: "0 0 4px" }}>AppFill</h1>
      <p style={{ color: "#6b7280", marginTop: 0 }}>
        Autofills job applications on any site and learns from your submissions.
      </p>
      {msg && <div style={banner}>{msg}</div>}

      <Section title="1 · Resume">
        <label style={label}>Resume file (PDF/DOCX) — attached to upload fields</label>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <input type="file" accept=".pdf,.doc,.docx" onChange={onResumeUpload} />
          {resumeName && (
            <>
              <span style={{ fontSize: 13 }}>{resumeName}</span>
              <button style={linkBtn} onClick={onDeleteResume}>
                remove
              </button>
            </>
          )}
        </div>

        <label style={{ ...label, marginTop: 16 }}>
          Resume markdown — the LLM-readable source for filling & generation
        </label>
        <textarea
          value={markdown}
          onChange={(e) => setMarkdown(e.target.value)}
          rows={10}
          placeholder="# Jane Doe&#10;Backend Engineer · jane@example.com · +81…&#10;## Experience&#10;…"
          style={textarea}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button style={btn} onClick={onExtract} disabled={busy}>
            {busy ? "Extracting…" : "Extract profile with AI"}
          </button>
          <span style={{ fontSize: 12, color: "#6b7280", alignSelf: "center" }}>
            Needs an OpenAI key (section 3). Or fill the fields below by hand.
          </span>
        </div>
      </Section>

      <Section title="2 · Master resume (YAML)">
        <p style={{ fontSize: 12, color: "#6b7280", marginTop: 0 }}>
          The single source of truth for everything AppFill knows about you —
          contact, summary, work history, education, skills, links, and
          eligibility. Autofill and generation derive from this. Edit it directly,
          or bootstrap it from your markdown resume above with “Extract”.
        </p>
        <textarea
          value={yamlText}
          onChange={(e) => setYamlText(e.target.value)}
          rows={20}
          spellCheck={false}
          style={{ ...textarea, fontFamily: "ui-monospace, monospace", fontSize: 12.5 }}
        />
        <div style={{ fontSize: 12, color: "#6b7280", margin: "6px 0" }}>
          Parsed: <b>{parsedPreview}</b>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
          <button style={primaryBtn} onClick={onSaveProfile}>
            Save master resume
          </button>
          <button style={btn} onClick={onDownloadPdf}>
            Download / print PDF
          </button>
        </div>
      </Section>

      <Section title="Application preferences (EEO · work eligibility · logistics)">
        <p style={{ fontSize: 12, color: "#6b7280", marginTop: 0 }}>
          Set these once. They map deterministically to the repetitive questions
          on nearly every application (sponsorship, authorization, notice period,
          voluntary EEO). Saved into your master resume above.
        </p>
        <div style={grid}>
          <Field
            label="Work authorization"
            value={elig.workAuthorization}
            onChange={(v) => setEligText("workAuthorization", v)}
          />
          <Select
            label="Requires visa sponsorship?"
            value={yesNo(elig.requiresSponsorship)}
            onChange={(v) => setEligBool("requiresSponsorship", v)}
            options={yesNoOptions}
          />
          <Select
            label="Willing to relocate?"
            value={yesNo(elig.willingToRelocate)}
            onChange={(v) => setEligBool("willingToRelocate", v)}
            options={yesNoOptions}
          />
          <Field
            label="Notice period"
            value={elig.noticePeriod}
            onChange={(v) => setEligText("noticePeriod", v)}
          />
          <Field
            label="Available start date"
            value={elig.availableStartDate}
            onChange={(v) => setEligText("availableStartDate", v)}
          />
          <Field
            label="Desired salary"
            value={elig.desiredSalary}
            onChange={(v) => setEligText("desiredSalary", v)}
          />
        </div>
        <p style={{ ...label, marginTop: 14, marginBottom: 6, color: "#6b7280" }}>
          Voluntary EEO (optional — leave blank or “Prefer not to say”)
        </p>
        <div style={grid}>
          <Select
            label="Gender"
            value={elig.gender ?? ""}
            onChange={(v) => setEligText("gender", v)}
            options={["", "Male", "Female", "Non-binary", "Prefer not to say"]}
          />
          <Field
            label="Race / ethnicity"
            value={elig.raceEthnicity}
            onChange={(v) => setEligText("raceEthnicity", v)}
          />
          <Select
            label="Veteran status"
            value={elig.veteranStatus ?? ""}
            onChange={(v) => setEligText("veteranStatus", v)}
            options={[
              "",
              "I am not a protected veteran",
              "I am a protected veteran",
              "Prefer not to say",
            ]}
          />
          <Select
            label="Disability status"
            value={elig.disabilityStatus ?? ""}
            onChange={(v) => setEligText("disabilityStatus", v)}
            options={[
              "",
              "No, I do not have a disability",
              "Yes, I have a disability",
              "Prefer not to say",
            ]}
          />
        </div>
        <button style={{ ...primaryBtn, marginTop: 12 }} onClick={onSaveProfile}>
          Save preferences
        </button>
      </Section>

      <Section title="3 · LLM">
        <label style={label}>How AppFill generates text</label>
        <Select
          label=""
          value={settings.llmMode}
          onChange={(v) => patchSettings({ llmMode: v as Settings["llmMode"] })}
          options={["direct", "webchat", "off"]}
        />
        <p style={{ fontSize: 12, color: "#6b7280", margin: "6px 0 0" }}>
          <b>Direct API</b>: call an OpenAI-compatible endpoint with your key.{" "}
          <b>Web chat</b>: hand the prompt to a logged-in chat (Claude / ChatGPT /
          Gemini / Kimi) — <i>no API key needed</i>. <b>Off</b>: deterministic +
          learned autofill only.
        </p>

        {settings.llmMode === "webchat" && (
          <div style={{ marginTop: 12, padding: 12, background: "#f9fafb", borderRadius: 8 }}>
            <Select
              label="Chat provider"
              value={settings.webchatProvider}
              onChange={(v) => patchSettings({ webchatProvider: v })}
              options={["claude", "chatgpt", "gemini", "kimi"]}
            />
            <div style={{ marginTop: 8 }}>
              <Toggle
                label="Auto-paste the prompt into the chat (best effort)"
                checked={settings.webchatAutoInject}
                onChange={(v) => patchSettings({ webchatAutoInject: v })}
              />
            </div>
            <p style={{ fontSize: 12, color: "#6b7280", margin: "6px 0 0" }}>
              “Generate with {settings.webchatProvider}” opens the chat with your
              prompt (also copied to your clipboard). The answer returns to the
              field automatically when possible, or paste it back yourself. Nothing
              is sent until you submit the chat — AppFill never auto-sends.
            </p>
          </div>
        )}

        {settings.llmMode === "direct" && (
          <div style={{ marginTop: 12 }}>
            <p style={{ fontSize: 12, color: "#6b7280", marginTop: 0 }}>
              Key stored locally and used only from the background worker. Any
              OpenAI-compatible base URL works (OpenAI, DeepSeek, local vLLM…).
            </p>
            <Field
              label="API key (single, or comma-separated pool)"
              value={settings.openaiApiKey}
              onChange={(v) => patchSettings({ openaiApiKey: v })}
              type="password"
              full
            />
            <div style={grid}>
              <Field label="Base URL" value={settings.openaiBaseUrl} onChange={(v) => patchSettings({ openaiBaseUrl: v })} />
              <Field label="Model" value={settings.openaiModel} onChange={(v) => patchSettings({ openaiModel: v })} />
            </div>
          </div>
        )}

        {settings.llmMode !== "off" && (
          <div style={{ marginTop: 10 }}>
            {settings.llmMode === "direct" && (
              <Toggle label="LLM field mapping (ambiguous fields)" checked={settings.llmFieldMappingEnabled} onChange={(v) => patchSettings({ llmFieldMappingEnabled: v })} />
            )}
            <Toggle label="Cover letter generation" checked={settings.coverLetterEnabled} onChange={(v) => patchSettings({ coverLetterEnabled: v })} />
            <Toggle label="Screening-question answers" checked={settings.screeningAnswersEnabled} onChange={(v) => patchSettings({ screeningAnswersEnabled: v })} />
            <Toggle label="Field-value tailoring" checked={settings.fieldTailoringEnabled} onChange={(v) => patchSettings({ fieldTailoringEnabled: v })} />
          </div>
        )}
      </Section>

      <Section title="4 · Fill behavior">
        <Toggle label="Suggest a value when I focus a field (recommended)" checked={settings.suggestOnFocus} onChange={(v) => patchSettings({ suggestOnFocus: v })} />
        <Toggle label="Auto-fill the whole form on page load (off by default)" checked={settings.autofillOnLoad} onChange={(v) => patchSettings({ autofillOnLoad: v })} />
        <p style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 0" }}>
          By default AppFill stays passive: it only offers a suggestion when you
          click into a field. Turn on auto-fill globally here, or per-site from
          the toolbar popup.
        </p>
        <label style={{ ...label, marginTop: 10 }}>
          Low-confidence threshold: {settings.lowConfidenceThreshold.toFixed(2)} (below
          this, values are badged “review”)
        </label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={settings.lowConfidenceThreshold}
          onChange={(e) => patchSettings({ lowConfidenceThreshold: Number(e.target.value) })}
        />
        {Object.keys(settings.siteOverrides).length > 0 && (
          <div style={{ marginTop: 12, fontSize: 13 }}>
            <b>Per-site overrides</b>
            {Object.entries(settings.siteOverrides).map(([d, on]) => (
              <div key={d} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span>{d}: {on ? "on" : "off"}</span>
                <button style={linkBtn} onClick={() => {
                  const next = { ...settings.siteOverrides };
                  delete next[d];
                  void patchSettings({ siteOverrides: next });
                }}>clear</button>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="5 · Learned memory">
        <p style={{ fontSize: 12, color: "#6b7280", marginTop: 0 }}>
          Answers captured when you submit applications. Reused on the same
          platform first, then anywhere.
        </p>
        {memory.length === 0 ? (
          <div style={{ color: "#6b7280", fontSize: 13 }}>Nothing learned yet.</div>
        ) : (
          <div style={{ maxHeight: 240, overflow: "auto" }}>
            {memory.map((m) => (
              <div key={m.signature} style={memRow}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: "#6b7280", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.signature}</div>
                  <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.globalValue}</div>
                </div>
                <button style={linkBtn} onClick={async () => {
                  await deleteMemory(m.signature);
                  setMemory(await getAllMemory());
                }}>delete</button>
              </div>
            ))}
          </div>
        )}
        {memory.length > 0 && (
          <button style={{ ...btn, marginTop: 8 }} onClick={async () => {
            await clearMemory();
            setMemory([]);
          }}>Clear all learned answers</button>
        )}
      </Section>

      <Section title="6 · Backup">
        <p style={{ fontSize: 12, color: "#6b7280", marginTop: 0 }}>
          Export everything (profile, resume, learned answers, settings) to a JSON
          file, or restore from one. The file includes your API key — keep it safe.
        </p>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button style={btn} onClick={onExport}>Export backup</button>
          <label style={{ ...btn, display: "inline-flex", alignItems: "center", gap: 6 }}>
            Import backup
            <input type="file" accept="application/json" onChange={onImport} style={{ display: "none" }} />
          </label>
        </div>
      </Section>

      <Section title="7 · Tips">
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "#374151" }}>
          <li>Focus any field to get a fill suggestion. If it's not in your profile, type a value once — AppFill remembers it and offers to save it.</li>
          <li>Right-click a field → <b>AppFill: fill this field</b>, or a page → <b>fill this form</b>.</li>
          <li>Keyboard: <b>Ctrl/Cmd+Shift+L</b> fills the current form (rebind at <code>chrome://extensions/shortcuts</code>).</li>
          <li>On big text boxes (cover letter / “why this company”), use <b>✨ Generate</b>.</li>
        </ul>
      </Section>
    </div>
  );
}

// --- small presentational helpers ---
function Section(props: { title: string; children: React.ReactNode }) {
  return (
    <section style={card}>
      <h2 style={{ fontSize: 15, margin: "0 0 10px" }}>{props.title}</h2>
      {props.children}
    </section>
  );
}

function Field(props: {
  label: string;
  value?: string;
  onChange: (v: string) => void;
  type?: string;
  full?: boolean;
}) {
  return (
    <div style={{ gridColumn: props.full ? "1 / -1" : undefined }}>
      <label style={label}>{props.label}</label>
      <input
        type={props.type ?? "text"}
        value={props.value ?? ""}
        onChange={(e) => props.onChange(e.target.value)}
        style={input}
      />
    </div>
  );
}

const yesNoOptions = ["", "yes", "no"];

const OPTION_LABELS: Record<string, string> = {
  "": "—",
  yes: "Yes",
  no: "No",
  direct: "Direct API (your key)",
  webchat: "Web chat (no key)",
  off: "Off",
  claude: "Claude",
  chatgpt: "ChatGPT",
  gemini: "Gemini",
  kimi: "Kimi",
};

function Select(props: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <div>
      {props.label && <label style={label}>{props.label}</label>}
      <select
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        style={input}
      >
        {props.options.map((o) => (
          <option key={o} value={o}>
            {OPTION_LABELS[o] ?? o}
          </option>
        ))}
      </select>
    </div>
  );
}

function Toggle(props: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", fontSize: 13 }}>
      <input type="checkbox" checked={props.checked} onChange={(e) => props.onChange(e.target.checked)} />
      {props.label}
    </label>
  );
}

const wrap: React.CSSProperties = { maxWidth: 720, margin: "0 auto", padding: 24 };
const card: React.CSSProperties = { background: "#fff", borderRadius: 12, padding: 18, marginTop: 16, boxShadow: "0 1px 2px rgba(0,0,0,0.05)" };
const grid: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 };
const label: React.CSSProperties = { display: "block", fontSize: 12, color: "#374151", marginBottom: 4 };
const input: React.CSSProperties = { width: "100%", boxSizing: "border-box", padding: "7px 9px", border: "1px solid #d1d5db", borderRadius: 7, fontSize: 13 };
const textarea: React.CSSProperties = { ...input, resize: "vertical" };
const btn: React.CSSProperties = { padding: "8px 12px", borderRadius: 8, border: "1px solid #d1d5db", background: "#fff", cursor: "pointer", fontSize: 13 };
const primaryBtn: React.CSSProperties = { ...btn, background: "#2563eb", color: "#fff", border: "1px solid #2563eb", fontWeight: 600 };
const linkBtn: React.CSSProperties = { background: "none", border: "none", color: "#2563eb", cursor: "pointer", fontSize: 12, padding: 0 };
const banner: React.CSSProperties = { background: "#ecfdf5", border: "1px solid #a7f3d0", color: "#065f46", padding: "8px 12px", borderRadius: 8, fontSize: 13, marginTop: 10 };
const memRow: React.CSSProperties = { display: "flex", gap: 10, justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #f3f4f6" };
