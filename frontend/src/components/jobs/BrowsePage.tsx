"use client";

import { useEffect, useState } from "react";
import { JobList } from "./JobList";
import { JobDetailPane } from "./JobDetailPane";
import { useJobs } from "@/hooks/useJobs";
import { useFilters } from "@/lib/filter-context";
import type { BrowseItem } from "@/lib/types";

export function BrowsePage() {
  const { filters } = useFilters();
  const [selectedItem, setSelectedItem] = useState<BrowseItem | null>(null);
  const [mobileShowDetail, setMobileShowDetail] = useState(false);

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } = useJobs(filters);

  const items = data?.pages.flatMap((p) => p.results) ?? [];

  // Auto-select first result on load
  useEffect(() => {
    if (!selectedItem && items.length > 0) {
      setSelectedItem(items[0]);
    }
  }, [items.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelect = (item: BrowseItem) => {
    setSelectedItem(item);
    setMobileShowDetail(true);
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Left: job list ──────────────────────────── */}
      <div className={cn(
        "flex flex-col border-r border-border bg-base shrink-0",
        "w-full md:w-[340px] lg:w-[380px]",
        mobileShowDetail ? "hidden md:flex" : "flex"
      )}>
        {/* Result count header */}
        <div className="px-3 py-2 border-b border-border bg-base-surface flex items-center justify-between shrink-0">
          <span className="text-xs font-semibold text-ink-secondary">Jobs</span>
          {!isLoading && (
            <span className="text-xs text-ink-muted tabular-nums">
              {(data?.pages[0]?.count ?? 0).toLocaleString()} results
            </span>
          )}
        </div>

        <div className="flex-1 overflow-hidden">
          <JobList
            items={items}
            selectedId={selectedItem?.id ?? null}
            onSelect={handleSelect}
            hasNextPage={!!hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            fetchNextPage={fetchNextPage}
            isLoading={isLoading}
          />
        </div>
      </div>

      {/* ── Right: detail pane ──────────────────────── */}
      <div className={cn(
        "flex-1 min-w-0 overflow-hidden",
        mobileShowDetail ? "flex flex-col" : "hidden md:flex md:flex-col"
      )}>
        <JobDetailPane
          item={selectedItem}
          onBack={() => setMobileShowDetail(false)}
        />
      </div>
    </div>
  );
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
