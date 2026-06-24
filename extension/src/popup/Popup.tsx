import { useEffect, useState } from "react";
import type { Message, MessageResponse, JobContext } from "@/shared/messages";
import {
  getSettings,
  saveSettings,
  autofillEnabledForDomain,
  type Settings,
} from "@/storage/settings";
import { getProfile } from "@/storage/profile";
import {
  buildCoverLetterMessages,
  buildTailoredResumeMessages,
  buildConnectNoteMessages,
  buildOutreachMessages,
  buildColdEmailMessages,
} from "@/llm/prompts";
import { pickBestEmail, parseSubjectBody } from "@/content/emails";
import {
  getTemplates,
  renderTemplate,
  type OutreachTemplate,
} from "@/storage/templates";
import { messagesToPrompt } from "@/llm/promptText";
import { getProvider } from "@/llm/webchat/providers";
import { matchResumeToJob } from "@/llm/resumeMatch";
import { profileToResumeHtml } from "@/profile/resumeHtml";
import {
  addContact,
  getContacts,
  dueContacts,
  markContacted,
  type Contact,
} from "@/storage/contacts";

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
  const [angle, setAngle] = useState("generic");
  const [templates, setTemplates] = useState<OutreachTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [due, setDue] = useState<Contact[]>([]);

  useEffect(() => {
    void (async () => {
      const s = await getSettings();
      setSettings(s);
      const tpls = await getTemplates();
      setTemplates(tpls);
      setTemplateId(tpls[0]?.id ?? "");
      setDue(dueContacts(await getContacts(), s.followUpCadenceDays));
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

  async function refreshDue() {
    if (!settings) return;
    setDue(dueContacts(await getContacts(), settings.followUpCadenceDays));
  }

  async function followUp(contact: Contact) {
    setBusy(true);
    try {
      const profile = await getProfile();
      const tpl =
        templates.find((t) => t.id === "recruiter_followup") ?? templates[0];
      const myName =
        profile.contact.fullName ||
        [profile.contact.firstName, profile.contact.lastName].filter(Boolean).join(" ");
      const text = tpl
        ? renderTemplate(tpl.body, {
            name: contact.name,
            firstName: contact.name?.split(" ")[0],
            company: contact.company,
            role: contact.role,
            myName,
            myTitle: profile.headline || profile.currentTitle,
          })
        : `Hi ${contact.name ?? ""}, following up — thanks!`;
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        /* ignore */
      }
      await markContacted(contact.id);
      await refreshDue();
      setNote(`Follow-up for ${contact.name ?? "contact"} copied ✓`);
    } finally {
      setBusy(false);
    }
  }

  async function snooze(contact: Contact) {
    setBusy(true);
    try {
      await markContacted(contact.id);
      await refreshDue();
      setNote(`${contact.name ?? "Contact"} snoozed ✓`);
    } catch {
      setNote("Couldn't update this contact — try again.");
    } finally {
      setBusy(false);
    }
  }

  async function draftColdEmail() {
    const tab = await activeTab();
    if (!tab?.id) return;
    setBusy(true);
    setNote("");
    try {
      const profile = await getProfile();
      const job = await getJobContext();
      let emails: string[] = [];
      try {
        const e = await sendToTab(tab.id, { type: "GET_PAGE_EMAILS" });
        if (e.ok && "emails" in e) emails = e.emails;
      } catch {
        /* no content script here */
      }
      const to = pickBestEmail(emails);

      if (settings?.llmMode === "webchat") {
        const prompt = messagesToPrompt(buildColdEmailMessages(profile, job));
        try {
          await navigator.clipboard.writeText(prompt);
        } catch {
          /* ignore */
        }
        const provider = getProvider(settings.webchatProvider);
        await chrome.runtime.sendMessage({
          type: "WEBCHAT_HANDOFF",
          providerId: settings.webchatProvider,
          prompt,
        } satisfies Message);
        setNote(
          `Opened ${provider?.label ?? "your LLM"} to draft the email${to ? ` (to ${to})` : ""}.`
        );
        return;
      }
      if (settings?.llmMode === "off" || !settings) {
        setNote(
          to ? `Found ${to}. Enable an LLM to draft the email.` : "No contact email found on this page."
        );
        return;
      }

      const resp = (await chrome.runtime.sendMessage({
        type: "LLM_COLD_EMAIL",
        profile,
        job,
      } satisfies Message)) as MessageResponse;
      if (resp.ok && "text" in resp) {
        const { subject, body } = parseSubjectBody(resp.text);
        try {
          await navigator.clipboard.writeText(resp.text);
        } catch {
          /* ignore */
        }
        if (to) {
          const url = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
          await chrome.tabs.create({ url });
          setNote(`Email drafted to ${to} (also copied). Attach your resume before sending.`);
        } else {
          setNote("Email drafted & copied — no address found, paste it into your mail client.");
        }
      } else if (!resp.ok) {
        setNote(resp.error);
      }
    } catch {
      setNote("Cold-email draft failed.");
    } finally {
      setBusy(false);
    }
  }

  async function draftOutreach() {
    const tab = await activeTab();
    setBusy(true);
    setNote("");
    try {
      const profile = await getProfile();
      let contact: { name?: string; role?: string; company?: string } = {};
      if (tab?.id != null) {
        try {
          const ci = await sendToTab(tab.id, { type: "GET_CONTACT_INFO" });
          if (ci.ok && "contact" in ci) contact = ci.contact;
        } catch {
          /* not a profile page; placeholders may be blank */
        }
      }
      const job = await getJobContext();
      const tpl = templates.find((t) => t.id === templateId) ?? templates[0];
      if (!tpl) return setNote("No outreach templates configured.");
      const myName =
        profile.contact.fullName ||
        [profile.contact.firstName, profile.contact.lastName].filter(Boolean).join(" ");
      const draft = renderTemplate(tpl.body, {
        name: contact.name,
        firstName: contact.name?.split(" ")[0],
        company: contact.company || job.company,
        role: contact.role || job.title,
        myName,
        myTitle: profile.headline || profile.currentTitle,
      });

      if (settings?.llmMode === "webchat") {
        const prompt = messagesToPrompt(buildOutreachMessages(profile, contact, draft, job));
        try {
          await navigator.clipboard.writeText(prompt);
        } catch {
          /* ignore */
        }
        const provider = getProvider(settings.webchatProvider);
        await chrome.runtime.sendMessage({
          type: "WEBCHAT_HANDOFF",
          providerId: settings.webchatProvider,
          prompt,
        } satisfies Message);
        setNote(`Opened ${provider?.label ?? "your LLM"} to draft the outreach.`);
        return;
      }

      let text = draft;
      if (settings?.llmMode === "direct" && settings.openaiApiKey) {
        const resp = (await chrome.runtime.sendMessage({
          type: "LLM_OUTREACH",
          profile,
          contact,
          draft,
          job,
        } satisfies Message)) as MessageResponse;
        if (resp.ok && "text" in resp) text = resp.text;
        else if (!resp.ok) setNote(resp.error);
      }
      try {
        await navigator.clipboard.writeText(text);
        setNote(`Outreach copied to clipboard ✓ (${tpl.name})`);
      } catch {
        setNote("Generated, but clipboard was blocked.");
      }
    } catch {
      setNote("Outreach failed.");
    } finally {
      setBusy(false);
    }
  }

  async function draftConnectNote() {
    const tab = await activeTab();
    if (!tab?.id) return;
    setBusy(true);
    setNote("");
    try {
      const profile = await getProfile();
      const ci = await sendToTab(tab.id, { type: "GET_CONTACT_INFO" });
      const contact = ci.ok && "contact" in ci ? ci.contact : {};

      if (settings?.llmMode === "webchat") {
        const prompt = messagesToPrompt(
          buildConnectNoteMessages(profile, contact, angle as never)
        );
        try {
          await navigator.clipboard.writeText(prompt);
        } catch {
          /* auto-inject still works */
        }
        const provider = getProvider(settings.webchatProvider);
        await chrome.runtime.sendMessage({
          type: "WEBCHAT_HANDOFF",
          providerId: settings.webchatProvider,
          prompt,
        } satisfies Message);
        setNote(`Opened ${provider?.label ?? "your LLM"} to draft the note.`);
        return;
      }
      if (settings?.llmMode === "off" || !settings) {
        setNote("Enable an LLM (settings) to draft a connection note.");
        return;
      }

      const resp = (await chrome.runtime.sendMessage({
        type: "LLM_CONNECT_NOTE",
        profile,
        contact,
        angle,
      } satisfies Message)) as MessageResponse;
      if (resp.ok && "text" in resp) {
        try {
          await navigator.clipboard.writeText(resp.text);
        } catch {
          /* ignore */
        }
        await sendToTab(tab.id, { type: "FILL_CONNECT_NOTE", text: resp.text });
        setNote(`Note ready (${resp.text.length}/300) — filled if the connect box is open, also copied.`);
      } else if (!resp.ok) {
        setNote(resp.error);
      }
    } catch {
      setNote("Open a LinkedIn profile to draft a connection note.");
    } finally {
      setBusy(false);
    }
  }

  async function saveContact() {
    const tab = await activeTab();
    if (!tab?.id) return;
    setBusy(true);
    setNote("");
    try {
      const resp = await sendToTab(tab.id, { type: "GET_CONTACT_INFO" });
      if (resp.ok && "contact" in resp) {
        const c = await addContact(resp.contact);
        setNote(`Saved ${c.name || "contact"}${c.company ? ` · ${c.company}` : ""} ✓`);
      }
    } catch {
      setNote("Couldn't read this page. Open a LinkedIn/company page.");
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

      {due.length > 0 && (
        <div
          style={{
            marginTop: 10,
            padding: 8,
            background: "#fffbeb",
            border: "1px solid #fde68a",
            borderRadius: 8,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 4 }}>
            Follow-ups due ({due.length})
          </div>
          {due.slice(0, 4).map((c) => (
            <div
              key={c.id}
              style={{ display: "flex", gap: 6, alignItems: "center", padding: "2px 0", fontSize: 12 }}
            >
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {c.name || "(contact)"}
                {c.company ? ` · ${c.company}` : ""}
              </span>
              <button onClick={() => followUp(c)} disabled={busy} style={miniBtn}>
                draft
              </button>
              <button onClick={() => snooze(c)} disabled={busy} style={miniBtnGhost}>
                done
              </button>
            </div>
          ))}
        </div>
      )}

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
        <button onClick={saveContact} disabled={busy} style={btn}>
          Save this contact (networking)
        </button>
        <div style={{ display: "flex", gap: 6 }}>
          <select
            value={angle}
            onChange={(e) => setAngle(e.target.value)}
            style={{ ...btn, flex: "0 0 auto" }}
            title="Connection angle"
          >
            <option value="generic">Generic</option>
            <option value="alum">Alum</option>
            <option value="same_stack">Same stack</option>
            <option value="hiring_manager">Hiring mgr</option>
            <option value="mutual_interest">Shared interest</option>
            <option value="referral">Referral</option>
          </select>
          <button onClick={draftConnectNote} disabled={busy} style={{ ...btn, flex: 1 }}>
            Draft LinkedIn connect note
          </button>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <select
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            style={{ ...btn, flex: "0 0 auto" }}
            title="Outreach template"
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <button onClick={draftOutreach} disabled={busy} style={{ ...btn, flex: 1 }}>
            Draft outreach → clipboard
          </button>
        </div>
        <button onClick={draftColdEmail} disabled={busy} style={btn}>
          Draft cold email (no-ATS page)
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
const miniBtn: React.CSSProperties = {
  padding: "3px 8px",
  borderRadius: 6,
  border: "none",
  background: "#2563eb",
  color: "#fff",
  cursor: "pointer",
  fontSize: 11,
  fontWeight: 600,
};
const miniBtnGhost: React.CSSProperties = {
  ...miniBtn,
  background: "#e5e7eb",
  color: "#374151",
};
const toggleRow: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  fontSize: 12,
};
