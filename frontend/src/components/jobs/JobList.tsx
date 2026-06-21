"use client";

import { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { JobCard } from "./JobCard";
import { JobCardSkeleton } from "@/components/ui/Skeleton";
import type { BrowseItem } from "@/lib/types";

interface Props {
  items: BrowseItem[];
  selectedId: number | null;
  onSelect: (item: BrowseItem) => void;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  isLoading: boolean;
  onApplyTriggered?: (jobId: number, title: string, company: string) => void;
}

export function JobList({
  items,
  selectedId,
  onSelect,
  hasNextPage,
  isFetchingNextPage,
  fetchNextPage,
  isLoading,
  onApplyTriggered,
}: Props) {
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: hasNextPage ? items.length + 1 : items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 180,
    overscan: 5,
  });

  // Trigger fetchNextPage when the sentinel row becomes visible
  const virtualItems = rowVirtualizer.getVirtualItems();
  const lastVirtualItem = virtualItems[virtualItems.length - 1];
  useEffect(() => {
    if (!lastVirtualItem) return;
    if (lastVirtualItem.index >= items.length - 1 && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [lastVirtualItem?.index, hasNextPage, isFetchingNextPage, items.length, fetchNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) {
    return (
      <div>
        {Array.from({ length: 8 }).map((_, i) => (
          <JobCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!isLoading && items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <p className="text-sm font-medium text-ink-secondary mb-1">No jobs match your filters</p>
        <p className="text-xs text-ink-muted">Try adjusting the tier or date range</p>
      </div>
    );
  }

  return (
    <div ref={parentRef} className="h-full overflow-y-auto">
      <div
        style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: "relative" }}
      >
        {rowVirtualizer.getVirtualItems().map((virtualItem) => {
          const isLoaderRow = virtualItem.index > items.length - 1;
          const item = items[virtualItem.index];

          return (
            <div
              key={virtualItem.key}
              data-index={virtualItem.index}
              ref={rowVirtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualItem.start}px)`,
              }}
            >
              {isLoaderRow ? (
                isFetchingNextPage ? <JobCardSkeleton /> : null
              ) : (
                <JobCard
                  item={item}
                  isSelected={item.id === selectedId}
                  onClick={() => onSelect(item)}
                  onApplyTriggered={onApplyTriggered}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
