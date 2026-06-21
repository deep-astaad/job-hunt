import { useMutation, useQueryClient } from "@tanstack/react-query";
import { patchJob } from "@/lib/api";
import { toast } from "sonner";

export function useJobMutation() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({
      jobId,
      data,
    }: {
      jobId: number;
      data: { is_applied?: boolean };
    }) => patchJob(jobId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => {
      toast.error(`Failed to update job status: ${err.message}`);
    },
  });
}
