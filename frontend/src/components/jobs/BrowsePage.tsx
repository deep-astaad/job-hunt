"use client";

import { useEffect, useState } from "react";
import { JobList } from "./JobList";
import { JobDetailPane } from "./JobDetailPane";
import { ApplyConfirmModal } from "./ApplyConfirmModal";
import { FilterBar } from "./FilterBar";
import { useJobs } from "@/hooks/useJobs";
import { useFilters } from "@/lib/filter-context";
import { useProfiles } from "@/hooks/useProfiles";
import type { BrowseItem } from "@/lib/types";

export function BrowsePage() {
  const { filters, updateFilters } = useFilters();
  const { data: profilesData } = useProfiles();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [mobileShowDetail, setMobileShowDetail] = useState(false);
  const [confirmJob, setConfirmJob] = useState<{ id: number; title: string; company: string } | null>(null);

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } = useJobs(filters);

  const items = data?.pages.flatMap((p) => p.results) ?? [];
  const sourceChoices = profilesData?.source_choices ?? [];
  const languageChoices = profilesData?.language_choices ?? [];

  const selectedItem = items.find((item) => item.id === selectedId) ?? null;

  // Auto-select first result on load
  useEffect(() => {
    if (selectedId === null && items.length > 0) {
      setSelectedId(items[0].id);
    }
  }, [items.length, selectedId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSelect = (item: BrowseItem) => {
    setSelectedId(item.id);
    setMobileShowDetail(true);
  };

  const handleApplyTriggered = (jobId: number, title: string, company: string) => {
    setConfirmJob({ id: jobId, title, company });
  };

  return (
    <div className="flex h-full overflow-hidden relative">
      {/* ── Left: job list ──────────────────────────── */}
      <div className={cn(
        "flex flex-col border-r border-border bg-base shrink-0",
        "w-full md:w-[340px] lg:w-[380px]",
        mobileShowDetail ? "hidden md:flex" : "flex"
      )}>
        <FilterBar
          filters={filters}
          sourceChoices={sourceChoices}
          languageChoices={languageChoices}
          resultCount={data?.pages[0]?.count}
          onChange={updateFilters}
        />

        <div className="flex-1 overflow-hidden">
          <JobList
            items={items}
            selectedId={selectedItem?.id ?? null}
            onSelect={handleSelect}
            hasNextPage={!!hasNextPage}
            isFetchingNextPage={isFetchingNextPage}
            fetchNextPage={fetchNextPage}
            isLoading={isLoading}
            onApplyTriggered={handleApplyTriggered}
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
          onApplyTriggered={handleApplyTriggered}
        />
      </div>

      {/* Confirmation Modal */}
      {confirmJob && (
        <ApplyConfirmModal
          jobId={confirmJob.id}
          jobTitle={confirmJob.title}
          jobCompany={confirmJob.company}
          onClose={() => setConfirmJob(null)}
        />
      )}
    </div>
  );
}

function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
