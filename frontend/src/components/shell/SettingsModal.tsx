"use client";

import { useEffect, useRef, useState } from "react";
import { X, ExternalLink, Save, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { fetchSettings, saveSettings, type AppSettings } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

type FormState = {
  OPENAI_BASE_URL: string;
  OPENAI_MODEL: string;
  APIFY_API_TOKEN: string;
  OPENAI_API_KEYS: string; // newline-separated in the textarea
};

const EMPTY: FormState = {
  OPENAI_BASE_URL: "",
  OPENAI_MODEL: "",
  APIFY_API_TOKEN: "",
  OPENAI_API_KEYS: "",
};

export function SettingsModal({ isOpen, onClose }: Props) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const backdropRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setForbidden(false);
    setLoading(true);
    fetchSettings()
      .then((s: AppSettings) => {
        setForm({
          OPENAI_BASE_URL: s.OPENAI_BASE_URL ?? "",
          OPENAI_MODEL: s.OPENAI_MODEL ?? "",
          APIFY_API_TOKEN: s.APIFY_API_TOKEN ?? "",
          OPENAI_API_KEYS: (s.OPENAI_API_KEYS ?? []).join("\n"),
        });
      })
      .catch((e: Error) => {
        if (e.message.includes("403")) {
          setForbidden(true);
        } else {
          toast.error(`Failed to load settings: ${e.message}`);
          onClose();
        }
      })
      .finally(() => setLoading(false));
  }, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const keys = form.OPENAI_API_KEYS
        .split("\n")
        .map((k) => k.trim())
        .filter(Boolean);
      await saveSettings({
        OPENAI_BASE_URL: form.OPENAI_BASE_URL,
        OPENAI_MODEL: form.OPENAI_MODEL,
        APIFY_API_TOKEN: form.APIFY_API_TOKEN,
        OPENAI_API_KEYS: keys,
      });
      toast.success("Settings saved");
      onClose();
    } catch (e: unknown) {
      toast.error(`Save failed: ${e instanceof Error ? e.message : "error"}`);
    } finally {
      setSaving(false);
    }
  };

  const set = (key: keyof FormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  if (!isOpen) return null;

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === backdropRef.current) onClose(); }}
    >
      <div className="bg-base-surface border border-border rounded-xl shadow-xl w-full max-w-md mx-4 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="font-display font-bold text-base text-ink-primary">API Settings</h2>
          <button onClick={onClose} className="p-1 text-ink-muted hover:text-ink-primary rounded transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-5 space-y-4 overflow-y-auto max-h-[70vh]">
          {loading && (
            <div className="flex items-center justify-center py-8 text-ink-muted">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              <span className="text-sm">Loading…</span>
            </div>
          )}

          {forbidden && !loading && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              Admin access required. Log into{" "}
              <a href="/admin/" target="_blank" rel="noopener noreferrer" className="underline">
                Django Admin
              </a>{" "}
              first, then reopen this dialog.
            </div>
          )}

          {!loading && !forbidden && (
            <>
              <Field label="OpenAI Base URL" hint="Leave as default for OpenAI; change for local/proxy models">
                <input
                  type="text"
                  value={form.OPENAI_BASE_URL}
                  onChange={set("OPENAI_BASE_URL")}
                  placeholder="https://api.openai.com/v1"
                  className={inputCls}
                />
              </Field>

              <Field label="OpenAI Model">
                <input
                  type="text"
                  value={form.OPENAI_MODEL}
                  onChange={set("OPENAI_MODEL")}
                  placeholder="gpt-4o-mini"
                  className={inputCls}
                />
              </Field>

              <Field label="Apify API Token">
                <input
                  type="password"
                  value={form.APIFY_API_TOKEN}
                  onChange={set("APIFY_API_TOKEN")}
                  placeholder="apify_api_…"
                  className={inputCls}
                  autoComplete="off"
                />
              </Field>

              <Field label="OpenAI API Keys" hint="One key per line — rotated round-robin">
                <textarea
                  value={form.OPENAI_API_KEYS}
                  onChange={set("OPENAI_API_KEYS")}
                  placeholder={"sk-…\nsk-…"}
                  rows={3}
                  className={cn(inputCls, "resize-none font-mono text-xs")}
                />
              </Field>
            </>
          )}
        </div>

        {/* Footer */}
        {!loading && (
          <div className="px-5 py-4 border-t border-border flex items-center justify-between gap-3">
            <a
              href="/admin/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink-primary transition-colors"
            >
              Django Admin <ExternalLink className="w-3 h-3" />
            </a>
            <div className="flex items-center gap-2">
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded-md text-sm text-ink-muted hover:text-ink-primary border border-border hover:border-border-hover transition-colors"
              >
                Cancel
              </button>
              {!forbidden && (
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm bg-brand text-white hover:bg-brand/90 transition-colors disabled:opacity-50"
                >
                  {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                  Save
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const inputCls =
  "w-full bg-base-card border border-border rounded-md px-3 py-1.5 text-sm text-ink-primary placeholder:text-ink-muted focus:border-brand outline-none transition-colors";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="text-[0.7rem] font-bold text-ink-muted uppercase tracking-widest">{label}</label>
      {children}
      {hint && <p className="text-[0.65rem] text-ink-muted">{hint}</p>}
    </div>
  );
}
