"use client";

import { FormEvent, useEffect, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/session-context";

export type Referral = {
  id: string;
  referral_number: string;
  patient_id: string;
  source_text: string;
  requested_exam: string | null;
  modality: string | null;
  body_region: string | null;
  status: string;
  completeness_status: string;
  extraction_confidence: number | null;
};

type Props = {
  initialReferrals?: Referral[];
  currentRole?:
    | "scheduler"
    | "pacs_admin"
    | "operations_manager"
    | "auditor"
    | "system_admin";
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const ReferralSchema: z.ZodType<Referral> = z
  .object({
    id: z.string(),
    referral_number: z.string(),
    patient_id: z.string(),
    source_text: z.string(),
    requested_exam: z.string().nullable(),
    modality: z.string().nullable(),
    body_region: z.string().nullable(),
    status: z.string(),
    completeness_status: z.string(),
    extraction_confidence: z.number().nullable(),
  })
  .strict();
const ReferralPageSchema = z
  .object({ items: z.array(ReferralSchema) })
  .strict();

export function SchedulingWorkspace({ initialReferrals, currentRole }: Props) {
  const { user, loading } = useSession();
  const role = currentRole ?? user?.role;
  const canWrite = role === "scheduler" || role === "operations_manager";
  const [referrals, setReferrals] = useState<Referral[]>(
    initialReferrals ?? [],
  );
  const [message, setMessage] = useState(
    initialReferrals === undefined
      ? "Sign in, then load the synthetic work queue."
      : "",
  );
  const [busyId, setBusyId] = useState<string | null>(null);

  async function loadQueue() {
    setMessage("Loading synthetic referrals…");
    try {
      const response = await fetch(`${apiUrl}/api/v1/referrals`, {
        credentials: "include",
      });
      if (!response.ok) {
        setMessage(
          response.status === 401
            ? "Sign in to access the scheduling queue."
            : "Queue could not be loaded.",
        );
        return;
      }
      const data = ReferralPageSchema.parse(await response.json());
      setReferrals(data.items);
      setMessage(`${data.items.length} synthetic referrals loaded.`);
    } catch {
      setMessage(
        "Queue could not be loaded because the API response was unavailable or invalid.",
      );
    }
  }

  useEffect(() => {
    if (initialReferrals !== undefined || currentRole !== undefined || loading)
      return;
    const timer = window.setTimeout(() => {
      setReferrals([]);
      if (
        !user ||
        !["scheduler", "operations_manager", "auditor"].includes(user.role)
      ) {
        setMessage("Sign in to access the scheduling queue.");
        return;
      }
      void loadQueue();
    }, 0);
    return () => window.clearTimeout(timer);
    // loadQueue is intentionally rerun only when the authenticated principal changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRole, initialReferrals, loading, user?.id, user?.role]);

  async function createReferral(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setMessage("Creating synthetic referral…");
    try {
      const response = await fetch(`${apiUrl}/api/v1/referrals`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: data.get("patient_id"),
          source_text: `[SYNTHETIC] ${String(data.get("source_text"))}`,
          synthetic_data_confirmed:
            data.get("synthetic_data_confirmed") === "on",
        }),
      });
      if (!response.ok) {
        setMessage(
          `Referral creation failed (${response.status}). Use a seeded synthetic patient UUID.`,
        );
        return;
      }
      ReferralSchema.parse(await response.json());
      form.reset();
      await loadQueue();
    } catch {
      setMessage(
        "Referral creation failed because the API response was unavailable or invalid.",
      );
    }
  }

  async function reviewReferral(referral: Referral) {
    setBusyId(referral.id);
    setMessage(
      `Extracting administrative facts for ${referral.referral_number}…`,
    );
    try {
      const extracted = await fetch(
        `${apiUrl}/api/v1/referrals/${referral.id}/extract`,
        {
          method: "POST",
          credentials: "include",
        },
      );
      if (!extracted.ok) {
        setMessage(
          `Extraction failed (${extracted.status}); no action was executed.`,
        );
        return;
      }
      await extracted.json();
      const validated = await fetch(
        `${apiUrl}/api/v1/referrals/${referral.id}/validate`,
        {
          method: "POST",
          credentials: "include",
        },
      );
      if (!validated.ok) {
        setMessage(`Deterministic validation failed (${validated.status}).`);
        return;
      }
      await validated.json();
      await loadQueue();
    } catch {
      setMessage(
        "Referral review failed because the API response was unavailable or invalid.",
      );
    } finally {
      setBusyId(null);
    }
  }

  const ready = referrals.filter((item) => item.status === "ready").length;
  const exceptions = referrals.filter(
    (item) => item.status === "exception",
  ).length;
  const review = referrals.filter((item) =>
    ["new", "review"].includes(item.status),
  ).length;

  return (
    <div className="mt-8 space-y-8">
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          ["Awaiting review", review],
          ["Ready to schedule", ready],
          ["Human exceptions", exceptions],
        ].map(([label, value]) => (
          <article
            key={label}
            className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5"
          >
            <p className="text-sm text-slate-400">{label}</p>
            <p className="mt-3 text-3xl font-bold">{value}</p>
          </article>
        ))}
      </div>

      <section
        aria-labelledby="new-referral-title"
        className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 id="new-referral-title" className="text-lg font-semibold">
              New synthetic referral
            </h3>
            <p className="mt-1 text-sm text-slate-400">
              Administrative extraction only. No diagnosis or image
              interpretation.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadQueue()}
            className="rounded-lg border border-cyan-400/40 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-400/10"
          >
            Reload queue
          </button>
        </div>
        {canWrite ? (
          <form
            onSubmit={createReferral}
            className="mt-5 grid gap-4 lg:grid-cols-[minmax(15rem,0.6fr)_1fr_auto] lg:items-end"
          >
            <label className="text-sm font-medium">
              Synthetic patient UUID
              <input
                required
                name="patient_id"
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none focus:border-cyan-400"
              />
            </label>
            <label className="text-sm font-medium">
              Synthetic referral text
              <textarea
                required
                name="source_text"
                rows={2}
                className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none focus:border-cyan-400"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-amber-100">
              <input required type="checkbox" name="synthetic_data_confirmed" />
              I confirm this contains synthetic data only and no real patient
              information.
            </label>
            <button className="rounded-xl bg-cyan-400 px-5 py-3 font-semibold text-slate-950 hover:bg-cyan-300">
              Create referral
            </button>
          </form>
        ) : (
          <p className="mt-5 text-sm text-slate-400">
            Your current role has read-only scheduling access.
          </p>
        )}
        <p aria-live="polite" className="mt-4 text-sm text-slate-400">
          {message}
        </p>
      </section>

      <section
        aria-labelledby="queue-title"
        className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 id="queue-title" className="text-lg font-semibold">
            Referral work queue
          </h3>
          <p className="text-sm text-amber-200">
            Human review remains mandatory for detected ambiguity;
            identity-conflict detection is planned.
          </p>
        </div>
        {referrals.length === 0 ? (
          <div className="mt-6 rounded-xl border border-dashed border-slate-700 px-6 py-12 text-center text-slate-400">
            No synthetic referrals loaded.
          </div>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-slate-700 text-slate-400">
                <tr>
                  <th className="px-3 py-3">Referral</th>
                  <th className="px-3 py-3">Requested exam</th>
                  <th className="px-3 py-3">Status</th>
                  <th className="px-3 py-3">Confidence</th>
                  <th className="px-3 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {referrals.map((referral) => (
                  <tr key={referral.id} className="border-b border-slate-800">
                    <td className="px-3 py-4 font-medium">
                      {referral.referral_number}
                    </td>
                    <td className="px-3 py-4 text-slate-300">
                      {referral.requested_exam ?? "Not extracted"}
                    </td>
                    <td className="px-3 py-4">
                      <StatusBadge value={referral.status} />
                    </td>
                    <td className="px-3 py-4">
                      {referral.extraction_confidence === null
                        ? "—"
                        : `${Math.round(referral.extraction_confidence * 100)}%`}
                    </td>
                    <td className="px-3 py-4">
                      {canWrite ? (
                        <button
                          type="button"
                          disabled={busyId === referral.id}
                          aria-label={`Extract and validate ${referral.referral_number}`}
                          onClick={() => void reviewReferral(referral)}
                          className="rounded-lg border border-cyan-400/40 px-3 py-2 text-cyan-200 hover:bg-cyan-400/10 disabled:opacity-50"
                        >
                          {busyId === referral.id
                            ? "Reviewing…"
                            : "Extract & validate"}
                        </button>
                      ) : (
                        <span className="text-xs text-slate-500">
                          Read only
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  const tone =
    value === "ready"
      ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
      : value === "exception"
        ? "border-amber-400/30 bg-amber-400/10 text-amber-200"
        : "border-slate-600 bg-slate-800 text-slate-300";
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}
    >
      {value.replaceAll("_", " ")}
    </span>
  );
}
