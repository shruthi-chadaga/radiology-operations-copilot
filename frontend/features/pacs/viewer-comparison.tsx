"use client";

import { useEffect, useMemo, useState } from "react";

type ViewerStudy = {
  study_id: string;
  accession_number: string;
  study_instance_uid: string;
  study_date: string | null;
  modality: string | null;
  study_description: string | null;
  is_synthetic: boolean;
  preview_available: boolean;
  representative_instance_id: string | null;
  series_count: number;
  instance_count: number;
};

type Props = { current: ViewerStudy; priors: ViewerStudy[] };
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function PreviewPane({ study, label }: { study: ViewerStudy; label: string }) {
  const [brightness, setBrightness] = useState(100);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const previewEndpoint = study.representative_instance_id
    ? `${apiUrl}/api/v1/imaging/studies/${study.study_id}/preview/${study.representative_instance_id}`
    : null;

  useEffect(() => {
    if (!previewEndpoint || !study.preview_available) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    void fetch(previewEndpoint, {
      credentials: "include",
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setPreviewUrl(objectUrl);
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name !== "AbortError")
          setPreviewError(true);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [previewEndpoint, study.preview_available]);

  const showPreview = Boolean(
    previewEndpoint && study.preview_available && previewUrl && !previewError,
  );
  return (
    <article className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/80">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
            {label}
          </p>
          <h5 className="mt-1 font-medium text-slate-200">
            {study.study_description ?? study.accession_number}
          </h5>
          <p className="mt-1 text-xs text-slate-500">
            {study.study_date ?? "Date unavailable"} ·{" "}
            {study.modality ?? "Modality unavailable"}
          </p>
        </div>
        <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-amber-200">
          Synthetic
        </span>
      </div>
      <div className="relative flex aspect-[4/3] items-center justify-center overflow-hidden bg-slate-950 p-4">
        {showPreview ? (
          <img
            src={previewUrl ?? ""}
            alt={`${label} synthetic preview`}
            className="max-h-full max-w-full object-contain"
            style={{ filter: `brightness(${brightness}%)` }}
          />
        ) : (
          <div className="text-center text-sm text-slate-500">
            <p>
              {previewError
                ? "Preview could not be loaded"
                : "Preview unavailable"}
            </p>
            <p className="mt-1 text-xs">Study metadata remains available.</p>
          </div>
        )}
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="rotate-[-24deg] text-2xl font-black uppercase tracking-[0.35em] text-white/10">
            Synthetic demo
          </span>
        </div>
      </div>
      <div className="border-t border-slate-800 px-4 py-3">
        <label className="flex items-center gap-3 text-xs text-slate-400">
          Brightness{" "}
          <input
            aria-label={`${label} brightness`}
            type="range"
            min="50"
            max="160"
            value={brightness}
            onChange={(event) => setBrightness(Number(event.target.value))}
            className="min-w-0 flex-1 accent-cyan-400"
          />
          <span className="w-8 text-right tabular-nums">{brightness}%</span>
        </label>
        <p className="mt-2 text-[11px] text-slate-600">
          {study.series_count} series · {study.instance_count} instances ·
          rendered preview only
        </p>
      </div>
    </article>
  );
}

export function ViewerComparison({ current, priors }: Props) {
  const [selectedPriorId, setSelectedPriorId] = useState("");
  const selectedPrior = useMemo(
    () => priors.find((prior) => prior.study_id === selectedPriorId) ?? null,
    [priors, selectedPriorId],
  );
  return (
    <section
      aria-labelledby="viewer-comparison-heading"
      className="rounded-2xl border border-cyan-400/20 bg-cyan-400/5 p-6"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200">
            Phase 2 view
          </p>
          <h4
            id="viewer-comparison-heading"
            className="mt-1 text-xl font-semibold"
          >
            Current study and prior comparison
          </h4>
          <p className="mt-1 max-w-2xl text-sm text-slate-400">
            Server-rendered synthetic previews with deterministic prior
            matching. This is a viewing surface, not image interpretation.
          </p>
        </div>
        {priors.length > 0 && (
          <label className="text-xs text-slate-400">
            Compare prior
            <select
              aria-label="Compare prior"
              value={selectedPriorId}
              onChange={(event) => setSelectedPriorId(event.target.value)}
              className="ml-2 rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-200"
            >
              <option value="">No prior</option>
              {priors.map((prior) => (
                <option key={prior.study_id} value={prior.study_id}>
                  {prior.study_date ?? prior.accession_number}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div
        className={`mt-6 grid gap-4 ${selectedPrior ? "lg:grid-cols-2" : "max-w-2xl"}`}
      >
        <PreviewPane key={current.study_id} study={current} label="Current" />
        {selectedPrior && (
          <PreviewPane
            key={selectedPrior.study_id}
            study={selectedPrior}
            label="Prior"
          />
        )}
      </div>
      {priors.length === 0 && (
        <p className="mt-4 text-xs text-slate-500">
          No earlier same-patient, same-modality synthetic study matched by
          date.
        </p>
      )}
      <p className="mt-5 text-xs text-amber-200/80">
        Synthetic preview only. No diagnosis, measurement, clinical
        interpretation, or image-derived recommendation is provided.
      </p>
    </section>
  );
}

export type { ViewerStudy };
