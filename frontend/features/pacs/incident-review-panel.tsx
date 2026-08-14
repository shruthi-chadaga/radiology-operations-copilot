"use client";

import { useCallback, useEffect, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/session-context";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ApprovalSchema = z.object({ decision: z.string(), decision_reason: z.string() }).passthrough();
const ProposalSchema = z
  .object({
    id: z.string(),
    requested_action: z.string(),
    proposer_id: z.string(),
    status: z.string(),
    rationale: z.string(),
    approval: ApprovalSchema.nullable(),
  })
  .passthrough();
const IncidentSchema = z
  .object({
    id: z.string(),
    incident_number: z.string(),
    category: z.string(),
    severity: z.string(),
    status: z.string(),
    approval_state: z.string(),
    retry_candidate: z.boolean(),
    redacted_summary: z.string(),
    proposals: z.array(ProposalSchema),
  })
  .passthrough();
const IncidentPageSchema = z.object({ items: z.array(IncidentSchema) }).strict();

type Incident = z.infer<typeof IncidentSchema>;
type Proposal = z.infer<typeof ProposalSchema>;

function canPropose(role: string | undefined) {
  return role === "pacs_admin" || role === "operations_manager";
}

function canDecide(role: string | undefined) {
  return role === "operations_manager" || role === "system_admin";
}

export function IncidentReviewPanel() {
  const { user, loading: sessionLoading } = useSession();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [rationales, setRationales] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState("");

  const loadIncidents = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/incidents`, { credentials: "include" });
      if (!response.ok) throw new Error();
      setIncidents(IncidentPageSchema.parse(await response.json()).items);
    } catch {
      setMessage("Incident review data could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const authorized =
      canDecide(user?.role) || canPropose(user?.role) || user?.role === "auditor";
    if (sessionLoading || !user || !authorized) return;
    const timer = window.setTimeout(() => void loadIncidents(), 0);
    return () => window.clearTimeout(timer);
  }, [loadIncidents, sessionLoading, user]);

  async function createProposal(incident: Incident) {
    const rationale = rationales[incident.id]?.trim() ?? "";
    if (!rationale) {
      setMessage("A proposal rationale is required.");
      return;
    }
    setBusyId(incident.id);
    try {
      const response = await fetch(`${apiUrl}/api/v1/incidents/${incident.id}/proposals`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requested_action: "RETRY_TRANSFER", rationale }),
      });
      if (!response.ok) throw new Error();
      setMessage("Proposal recorded for independent review. No retry was executed.");
      setRationales((current) => ({ ...current, [incident.id]: "" }));
      await loadIncidents();
    } catch {
      setMessage("The proposal could not be recorded.");
    } finally {
      setBusyId("");
    }
  }

  async function decide(proposal: Proposal, decision: "approve" | "reject") {
    const reason = window.prompt(decision === "approve" ? "Approval reason" : "Rejection reason");
    if (!reason?.trim()) return;
    setBusyId(proposal.id);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/incidents/proposals/${proposal.id}/${decision}`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision_reason: reason.trim() }),
        },
      );
      if (!response.ok) {
        const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(detail?.detail ?? "Decision rejected");
      }
      setMessage(
        decision === "approve"
          ? "Approval recorded. Execution remains disabled in this slice."
          : "Proposal rejected and returned to open review.",
      );
      await loadIncidents();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The decision could not be recorded.");
    } finally {
      setBusyId("");
    }
  }

  async function drainOutbox() {
    setBusyId("outbox");
    try {
      const response = await fetch(`${apiUrl}/api/v1/incidents/outbox/drain`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 20 }),
      });
      if (!response.ok) throw new Error();
      const result = (await response.json()) as {
        selected: number;
        completed: number;
        failed: number;
      };
      setMessage(
        `Evidence recovery: ${result.completed}/${result.selected} completed; ${result.failed} failed. No remediation was executed.`,
      );
      await loadIncidents();
    } catch {
      setMessage("Incident evidence recovery could not be completed.");
    } finally {
      setBusyId("");
    }
  }

  const visibleIncidents = incidents.filter((incident) => incident.status !== "resolved");

  return (
    <section
      aria-labelledby="incident-review-title"
      className="mt-6 rounded-2xl border border-amber-400/20 bg-amber-400/5 p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-200">
            Human review
          </p>
          <h3 id="incident-review-title" className="mt-1 text-lg font-semibold text-slate-100">
            PACS incidents and approval evidence
          </h3>
          <p className="mt-2 max-w-3xl text-sm text-slate-400">
            Failures are classified and preserved for review. Approval records intent only; this
            workspace never retries a transfer or performs remediation.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void loadIncidents()}
            disabled={loading}
            className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            Refresh
          </button>
          {canDecide(user?.role) && (
            <button
              type="button"
              onClick={() => void drainOutbox()}
              disabled={busyId === "outbox"}
              className="rounded-lg border border-amber-400/30 px-3 py-2 text-xs text-amber-100 hover:bg-amber-400/10 disabled:opacity-50"
            >
              Recover evidence
            </button>
          )}
        </div>
      </div>
      {message && <p aria-live="polite" className="mt-4 text-sm text-amber-100">{message}</p>}
      {!loading && visibleIncidents.length === 0 && (
        <p className="mt-5 text-sm text-slate-500">No open incidents require review.</p>
      )}
      <div className="mt-5 space-y-3">
        {visibleIncidents.map((incident) => {
          const activeProposal = incident.proposals.find(
            (proposal) => proposal.status === "pending",
          );
          const canApprove =
            canDecide(user?.role) &&
            activeProposal &&
            activeProposal.proposer_id !== user?.id;
          return (
            <article key={incident.id} className="rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-200">
                    {incident.incident_number} · {incident.category}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">{incident.redacted_summary}</p>
                </div>
                <div className="flex gap-2 text-xs">
                  <span className="rounded-full border border-slate-700 px-2 py-1 text-slate-300">
                    {incident.severity}
                  </span>
                  <span className="rounded-full border border-amber-400/30 px-2 py-1 text-amber-100">
                    {incident.approval_state}
                  </span>
                </div>
              </div>
              {activeProposal && (
                <div className="mt-3 rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-3 text-xs text-slate-300">
                  <p>
                    Proposal: {activeProposal.requested_action} · {activeProposal.rationale}
                  </p>
                  {canApprove && (
                    <div className="mt-3 flex gap-2">
                      <button
                        type="button"
                        onClick={() => void decide(activeProposal, "approve")}
                        disabled={busyId === activeProposal.id}
                        className="rounded-lg bg-cyan-500 px-3 py-1.5 font-semibold text-slate-950 disabled:opacity-50"
                      >
                        Approve evidence
                      </button>
                      <button
                        type="button"
                        onClick={() => void decide(activeProposal, "reject")}
                        disabled={busyId === activeProposal.id}
                        className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              )}
              {!activeProposal && incident.retry_candidate && canPropose(user?.role) && (
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <input
                    aria-label={`Rationale for ${incident.incident_number}`}
                    value={rationales[incident.id] ?? ""}
                    onChange={(event) =>
                      setRationales((current) => ({
                        ...current,
                        [incident.id]: event.target.value,
                      }))
                    }
                    placeholder="Why should this be reviewed?"
                    className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
                  />
                  <button
                    type="button"
                    onClick={() => void createProposal(incident)}
                    disabled={busyId === incident.id}
                    className="rounded-lg border border-amber-400/30 px-3 py-2 text-xs text-amber-100 hover:bg-amber-400/10 disabled:opacity-50"
                  >
                    Propose review
                  </button>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
