import { SchedulingWorkspace } from "@/features/scheduling/scheduling-workspace";

export default function SchedulingPage() {
  return (
    <section aria-labelledby="scheduling-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-cyan-300">Workspace 01</p>
          <h2
            id="scheduling-title"
            className="mt-1 text-3xl font-bold tracking-tight"
          >
            Scheduling Automation
          </h2>
          <p className="mt-3 max-w-3xl text-slate-400">
            Referral intake, schema-validated administrative extraction,
            deterministic validation, slot ranking, transactional booking,
            rescheduling, and human-controlled exceptions.
          </p>
        </div>
        <span className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-sm text-cyan-200">
          Phase 2 active
        </span>
      </div>
      <SchedulingWorkspace />
    </section>
  );
}
