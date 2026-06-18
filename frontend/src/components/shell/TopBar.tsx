"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Zap, BarChart2, List, AlertTriangle, ChevronDown, RefreshCw, Play } from "lucide-react";
import { cn, BASE_PATH } from "@/lib/utils";
import { useProfiles } from "@/hooks/useProfiles";
import { useApifyAlert } from "@/hooks/useInsights";
import { triggerScrape, triggerProcessing } from "@/lib/api";
import { toast } from "sonner";
import type { Profile } from "@/lib/types";

interface Props {
  selectedProfileId: string;
  onProfileChange: (id: string) => void;
}

export function TopBar({ selectedProfileId, onProfileChange }: Props) {
  const pathname = usePathname();
  const { data: profilesData } = useProfiles();
  const { data: alertData } = useApifyAlert();
  const [actionsPending, setActionsPending] = useState(false);

  const profiles = profilesData?.profiles ?? [];
  const alert = alertData?.alert;
  const selectedProfile = profiles.find((p) => p.id === selectedProfileId);

  const handleTriggerScrape = async () => {
    setActionsPending(true);
    try {
      await triggerScrape();
      toast.success("Scrape pipeline triggered");
    } catch (e: unknown) {
      toast.error(`Failed: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setActionsPending(false);
    }
  };

  const handleTriggerProcessing = async () => {
    setActionsPending(true);
    try {
      await triggerProcessing();
      toast.success("Processing triggered");
    } catch (e: unknown) {
      toast.error(`Failed: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setActionsPending(false);
    }
  };

  const navLinks = [
    { href: `${BASE_PATH}/`, label: "Browse", icon: List },
    { href: `${BASE_PATH}/insights`, label: "Insights", icon: BarChart2 },
  ];

  return (
    <header className="h-14 border-b border-border bg-base-surface flex items-center px-4 gap-4 z-30 shrink-0">
      {/* Brand */}
      <Link href={`${BASE_PATH}/`} className="font-display font-bold text-lg text-gradient shrink-0">
        JobHunter
      </Link>

      {/* Nav links */}
      <nav className="flex items-center gap-1">
        {navLinks.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href.endsWith("/insights") && pathname?.includes("insights"));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded text-sm transition-colors",
                active
                  ? "bg-brand/15 text-brand font-semibold"
                  : "text-ink-muted hover:text-ink-primary hover:bg-base-hover"
              )}
            >
              <Icon className="w-3.5 h-3.5" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Apify alert banner (inline) */}
      {alert && (
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs max-w-xs truncate">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{alert.message}</span>
        </div>
      )}

      {/* Profile switcher */}
      {profiles.length > 0 && (
        <ProfileSwitcher
          profiles={profiles}
          selected={selectedProfile ?? profiles[0]}
          onChange={onProfileChange}
        />
      )}

      {/* Admin actions */}
      <div className="flex items-center gap-1">
        <button
          onClick={handleTriggerProcessing}
          disabled={actionsPending}
          title="Process unranked jobs"
          className="p-1.5 rounded text-ink-muted hover:text-brand hover:bg-base-hover transition-colors disabled:opacity-50"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
        <button
          onClick={handleTriggerScrape}
          disabled={actionsPending}
          title="Trigger scrape pipeline"
          className="p-1.5 rounded text-ink-muted hover:text-brand hover:bg-base-hover transition-colors disabled:opacity-50"
        >
          <Play className="w-4 h-4" />
        </button>
      </div>

      {/* Django admin link */}
      <a
        href="/admin/"
        target="_blank"
        rel="noopener noreferrer"
        className="hidden sm:flex items-center gap-1 text-[0.7rem] text-ink-muted hover:text-ink-primary transition-colors px-2 py-1 rounded border border-border hover:border-border-hover"
      >
        <Zap className="w-3 h-3" />
        Admin
      </a>
    </header>
  );
}

function ProfileSwitcher({
  profiles,
  selected,
  onChange,
}: {
  profiles: Profile[];
  selected: Profile;
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-border hover:border-border-hover bg-base text-sm text-ink-primary transition-colors"
      >
        <span className="max-w-[120px] truncate">{selected.title}</span>
        <ChevronDown className={cn("w-3.5 h-3.5 text-ink-muted transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 w-56 bg-base-surface border border-border rounded-md shadow-lg z-50 overflow-hidden">
            {profiles.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  onChange(p.id);
                  setOpen(false);
                }}
                className={cn(
                  "w-full text-left px-3 py-2.5 text-sm transition-colors hover:bg-base-hover",
                  p.id === selected.id ? "text-brand bg-brand/5" : "text-ink-secondary"
                )}
              >
                <div className="font-medium">{p.title}</div>
                <div className="text-[0.65rem] text-ink-muted mt-0.5">{p.experience}</div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
