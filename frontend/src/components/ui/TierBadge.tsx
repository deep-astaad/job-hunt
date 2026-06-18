import { cn, TIER_COLORS } from "@/lib/utils";
import type { Tier } from "@/lib/types";

interface Props {
  tier: Tier;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function TierBadge({ tier, size = "md", className }: Props) {
  const c = TIER_COLORS[tier];
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center font-sans font-bold rounded-full border tracking-wide",
        c.bg,
        c.text,
        c.border,
        size === "sm" && "text-[0.6rem] px-1.5 py-0.5",
        size === "md" && "text-[0.7rem] px-2.5 py-0.5",
        size === "lg" && "text-xs px-3 py-1",
        className
      )}
    >
      {tier}
    </span>
  );
}
