import { useMutation, useQueryClient } from "@tanstack/react-query";
import { patchRanking } from "@/lib/api";
import { toast } from "sonner";

export function useRankingMutation() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      rankingId,
      data,
    }: {
      rankingId: number;
      data: { match_tier?: string; rank?: number };
    }) => patchRanking(rankingId, data),
    onSuccess: () => {
      toast.success("Ranking updated");
      // Invalidate browse queries so the list reflects the change
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => {
      toast.error(`Failed to update: ${err.message}`);
    },
  });
}
