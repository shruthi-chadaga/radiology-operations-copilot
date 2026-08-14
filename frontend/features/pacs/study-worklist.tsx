"use client";

import { useMemo, useState, type ReactNode } from "react";
import type { PacsNode, PacsStudy } from "./pacs-operations-workspace";

type SortField =
  | "accession_number"
  | "patient_id"
  | "patient_name"
  | "modality"
  | "study_date"
  | "study_description";
type SortDir = "asc" | "desc";

const MODALITY_LABELS: Record<string, string> = {
  OT: "Other",
  CT: "CT",
  MR: "MR",
  US: "Ultrasound",
  XA: "Angiography",
  CR: "Computed Radiography",
  DX: "Digital Radiography",
  NM: "Nuclear Medicine",
  PT: "PET",
  MG: "Mammography",
};

type Props = {
  studies: PacsStudy[];
  nodes: PacsNode[];
  onSelectStudy: (study: PacsStudy) => void;
  selectedStudyId?: string | null;
};

type WorklistHeaderProps = {
  field: SortField;
  currentField: SortField;
  direction: SortDir;
  onSort: (field: SortField) => void;
  children: ReactNode;
};

const nodeNameById = (nodes: PacsNode[], id: string) =>
  nodes.find((node) => node.id === id)?.name ?? "—";

function WorklistHeader({
  field,
  currentField,
  direction,
  onSort,
  children,
}: WorklistHeaderProps) {
  return (
    <th
      className="cursor-pointer select-none px-3 py-3 text-left transition-colors hover:text-slate-200"
      onClick={() => onSort(field)}
    >
      {children}
      {currentField === field && (
        <span className="ml-1 inline-block text-violet-300">
          {direction === "asc" ? "↑" : "↓"}
        </span>
      )}
    </th>
  );
}

export function StudyWorklist({
  studies,
  nodes,
  onSelectStudy,
  selectedStudyId,
}: Props) {
  const [filterText, setFilterText] = useState("");
  const [modalityFilter, setModalityFilter] = useState("");
  const [sortField, setSortField] = useState<SortField>("study_date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [showTechnical, setShowTechnical] = useState(false);

  const allModalities = useMemo(() => {
    const values = new Set<string>();
    for (const study of studies) {
      if (study.modality) values.add(study.modality);
    }
    return [...values].sort();
  }, [studies]);

  const filtered = useMemo(() => {
    let list = studies;
    if (filterText.trim()) {
      const query = filterText.toLowerCase();
      list = list.filter(
        (study) =>
          study.accession_number.toLowerCase().includes(query) ||
          study.patient_id.toLowerCase().includes(query) ||
          (study.patient_name ?? "").toLowerCase().includes(query) ||
          (study.study_description ?? "").toLowerCase().includes(query),
      );
    }
    if (modalityFilter) {
      list = list.filter((study) => study.modality === modalityFilter);
    }
    return [...list].sort((a, b) => {
      const aValue = a[sortField] ?? "";
      const bValue = b[sortField] ?? "";
      const comparison = aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      return sortDir === "asc" ? comparison : -comparison;
    });
  }, [studies, filterText, modalityFilter, sortField, sortDir]);

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }

  return (
    <section aria-labelledby="worklist-title" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 id="worklist-title" className="text-lg font-semibold tracking-tight">
            Imaging Worklist
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Select a study to review its patient context and study content.
          </p>
        </div>
        <span className="text-xs text-slate-500">
          {filtered.length} of {studies.length} studies
        </span>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="relative min-w-[200px] flex-1">
          <svg
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            placeholder="Search accession, patient, description…"
            value={filterText}
            onChange={(event) => setFilterText(event.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-10 pr-4 text-sm text-slate-200 placeholder:text-slate-500 focus:border-violet-400/50 focus:outline-none focus:ring-1 focus:ring-violet-400/30"
          />
        </div>
        <select
          value={modalityFilter}
          onChange={(event) => setModalityFilter(event.target.value)}
          className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 text-sm text-slate-200 focus:border-violet-400/50 focus:outline-none"
        >
          <option value="">All modalities</option>
          {allModalities.map((modality) => (
            <option key={modality} value={modality}>
              {MODALITY_LABELS[modality] ?? modality}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-pressed={showTechnical}
          onClick={() => setShowTechnical((value) => !value)}
          className="rounded-xl border border-slate-700 px-3 py-2.5 text-sm text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
        >
          {showTechnical ? "Hide technical details" : "Show technical details"}
        </button>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-10 text-center">
          <p className="text-sm text-slate-500">
            {studies.length === 0
              ? "No synthetic studies received yet. An administrator can synchronize the imaging inbox from System Operations."
              : "No studies match the current filters."}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900/60">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-slate-700 text-xs uppercase tracking-wider text-slate-400">
              <tr>
                <WorklistHeader field="accession_number" currentField={sortField} direction={sortDir} onSort={toggleSort}>
                  Accession #
                </WorklistHeader>
                <WorklistHeader field="patient_id" currentField={sortField} direction={sortDir} onSort={toggleSort}>
                  Patient ID
                </WorklistHeader>
                <WorklistHeader field="patient_name" currentField={sortField} direction={sortDir} onSort={toggleSort}>
                  Patient Name
                </WorklistHeader>
                <WorklistHeader field="modality" currentField={sortField} direction={sortDir} onSort={toggleSort}>
                  Modality
                </WorklistHeader>
                <WorklistHeader field="study_date" currentField={sortField} direction={sortDir} onSort={toggleSort}>
                  Study Date
                </WorklistHeader>
                <WorklistHeader field="study_description" currentField={sortField} direction={sortDir} onSort={toggleSort}>
                  Study
                </WorklistHeader>
                {showTechnical && <th className="px-3 py-3">Storage</th>}
                {showTechnical && <th className="px-3 py-3">Content</th>}
              </tr>
            </thead>
            <tbody>
              {filtered.map((study) => {
                const isSelected = study.id === selectedStudyId;
                return (
                  <tr
                    key={study.id}
                    onClick={() => onSelectStudy(study)}
                    className={`cursor-pointer border-b border-slate-800/50 transition-colors hover:bg-slate-800/40 ${
                      isSelected
                        ? "bg-violet-400/10 ring-1 ring-inset ring-violet-400/20"
                        : ""
                    }`}
                  >
                    <td className="px-3 py-3.5 font-mono font-medium text-violet-200">
                      {study.accession_number}
                    </td>
                    <td className="px-3 py-3.5 font-mono text-xs">{study.patient_id}</td>
                    <td className="px-3 py-3.5 text-slate-200">{study.patient_name ?? "—"}</td>
                    <td className="px-3 py-3.5">
                      <span className="rounded-full border border-slate-600 bg-slate-800 px-2 py-0.5 text-xs font-medium">
                        {MODALITY_LABELS[study.modality ?? ""] ?? study.modality ?? "—"}
                      </span>
                    </td>
                    <td className="px-3 py-3.5 text-xs text-slate-400">
                      {study.study_date
                        ? `${study.study_date.slice(0, 4)}-${study.study_date.slice(4, 6)}-${study.study_date.slice(6, 8)}`
                        : "—"}
                    </td>
                    <td className="max-w-[260px] truncate px-3 py-3.5 text-slate-300">
                      {study.study_description ?? "—"}
                    </td>
                    {showTechnical && (
                      <td className="px-3 py-3.5 text-xs text-slate-500">
                        {nodeNameById(nodes, study.node_id)}
                      </td>
                    )}
                    {showTechnical && (
                      <td className="px-3 py-3.5 text-xs tabular-nums text-slate-500">
                        {study.series_count} series · {study.instance_count} instances
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
