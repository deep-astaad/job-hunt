import { useInfiniteQuery } from "@tanstack/react-query";
import { fetchBrowsePage } from "@/lib/api";
import type { BrowseFilters } from "@/lib/types";

export function useJobs(filters: BrowseFilters) {
  return useInfiniteQuery({
    queryKey: ["jobs", filters],
    queryFn: ({ pageParam = 1 }) => fetchBrowsePage(filters, pageParam as number),
    getNextPageParam: (last, pages) => {
      if (!last.next) return undefined;
      return pages.length + 1;
    },
    initialPageParam: 1,
    staleTime: 1000 * 60,
  });
}
