"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/session-context";

export type PacsNode = {
  id: string;
  name: string;
  node_type: string;
  dicom_ae_title: string;
  active: boolean;
  last_health_status: string | null;
  last_health_at: string | null;
};

export type PacsStudy = {
  id: string;
  node_id: string;
  study_instance_uid: string;
  accession_number: string;
  patient_id: string;
  patient_name: string | null;
  patient_birth_date: string | null;
  patient_sex: string | null;
  study_date: string | null;
  study_description: string | null;
  modality: string | null;
  series_count: number;
  instance_count: number;
};

type Transfer = {
  id: string;
  source_node_id: string;
  destination_node_id: string;
  study_id: string;
  status: string;
  retry_count: number;
  maximum_retries: number;
  correlation_id: string;
};

type Props = {
  initialNodes?: PacsNode[];
  initialStudies?: PacsStudy[];
  initialTransfers?: Transfer[];
  currentRole?:
    | "scheduler"
    | "pacs_admin"
    | "operations_manager"
    | "auditor"
    | "system_admin";
  // Callback props for parent orchestration
  onNodesLoaded?: (nodes: PacsNode[]) => void;
  onStudiesLoaded?: (studies: PacsStudy[]) => void;
  onMessage?: (message: string) => void;
  onDataRefresh?: () => void;
  // Embedded mode (used inside collapsible operations panel)
  embedded?: boolean;
  nodes?: PacsNode[];
  studies?: PacsStudy[];
  canWrite?: boolean;
  preselectedStudyId?: string;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PacsNodeSchema: z.ZodType<PacsNode> = z
  .object({
    id: z.string(),
    name: z.string(),
    node_type: z.string(),
    dicom_ae_title: z.string(),
    active: z.boolean(),
    last_health_status: z.string().nullable(),
    last_health_at: z.string().nullable(),
  })
  .strict();
const PacsStudySchema: z.ZodType<PacsStudy> = z
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
  .strict();
const TransferSchema: z.ZodType<Transfer> = z
  .object({
    id: z.string(),
    source_node_id: z.string(),
    destination_node_id: z.string(),
    study_id: z.string(),
    status: z.string(),
    retry_count: z.number().int(),
    maximum_retries: z.number().int(),
    correlation_id: z.string(),
  })
  .strict();
const NodePageSchema = z.object({ items: z.array(PacsNodeSchema) }).strict();
const StudyPageSchema = z.object({ items: z.array(PacsStudySchema) }).strict();
const TransferPageSchema = z
  .object({ items: z.array(TransferSchema) })
  .strict();

export function PacsOperationsWorkspace({
  initialNodes,
  initialStudies,
  initialTransfers,
  currentRole,
  onNodesLoaded,
  onStudiesLoaded,
  onMessage,
  onDataRefresh,
  embedded = false,
  nodes: externalNodes,
  studies: externalStudies,
  canWrite: externalCanWrite,
  preselectedStudyId,
}: Props) {
  const { user, loading } = useSession();
  const role = currentRole ?? user?.role;
  const canWrite =
    externalCanWrite ?? (role === "pacs_admin" || role === "operations_manager");
  const [nodes, setNodes] = useState(initialNodes ?? []);
  const [studies, setStudies] = useState(initialStudies ?? []);
  const [transfers, setTransfers] = useState(initialTransfers ?? []);
  const [message, setMessage] = useState(
    "Metadata only — no pixels stored in PostgreSQL",
  );
  const ambiguousRequest = useRef<{ signature: string; key: string } | null>(
    null,
  );

  // Use external data when embedded
  const displayNodes = embedded ? (externalNodes ?? nodes) : nodes;
  const displayStudies = embedded ? (externalStudies ?? studies) : studies;

  async function loadAll() {
    try {
      const responses = await Promise.all(
        ["nodes", "studies", "transfers"].map((path) =>
          fetch(`${apiUrl}/api/v1/pacs/${path}`, { credentials: "include" }),
        ),
      );
      if (responses.some((response) => !response.ok)) {
        const msg = responses.some((response) => response.status === 401)
          ? "Sign in with a PACS-authorized local account."
          : "PACS metadata could not be loaded.";
        setMessage(msg);
        onMessage?.(msg);
        return;
      }
      const payloads = await Promise.all(
        responses.map((response) => response.json()),
      );
      const loadedNodes = NodePageSchema.parse(payloads[0]).items;
      const loadedStudies = StudyPageSchema.parse(payloads[1]).items;
      const loadedTransfers = TransferPageSchema.parse(payloads[2]).items;
      setNodes(loadedNodes);
      setStudies(loadedStudies);
      setTransfers(loadedTransfers);
      onNodesLoaded?.(loadedNodes);
      onStudiesLoaded?.(loadedStudies);
      const msg = "Metadata only — no pixels stored in PostgreSQL";
      setMessage(msg);
      onMessage?.(msg);
      onDataRefresh?.();
    } catch {
      const msg =
        "PACS metadata could not be loaded because the API response was unavailable or invalid.";
      setMessage(msg);
      onMessage?.(msg);
    }
  }

  useEffect(() => {
    if (embedded) return; // Don't auto-fetch in embedded mode
    if (initialNodes !== undefined || currentRole !== undefined || loading)
      return;
    const timer = window.setTimeout(() => {
      setNodes([]);
      setStudies([]);
      setTransfers([]);
      ambiguousRequest.current = null;
      if (
        !user ||
        !["pacs_admin", "operations_manager", "auditor"].includes(user.role)
      ) {
        const msg = "Sign in with a PACS-authorized local account.";
        setMessage(msg);
        onMessage?.(msg);
        return;
      }
      void loadAll();
    }, 0);
    return () => window.clearTimeout(timer);
    // loadAll is intentionally rerun only when the authenticated principal changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRole, initialNodes, loading, user?.id, user?.role, embedded]);

  async function checkHealth(node: PacsNode) {
    setMessage(`Checking ${node.name}…`);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/pacs/nodes/${node.id}/health-check`,
        {
          method: "POST",
          credentials: "include",
        },
      );
      const msg = response.ok
        ? `${node.name} health evidence stored.`
        : `Health check failed (${response.status}).`;
      setMessage(msg);
      onMessage?.(msg);
      if (response.ok) await loadAll();
    } catch {
      const msg = "Health check failed because the API is unavailable.";
      setMessage(msg);
      onMessage?.(msg);
    }
  }

  async function syncNode(node: PacsNode) {
    setMessage(`Synchronizing metadata from ${node.name}…`);
    try {
      const response = await fetch(`${apiUrl}/api/v1/pacs/studies/sync`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          node_id: node.id,
          synthetic_data_confirmed: true,
        }),
      });
      const msg = response.ok
        ? "Metadata inventory synchronized without deletion."
        : `Inventory sync failed (${response.status}).`;
      setMessage(msg);
      onMessage?.(msg);
      if (response.ok) await loadAll();
    } catch {
      const msg = "Inventory sync failed because the API is unavailable.";
      setMessage(msg);
      onMessage?.(msg);
    }
  }

  async function queueTransfer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const payload = {
      source_node_id: String(data.get("source_node_id")),
      destination_node_id: String(data.get("destination_node_id")),
      study_id: String(data.get("study_id")),
    };
    const signature = JSON.stringify(payload);
    const key =
      ambiguousRequest.current?.signature === signature
        ? ambiguousRequest.current.key
        : `ui-transfer-${crypto.randomUUID()}`;
    ambiguousRequest.current = { signature, key };
    try {
      const response = await fetch(`${apiUrl}/api/v1/pacs/transfers`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "Idempotency-Key": key },
        body: signature,
      });
      if (!response.ok) {
        if (response.status < 500) ambiguousRequest.current = null;
        const msg = `Transfer request was rejected (${response.status}).`;
        setMessage(msg);
        onMessage?.(msg);
        return;
      }
      TransferSchema.parse(await response.json());
      ambiguousRequest.current = null;
      const msg = "Transfer request accepted into the durable dispatch queue.";
      setMessage(msg);
      onMessage?.(msg);
      await loadAll();
    } catch {
      const msg =
        "Transfer status is unknown because the API response was unavailable or invalid; retrying will reuse the same idempotency key.";
      setMessage(msg);
      onMessage?.(msg);
    }
  }

  // Only render the full UI when NOT embedded (embedded just uses the hidden loader)
  if (embedded) {
    return (
      <div className="space-y-6">
        <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h4 className="font-semibold text-sm">PACS nodes</h4>
              <p className="mt-0.5 text-xs text-slate-500">
                Non-destructive health checks &amp; inventory sync
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadAll()}
              className="rounded-lg border border-violet-400/40 px-3 py-2 text-xs text-violet-200 hover:bg-violet-400/10 transition-colors"
            >
              Reload metadata
            </button>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {displayNodes.map((node) => (
              <article
                key={node.id}
                className="rounded-lg border border-slate-700 bg-slate-950/50 p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h5 className="font-semibold text-sm">{node.name}</h5>
                    <p className="mt-0.5 text-xs text-slate-500">
                      AE: {node.dicom_ae_title}
                    </p>
                  </div>
                  <Status value={node.last_health_status ?? "not checked"} />
                </div>
                {canWrite && (
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => void checkHealth(node)}
                      className="rounded-lg border border-cyan-400/40 px-2.5 py-1.5 text-xs text-cyan-200 hover:bg-cyan-400/10 transition-colors"
                    >
                      Check health
                    </button>
                    <button
                      type="button"
                      onClick={() => void syncNode(node)}
                      className="rounded-lg border border-slate-600 px-2.5 py-1.5 text-xs text-slate-200 hover:bg-slate-700 transition-colors"
                    >
                      Sync inventory
                    </button>
                  </div>
                )}
              </article>
            ))}
          </div>
        </section>

        {canWrite && (
          <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-5">
            <h4 className="font-semibold text-sm">Queue study transfer</h4>
            <p className="mt-0.5 text-xs text-slate-500">
              Source-to-destination storage only. No deletion or tag
              modification.
            </p>
            <form
              onSubmit={queueTransfer}
              className="mt-4 grid gap-3 md:grid-cols-4 md:items-end"
            >
              <Select
                label="Source node"
                name="source_node_id"
                items={displayNodes
                  .filter((item) => item.node_type === "source")
                  .map((item) => [item.id, item.name])}
              />
              <Select
                label="Destination node"
                name="destination_node_id"
                items={displayNodes
                  .filter((item) => item.node_type === "destination")
                  .map((item) => [item.id, item.name])}
              />
              <Select
                label="Synthetic study"
                name="study_id"
                defaultValue={
                  preselectedStudyId
                    ? displayStudies.find((s) => s.id === preselectedStudyId)
                        ?.accession_number
                    : undefined
                }
                items={displayStudies.map((item) => [
                  item.id,
                  item.accession_number,
                ])}
              />
              <button
                disabled={!displayStudies.length}
                className="rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 hover:bg-violet-400 transition-colors"
              >
                Queue transfer
              </button>
            </form>
          </section>
        )}

        <div className="space-y-2">
          {transfers.length === 0 ? (
            <p className="text-xs text-slate-500">No transfer jobs queued.</p>
          ) : (
            transfers.map((transfer) => (
              <article
                key={transfer.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-700 px-4 py-2.5"
              >
                <span className="font-mono text-xs text-slate-400">
                  {transfer.id.slice(0, 12)}…
                </span>
                <Status value={transfer.status} />
                <span className="text-xs text-slate-500">
                  Retries {transfer.retry_count}/{transfer.maximum_retries}
                </span>
              </article>
            ))
          )}
        </div>
      </div>
    );
  }

  // Standalone mode (kept for backwards compatibility / hidden data loader)
  return (
    <div className="mt-8 space-y-8">
      <section
        aria-labelledby="node-health-title"
        className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 id="node-health-title" className="text-lg font-semibold">
              PACS nodes
            </h3>
            <p className="mt-1 text-sm text-violet-200">
              Non-destructive PACS adapter
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadAll()}
            className="rounded-lg border border-violet-400/40 px-3 py-2 text-sm text-violet-200 hover:bg-violet-400/10"
          >
            Reload metadata
          </button>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {nodes.map((node) => (
            <article
              key={node.id}
              className="rounded-xl border border-slate-700 bg-slate-950/50 p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h4 className="font-semibold">{node.name}</h4>
                  <p className="mt-1 text-xs text-slate-500">
                    AE: {node.dicom_ae_title}
                  </p>
                </div>
                <Status value={node.last_health_status ?? "not checked"} />
              </div>
              {canWrite ? (
                <div className="mt-4 flex gap-2">
                  <button
                    type="button"
                    onClick={() => void checkHealth(node)}
                    className="rounded-lg border border-cyan-400/40 px-3 py-2 text-sm text-cyan-200"
                  >
                    Check health
                  </button>
                  <button
                    type="button"
                    onClick={() => void syncNode(node)}
                    className="rounded-lg border border-slate-600 px-3 py-2 text-sm text-slate-200"
                  >
                    Sync inventory
                  </button>
                </div>
              ) : (
                <p className="mt-4 text-xs text-slate-500">
                  Read-only PACS access
                </p>
              )}
            </article>
          ))}
        </div>
        <p aria-live="polite" className="mt-4 text-sm text-slate-400">
          {message}
        </p>
      </section>

      <section
        aria-labelledby="study-inventory-title"
        className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6"
      >
        <h3 id="study-inventory-title" className="text-lg font-semibold">
          Study metadata inventory
        </h3>
        {studies.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500">
            No synthetic study metadata discovered.
          </p>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-slate-700 text-slate-400">
                <tr>
                  <th className="px-3 py-3">Accession</th>
                  <th className="px-3 py-3">Synthetic patient</th>
                  <th className="px-3 py-3">Description</th>
                  <th className="px-3 py-3">Series</th>
                  <th className="px-3 py-3">Instances</th>
                </tr>
              </thead>
              <tbody>
                {studies.map((study) => (
                  <tr key={study.id} className="border-b border-slate-800">
                    <td className="px-3 py-4 font-medium">
                      {study.accession_number}
                    </td>
                    <td className="px-3 py-4">{study.patient_id}</td>
                    <td className="px-3 py-4 text-slate-300">
                      {study.study_description ?? "—"}
                    </td>
                    <td className="px-3 py-4">{study.series_count}</td>
                    <td className="px-3 py-4">{study.instance_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section
        aria-labelledby="transfer-title"
        className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6"
      >
        <h3 id="transfer-title" className="text-lg font-semibold">
          Allowlisted study transfer
        </h3>
        <p className="mt-1 text-sm text-slate-400">
          Queues source-to-destination storage only. No deletion, tag
          modification, or identity editing.
        </p>
        {canWrite ? (
          <form
            onSubmit={queueTransfer}
            className="mt-5 grid gap-4 md:grid-cols-4 md:items-end"
          >
            <Select
              label="Source node"
              name="source_node_id"
              items={nodes
                .filter((item) => item.node_type === "source")
                .map((item) => [item.id, item.name])}
            />
            <Select
              label="Destination node"
              name="destination_node_id"
              items={nodes
                .filter((item) => item.node_type === "destination")
                .map((item) => [item.id, item.name])}
            />
            <Select
              label="Synthetic study"
              name="study_id"
              items={studies.map((item) => [item.id, item.accession_number])}
            />
            <button
              disabled={!studies.length}
              className="rounded-xl bg-violet-400 px-4 py-3 font-semibold text-slate-950 disabled:opacity-50"
            >
              Queue transfer
            </button>
          </form>
        ) : (
          <p className="mt-5 text-sm text-slate-400">
            Your current role cannot create PACS transfers.
          </p>
        )}
        <div className="mt-6 space-y-3">
          {transfers.length === 0 ? (
            <p className="text-sm text-slate-500">No transfer jobs queued.</p>
          ) : (
            transfers.map((transfer) => (
              <article
                key={transfer.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-700 px-4 py-3"
              >
                <span className="font-mono text-xs text-slate-400">
                  {transfer.id}
                </span>
                <Status value={transfer.status} />
                <span className="text-xs text-slate-500">
                  Retries {transfer.retry_count}/{transfer.maximum_retries}
                </span>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function Select({
  label,
  name,
  items,
  defaultValue,
}: {
  label: string;
  name: string;
  items: string[][];
  defaultValue?: string;
}) {
  return (
    <label className="text-sm font-medium">
      {label}
      <select
        required
        name={name}
        defaultValue={defaultValue}
        className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3"
      >
        {items.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

function Status({ value }: { value: string }) {
  const healthy = ["healthy", "completed", "transferred"].includes(value);
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs ${
        healthy
          ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
          : "border-amber-400/30 bg-amber-400/10 text-amber-100"
      }`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}
