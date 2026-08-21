"use client";

import { useCallback, useEffect, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/session-context";
import { IncidentReviewPanel } from "@/features/pacs/incident-review-panel";
import { PacsDashboard } from "@/features/pacs/pacs-dashboard";
import {
  PacsOperationsWorkspace,
  type PacsNode,
  type PacsStudy,
} from "@/features/pacs/pacs-operations-workspace";
import {
  ImagingWorklist,
  type WorklistItem,
} from "@/features/pacs/imaging-worklist";
import {
  PatientTimeline,
  type TimelineEvent,
} from "@/features/pacs/patient-timeline";
import { ReportEditor } from "@/features/pacs/report-editor";
import { StudyDetail } from "@/features/pacs/study-detail";
import {
  ViewerComparison,
  type ViewerStudy,
} from "@/features/pacs/viewer-comparison";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const NodePageSchema = z
  .object({
    items: z.array(
      z
        .object({
          id: z.string(),
          name: z.string(),
          node_type: z.string(),
          dicom_ae_title: z.string(),
          active: z.boolean(),
          last_health_status: z.string().nullable(),
          last_health_at: z.string().nullable(),
        })
        .strict(),
    ),
  })
  .strict();
const StudyPageSchema = z
  .object({
    items: z.array(
      z
        .object({
          id: z.string(),
          node_id: z.string(),
          study_instance_uid: z.string(),
          accession_number: z.string(),
          patient_id: z.string(),
          patient_name: z.string().nullable(),
          patient_birth_date: z.string().nullable(),
          patient_sex: z.string().nullable(),
          study_date: z.string().nullable(),
          study_description: z.string().nullable(),
          modality: z.string().nullable(),
          series_count: z.number().int(),
          instance_count: z.number().int(),
        })
        .strict(),
    ),
  })
  .strict();
const WorklistSchema = z
  .object({
    items: z.array(
      z
        .object({
          id: z.string(),
          patient_id: z.string().nullable(),
          pacs_patient_id: z.string(),
          patient_name: z.string().nullable(),
          patient_birth_date: z.string().nullable(),
          accession_number: z.string(),
          modality: z.string().nullable(),
          study_description: z.string().nullable(),
          study_date: z.string().nullable(),
          workflow_status: z.string(),
          priority: z.string(),
          assigned_reader_id: z.string().nullable(),
          report_status: z.string(),
          scheduled_at: z.string().nullable(),
          received_at: z.string().nullable(),
          pacs_study_id: z.string().nullable(),
          appointment_id: z.string().nullable(),
        })
        .strict(),
    ),
    generated_at: z.string(),
  })
  .strict();
const TimelineSchema = z
  .object({
    patient_id: z.string(),
    external_patient_id: z.string(),
    patient_name: z.string(),
    events: z.array(
      z
        .object({
          event_type: z.string(),
          event_id: z.string(),
          occurred_at: z.string(),
          label: z.string(),
          detail: z.string(),
          status: z.string(),
        })
        .strict(),
    ),
  })
  .strict();
const ViewerStudySchema: z.ZodType<ViewerStudy> = z
  .object({
    study_id: z.string(),
    accession_number: z.string(),
    study_instance_uid: z.string(),
    study_date: z.string().nullable(),
    modality: z.string().nullable(),
    study_description: z.string().nullable(),
    is_synthetic: z.boolean(),
    preview_available: z.boolean(),
    representative_instance_id: z.string().nullable(),
    series_count: z.number().int(),
    instance_count: z.number().int(),
  })
  .strict();
const ViewerSchema = z
  .object({ current: ViewerStudySchema, priors: z.array(ViewerStudySchema) })
  .strict();

type SelectedContext = {
  item: WorklistItem;
  events: TimelineEvent[];
  patientName: string;
  externalPatientId: string;
};

export default function PacsOpsPage() {
  const { user, loading: sessionLoading } = useSession();
  const role = user?.role;
  const canWrite = role === "pacs_admin" || role === "operations_manager";
  const canRead = ["pacs_admin", "operations_manager", "auditor"].includes(
    role ?? "",
  );
  const canReviewIncidents = role === "system_admin";
  const [nodes, setNodes] = useState<PacsNode[]>([]);
  const [studies, setStudies] = useState<PacsStudy[]>([]);
  const [worklist, setWorklist] = useState<WorklistItem[]>([]);
  const [selectedContext, setSelectedContext] =
    useState<SelectedContext | null>(null);
  const [viewer, setViewer] = useState<{
    current: ViewerStudy;
    priors: ViewerStudy[];
  } | null>(null);
  const [viewerError, setViewerError] = useState("");
  const [showOperations, setShowOperations] = useState(false);
  const [message, setMessage] = useState(
    "Imaging workspace ready — synthetic metadata only",
  );
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [nodeResponse, studyResponse, worklistResponse] = await Promise.all(
        [
          fetch(`${apiUrl}/api/v1/pacs/nodes`, { credentials: "include" }),
          fetch(`${apiUrl}/api/v1/pacs/studies`, { credentials: "include" }),
          fetch(`${apiUrl}/api/v1/imaging/worklist`, {
            credentials: "include",
          }),
        ],
      );
      if (
        [nodeResponse, studyResponse, worklistResponse].some(
          (response) => !response.ok,
        )
      ) {
        throw new Error("workspace data unavailable");
      }
      const [nodePayload, studyPayload, worklistPayload] = await Promise.all([
        nodeResponse.json(),
        studyResponse.json(),
        worklistResponse.json(),
      ]);
      setNodes(NodePageSchema.parse(nodePayload).items);
      setStudies(StudyPageSchema.parse(studyPayload).items);
      setWorklist(WorklistSchema.parse(worklistPayload).items);
      setMessage("Imaging workspace ready — synthetic metadata only");
    } catch {
      setMessage("Imaging workspace data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionLoading || !user || !canRead) return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [sessionLoading, user, canRead, loadData]);

  async function selectWorklistItem(item: WorklistItem) {
    setViewer(null);
    setViewerError("");
    const fallback = {
      item,
      events: [],
      patientName: item.patient_name ?? item.pacs_patient_id,
      externalPatientId: item.pacs_patient_id,
    };
    if (!item.patient_id) {
      setSelectedContext(fallback);
      return;
    }
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/imaging/patients/${item.patient_id}/timeline`,
        { credentials: "include" },
      );
      if (!response.ok) throw new Error();
      const payload = TimelineSchema.parse(await response.json());
      setSelectedContext({
        item,
        events: payload.events,
        patientName: payload.patient_name,
        externalPatientId: payload.external_patient_id,
      });
    } catch {
      setSelectedContext(fallback);
    }
  }

  async function loadViewer(studyId: string) {
    setViewerError("");
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/imaging/studies/${studyId}/viewer`,
        { credentials: "include" },
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setViewer(ViewerSchema.parse(await response.json()));
    } catch {
      setViewer(null);
      setViewerError(
        "The synthetic viewer could not prepare a rendered preview. Study metadata remains available.",
      );
    }
  }

  const selectedStudy = selectedContext?.item.pacs_study_id
    ? studies.find((study) => study.id === selectedContext.item.pacs_study_id)
    : undefined;

  return (
    <section aria-labelledby="pacs-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-violet-300">Workspace 01</p>
          <h2
            id="pacs-title"
            className="mt-1 text-3xl font-bold tracking-tight"
          >
            Imaging Workspace
          </h2>
          <p className="mt-3 max-w-3xl text-slate-400">
            Receive, find, review, and track synthetic imaging studies.
            Technical storage operations remain available when an operator needs
            them.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {selectedContext && (
            <button
              onClick={() => {
                setSelectedContext(null);
                setViewer(null);
              }}
              className="rounded-full border border-slate-700 px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            >
              ← Worklist
            </button>
          )}
          <span className="rounded-full border border-violet-400/30 bg-violet-400/10 px-3 py-1 text-sm text-violet-100">
            Metadata + preview mode
          </span>
        </div>
      </div>
      {!sessionLoading && loading && canRead && (
        <div className="mt-12 text-sm text-slate-400">
          Loading imaging worklist…
        </div>
      )}
      {!sessionLoading && !canRead && !canReviewIncidents && (
        <div className="mt-8 rounded-2xl border border-amber-400/20 bg-amber-400/5 p-6 text-sm text-amber-100">
          Sign in with an imaging-authorized local account.
        </div>
      )}
      {!sessionLoading && canReviewIncidents && (
        <section
          aria-labelledby="incident-approval-console-title"
          className="mt-8 rounded-2xl border border-amber-400/20 bg-amber-400/5 p-6"
        >
          <h3
            id="incident-approval-console-title"
            className="text-lg font-semibold text-slate-100"
          >
            Incident approval console
          </h3>
          <p className="mt-2 max-w-3xl text-sm text-slate-400">
            Your role is authorized to review incident approval evidence and
            decide proposals. Imaging storage operations remain limited to
            imaging-authorized accounts.
          </p>
          <IncidentReviewPanel />
        </section>
      )}
      {!loading && canRead && (
        <div className="mt-8 space-y-8">
          {selectedContext ? (
            <div className="space-y-6">
              <div className="rounded-2xl border border-violet-400/20 bg-violet-400/5 p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-200">
                  Selected work item
                </p>
                <h3 className="mt-2 text-2xl font-semibold">
                  {selectedContext.item.study_description ??
                    selectedContext.item.accession_number}
                </h3>
                <p className="mt-2 text-sm text-slate-400">
                  {selectedContext.item.patient_name ??
                    selectedContext.item.pacs_patient_id}{" "}
                  · {selectedContext.item.accession_number}
                </p>
              </div>
              <PatientTimeline
                patientName={selectedContext.patientName}
                externalPatientId={selectedContext.externalPatientId}
                events={selectedContext.events}
              />
              {selectedStudy ? (
                <>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={() => void loadViewer(selectedStudy.id)}
                      className="rounded-xl bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 hover:bg-cyan-400"
                    >
                      Open synthetic viewer
                    </button>
                    {viewerError && (
                      <p className="text-sm text-amber-200">{viewerError}</p>
                    )}
                  </div>
                  {viewer && (
                    <ViewerComparison
                      current={viewer.current}
                      priors={viewer.priors}
                    />
                  )}
                  <ReportEditor
                    studyId={selectedStudy.id}
                    canWrite={canWrite}
                  />
                  <StudyDetail
                    key={selectedStudy.id}
                    study={selectedStudy}
                    nodes={nodes}
                    canWrite={canWrite}
                    onClose={() => setSelectedContext(null)}
                    onTransfer={() => setShowOperations(true)}
                  />
                </>
              ) : (
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 text-sm text-slate-400">
                  This work item has no separately loaded PACS study metadata.
                  Viewer and reporting remain unavailable.
                </div>
              )}
            </div>
          ) : (
            <>
              <section className="rounded-2xl border border-violet-400/20 bg-gradient-to-br from-violet-400/10 via-slate-900/60 to-cyan-400/5 p-6">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-200">
                  Today&apos;s imaging desk
                </p>
                <h3 className="mt-2 text-2xl font-semibold">
                  What needs attention?
                </h3>
                <p className="mt-2 max-w-2xl text-sm text-slate-300">
                  Prioritized work items connect scheduled exams with received
                  synthetic studies and longitudinal patient context.
                </p>
              </section>
              <ImagingWorklist items={worklist} onSelect={selectWorklistItem} />
            </>
          )}
          <details
            className="rounded-2xl border border-slate-800 bg-slate-900/40"
            open={showOperations}
            onToggle={(event) => setShowOperations(event.currentTarget.open)}
          >
            <summary className="cursor-pointer list-none px-6 py-4 text-left">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                    System Operations
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Administrator tools: node health, inventory sync, transfers,
                    reconciliation, and incident review
                  </p>
                </div>
                <span className="text-xs text-slate-500">
                  Show technical details
                </span>
              </div>
            </summary>
            <div className="border-t border-slate-800 px-6 pb-6 pt-4">
              <PacsDashboard nodes={nodes} studies={studies} />
              <PacsOperationsWorkspace
                nodes={nodes}
                studies={studies}
                canWrite={canWrite}
                preselectedStudyId={
                  selectedContext?.item.pacs_study_id ?? undefined
                }
                embedded
              />
              <IncidentReviewPanel />
            </div>
          </details>
          <p aria-live="polite" className="text-sm text-slate-500">
            {message}
          </p>
        </div>
      )}
    </section>
  );
}
