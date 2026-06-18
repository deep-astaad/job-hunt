import { useQuery } from "@tanstack/react-query";
import { fetchProfiles } from "@/lib/api";

export function useProfiles() {
  return useQuery({
    queryKey: ["profiles"],
    queryFn: fetchProfiles,
    staleTime: Infinity, // profiles don't change at runtime
  });
}
