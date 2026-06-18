export type Tier = "S" | "A" | "B" | "C" | "F";

export type AuthUser =
  | { authenticated: true; username: string; is_staff: boolean }
  | { authenticated: false };

export interface JobInline {
  id: number;
  title: string;
  company: string;
  url: string;
  source: string;
  salary: string;
  salary_yen: number | null;
  language: "EN" | "JP" | "non-english" | null;
  experience_required: string;
  description: string;
  tech_stack: string[] | null;
  scraped_at: string;
  jlpt_level: number | null;
  location: string;
  region: string;
  country: string;
  is_remote: boolean;
}

export interface BrowseItem {
  id: number;
  profile_id: string;
  match_tier: Tier;
  llm_tier: Tier | null;
  rank: number;
  match_score: number | null;
  jd_summary: string;
  created_at: string;
  job: JobInline;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Profile {
  id: string;
  title: string;
  experience?: string;
  core_skills?: string[];
  language_requirements?: string;
  preferences?: string;
}

export interface Choice {
  value: string;
  label: string;
}

export interface ProfilesResponse {
  profiles: Profile[];
  source_choices: Choice[];
  language_choices: Choice[];
  location_choices: Choice[];
}

export interface TrendingTechItem {
  name: string;
  count: number;
  percentage: number;
}

export interface TierCount {
  S: number;
  A: number;
  B: number;
  C: number;
  F: number;
}

export interface StatsPayload {
  total: number;
  active: number;
  today_scraped: number;
  today_formatted: number;
  today_ranked: number;
  by_source: { source: string; count: number }[];
  by_tier: { match_tier: Tier; count: number }[];
  tiers_count: TierCount;
  today_tiers_count: TierCount;
}

export interface SkillGapItem {
  name: string;
  count: number;
  percentage: number;
  unlock_count: number;
  samples: string[];
}

export interface TrendItem {
  name: string;
  delta: number;
}

export interface HighPayingSkill {
  name: string;
  avg: number;
  avg_display: string;
  count: number;
}

export interface SalaryInsight {
  count: number;
  median: number;
  median_display: string;
  min_display: string;
  max_display: string;
  high_paying: HighPayingSkill[];
}

export interface JpInsight {
  locked: number;
  reachable: number;
  relevant_total: number;
  locked_pct: number;
  unlock_pct: number;
  jp_total: number;
  active_total: number;
  jp_market_pct: number;
  jlpt: { n3: number; n2: number; n1: number };
}

export interface GrowthInsights {
  skill_gap: SkillGapItem[];
  skill_gap_job_count: number;
  jp: JpInsight | null;
  trends: { rising: TrendItem[]; falling: TrendItem[] } | null;
  salary: SalaryInsight | null;
  companies: { name: string; count: number }[];
}

export interface DashboardPayload {
  stats: StatsPayload;
  trending_tech: TrendingTechItem[];
  insights: GrowthInsights;
}

export interface ApifyAlert {
  message: string;
  actor_id: string;
  at: string;
}

export interface BrowseFilters {
  profileId: string;
  tiers: Tier[];
  source: string;
  language: string;
  location: string;
  remote: "" | "true" | "false";
  date: "today" | "3days" | "7days" | "all";
  q: string;
  page: number;
}
