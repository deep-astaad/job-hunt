"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { ALL_TIERS } from "@/lib/utils";
import type { BrowseFilters, Tier } from "@/lib/types";
import { useProfile } from "@/lib/profile-context";

function defaultFilters(profileId: string, params: URLSearchParams): BrowseFilters {
  const tiersParam = params.get("tiers");
  const tiers: Tier[] = tiersParam
    ? (tiersParam.split(",").filter((t) => ALL_TIERS.includes(t as Tier)) as Tier[])
    : ["S", "A"];

  return {
    profileId,
    tiers,
    source: params.get("source") ?? "",
    language: params.get("language") ?? "",
    location: params.get("location") ?? "japan",
    remote: (params.get("remote") as BrowseFilters["remote"]) ?? "",
    applied: (params.get("applied") as BrowseFilters["applied"]) ?? "",
    date: (params.get("date") as BrowseFilters["date"]) ?? "today",
    q: params.get("q") ?? "",
    page: 1,
  };
}

interface FilterContextValue {
  filters: BrowseFilters;
  updateFilters: (partial: Partial<BrowseFilters>) => void;
}

const FilterContext = createContext<FilterContextValue>({
  filters: {
    profileId: "",
    tiers: ["S", "A"],
    source: "",
    language: "",
    location: "japan",
    remote: "",
    applied: "",
    date: "today",
    q: "",
    page: 1,
  },
  updateFilters: () => {},
});

export function FilterProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { profileId } = useProfile();

  const [filters, setFilters] = useState<BrowseFilters>(() =>
    defaultFilters(profileId, searchParams)
  );

  // Sync profileId changes into filters
  useEffect(() => {
    if (profileId) setFilters((f) => ({ ...f, profileId, page: 1 }));
  }, [profileId]);

  const updateFilters = useCallback(
    (partial: Partial<BrowseFilters>) => {
      setFilters((prev) => {
        const next = { ...prev, ...partial, page: partial.page ?? 1 };
        // Only sync to URL on the browse page
        if (typeof window !== "undefined" && (window.location.pathname.endsWith("/") || window.location.pathname === "")) {
          const p = new URLSearchParams();
          if (next.tiers.length && next.tiers.length < 5) p.set("tiers", next.tiers.join(","));
          if (next.source) p.set("source", next.source);
          if (next.language) p.set("language", next.language);
          if (next.location) p.set("location", next.location);
          if (next.remote) p.set("remote", next.remote);
          if (next.applied) p.set("applied", next.applied);
          if (next.date !== "today") p.set("date", next.date);
          if (next.q) p.set("q", next.q);
          const qs = p.toString();
          router.replace(`${pathname}${qs ? "?" + qs : ""}`, { scroll: false });
        }
        return next;
      });
    },
    [pathname, router]
  );

  return (
    <FilterContext.Provider value={{ filters, updateFilters }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  return useContext(FilterContext);
}
