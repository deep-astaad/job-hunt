"use client";

import { useEffect, useRef } from "react";
import { X, CheckCircle2, AlertCircle } from "lucide-react";
import { useJobMutation } from "@/hooks/useJobMutation";
import { toast } from "sonner";

interface Props {
  jobId: number;
  jobTitle: string;
  jobCompany: string;
  onClose: () => void;
}

export function ApplyConfirmModal({ jobId, jobTitle, jobCompany, onClose }: Props) {
  const jobMutation = useJobMutation();
  const modalRef = useRef<HTMLDivElement>(null);

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const handleConfirm = async (applied: boolean) => {
    try {
      await jobMutation.mutateAsync({
        jobId,
        data: { is_applied: applied },
      });
      if (applied) {
        toast.success(`Marked as applied to ${jobCompany}`);
      }
      onClose();
    } catch (err) {
      // Error is handled in the mutation hook via toast
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={modalRef}
        className="relative bg-base-card border border-border rounded-2xl shadow-xl w-full max-w-sm overflow-hidden animate-in fade-in zoom-in-95 duration-150 p-6 flex flex-col items-center text-center"
        role="dialog"
        aria-modal="true"
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-ink-muted hover:text-ink-primary rounded-lg p-1 hover:bg-base-surface transition-colors"
          aria-label="Close dialog"
        >
          <X className="w-4 h-4" />
        </button>

        {/* Icon */}
        <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-100 flex items-center justify-center mb-4 text-emerald-600">
          <CheckCircle2 className="w-6 h-6" />
        </div>

        {/* Header */}
        <h3 className="text-base font-bold text-ink-primary mb-1">
          Did you apply for this job?
        </h3>
        <p className="text-xs text-ink-muted mb-4 max-w-[280px]">
          We can automatically track your application status for <span className="font-semibold text-ink-secondary">{jobTitle}</span> at <span className="font-semibold text-ink-secondary">{jobCompany}</span>.
        </p>

        {/* Actions */}
        <div className="flex flex-col gap-2 w-full">
          <button
            onClick={() => handleConfirm(true)}
            disabled={jobMutation.isPending}
            className="w-full py-2.5 rounded-xl text-sm font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition-colors disabled:opacity-50"
          >
            {jobMutation.isPending ? "Updating..." : "Yes, mark as Applied"}
          </button>
          <button
            onClick={() => handleConfirm(false)}
            disabled={jobMutation.isPending}
            className="w-full py-2.5 rounded-xl text-sm font-semibold bg-transparent border border-border text-ink-muted hover:text-ink-primary hover:bg-base-surface transition-colors disabled:opacity-50"
          >
            No, not yet
          </button>
        </div>
      </div>
    </div>
  );
}
