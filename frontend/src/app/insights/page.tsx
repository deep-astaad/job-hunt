"use client";

import { ShellLayout } from "../shell-layout";
import { InsightsDashboard } from "@/components/insights/InsightsDashboard";
import { useProfile } from "@/lib/profile-context";

function InsightsContent() {
  const { profileId } = useProfile();
  return (
    <div className="h-full overflow-y-auto">
      <InsightsDashboard profileId={profileId} />
    </div>
  );
}

export default function InsightsPage() {
  return (
    <ShellLayout>
      <InsightsContent />
    </ShellLayout>
  );
}
