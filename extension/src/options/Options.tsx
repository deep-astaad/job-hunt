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
import { type CandidateProfile, emptyProfile } from "@/profile/schema";
import { extractProfileFromMarkdown } from "@/profile/markdownImport";

export function Options() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [profile, setProfile] = useState<CandidateProfile>(emptyProfile());
  const [markdown, setMarkdown] = useState("");
  const [advanced, setAdvanced] = useState("");
  const [resumeName, setResumeName] = useState<string | null>(null);
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void (async () => {
      setSettings(await getSettings());
      const p = await getProfile();
      setProfile(p);
      setMarkdown(p.rawMarkdown ?? "");
      setAdvanced(serializeAdvanced(p));
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
      setProfile(extracted);
      setAdvanced(serializeAdvanced(extracted));
      await saveProfile(extracted);
      flash("Profile extracted ✓ Review the fields below.");
    } catch (e) {
      flash(e instanceof Error ? e.message : "Extraction failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onSaveProfile() {
    let merged = { ...profile, rawMarkdown: markdown };
    try {
      merged = { ...merged, ...deserializeAdvanced(advanced) };
    } catch {
      return flash("Advanced JSON is invalid — fix it before saving.");
    }
    setProfile(merged);
    await saveProfile(merged);
    flash("Profile saved ✓");
  }

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

  function setContact(k: keyof CandidateProfile["contact"], v: string) {
    setProfile((p) => ({ ...p, contact: { ...p.contact, [k]: v } }));
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

      <Section title="2 · Profile">
        <div style={grid}>
          <Field label="First name" value={profile.contact.firstName} onChange={(v) => setContact("firstName", v)} />
          <Field label="Last name" value={profile.contact.lastName} onChange={(v) => setContact("lastName", v)} />
          <Field label="Email" value={profile.contact.email} onChange={(v) => setContact("email", v)} />
          <Field label="Phone" value={profile.contact.phone} onChange={(v) => setContact("phone", v)} />
          <Field label="City" value={profile.contact.city} onChange={(v) => setContact("city", v)} />
          <Field label="Country" value={profile.contact.country} onChange={(v) => setContact("country", v)} />
        </div>
        <label style={{ ...label, marginTop: 14 }}>
          Advanced (links, work history, education, eligibility) — JSON
        </label>
        <textarea
          value={advanced}
          onChange={(e) => setAdvanced(e.target.value)}
          rows={10}
          style={{ ...textarea, fontFamily: "ui-monospace, monospace", fontSize: 12 }}
        />
        <button style={{ ...primaryBtn, marginTop: 10 }} onClick={onSaveProfile}>
          Save profile
        </button>
      </Section>

      <Section title="3 · LLM (OpenAI-compatible)">
        <p style={{ fontSize: 12, color: "#6b7280", marginTop: 0 }}>
          Stored locally in your browser and used only from the extension's
          background worker. With LLM features off, deterministic + learned
          autofill still works and nothing leaves your device.
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
        <div style={{ marginTop: 10 }}>
          <Toggle label="LLM field mapping (ambiguous fields)" checked={settings.llmFieldMappingEnabled} onChange={(v) => patchSettings({ llmFieldMappingEnabled: v })} />
          <Toggle label="Cover letter generation" checked={settings.coverLetterEnabled} onChange={(v) => patchSettings({ coverLetterEnabled: v })} />
          <Toggle label="Screening-question answers" checked={settings.screeningAnswersEnabled} onChange={(v) => patchSettings({ screeningAnswersEnabled: v })} />
          <Toggle label="Field-value tailoring" checked={settings.fieldTailoringEnabled} onChange={(v) => patchSettings({ fieldTailoringEnabled: v })} />
        </div>
      </Section>

      <Section title="4 · Fill behavior">
        <Toggle label="Auto-fill forms on page load" checked={settings.autofillOnLoad} onChange={(v) => patchSettings({ autofillOnLoad: v })} />
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
    </div>
  );
}

// --- profile serialization for the "advanced" JSON box ---
function serializeAdvanced(p: CandidateProfile): string {
  return JSON.stringify(
    {
      headline: p.headline,
      summary: p.summary,
      yearsOfExperience: p.yearsOfExperience,
      currentCompany: p.currentCompany,
      currentTitle: p.currentTitle,
      skills: p.skills,
      links: p.links,
      workExperience: p.workExperience,
      education: p.education,
      eligibility: p.eligibility,
    },
    null,
    2
  );
}

function deserializeAdvanced(s: string): Partial<CandidateProfile> {
  const o = JSON.parse(s);
  return {
    headline: o.headline,
    summary: o.summary,
    yearsOfExperience: o.yearsOfExperience,
    currentCompany: o.currentCompany,
    currentTitle: o.currentTitle,
    skills: o.skills ?? [],
    links: o.links ?? {},
    workExperience: o.workExperience ?? [],
    education: o.education ?? [],
    eligibility: o.eligibility ?? {},
  };
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
