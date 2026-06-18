"use client";

import { useEffect, useRef, useState } from "react";
import { X, ExternalLink, Globe, DollarSign, Star, Briefcase, Bot, Pencil } from "lucide-react";
import { cn, TIER_COLORS, ALL_TIERS, formatYen } from "@/lib/utils";
import { TierBadge } from "@/components/ui/TierBadge";
import { useRankingMutation } from "@/hooks/useRankingMutation";
import type { BrowseItem, Tier } from "@/lib/types";

interface Props {
  item: BrowseItem | null;
  onClose: () => void;
}

export function JobSheet({ item, onClose }: Props) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const { mutate: patchRanking, isPending } = useRankingMutation();
  const [editTier, setEditTier] = useState<Tier | null>(null);
  const [editRank, setEditRank] = useState<string>("");

  // Sync edit state when item changes
  useEffect(() => {
    if (item) {
      setEditTier(item.match_tier);
      setEditRank(String(item.rank || 0));
    }
  }, [item]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!item) return null;

  const { job } = item;
  const tier = editTier || item.match_tier;
  const tc = TIER_COLORS[tier];

  const handleSaveRanking = () => {
    patchRanking({
      rankingId: item.id,
      data: {
        match_tier: editTier || item.match_tier,
        rank: parseInt(editRank, 10) || 0,
      },
    });
  };

  const jlptLabel = job.jlpt_level
    ? { 1: "N1", 2: "N2", 3: "N3", 4: "N4", 5: "N5" }[job.jlpt_level] ?? `N${job.jlpt_level}`
    : null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-base/80 backdrop-blur-sm z-40"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div
        ref={sheetRef}
        className="fixed right-0 top-0 h-full w-full max-w-[600px] bg-base-surface border-l border-border shadow-lg z-50 flex flex-col"
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className={cn("border-l-4 px-5 py-4 border-b border-border", tc.border.replace("border-", "border-l-").replace("/40",""))}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink-secondary mb-1 truncate">{job.company}</p>
              <h2 className="font-display font-bold text-ink-primary text-xl leading-snug">
                {job.title}
              </h2>
            </div>
            <button
              onClick={onClose}
              className="shrink-0 text-ink-muted hover:text-ink-primary transition-colors p-1 rounded"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Quick chips */}
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <TierBadge tier={tier} />
            {item.rank > 0 && (
              <span className="text-xs bg-base border border-border text-ink-muted px-2 py-0.5 rounded-full">
                #{item.rank}
              </span>
            )}
            <span className="text-xs bg-base border border-border text-ink-muted px-2 py-0.5 rounded capitalize">
              {job.source}
            </span>
            {job.language && (
              <span className="text-xs bg-base border border-border text-ink-muted px-2 py-0.5 rounded">
                {job.language}
              </span>
            )}
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

          {/* AI Match summary */}
          <div className={cn("rounded-md p-4 border", tc.bg, tc.border)}>
            <div className="flex items-center gap-2 mb-2">
              <Bot className="w-4 h-4 text-brand" />
              <span className="text-xs font-semibold text-brand uppercase tracking-wide">
                AI Match Analysis
              </span>
              {item.llm_tier && item.llm_tier !== item.match_tier && (
                <span className="text-xs text-ink-muted ml-auto">
                  LLM: {item.llm_tier} → overridden to {item.match_tier}
                </span>
              )}
            </div>
            <p className="text-sm text-ink-secondary leading-relaxed italic">
              {item.jd_summary || "No AI summary available."}
            </p>
          </div>

          {/* Meta grid */}
          <div className="grid grid-cols-2 gap-3">
            {(job.salary_yen || job.salary) && (
              <MetaBox icon={<DollarSign className="w-3.5 h-3.5" />} label="Salary">
                {job.salary_yen ? formatYen(job.salary_yen) : job.salary}
              </MetaBox>
            )}
            {job.experience_required && (
              <MetaBox icon={<Star className="w-3.5 h-3.5" />} label="Experience">
                {job.experience_required}
              </MetaBox>
            )}
            {job.language && (
              <MetaBox icon={<Globe className="w-3.5 h-3.5" />} label="Language">
                {job.language}
                {jlptLabel && <span className="ml-1 text-ink-muted">(req. {jlptLabel})</span>}
              </MetaBox>
            )}
            <MetaBox icon={<Briefcase className="w-3.5 h-3.5" />} label="Source">
              {job.source}
            </MetaBox>
          </div>

          {/* Tech stack */}
          {job.tech_stack && job.tech_stack.length > 0 && (
            <div>
              <SectionTitle>Tech Stack</SectionTitle>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {job.tech_stack.map((t) => (
                  <span
                    key={t}
                    className="text-xs bg-base border border-border text-ink-secondary px-2 py-0.5 rounded"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Edit ranking */}
          <div className="rounded-md border border-brand/20 bg-brand/5 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Pencil className="w-4 h-4 text-brand" />
              <span className="text-xs font-semibold text-brand uppercase tracking-wide">
                Adjust Ranking
              </span>
            </div>
            <div>
              <label className="text-xs text-ink-muted mb-1.5 block">Tier</label>
              <div className="flex gap-1.5">
                {ALL_TIERS.map((t) => {
                  const c = TIER_COLORS[t];
                  return (
                    <button
                      key={t}
                      onClick={() => setEditTier(t)}
                      className={cn(
                        "flex-1 py-1.5 text-sm font-bold font-display rounded border transition-all",
                        editTier === t
                          ? `${c.bg} ${c.text} ${c.border} scale-105`
                          : "bg-base border-border text-ink-muted hover:border-border-hover"
                      )}
                    >
                      {t}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="flex gap-3 items-end">
              <div className="flex-1">
                <label className="text-xs text-ink-muted mb-1.5 block">Numerical Rank</label>
                <input
                  type="number"
                  min={0}
                  value={editRank}
                  onChange={(e) => setEditRank(e.target.value)}
                  className="w-full bg-base border border-border rounded px-3 py-1.5 text-sm text-ink-primary focus:border-brand outline-none transition-colors"
                />
              </div>
              <button
                onClick={handleSaveRanking}
                disabled={isPending}
                className="px-4 py-1.5 text-sm font-semibold bg-brand text-base rounded hover:brightness-110 transition disabled:opacity-50"
              >
                {isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </div>

          {/* Description */}
          {(job.description) && (
            <div>
              <SectionTitle>Job Description</SectionTitle>
              <pre className="mt-2 text-xs text-ink-secondary leading-relaxed whitespace-pre-wrap bg-base border border-border rounded p-3 max-h-80 overflow-y-auto">
                {job.description}
              </pre>
            </div>
          )}
        </div>

        {/* Footer CTA */}
        <div className="px-5 py-3 border-t border-border bg-base-surface">
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full py-2.5 font-semibold text-base rounded bg-brand text-base-DEFAULT hover:brightness-110 transition text-sm"
          >
            Apply on {job.source} <ExternalLink className="w-4 h-4" />
          </a>
        </div>
      </div>
    </>
  );
}

function MetaBox({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-base border border-border rounded p-3">
      <div className="flex items-center gap-1.5 text-[0.65rem] text-ink-muted uppercase tracking-wide mb-1">
        <span className="text-brand/70">{icon}</span>
        {label}
      </div>
      <div className="text-sm font-semibold text-ink-primary">{children}</div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-xs font-bold text-brand uppercase tracking-widest flex items-center gap-2">
      {children}
    </h4>
  );
}
