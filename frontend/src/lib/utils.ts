import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Tier } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const BASE_PATH = "";

/** Build a URL to the BFF proxy (same-origin, no CORS).
 * Strips any trailing slash on the path part so requests match Next.js's
 * canonical (trailingSlash: false) form and avoid a 308 redirect on every
 * call. The BFF route re-appends the slash Django expects. */
export function proxyUrl(path: string): string {
  const [p, q] = path.split("?");
  const clean = p.replace(/\/+$/, "");
  return `/bff${clean}${q ? `?${q}` : ""}`;
}

export const TIER_LABELS: Record<Tier, string> = {
  S: "S",
  A: "A",
  B: "B",
  C: "C",
  F: "F",
};

export const TIER_COLORS: Record<Tier, { bg: string; text: string; border: string; dot: string }> = {
  S: { bg: "bg-amber-50",   text: "text-amber-700",   border: "border-amber-300/70",   dot: "bg-amber-500"   },
  A: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-300/70", dot: "bg-emerald-500" },
  B: { bg: "bg-violet-50",  text: "text-violet-700",  border: "border-violet-300/70",  dot: "bg-violet-500"  },
  C: { bg: "bg-slate-100",  text: "text-slate-600",   border: "border-slate-300/70",   dot: "bg-slate-400"   },
  F: { bg: "bg-red-50",     text: "text-red-700",     border: "border-red-300/70",     dot: "bg-red-500"     },
};

export const TIER_ACCENT: Record<Tier, string> = {
  S: "tier-accent-s",
  A: "tier-accent-a",
  B: "tier-accent-b",
  C: "tier-accent-c",
  F: "tier-accent-f",
};

export const ALL_TIERS: Tier[] = ["S", "A", "B", "C", "F"];

export const TIER_DOT_HEX: Record<Tier, string> = {
  S: "#D97706",
  A: "#059669",
  B: "#7C3AED",
  C: "#6B7280",
  F: "#DC2626",
};

export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = (now.getTime() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function formatYen(yen: number): string {
  if (yen >= 1_000_000) return `¥${(yen / 1_000_000).toFixed(1)}M`;
  if (yen >= 10_000) return `¥${Math.round(yen / 10_000)}万`;
  return `¥${yen.toLocaleString()}`;
}
