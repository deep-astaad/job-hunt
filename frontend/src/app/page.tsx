import { Suspense } from "react";
import { ShellLayout } from "./shell-layout";
import { BrowsePage } from "@/components/jobs/BrowsePage";
import { JobCardSkeleton } from "@/components/ui/Skeleton";

export default function Home() {
  return (
    <ShellLayout>
      <Suspense fallback={
        <div className="p-4 space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <JobCardSkeleton key={i} />)}
        </div>
      }>
        <BrowsePage />
      </Suspense>
    </ShellLayout>
  );
}
