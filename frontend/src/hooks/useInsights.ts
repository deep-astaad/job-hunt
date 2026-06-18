import { useQuery } from "@tanstack/react-query";
import { fetchDashboard, fetchDashboardAlert } from "@/lib/api";

export function useInsights(profileId: string) {
  return useQuery({
    queryKey: ["dashboard", profileId],
    queryFn: () => fetchDashboard(profileId),
    enabled: !!profileId,
    staleTime: 1000 * 60 * 5, // matches backend 5-min cache TTL
  });
}

export function useApifyAlert() {
  return useQuery({
    queryKey: ["apify-alert"],
    queryFn: fetchDashboardAlert,
    staleTime: 1000 * 60,
  });
}
