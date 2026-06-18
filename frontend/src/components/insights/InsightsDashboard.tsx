"use client";

import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  LabelList,
  ReferenceLine,
} from "recharts";
import { useInsights } from "@/hooks/useInsights";
import { Skeleton } from "@/components/ui/Skeleton";
import { TIER_COLORS } from "@/lib/utils";
import type { Tier, DashboardPayload } from "@/lib/types";

const TIER_HEX: Record<Tier, string> = {
  S: "hsl(45,93%,47%)",
  A: "hsl(162,84%,40%)",
  B: "hsl(262,83%,58%)",
  C: "hsl(215,16%,47%)",
  F: "hsl(346,84%,55%)",
};

interface Props {
  profileId: string;
}

export function InsightsDashboard({ profileId }: Props) {
  const { data, isLoading, error } = useInsights(profileId);

  if (isLoading) return <InsightsSkeleton />;
  if (error || !data)
    return (
      <div className="text-ink-muted text-sm p-6">
        Failed to load insights. Please try again.
      </div>
    );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 p-4">
      <StatsRow data={data} />
      <TierDonut data={data} />
      <TrendingTech data={data} />
      <MarketTrends data={data} />
      <SalaryBands data={data} />
      <JapaneseROI data={data} />
      <TopCompanies data={data} />
    </div>
  );
}

// ── Stats row ────────────────────────────────────────────────────────────────

function StatsRow({ data }: { data: DashboardPayload }) {
  const { stats } = data;
  const stats_items = [
    { label: "Total jobs", value: stats.total.toLocaleString() },
    { label: "Active", value: stats.active.toLocaleString() },
    { label: "Scraped today", value: stats.today_scraped.toLocaleString() },
    { label: "Ranked today", value: stats.today_ranked.toLocaleString() },
  ];
  return (
    <div className="col-span-full grid grid-cols-2 sm:grid-cols-4 gap-3">
      {stats_items.map((s) => (
        <div key={s.label} className="bg-base-card border border-border rounded-md p-4 text-center">
          <div className="text-2xl font-display font-bold text-brand">{s.value}</div>
          <div className="text-xs text-ink-muted mt-1">{s.label}</div>
        </div>
      ))}
    </div>
  );
}

// ── Tier distribution donut ──────────────────────────────────────────────────

function TierDonut({ data }: { data: DashboardPayload }) {
  const tiers = data.stats.tiers_count;
  const chartData = (["S", "A", "B", "C", "F"] as Tier[])
    .map((t) => ({ name: t, value: tiers[t], fill: TIER_HEX[t] }))
    .filter((d) => d.value > 0);
  const total = chartData.reduce((sum, d) => sum + d.value, 0);

  return (
    <Card title="Tier Distribution">
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={75}
            paddingAngle={2}
            dataKey="value"
          >
            {chartData.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} stroke="none" />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: "#FFFFFF", border: "1px solid #E4E1DC", borderRadius: 6, color: "#18181B", boxShadow: "0 4px 16px rgba(0,0,0,0.08)", fontSize: 12 }}
            formatter={(val: number, name: string) => [
              `${val} (${Math.round((val / total) * 100)}%)`,
              `Tier ${name}`,
            ]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap justify-center gap-2 mt-2">
        {chartData.map((d) => (
          <div key={d.name} className="flex items-center gap-1 text-xs text-ink-secondary">
            <span className="w-2 h-2 rounded-full" style={{ background: d.fill }} />
            <span>
              {d.name}: {d.value}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ── Trending tech ─────────────────────────────────────────────────────────────

function TrendingTech({ data }: { data: DashboardPayload }) {
  const items = data.trending_tech.slice(0, 8);
  return (
    <Card title="Trending Technologies">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={items} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={80} tick={{ fill: "#71717A", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#FFFFFF", border: "1px solid #E4E1DC", borderRadius: 6, color: "#18181B", boxShadow: "0 4px 16px rgba(0,0,0,0.08)", fontSize: 12 }}
            formatter={(val: number) => [`${val} jobs`]}
          />
          <Bar dataKey="count" fill="#6366F1" radius={[0, 4, 4, 0]}>
            <LabelList dataKey="percentage" position="right" formatter={(v: number) => `${v}%`} style={{ fill: "#71717A", fontSize: 10 }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ── Market trends ─────────────────────────────────────────────────────────────

function MarketTrends({ data }: { data: DashboardPayload }) {
  const trends = data.insights.trends;
  if (!trends) return null;

  const chartData = [
    ...trends.rising.map((d) => ({ name: d.name, delta: d.delta })),
    ...trends.falling.map((d) => ({ name: d.name, delta: d.delta })),
  ].sort((a, b) => b.delta - a.delta);

  return (
    <Card title="Market Trends (7d)">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 30, left: 0, bottom: 0 }}>
          <XAxis type="number" tick={{ fill: "#71717A", fontSize: 10 }} />
          <YAxis type="category" dataKey="name" width={80} tick={{ fill: "#71717A", fontSize: 11 }} />
          <ReferenceLine x={0} stroke="#E4E1DC" />
          <Tooltip
            contentStyle={{ background: "#FFFFFF", border: "1px solid #E4E1DC", borderRadius: 6, color: "#18181B", boxShadow: "0 4px 16px rgba(0,0,0,0.08)", fontSize: 12 }}
            formatter={(val: number) => [`${val > 0 ? "+" : ""}${val} listings`]}
          />
          <Bar dataKey="delta" radius={[0, 4, 4, 0]}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.delta > 0 ? "#059669" : "#DC2626"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ── Salary bands ──────────────────────────────────────────────────────────────

function SalaryBands({ data }: { data: DashboardPayload }) {
  const salary = data.insights.salary;
  if (!salary) return null;

  return (
    <Card title="Salary by Skill">
      <div className="text-center mb-3">
        <span className="text-xs text-ink-muted">Median across {salary.count} ranked jobs</span>
        <div className="text-2xl font-display font-bold text-brand mt-1">{salary.median_display}</div>
        <div className="text-xs text-ink-muted mt-0.5">
          Range: {salary.min_display} – {salary.max_display}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={salary.high_paying} layout="vertical" margin={{ top: 0, right: 40, left: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={70} tick={{ fill: "#71717A", fontSize: 10 }} />
          <Tooltip
            contentStyle={{ background: "#FFFFFF", border: "1px solid #E4E1DC", borderRadius: 6, color: "#18181B", boxShadow: "0 4px 16px rgba(0,0,0,0.08)", fontSize: 12 }}
            formatter={(val: number) => [`¥${(val / 1_000_000).toFixed(1)}M avg`]}
          />
          <Bar dataKey="avg" fill="#4F46E5" radius={[0, 4, 4, 0]}>
            <LabelList
              dataKey="avg_display"
              position="right"
              style={{ fill: "#71717A", fontSize: 10 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ── Japanese ROI ──────────────────────────────────────────────────────────────

function JapaneseROI({ data }: { data: DashboardPayload }) {
  const jp = data.insights.jp;
  if (!jp) return null;

  return (
    <Card title="Japanese Language ROI">
      <div className="space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-ink-secondary">Currently reachable</span>
          <span className="font-bold text-emerald-700">{jp.reachable}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-ink-secondary">Locked behind JP requirement</span>
          <span className="font-bold text-amber-700">{jp.locked}</span>
        </div>
        <div className="w-full bg-base-surface border border-border rounded-full h-2 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-amber-400 to-amber-500 transition-all"
            style={{ width: `${jp.locked_pct}%` }}
          />
        </div>
        <p className="text-xs text-ink-muted">
          {jp.locked_pct}% of relevant roles are locked. Learning Japanese could unlock{" "}
          <span className="text-amber-700 font-semibold">+{jp.unlock_pct}%</span> more opportunities.
        </p>
        <div className="grid grid-cols-3 gap-2 pt-1">
          {(["n3", "n2", "n1"] as const).map((level) => (
            <div key={level} className="text-center p-2 bg-base-surface rounded border border-border">
              <div className="text-sm font-bold text-ink-primary">{jp.jlpt[level]}</div>
              <div className="text-[0.65rem] text-ink-muted">{level.toUpperCase()} unlock</div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

// ── Top companies ─────────────────────────────────────────────────────────────

function TopCompanies({ data }: { data: DashboardPayload }) {
  const companies = data.insights.companies;
  if (!companies || companies.length === 0) return null;
  const max = companies[0]?.count || 1;

  return (
    <Card title="Top Hiring Companies">
      <div className="space-y-2">
        {companies.map((c, i) => (
          <div key={c.name} className="flex items-center gap-2">
            <span className="text-xs text-ink-muted w-4 text-right">{i + 1}.</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs text-ink-primary truncate">{c.name}</span>
                <span className="text-xs text-ink-muted ml-2">{c.count}</span>
              </div>
              <div className="w-full bg-base-surface border border-border rounded-full h-1.5 overflow-hidden">
                <div
                  className="h-full bg-brand/60 rounded-full transition-all"
                  style={{ width: `${(c.count / max) * 100}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ── Shared card wrapper ───────────────────────────────────────────────────────

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-base-card border border-border rounded-md p-4 space-y-3">
      <h3 className="text-xs font-bold text-brand uppercase tracking-widest">{title}</h3>
      {children}
    </div>
  );
}

// ── Skeleton loader ───────────────────────────────────────────────────────────

function InsightsSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 p-4">
      <div className="col-span-full grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-md" />
        ))}
      </div>
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-64 rounded-md" />
      ))}
    </div>
  );
}
