"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Briefcase, BarChart2, X, Settings, LogOut,
  AlertTriangle, Play, RefreshCw, Search,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { triggerScrape, triggerProcessing } from "@/lib/api";
import { toast } from "sonner";
import { cn, ALL_TIERS, TIER_COLORS } from "@/lib/utils";
import { useProfile } from "@/lib/profile-context";
import { useProfiles } from "@/hooks/useProfiles";
import { useApifyAlert } from "@/hooks/useInsights";
import { useFilters } from "@/lib/filter-context";
import { SettingsModal } from "./SettingsModal";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import type { Tier } from "@/lib/types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const DATE_OPTS = [
  { value: "today" as const, label: "Today" },
  { value: "3days" as const, label: "3d" },
  { value: "7days" as const, label: "7d" },
  { value: "all" as const, label: "All" },
];

const NAV = [
  { href: "/", label: "Browse", icon: Briefcase },
  { href: "/insights", label: "Insights", icon: BarChart2 },
];

export function Sidebar({ isOpen, onClose }: Props) {
  const pathname = usePathname();
  const { profileId, setProfileId } = useProfile();
  const { data: profilesData } = useProfiles();
  const { data: alertData } = useApifyAlert();
  const { filters, updateFilters } = useFilters();
  const [pending, setPending] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { signOut } = useAuth();
  const router = useRouter();

  const [localQ, setLocalQ] = useState(filters.q);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateFilters({ q: localQ });
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [localQ]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep local search in sync if filters reset externally
  useEffect(() => { setLocalQ(filters.q); }, [filters.q]);

  const toggleTier = useCallback(
    (tier: Tier) => {
      const next = filters.tiers.includes(tier)
        ? filters.tiers.filter((t) => t !== tier)
        : [...filters.tiers, tier];
      updateFilters({ tiers: next });
    },
    [filters.tiers, updateFilters]
  );

  const runPipeline = async (action: "scrape" | "process") => {
    setPending(true);
    try {
      if (action === "scrape") { await triggerScrape(); toast.success("Scrape triggered"); }
      else { await triggerProcessing(); toast.success("Processing triggered"); }
    } catch (e: unknown) {
      toast.error(`Failed: ${e instanceof Error ? e.message : "error"}`);
    } finally {
      setPending(false);
    }
  };

  const isActive = (path: string) =>
    path === "/" ? pathname === "/" || pathname === "" : pathname.startsWith(path);

  const sourceChoices = profilesData?.source_choices ?? [];
  const languageChoices = profilesData?.language_choices ?? [];
  const locationChoices = profilesData?.location_choices ?? [];

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 w-60 bg-base-surface border-r border-border flex flex-col",
        "transition-transform duration-200 ease-out",
        "md:relative md:translate-x-0 md:flex md:shrink-0",
        isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
      )}
    >
      {/* ── Brand ──────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 h-14 border-b border-border shrink-0">
        <div>
          <div className="font-display font-bold text-lg text-ink-primary tracking-tight leading-none">JobHunt</div>
          <div className="text-[0.6rem] text-ink-muted mt-0.5 uppercase tracking-wide">Tokyo Tech Radar</div>
        </div>
        <button onClick={onClose} className="md:hidden p-1 text-ink-muted hover:text-ink-primary rounded transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* ── Apify alert ────────────────────────────────── */}
      {alertData?.alert && (
        <div className="mx-3 mt-3 flex items-start gap-2 px-3 py-2.5 rounded-md border border-red-200 bg-red-50 text-xs text-red-700">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-red-500" />
          <span className="leading-relaxed">{alertData.alert.message}</span>
        </div>
      )}

      {/* ── Scrollable filter area ─────────────────────── */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">

        {/* Nav */}
        <nav className="space-y-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = isActive(href);
            return (
              <Link key={href} href={href} onClick={onClose}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
                  active
                    ? "bg-brand/8 text-brand font-semibold"
                    : "text-ink-secondary hover:bg-base-hover hover:text-ink-primary"
                )}
                aria-current={active ? "page" : undefined}
              >
                <Icon className={cn("w-4 h-4 shrink-0", active ? "text-brand" : "text-ink-muted")} />
                {label}
                {active && <span className="ml-auto w-1 h-4 bg-brand rounded-full" />}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border" />

        {/* Profile */}
        {(profilesData?.profiles.length ?? 0) > 0 && (
          <div>
            <FilterLabel>Profile</FilterLabel>
            <select
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              className="w-full bg-base-card border border-border rounded-md px-2.5 py-1.5 text-sm text-ink-primary focus:border-brand outline-none cursor-pointer transition-colors appearance-none"
            >
              {profilesData!.profiles.map((p) => (
                <option key={p.id} value={p.id}>{p.title}</option>
              ))}
            </select>
          </div>
        )}

        {/* Search */}
        <div>
          <FilterLabel>Search</FilterLabel>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink-muted pointer-events-none" />
            <input
              type="text"
              placeholder="Jobs, companies, skills…"
              value={localQ}
              onChange={(e) => setLocalQ(e.target.value)}
              className="w-full bg-base-card border border-border rounded-md pl-8 pr-3 py-1.5 text-sm text-ink-primary placeholder:text-ink-muted focus:border-brand outline-none transition-colors"
            />
          </div>
        </div>

        {/* Tier */}
        <div>
          <FilterLabel>Tier</FilterLabel>
          <div className="flex gap-1.5 flex-wrap">
            {ALL_TIERS.map((tier) => {
              const c = TIER_COLORS[tier];
              const active = filters.tiers.includes(tier);
              return (
                <button
                  key={tier}
                  onClick={() => toggleTier(tier)}
                  aria-pressed={active}
                  className={cn(
                    "flex-1 min-w-[30px] py-1.5 rounded-md text-xs font-bold border transition-all",
                    active
                      ? cn(c.bg, c.text, c.border, "shadow-sm")
                      : "bg-base-card text-ink-muted border-border hover:border-border-hover"
                  )}
                >
                  {tier}
                </button>
              );
            })}
          </div>
        </div>

        {/* Date */}
        <div>
          <FilterLabel>Posted</FilterLabel>
          <div className="flex gap-1">
            {DATE_OPTS.map((opt) => {
              const active = filters.date === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => updateFilters({ date: opt.value })}
                  className={cn(
                    "flex-1 py-1.5 rounded-md text-xs font-medium border transition-all",
                    active
                      ? "bg-brand text-white border-brand shadow-sm"
                      : "bg-base-card text-ink-muted border-border hover:border-border-hover"
                  )}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Source */}
        {sourceChoices.length > 0 && (
          <div>
            <FilterLabel>Source</FilterLabel>
            <div className="flex flex-wrap gap-1">
              {sourceChoices.map((opt) => {
                const active = filters.source === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => updateFilters({ source: active ? "" : opt.value })}
                    className={cn(
                      "px-2.5 py-1 rounded-md text-xs border transition-all",
                      active
                        ? "bg-brand/8 text-brand border-brand/30 font-semibold"
                        : "bg-base-card text-ink-muted border-border hover:border-border-hover"
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Language */}
        {languageChoices.length > 0 && (
          <div>
            <FilterLabel>Language</FilterLabel>
            <div className="flex flex-wrap gap-1">
              {languageChoices.map((opt) => {
                const active = filters.language === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => updateFilters({ language: active ? "" : opt.value })}
                    className={cn(
                      "px-2.5 py-1 rounded-md text-xs border transition-all",
                      active
                        ? "bg-brand/8 text-brand border-brand/30 font-semibold"
                        : "bg-base-card text-ink-muted border-border hover:border-border-hover"
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Location */}
        <div>
          <FilterLabel>Location</FilterLabel>
          {/* Remote toggle */}
          <div className="flex gap-1 mb-2">
            {(["", "true", "false"] as const).map((val) => {
              const label = val === "" ? "Any" : val === "true" ? "Remote" : "Onsite";
              const active = filters.remote === val;
              return (
                <button
                  key={val}
                  onClick={() => updateFilters({ remote: val })}
                  className={cn(
                    "flex-1 py-1.5 rounded-md text-xs font-medium border transition-all",
                    active
                      ? "bg-brand/8 text-brand border-brand/30 font-semibold"
                      : "bg-base-card text-ink-muted border-border hover:border-border-hover"
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
          {/* Region choices from DB */}
          {locationChoices.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {locationChoices.map((opt) => {
                const active = filters.location === opt.value;
                return (
                  <button
                    key={opt.value}
                    onClick={() => updateFilters({ location: active ? "" : opt.value })}
                    className={cn(
                      "px-2.5 py-1 rounded-md text-xs border transition-all",
                      active
                        ? "bg-brand/8 text-brand border-brand/30 font-semibold"
                        : "bg-base-card text-ink-muted border-border hover:border-border-hover"
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          )}
          {locationChoices.length === 0 && (
            <p className="text-[0.65rem] text-ink-muted italic">No location data yet</p>
          )}
        </div>

      </div>

      {/* ── Footer ─────────────────────────────────────── */}
      <div className="px-3 py-3 border-t border-border shrink-0 space-y-1.5">
        <div className="flex gap-1.5">
          <button onClick={() => runPipeline("scrape")} disabled={pending}
            className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs text-ink-muted hover:text-brand hover:bg-brand/5 border border-border hover:border-brand/30 transition-colors disabled:opacity-40">
            <Play className="w-3 h-3" />Scrape
          </button>
          <button onClick={() => runPipeline("process")} disabled={pending}
            className="flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-md text-xs text-ink-muted hover:text-brand hover:bg-brand/5 border border-border hover:border-brand/30 transition-colors disabled:opacity-40">
            <RefreshCw className="w-3 h-3" />Rank
          </button>
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={() => setSettingsOpen(true)}
            className="flex-1 flex items-center gap-2 px-3 py-2 rounded-md text-xs text-ink-muted hover:text-ink-primary hover:bg-base-hover transition-colors"
          >
            <Settings className="w-3.5 h-3.5 shrink-0" />
            <span>Settings</span>
          </button>
          <button
            onClick={async () => { await signOut(); router.replace("/login"); }}
            className="flex items-center gap-1.5 px-2.5 py-2 rounded-md text-xs text-ink-muted hover:text-red-600 hover:bg-red-50 transition-colors"
            title="Sign out"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <SettingsModal isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </aside>
  );
}

function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[0.6rem] font-bold text-ink-muted uppercase tracking-widest mb-1.5 px-0.5">
      {children}
    </div>
  );
}
