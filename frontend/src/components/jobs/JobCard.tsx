import { ExternalLink, Check } from "lucide-react";
import { cn, TIER_COLORS, TIER_ACCENT, formatRelativeTime, formatYen } from "@/lib/utils";
import { TierBadge } from "@/components/ui/TierBadge";
import type { BrowseItem } from "@/lib/types";

interface Props {
  item: BrowseItem;
  isSelected: boolean;
  onClick: () => void;
  onApplyTriggered?: (jobId: number, title: string, company: string) => void;
}

export function JobCard({ item, isSelected, onClick, onApplyTriggered }: Props) {
  const { job } = item;
  const tc = TIER_COLORS[item.match_tier];

  const handleApplyClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    e.stopPropagation();
    e.preventDefault();
    window.open(job.url, "_blank", "noopener,noreferrer");
    onApplyTriggered?.(job.id, job.title, job.company);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onClick(); }}
      className={cn(
        "w-full text-left border-l-[3px] border border-b-0 last:border-b cursor-pointer group",
        "transition-colors duration-100 select-none",
        TIER_ACCENT[item.match_tier],
        isSelected
          ? "bg-base-card border-r-border border-t-border"
          : "bg-transparent border-r-transparent border-t-transparent hover:bg-base-hover"
      )}
    >
      <div className="px-3 py-3">
        {/* Top row: tier + company + status badge + time */}
        <div className="flex items-center gap-2 mb-1.5 min-w-0">
          <TierBadge tier={item.match_tier} size="sm" />
          <span className="text-xs font-semibold text-ink-secondary truncate flex-1 min-w-0">
            {job.company}
          </span>
          {job.is_applied && (
            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[0.6rem] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/60 shrink-0">
              <Check className="w-2.5 h-2.5" />
              Applied
            </span>
          )}
          <span className="text-[0.6rem] text-ink-muted shrink-0">
            {formatRelativeTime(job.scraped_at)}
          </span>
        </div>

        {/* Title */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className={cn(
            "font-sans font-semibold text-sm leading-snug line-clamp-2 flex-1",
            isSelected ? "text-brand" : "text-ink-primary group-hover:text-ink-primary"
          )}>
            {job.title}
          </h3>
          {/* Apply button — always visible, stops card click and triggers confirmation */}
          <a
            href={job.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={handleApplyClick}
            className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-md text-[0.65rem] font-semibold bg-brand text-white hover:bg-brand-secondary transition-colors"
            aria-label={`Apply for ${job.title}`}
          >
            Apply
            <ExternalLink className="w-2.5 h-2.5" />
          </a>
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-muted">
          {(job.salary_yen || job.salary) && (
            <span className={cn("font-mono font-semibold text-[0.7rem]", tc.text)}>
              {job.salary_yen ? formatYen(job.salary_yen) : job.salary}
            </span>
          )}
          {job.experience_required && (
            <span>{job.experience_required}</span>
          )}
          {job.language && job.language !== "EN" && (
            <span className="text-red-600 font-medium">{job.language}{job.jlpt_level ? ` N${job.jlpt_level}` : ""}</span>
          )}
          {job.is_remote && (
            <span className="text-emerald-700 font-medium">Remote</span>
          )}
          {!job.is_remote && (job.region || job.location) && (
            <span className="truncate max-w-[100px]">{job.region || job.location}</span>
          )}
          {job.tech_stack && job.tech_stack.length > 0 && (
            <span className="ml-auto text-[0.6rem] text-ink-muted/70 truncate max-w-[110px]">
              {job.tech_stack.slice(0, 3).join(" · ")}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
