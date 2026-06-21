import { useEffect, useState } from "react";
import type { Message, MessageResponse, JobContext } from "@/shared/messages";
import {
  getSettings,
  saveSettings,
  autofillEnabledForDomain,
  type Settings,
} from "@/storage/settings";
import { getProfile } from "@/storage/profile";
import { buildCoverLetterMessages, buildTailoredResumeMessages } from "@/llm/prompts";
import { messagesToPrompt } from "@/llm/promptText";
import { getProvider } from "@/llm/webchat/providers";
import { matchResumeToJob } from "@/llm/resumeMatch";
import { profileToResumeHtml } from "@/profile/resumeHtml";

type Status = {
  platform: string;
  fieldCount: number;
  filledCount: number;
  autofillEnabled: boolean;
};

async function activeTab(): Promise<chrome.tabs.Tab | undefined> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function domainOf(url?: string): string {
  try {
    return url ? new URL(url).hostname : "";
  } catch {
    return "";
  }
}

async function sendToTab(tabId: number, msg: Message): Promise<MessageResponse> {
  return chrome.tabs.sendMessage(tabId, msg);
}

export function Popup() {
  const [status, setStatus] = useState<Status | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [domain, setDomain] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    void (async () => {
      const s = await getSettings();
      setSettings(s);
      const tab = await activeTab();
      setDomain(domainOf(tab?.url));
      if (tab?.id) {
        try {
          const resp = await sendToTab(tab.id, { type: "GET_STATUS" });
          if (resp.ok && "status" in resp) setStatus(resp.status);
        } catch {
          setNote("Open a job application page to use AppFill.");
        }
      }
    })();
  }, []);

  async function fillNow() {
    const tab = await activeTab();
    if (!tab?.id) return;
    setBusy(true);
    setNote("");
    try {
      await sendToTab(tab.id, { type: "FILL_NOW" });
      const resp = await sendToTab(tab.id, { type: "GET_STATUS" });
      if (resp.ok && "status" in resp) setStatus(resp.status);
    } catch {
      setNote("Couldn't reach this page. Reload and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function checkBeforeSubmit() {
    const tab = await activeTab();
    if (!tab?.id) return;
    setBusy(true);
    setNote("");
    try {
      const resp = await sendToTab(tab.id, { type: "VALIDATE_FORM" });
      if (resp.ok && "status" in resp) {
        const blocking = resp.status.filledCount;
        setNote(
          blocking > 0
            ? `${blocking} blocking issue(s) — see the checklist on the page.`
            : "Checklist shown on the page."
        );
        window.close();
      }
    } catch {
      setNote("Couldn't reach this page. Reload and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function fillWorkHistory() {
    const tab = await activeTab();
    if (!tab?.id) return;
    setBusy(true);
    setNote("");
    try {
      const resp = await sendToTab(tab.id, { type: "FILL_WORK_HISTORY" });
      if (resp.ok && "status" in resp) {
        setStatus(resp.status);
        setNote(`Filled ${resp.status.filledCount} work-history fields.`);
      }
    } catch {
      setNote("Couldn't reach this page. Reload and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function startGuidedFlow() {
    const tab = await activeTab();
    if (!tab?.id) return;
    try {
      await sendToTab(tab.id, { type: "FLOW_START" });
      window.close(); // get out of the way; the on-page bar drives the flow
    } catch {
      setNote("Couldn't start on this page. Reload and try again.");
    }
  }

  async function toggleSite() {
    if (!settings) return;
    const enabled = autofillEnabledForDomain(settings, domain);
    const next = await saveSettings({
      siteOverrides: { ...settings.siteOverrides, [domain]: !enabled },
    });
    setSettings(next);
  }

  async function getJobContext(): Promise<JobContext> {
    const tab = await activeTab();
    let job: JobContext = { url: tab?.url, title: tab?.title };
    if (tab?.id != null) {
      try {
        const jc = await sendToTab(tab.id, { type: "GET_JOB_CONTEXT" });
        if (jc.ok && "job" in jc) job = jc.job;
      } catch {
        /* not a content-script page; fall back to title/url */
      }
    }
    return job;
  }

  async function tailorResume() {
    setBusy(true);
    setNote("");
    try {
      const profile = await getProfile();
      const job = await getJobContext();
      const jobText = [job.title, job.company, job.description]
        .filter(Boolean)
        .join("\n");
      const m = matchResumeToJob(profile, jobText);
      const scoreLine = `Match ${m.score}/100 · ${m.matchedSkills.length ? m.matchedSkills.slice(0, 6).join(", ") : "no skill keywords found"}`;

      if (settings?.llmMode === "webchat") {
        const prompt = messagesToPrompt(buildTailoredResumeMessages(profile, job));
        try {
          await navigator.clipboard.writeText(prompt);
        } catch {
          /* auto-inject still works */
        }
        const provider = getProvider(settings.webchatProvider);
        const resp = (await chrome.runtime.sendMessage({
          type: "WEBCHAT_HANDOFF",
          providerId: settings.webchatProvider,
          prompt,
        } satisfies Message)) as MessageResponse;
        setNote(
          resp.ok
            ? `${scoreLine}. Opened ${provider?.label ?? "your LLM"} to draft a tailored resume.`
            : resp.error
        );
        return;
      }

      if (settings?.llmMode === "off" || !settings) {
        setNote(`${scoreLine}. (Enable an LLM in settings to generate a tailored resume.)`);
        return;
      }

      const resp = (await chrome.runtime.sendMessage({
        type: "LLM_TAILOR_RESUME",
        profile,
        job,
      } satisfies Message)) as MessageResponse;
      if (resp.ok && "profile" in resp) {
        const html = profileToResumeHtml(resp.profile);
        const w = window.open("", "_blank");
        if (w) {
          w.document.write(html);
          w.document.close();
          setTimeout(() => w.print(), 350);
        }
        setNote(`${scoreLine}. Tailored resume opened — print/save as PDF.`);
      } else if (!resp.ok) {
        setNote(resp.error);
      }
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Tailoring failed.");
    } finally {
      setBusy(false);
    }
  }

  async function generateCoverLetter() {
    setBusy(true);
    setNote("");
    try {
      const profile = await getProfile();
      const job = await getJobContext();

      if (settings?.llmMode === "webchat") {
        const prompt = messagesToPrompt(buildCoverLetterMessages(profile, job));
        try {
          await navigator.clipboard.writeText(prompt);
        } catch {
          /* fall through; auto-inject still works */
        }
        const provider = getProvider(settings.webchatProvider);
        const resp = (await chrome.runtime.sendMessage({
          type: "WEBCHAT_HANDOFF",
          providerId: settings.webchatProvider,
          prompt,
        } satisfies Message)) as MessageResponse;
        if (resp.ok) {
          setNote(
            `Opened ${provider?.label ?? "your LLM"} with the prompt — copy the answer back.`
          );
        } else {
          setNote(resp.error);
        }
        return;
      }

      const resp = (await chrome.runtime.sendMessage({
        type: "LLM_GENERATE",
        kind: "cover_letter",
        profile,
        job,
      } satisfies Message)) as MessageResponse;
      if (resp.ok && "text" in resp) {
        await navigator.clipboard.writeText(resp.text);
        setNote("Cover letter copied to clipboard ✓");
      } else if (!resp.ok) {
        setNote(resp.error);
      }
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      setBusy(false);
    }
  }

  const siteEnabled = settings ? autofillEnabledForDomain(settings, domain) : true;

  return (
    <div style={{ padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: 15 }}>AppFill</strong>
        <span style={{ marginLeft: "auto", color: "#6b7280" }}>{domain}</span>
      </div>

      <div
        style={{
          marginTop: 10,
          padding: 10,
          background: "#f9fafb",
          borderRadius: 8,
          fontSize: 12,
        }}
      >
        {status ? (
          <>
            <div>Platform: <b>{status.platform}</b></div>
            <div>
              Fields detected: <b>{status.fieldCount}</b> · filled:{" "}
              <b>{status.filledCount}</b>
            </div>
          </>
        ) : (
          <div style={{ color: "#6b7280" }}>{note || "Scanning page…"}</div>
        )}
      </div>

      <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
        <button onClick={fillNow} disabled={busy} style={primaryBtn}>
          {busy ? "Working…" : "Fill this form"}
        </button>
        <button onClick={startGuidedFlow} disabled={busy} style={btn}>
          Guided multi-page fill →
        </button>
        <button onClick={fillWorkHistory} disabled={busy} style={btn}>
          Fill work history & education
        </button>
        <button onClick={checkBeforeSubmit} disabled={busy} style={btn}>
          Check before submitting
        </button>
        <button onClick={generateCoverLetter} disabled={busy} style={btn}>
          Generate cover letter → clipboard
        </button>
        <button onClick={tailorResume} disabled={busy} style={btn}>
          Tailor resume for this job
        </button>
        <label style={toggleRow}>
          <input type="checkbox" checked={siteEnabled} onChange={toggleSite} />
          Auto-fill on this site
        </label>
      </div>

      {note && status && (
        <div style={{ marginTop: 10, fontSize: 12, color: "#374151" }}>{note}</div>
      )}

      <button
        onClick={() => chrome.runtime.openOptionsPage()}
        style={{ ...linkBtn, marginTop: 12 }}
      >
        Edit profile & settings →
      </button>
    </div>
  );
}

const btn: React.CSSProperties = {
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid #d1d5db",
  background: "#fff",
  cursor: "pointer",
  fontSize: 13,
};
const primaryBtn: React.CSSProperties = {
  ...btn,
  background: "#2563eb",
  color: "#fff",
  border: "1px solid #2563eb",
  fontWeight: 600,
};
const linkBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#2563eb",
  cursor: "pointer",
  padding: 0,
  fontSize: 12,
};
const toggleRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 12,
};
