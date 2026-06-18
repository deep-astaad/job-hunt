"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Search, X, SlidersHorizontal } from "lucide-react";
import { cn, ALL_TIERS, TIER_COLORS } from "@/lib/utils";
import type { BrowseFilters, Choice, Tier } from "@/lib/types";

interface Props {
  filters: BrowseFilters;
  sourceChoices: Choice[];
  languageChoices: Choice[];
  resultCount?: number;
  onChange: (partial: Partial<BrowseFilters>) => void;
}

const DATE_OPTIONS: { value: BrowseFilters["date"]; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "3days", label: "3 days" },
  { value: "7days", label: "7 days" },
  { value: "all", label: "All" },
];

const TIER_LABELS: Record<Tier, string> = { S: "S", A: "A", B: "B", C: "C", F: "F" };

export function FilterBar({ filters, sourceChoices, languageChoices, resultCount, onChange }: Props) {
  const [localQ, setLocalQ] = useState(filters.q);
  const [expanded, setExpanded] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onChange({ q: localQ, page: 1 });
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [localQ]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleTier = useCallback(
    (tier: Tier) => {
      const next = filters.tiers.includes(tier)
        ? filters.tiers.filter((t) => t !== tier)
        : [...filters.tiers, tier];
      onChange({ tiers: next, page: 1 });
    },
    [filters.tiers, onChange]
  );

  const secondaryActiveCount =
    (filters.source ? 1 : 0) +
    (filters.language ? 1 : 0) +
    (filters.date !== "today" ? 1 : 0);

  return (
    <div className="flex flex-col gap-0 border-b border-border">
      {/* ── Row 1: Search ──────────────────────────────────── */}
      <div className="px-3 pt-3 pb-2">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink-muted pointer-events-none" />
          <input
            type="text"
            placeholder="Search jobs, companies, skills…"
            value={localQ}
            onChange={(e) => setLocalQ(e.target.value)}
            className="w-full bg-base-card border border-border rounded-md pl-8 pr-7 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:border-brand focus:ring-1 focus:ring-brand/20 outline-none transition-all"
          />
          {localQ && (
            <button
              onClick={() => { setLocalQ(""); onChange({ q: "", page: 1 }); }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-primary transition-colors"
              aria-label="Clear search"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* ── Row 2: Tier chips + count + expand button ───────── */}
      <div className="px-3 pb-2.5 flex items-center gap-1.5 flex-wrap">
        {ALL_TIERS.map((tier) => {
          const c = TIER_COLORS[tier];
          const active = filters.tiers.includes(tier);
          return (
            <button
              key={tier}
              onClick={() => toggleTier(tier)}
              aria-pressed={active}
              className={cn(
                "inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border transition-all duration-100",
                active
                  ? cn(c.bg, c.text, c.border, "shadow-sm")
                  : "bg-transparent text-ink-muted border-border hover:border-border-hover hover:bg-base-hover"
              )}
            >
              {TIER_LABELS[tier]}
            </button>
          );
        })}

        {filters.tiers.length > 0 && filters.tiers.length < 5 && (
          <button
            onClick={() => onChange({ tiers: ["S", "A", "B", "C", "F"], page: 1 })}
            className="text-[0.65rem] text-ink-muted hover:text-ink-secondary transition-colors ml-0.5 px-1"
            aria-label="Select all tiers"
          >
            All
          </button>
        )}

        {/* Spacer + result count + expand */}
        <div className="ml-auto flex items-center gap-2">
          {resultCount !== undefined && (
            <span className="text-[0.7rem] text-ink-muted tabular-nums">
              {resultCount.toLocaleString()}
            </span>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className={cn(
              "inline-flex items-center gap-1 px-2 py-1 rounded-md text-[0.7rem] border transition-all",
              expanded || secondaryActiveCount > 0
                ? "border-brand/40 bg-brand/5 text-brand"
                : "border-border text-ink-muted hover:border-border-hover hover:text-ink-secondary"
            )}
          >
            <SlidersHorizontal className="w-3 h-3" />
            {secondaryActiveCount > 0 && (
              <span className="w-4 h-4 rounded-full bg-brand text-white text-[0.6rem] font-bold flex items-center justify-center">
                {secondaryActiveCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* ── Row 3: Secondary filters (collapsible) ──────────── */}
      {expanded && (
        <div className="px-3 pb-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border/50 pt-2.5 bg-base-surface/50">
          {/* Source */}
          {sourceChoices.length > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-[0.65rem] text-ink-muted uppercase tracking-wide font-semibold">Source</span>
              <select
                value={filters.source}
                onChange={(e) => onChange({ source: e.target.value, page: 1 })}
                className={cn(
                  "bg-base-card border border-border rounded-md px-2 py-1 text-xs outline-none cursor-pointer transition-colors focus:border-brand",
                  filters.source ? "text-ink-primary border-brand/40" : "text-ink-muted"
                )}
              >
                <option value="">Any</option>
                {sourceChoices.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Language */}
          {languageChoices.length > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-[0.65rem] text-ink-muted uppercase tracking-wide font-semibold">Language</span>
              <select
                value={filters.language}
                onChange={(e) => onChange({ language: e.target.value, page: 1 })}
                className={cn(
                  "bg-base-card border border-border rounded-md px-2 py-1 text-xs outline-none cursor-pointer transition-colors focus:border-brand",
                  filters.language ? "text-ink-primary border-brand/40" : "text-ink-muted"
                )}
              >
                <option value="">Any</option>
                {languageChoices.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Date */}
          <div className="flex items-center gap-1.5 ml-auto">
            <span className="text-[0.65rem] text-ink-muted uppercase tracking-wide font-semibold">Posted</span>
            <div className="flex gap-1">
              {DATE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => onChange({ date: opt.value, page: 1 })}
                  className={cn(
                    "px-2.5 py-1 text-xs rounded-md border transition-all",
                    filters.date === opt.value
                      ? "bg-brand text-white border-brand shadow-sm"
                      : "bg-transparent text-ink-muted border-border hover:border-border-hover"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Clear secondary */}
          {secondaryActiveCount > 0 && (
            <button
              onClick={() => onChange({ source: "", language: "", date: "today", page: 1 })}
              className="text-[0.65rem] text-ink-muted hover:text-red-600 transition-colors ml-1"
            >
              Clear filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}
