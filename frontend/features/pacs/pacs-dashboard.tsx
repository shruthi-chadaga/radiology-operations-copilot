"use client";

import { useEffect, useState } from "react";
import { z } from "zod";

import type { PacsNode, PacsStudy } from "./pacs-operations-workspace";

type DashboardData = {
  total_studies: number;
  healthy_nodes: number;
  total_nodes: number;
  modality_counts: Record<string, number>;
  recent_study_count: number;
  recent_transfer_count: number;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DashboardSchema: z.ZodType<DashboardData> = z
  .object({
    total_studies: z.number().int(),
    healthy_nodes: z.number().int(),
    total_nodes: z.number().int(),
    modality_counts: z.record(z.string(), z.number().int()),
    recent_study_count: z.number().int(),
    recent_transfer_count: z.number().int(),
  })
  .strict();

type Props = {
  nodes: PacsNode[];
  studies: PacsStudy[];
};

function StatCard({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: number | string;
  sub?: string;
  color: "emerald" | "violet" | "cyan" | "amber";
}) {
  const colors = {
    emerald: "border-emerald-400/20 bg-emerald-400/5",
    violet: "border-violet-400/20 bg-violet-400/5",
    cyan: "border-cyan-400/20 bg-cyan-400/5",
    amber: "border-amber-400/20 bg-amber-400/5",
  };
  const textColors = {
    emerald: "text-emerald-200",
    violet: "text-violet-200",
    cyan: "text-cyan-200",
    amber: "text-amber-200",
  };
  return (
    <div
      className={`rounded-xl border ${colors[color]} p-5 backdrop-blur-sm transition-colors hover:border-opacity-50`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
        {label}
      </p>
      <p
        className={`mt-2 text-3xl font-bold tracking-tight ${textColors[color]}`}
      >
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export function PacsDashboard({ nodes, studies }: Props) {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiUrl}/api/v1/pacs/dashboard`, {
      credentials: "include",
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => setDashboard(DashboardSchema.parse(data)))
      .catch((err) => {
        if (err.name !== "AbortError") setError("Dashboard unavailable");
      });

    return () => controller.abort();
  }, []);

  const computedModalityCounts: Record<string, number> = {};
  for (const study of studies) {
    const mod = study.modality ?? "Unknown";
    computedModalityCounts[mod] = (computedModalityCounts[mod] ?? 0) + 1;
  }
  const modalityCounts =
    dashboard?.modality_counts &&
    Object.keys(dashboard.modality_counts).length > 0
      ? dashboard.modality_counts
      : computedModalityCounts;
  const topModalities = Object.entries(modalityCounts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6);
  const totalModalityStudies = Object.values(modalityCounts).reduce(
    (sum, v) => sum + v,
    0,
  );

  return (
    <section aria-labelledby="dashboard-title" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3
          id="dashboard-title"
          className="text-lg font-semibold tracking-tight"
        >
          PACS Dashboard
        </h3>
        <div className="flex flex-wrap items-center gap-3">
          {nodes.map((node) => (
            <div
              key={node.id}
              className="flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/80 px-3 py-1.5 text-xs"
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  node.last_health_status === "healthy"
                    ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]"
                    : "bg-amber-400"
                }`}
              />
              <span className="text-slate-300">{node.name}</span>
              <span className="text-slate-500">{node.dicom_ae_title}</span>
            </div>
          ))}
          {error && (
            <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-3 py-1 text-xs text-amber-200">
              {error}
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Studies"
          value={dashboard?.total_studies ?? studies.length}
          color="violet"
        />
        <StatCard
          label="Node Health"
          value={
            dashboard
              ? `${dashboard.healthy_nodes}/${dashboard.total_nodes}`
              : "—"
          }
          sub="healthy / total"
          color="emerald"
        />
        <StatCard
          label="Recent Studies"
          value={dashboard?.recent_study_count ?? 0}
          sub="last 24h"
          color="cyan"
        />
        <StatCard
          label="Recent Transfers"
          value={dashboard?.recent_transfer_count ?? 0}
          sub="last 24h"
          color="amber"
        />
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
        <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Modality distribution
        </h4>
        {topModalities.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">
            No modality data available. Sync inventory to populate.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {topModalities.map(([modality, count]) => {
              const pct =
                totalModalityStudies > 0
                  ? Math.round((count / totalModalityStudies) * 100)
                  : 0;
              return (
                <div key={modality} className="flex items-center gap-3">
                  <span className="w-16 text-sm font-mono font-medium text-slate-300">
                    {modality}
                  </span>
                  <div className="relative h-5 flex-1 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-700"
                      style={{ width: `${Math.max(pct, 4)}%` }}
                    />
                  </div>
                  <span className="w-14 text-right text-xs tabular-nums text-slate-400">
                    {count}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
