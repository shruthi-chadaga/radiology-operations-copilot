"use client";

import { useCallback, useEffect, useState } from "react";
import { z } from "zod";

import { useSession } from "@/components/session-context";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ShareEntrySchema = z
  .object({
    id: z.string(),
    report_id: z.string(),
    study_id: z.string(),
    recipient_label: z.string(),
    status: z.string(),
    created_by: z.string(),
    created_at: z.string(),
    expires_at: z.string(),
    revoked_at: z.string().nullable(),
  })
  .strict();
const SharePageSchema = z.object({ items: z.array(ShareEntrySchema) }).strict();
const ShareCreatedSchema = ShareEntrySchema.extend({
  token: z.string(),
}).strict();

export type ShareEntry = z.infer<typeof ShareEntrySchema>;

type Props = { reportId: string; canWrite: boolean };

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

export function ReportSharePanel({ reportId, canWrite }: Props) {
  const { user } = useSession();
  const [shares, setShares] = useState<ShareEntry[]>([]);
  const [message, setMessage] = useState("");
  const [oneTimeToken, setOneTimeToken] = useState("");
  const [recipientLabel, setRecipientLabel] = useState("");
  const [expiresInHours, setExpiresInHours] = useState("48");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const loadShares = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/imaging/reports/${reportId}/shares`,
        { credentials: "include" },
      );
      if (!response.ok) throw new Error();
      setShares(SharePageSchema.parse(await response.json()).items);
      setLoadError("");
    } catch {
      setLoadError("The share allowlist could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadShares(), 0);
    return () => window.clearTimeout(timer);
  }, [loadShares]);

  async function createShare() {
    const label = recipientLabel.trim();
    if (!label) {
      setMessage("A recipient label is required.");
      return;
    }
    const hours = Number.parseInt(expiresInHours, 10);
    if (!Number.isFinite(hours) || hours < 1 || hours > 336) {
      setMessage("Expiry must be between 1 and 336 hours.");
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/imaging/reports/${reportId}/shares`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            recipient_label: label,
            expires_in_hours: hours,
          }),
        },
      );
      if (!response.ok) throw new Error();
      const created = ShareCreatedSchema.parse(await response.json());
      setOneTimeToken(created.token);
      setMessage("");
      setRecipientLabel("");
      await loadShares();
    } catch {
      setMessage("The share link could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function revokeShare(shareId: string) {
    if (user == null) return;
    if (
      !window.confirm(
        "Revoke this share? Recipients with the token will immediately lose access.",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/imaging/reports/shares/${shareId}`,
        { method: "DELETE", credentials: "include" },
      );
      if (!response.ok) throw new Error();
      setMessage("Share revoked. The token no longer resolves.");
      await loadShares();
    } catch {
      setMessage("The share could not be revoked.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="report-share-title" className="mt-6">
      <h3
        id="report-share-title"
        className="text-sm font-semibold uppercase tracking-wider text-slate-400"
      >
        Report sharing allowlist
      </h3>
      <p className="mt-1 text-xs text-slate-500">
        Allowlisted recipients receive an expiring token. Tokens are stored only
        as hashes and are shown once at creation.
      </p>
      {loadError && <p className="mt-2 text-sm text-amber-200">{loadError}</p>}
      {canWrite && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            aria-label="Recipient label"
            value={recipientLabel}
            onChange={(event) => setRecipientLabel(event.target.value)}
            placeholder="Who is this shared with?"
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <input
            aria-label="Expires in hours"
            type="number"
            min={1}
            max={336}
            value={expiresInHours}
            onChange={(event) => setExpiresInHours(event.target.value)}
            className="w-28 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200"
          />
          <button
            type="button"
            onClick={() => void createShare()}
            disabled={busy}
            className="rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-slate-950 hover:bg-cyan-400 disabled:opacity-50"
          >
            Create share link
          </button>
        </div>
      )}
      {!canWrite && shares.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Read-only view; sharing changes require an imaging operator role.
        </p>
      )}
      {oneTimeToken && (
        <div
          role="status"
          className="mt-3 rounded-lg border border-emerald-400/30 bg-emerald-400/10 p-3"
        >
          <p className="text-xs font-medium text-emerald-100">
            Copy this link token now — it is shown only once and cannot be
            recovered:
          </p>
          <code className="mt-1 block break-all font-mono text-xs text-emerald-200">
            {oneTimeToken}
          </code>
          <button
            type="button"
            onClick={() => setOneTimeToken("")}
            className="mt-2 text-xs text-emerald-300 underline"
          >
            I have saved the token
          </button>
        </div>
      )}
      {message && (
        <p aria-live="polite" className="mt-3 text-sm text-amber-100">
          {message}
        </p>
      )}
      {!loading && shares.length === 0 && !loadError && (
        <p className="mt-4 text-sm text-slate-500">
          No recipients on the allowlist.
        </p>
      )}
      <ul className="mt-4 space-y-2">
        {shares.map((share) => (
          <li
            key={share.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"
          >
            <div>
              <p className="font-medium text-slate-200">
                {share.recipient_label}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                Expires {formatDate(share.expires_at)} · created by{" "}
                {share.created_by}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`rounded-full border px-2 py-1 text-xs ${
                  share.status === "active"
                    ? "border-emerald-400/30 text-emerald-200"
                    : "border-slate-700 text-slate-400"
                }`}
              >
                {share.status}
              </span>
              {canWrite && share.status === "active" && (
                <button
                  type="button"
                  onClick={() => void revokeShare(share.id)}
                  disabled={busy}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
                >
                  Revoke
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
