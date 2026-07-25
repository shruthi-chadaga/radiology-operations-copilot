import { PacsOperationsWorkspace } from "@/features/pacs/pacs-operations-workspace";

export default function PacsOpsPage() {
  return (
    <section aria-labelledby="pacs-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-violet-300">Workspace 02</p>
          <h2
            id="pacs-title"
            className="mt-1 text-3xl font-bold tracking-tight"
          >
            PACS/RIS Automation
          </h2>
          <p className="mt-3 max-w-3xl text-slate-400">
            Non-destructive node monitoring, metadata-only study inventory,
            idempotent transfer evidence, and deterministic destination
            reconciliation.
          </p>
        </div>
        <span className="rounded-full border border-violet-400/30 bg-violet-400/10 px-3 py-1 text-sm text-violet-100">
          Phase 3 active
        </span>
      </div>
      <PacsOperationsWorkspace />
    </section>
  );
}
