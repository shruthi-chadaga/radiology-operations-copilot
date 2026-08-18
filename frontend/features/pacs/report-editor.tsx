"use client";

import { useCallback, useEffect, useState } from "react";
import { z } from "zod";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const VersionSchema = z.object({ id: z.string(), version_number: z.number().int(), kind: z.string(), author_id: z.string(), indication: z.string(), findings: z.string(), impression: z.string(), correction_reason: z.string().nullable(), created_at: z.string() }).strict();
const ReportSchema = z.object({ id: z.string(), study_id: z.string(), status: z.string(), current_version_number: z.number().int().nullable(), finalized_by: z.string().nullable(), finalized_at: z.string().nullable(), created_at: z.string(), updated_at: z.string(), versions: z.array(VersionSchema) }).strict();
type Report = z.infer<typeof ReportSchema>;

type Props = { studyId: string; canWrite: boolean };

export function ReportEditor({ studyId, canWrite }: Props) {
  const [report, setReport] = useState<Report | null>(null);
  const [indication, setIndication] = useState("");
  const [findings, setFindings] = useState("");
  const [impression, setImpression] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const response = await fetch(`${apiUrl}/api/v1/imaging/studies/${studyId}/report`, { credentials: "include" });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error();
    return ReportSchema.parse(await response.json());
  }, [studyId]);

  useEffect(() => {
    let active = true;
    const timer = window.setTimeout(() => {
      setReport(null);
      setIndication("");
      setFindings("");
      setImpression("");
      setCorrectionReason("");
      setMessage("");
      void load().then((next) => {
        if (!active || !next) return;
        setReport(next);
        const version = next.versions[next.versions.length - 1];
        if (version) {
          setIndication(version.indication);
          setFindings(version.findings);
          setImpression(version.impression);
        }
      }).catch(() => { if (active) setMessage("Report status could not be loaded."); });
    }, 0);
    return () => { active = false; window.clearTimeout(timer); };
  }, [load]);

  async function request(path: string, body?: object) {
    setBusy(true); setMessage("");
    try {
      const response = await fetch(`${apiUrl}${path}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Report action failed");
      const next = ReportSchema.parse(payload); setReport(next);
      const version = next.versions[next.versions.length - 1];
      if (version) { setIndication(version.indication); setFindings(version.findings); setImpression(version.impression); }
      setMessage("Saved to the immutable report history.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Report action failed."); } finally { setBusy(false); }
  }

  const finalized = report?.status === "finalized";
  const expectedVersionNumber = report?.current_version_number ?? undefined;
  const hasAuthoredContent = Boolean(indication.trim() && findings.trim() && impression.trim());
  const hasExpectedVersion = expectedVersionNumber !== undefined;
  const trimmedCorrectionReason = correctionReason.trim();
  const draftBody = {
    indication,
    findings,
    impression,
    ...(expectedVersionNumber === undefined ? {} : { expected_version_number: expectedVersionNumber }),
  };
  return <section className="rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-6" aria-label="Report workspace">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">Authored report</p><h3 className="mt-1 text-xl font-semibold text-slate-100">Draft and sign report</h3><p className="mt-2 max-w-2xl text-sm text-slate-400">User-authored synthetic text only. This workspace does not interpret images or provide diagnostic advice.</p></div><span className="rounded-full border border-emerald-400/30 px-3 py-1 text-xs text-emerald-200">{report?.status ?? "not started"}</span></div>
    {canWrite ? <div className="mt-6 space-y-4"><label className="block text-sm text-slate-300">Indication<input value={indication} onChange={(event) => setIndication(event.target.value)} disabled={busy} aria-describedby="report-validation-hint" className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm" maxLength={400} /></label><label className="block text-sm text-slate-300">Findings<textarea value={findings} onChange={(event) => setFindings(event.target.value)} disabled={busy} aria-describedby="report-validation-hint" className="mt-1 min-h-28 w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm" maxLength={12000} /></label><label className="block text-sm text-slate-300">Impression<textarea value={impression} onChange={(event) => setImpression(event.target.value)} disabled={busy} aria-describedby="report-validation-hint" className="mt-1 min-h-20 w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm" maxLength={4000} /></label><p id="report-validation-hint" className="text-xs text-slate-500">Complete all three authored fields before saving or creating a correction.</p><div className="flex flex-wrap gap-3"><button type="button" disabled={finalized || busy || !hasAuthoredContent} onClick={() => void request(`/api/v1/imaging/studies/${studyId}/report/draft`, draftBody)} className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-50">Save draft</button>{report && !finalized && <button type="button" disabled={busy || !hasAuthoredContent || !hasExpectedVersion} onClick={() => void request(`/api/v1/imaging/reports/${report.id}/finalize`, { expected_version_number: report.current_version_number })} className="rounded-lg border border-emerald-300/40 px-4 py-2 text-sm font-semibold text-emerald-100 disabled:opacity-50">Finalize authored report</button>}</div>{finalized && <div className="space-y-3 rounded-lg border border-amber-400/20 bg-amber-400/5 p-4"><p className="text-sm text-amber-100">Finalized versions are immutable. Create a correction to add a new version.</p><p id="correction-reason-hint" className="text-xs text-slate-500">A nonblank correction reason is required.</p><input value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} placeholder="Correction reason" aria-describedby="correction-reason-hint" className="w-full rounded-lg border border-slate-700 bg-slate-950/60 px-3 py-2 text-sm" maxLength={1000} /><button type="button" disabled={busy || !hasAuthoredContent || !trimmedCorrectionReason || !hasExpectedVersion} onClick={() => void request(`/api/v1/imaging/reports/${report.id}/correction`, { indication, findings, impression, correction_reason: trimmedCorrectionReason, expected_version_number: report.current_version_number })} className="rounded-lg border border-amber-300/40 px-4 py-2 text-sm font-semibold text-amber-100 disabled:opacity-50">Create correction version</button></div>}</div> : <p className="mt-5 text-sm text-slate-400">Read-only role. Report history is available to authorized operators; editing and finalization are restricted.</p>}
    {report && <div className="mt-6 border-t border-emerald-400/10 pt-4"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Immutable version history</p><ol className="mt-3 space-y-2">{report.versions.map((version) => <li key={version.id} className="flex flex-wrap justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs"><span className="text-slate-300">v{version.version_number} · {version.kind}</span><span className="text-slate-500">{new Date(version.created_at).toLocaleString()}</span></li>)}</ol></div>}
    <p aria-live="polite" className="mt-4 text-xs text-slate-400">{message}</p>
  </section>;
}
