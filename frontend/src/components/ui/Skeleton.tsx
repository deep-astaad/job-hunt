import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded bg-base-hover",
        className
      )}
    />
  );
}

export function JobCardSkeleton() {
  return (
    <div className="px-3 py-3 border-b border-border">
      <div className="flex items-center gap-2 mb-2">
        <Skeleton className="h-4 w-6 rounded-full" />
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-3 w-10 ml-auto" />
      </div>
      <div className="flex items-start gap-2 mb-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-5 w-14 ml-auto rounded-md" />
      </div>
      <div className="flex gap-3">
        <Skeleton className="h-3 w-14" />
        <Skeleton className="h-3 w-20" />
      </div>
    </div>
  );
}
