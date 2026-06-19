import { useQuery } from "@tanstack/react-query";
import { fetchProfiles } from "@/lib/api";

export function useProfiles(enabled = true) {
  return useQuery({
    queryKey: ["profiles"],
    queryFn: fetchProfiles,
    staleTime: Infinity, // profiles don't change at runtime
    enabled, // gated on auth so it doesn't 403 on the login page
  });
}
