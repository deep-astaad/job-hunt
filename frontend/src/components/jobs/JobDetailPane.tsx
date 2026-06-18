"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Globe, DollarSign, Star, Briefcase, Bot, Pencil, ArrowLeft, MapPin } from "lucide-react";
import { cn, TIER_COLORS, ALL_TIERS, TIER_DOT_HEX, formatYen } from "@/lib/utils";
import { TierBadge } from "@/components/ui/TierBadge";
import { useRankingMutation } from "@/hooks/useRankingMutation";
import type { BrowseItem, Tier } from "@/lib/types";

interface Props {
  item: BrowseItem | null;
  onBack?: () => void; // mobile: go back to list
}

export function JobDetailPane({ item, onBack }: Props) {
  const { mutate: patchRanking, isPending } = useRankingMutation();
  const [editTier, setEditTier] = useState<Tier | null>(null);
  const [editRank, setEditRank] = useState<string>("");

  useEffect(() => {
    if (item) {
      setEditTier(item.match_tier);
      setEditRank(String(item.rank || 0));
    }
  }, [item?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!item) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-ink-muted gap-3 select-none">
        <div className="w-12 h-12 rounded-xl bg-base-surface border border-border flex items-center justify-center">
          <Briefcase className="w-5 h-5 text-ink-muted" />
        </div>
        <p className="text-sm font-medium text-ink-secondary">Select a job to view details</p>
        <p className="text-xs text-ink-muted">Click any row in the list</p>
      </div>
    );
  }

  const { job } = item;
  const tier = editTier || item.match_tier;
  const tc = TIER_COLORS[tier];

  const jlptLabel = job.jlpt_level
    ? { 1: "N1", 2: "N2", 3: "N3", 4: "N4", 5: "N5" }[job.jlpt_level] ?? `N${job.jlpt_level}`
    : null;

  const isDowngraded = item.llm_tier && item.llm_tier !== item.match_tier;

  const handleSaveRanking = () => {
    patchRanking({
      rankingId: item.id,
      data: {
        match_tier: editTier || item.match_tier,
        rank: parseInt(editRank, 10) || 0,
      },
    });
  };

  return (
    <div className="h-full flex flex-col bg-base-card border-l border-border overflow-hidden">
      {/* ── Header ──────────────────────────────────────── */}
      <div
        className="border-b border-border px-5 py-4 shrink-0 border-l-4"
        style={{ borderLeftColor: TIER_DOT_HEX[tier] }}
      >
        {/* Mobile back button */}
        {onBack && (
          <button
            onClick={onBack}
            className="flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink-primary mb-3 -mt-1 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to list
          </button>
        )}

        {/* Company + title + Apply */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap mb-1.5">
              <TierBadge tier={tier} size="md" />
              {isDowngraded && (
                <span className="inline-flex items-center gap-1 text-[0.65rem] font-semibold text-red-600 bg-red-50 border border-red-200 px-2 py-0.5 rounded-full">
                  ↓ Downgraded from {item.llm_tier}
                </span>
              )}
              <span className="text-xs text-ink-muted capitalize bg-base-surface border border-border px-2 py-0.5 rounded-full">
                {job.source}
              </span>
            </div>
            <p className="text-xs font-semibold text-ink-muted mb-1">{job.company}</p>
            <h2 className="font-display font-bold text-ink-primary text-lg leading-snug">
              {job.title}
            </h2>
          </div>

          {/* Primary CTA — always visible in header */}
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-semibold bg-brand text-white hover:bg-brand-secondary shadow-sm transition-colors"
          >
            Apply
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>

      {/* ── Scrollable body ───────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">

        {/* Meta grid */}
        <div className="grid grid-cols-2 gap-2.5">
          {(job.salary_yen || job.salary) && (
            <MetaBox icon={<DollarSign className="w-3.5 h-3.5" />} label="Salary">
              <span className="font-mono font-semibold">
                {job.salary_yen ? formatYen(job.salary_yen) : job.salary}
              </span>
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
          {(job.location || job.region || job.is_remote) && (
            <MetaBox icon={<MapPin className="w-3.5 h-3.5" />} label="Location">
              {job.is_remote && <span className="text-emerald-700 font-semibold">Remote</span>}
              {!job.is_remote && (job.region || job.location || "—")}
            </MetaBox>
          )}
          <MetaBox icon={<Briefcase className="w-3.5 h-3.5" />} label="Source">
            {job.source}
          </MetaBox>
        </div>

        {/* AI Match summary */}
        {item.jd_summary && (
          <div className={cn("rounded-lg p-4 border", tc.bg, tc.border)}>
            <div className="flex items-center gap-2 mb-2">
              <Bot className="w-3.5 h-3.5 text-brand" />
              <span className="text-[0.65rem] font-bold text-brand uppercase tracking-widest">
                AI Match Summary
              </span>
              {item.match_score != null && (
                <span className="ml-auto text-[0.65rem] font-mono text-ink-muted">
                  Score: <span className={cn("font-bold", tc.text)}>{item.match_score}</span>/100
                </span>
              )}
            </div>
            <p className="text-sm text-ink-secondary leading-relaxed">
              {item.jd_summary}
            </p>
          </div>
        )}

        {/* Tech stack */}
        {job.tech_stack && job.tech_stack.length > 0 && (
          <div>
            <SectionLabel>Tech Stack</SectionLabel>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {job.tech_stack.map((t) => (
                <span
                  key={t}
                  className="text-xs bg-base-surface border border-border text-ink-secondary px-2.5 py-0.5 rounded-md font-mono"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Job description */}
        {job.description && (
          <div>
            <SectionLabel>Job Description</SectionLabel>
            <div className="mt-2 text-sm text-ink-secondary leading-relaxed whitespace-pre-wrap bg-base-surface border border-border rounded-lg p-4 max-h-96 overflow-y-auto">
              {job.description}
            </div>
          </div>
        )}

        {/* Ranking adjustment — at the bottom */}
        <div className="rounded-lg border border-border bg-base-surface p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Pencil className="w-3.5 h-3.5 text-ink-muted" />
            <span className="text-[0.65rem] font-bold text-ink-muted uppercase tracking-widest">
              Adjust Ranking
            </span>
          </div>
          <div>
            <label className="text-xs text-ink-muted mb-1.5 block">Tier override</label>
            <div className="flex gap-1.5">
              {ALL_TIERS.map((t) => {
                const c = TIER_COLORS[t];
                return (
                  <button
                    key={t}
                    onClick={() => setEditTier(t)}
                    className={cn(
                      "flex-1 py-1.5 text-xs font-bold rounded-md border transition-all",
                      editTier === t
                        ? cn(c.bg, c.text, c.border, "shadow-sm scale-105")
                        : "bg-base-card border-border text-ink-muted hover:border-border-hover"
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
              <label className="text-xs text-ink-muted mb-1.5 block">Numerical rank</label>
              <input
                type="number"
                min={0}
                value={editRank}
                onChange={(e) => setEditRank(e.target.value)}
                className="w-full bg-base-card border border-border rounded-md px-3 py-1.5 text-sm text-ink-primary focus:border-brand outline-none transition-colors"
              />
            </div>
            <button
              onClick={handleSaveRanking}
              disabled={isPending}
              className="px-4 py-1.5 text-sm font-semibold bg-brand text-white rounded-md hover:bg-brand-secondary transition disabled:opacity-50"
            >
              {isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>

      </div>

      {/* ── Sticky footer CTA ─────────────────────────── */}
      <div className="px-5 py-3 border-t border-border bg-base-surface shrink-0">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg font-semibold text-sm bg-brand text-white hover:bg-brand-secondary shadow-sm transition-colors"
        >
          Apply on {job.source}
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </div>
  );
}

function MetaBox({ label, icon, children }: { label: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-base-surface border border-border rounded-lg p-3">
      <div className="flex items-center gap-1.5 text-[0.6rem] text-ink-muted uppercase tracking-widest mb-1.5 font-semibold">
        <span className="text-brand/60">{icon}</span>
        {label}
      </div>
      <div className="text-sm font-semibold text-ink-primary">{children}</div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-[0.65rem] font-bold text-ink-muted uppercase tracking-widest">
      {children}
    </h4>
  );
}
