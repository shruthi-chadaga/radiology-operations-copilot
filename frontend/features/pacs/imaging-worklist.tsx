"use client";

import { useMemo, useState } from "react";

type WorklistItem = {
  id: string; patient_id: string | null; pacs_patient_id: string; patient_name: string | null; patient_birth_date: string | null;
  accession_number: string; modality: string | null; study_description: string | null; study_date: string | null;
  workflow_status: string; priority: string; assigned_reader_id: string | null; report_status: string;
  scheduled_at: string | null; received_at: string | null; pacs_study_id: string | null; appointment_id: string | null;
};

type Props = { items: WorklistItem[]; onSelect: (item: WorklistItem) => void };
const STATUS_LABELS: Record<string, string> = { scheduled: "Scheduled", received: "Received", ready_for_review: "Ready for review", in_review: "In review", report_draft: "Report draft", finalized: "Finalized", cancelled: "Cancelled" };
const MODALITY_LABELS: Record<string, string> = { CT: "CT", MR: "MR", US: "Ultrasound", DX: "X-ray", CR: "X-ray", MG: "Mammogram" };

function formatDate(value: string | null) {
  if (!value) return "—";
  if (/^\d{8}$/.test(value)) return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}`;
  return new Date(value).toLocaleDateString();
}
function StatusBadge({ value }: { value: string }) {
  const color = value === "ready_for_review" ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200" : value === "in_review" || value === "report_draft" ? "border-cyan-400/30 bg-cyan-400/10 text-cyan-200" : "border-slate-600 bg-slate-800 text-slate-300";
  return <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${color}`}>{STATUS_LABELS[value] ?? value}</span>;
}

export function ImagingWorklist({ items, onSelect }: Props) {
  const [query, setQuery] = useState(""); const [status, setStatus] = useState(""); const [modality, setModality] = useState(""); const [showAssignment, setShowAssignment] = useState(false);
  const modalities = useMemo(() => [...new Set(items.map((item) => item.modality).filter(Boolean))].sort(), [items]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      const matchesQuery = !normalized || [item.accession_number, item.pacs_patient_id, item.patient_name ?? "", item.study_description ?? ""].some((value) => value.toLowerCase().includes(normalized));
      return matchesQuery && (!status || item.workflow_status === status) && (!modality || item.modality === modality);
    });
  }, [items, modality, query, status]);
  return <section aria-labelledby="imaging-worklist-heading" className="space-y-4">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">Radiology desk</p><h3 id="imaging-worklist-heading" className="mt-1 text-xl font-semibold">Unified imaging worklist</h3><p className="mt-1 text-sm text-slate-500">Scheduled and received studies, with technical storage details kept out of the way.</p></div><span className="text-xs tabular-nums text-slate-500">{filtered.length} of {items.length} work items</span></div>
    <div className="flex flex-wrap gap-3"><input aria-label="Search imaging worklist" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search patient, accession, exam…" className="min-w-[220px] flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-2.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-violet-400/50 focus:outline-none" /><select aria-label="Filter worklist status" value={status} onChange={(event) => setStatus(event.target.value)} className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200"><option value="">All statuses</option>{Object.entries(STATUS_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><select aria-label="Filter worklist modality" value={modality} onChange={(event) => setModality(event.target.value)} className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200"><option value="">All modalities</option>{modalities.map((value) => <option key={value} value={value ?? ""}>{MODALITY_LABELS[value ?? ""] ?? value}</option>)}</select><button type="button" aria-pressed={showAssignment} onClick={() => setShowAssignment((value) => !value)} className="rounded-xl border border-slate-700 px-3 py-2.5 text-sm text-slate-300 hover:border-slate-500 hover:text-white">{showAssignment ? "Hide assignment" : "Show assignment"}</button></div>
    {filtered.length === 0 ? <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-10 text-center text-sm text-slate-500">No imaging work items match the current filters.</div> : <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60"><table className="w-full min-w-[920px] text-left text-sm"><thead className="border-b border-slate-700 text-xs uppercase tracking-wider text-slate-400"><tr><th className="px-4 py-3">Priority</th><th className="px-4 py-3">Patient / accession</th><th className="px-4 py-3">Exam</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Report</th>{showAssignment && <th className="px-4 py-3">Assignment</th>}<th className="px-4 py-3">Date</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id} onClick={() => onSelect(item)} className="cursor-pointer border-b border-slate-800/60 transition-colors last:border-0 hover:bg-slate-800/40"><td className="px-4 py-4"><span className={item.priority === "stat" ? "font-semibold text-rose-300" : item.priority === "urgent" ? "font-semibold text-amber-200" : "text-slate-400"}>{item.priority.toUpperCase()}</span></td><td className="px-4 py-4"><p className="font-medium text-slate-200">{item.patient_name ?? item.pacs_patient_id}</p><p className="mt-1 font-mono text-xs text-violet-200">{item.accession_number}</p></td><td className="px-4 py-4"><p className="text-slate-200">{MODALITY_LABELS[item.modality ?? ""] ?? item.modality ?? "—"}</p><p className="mt-1 max-w-[220px] truncate text-xs text-slate-500">{item.study_description ?? "—"}</p></td><td className="px-4 py-4"><StatusBadge value={item.workflow_status} /></td><td className="px-4 py-4 text-xs text-slate-400">{item.report_status.replaceAll("_", " ")}</td>{showAssignment && <td className="px-4 py-4 text-xs text-slate-400">{item.assigned_reader_id ?? "Unassigned"}</td>}<td className="px-4 py-4 text-xs text-slate-400">{formatDate(item.study_date ?? item.scheduled_at)}</td></tr>)}</tbody></table></div>}
  </section>;
}
export type { WorklistItem };
