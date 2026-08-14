"use client";

type TimelineEvent = {
  event_type: string;
  event_id: string;
  occurred_at: string;
  label: string;
  detail: string;
  status: string;
};

type Props = {
  patientName: string;
  externalPatientId: string;
  events: TimelineEvent[];
};

function formatDate(value: string) {
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function PatientTimeline({ patientName, externalPatientId, events }: Props) {
  return (
    <section aria-labelledby="patient-timeline-heading" className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-300">Longitudinal context</p>
          <h4 id="patient-timeline-heading" className="mt-1 text-lg font-semibold">Patient timeline</h4>
          <p className="mt-1 text-sm text-slate-500">{patientName} · {externalPatientId}</p>
        </div>
        <span className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-400">Metadata only</span>
      </div>
      {events.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">No scheduling or received-study events are available for this synthetic patient.</p>
      ) : (
        <ol className="mt-6 space-y-5">
          {events.map((event, index) => (
            <li key={`${event.event_type}-${event.event_id}`} className="relative flex gap-4">
              {index < events.length - 1 && <span className="absolute left-[7px] top-5 h-full w-px bg-slate-700" aria-hidden="true" />}
              <span className={`relative mt-1 h-4 w-4 shrink-0 rounded-full border-4 border-slate-900 ${event.event_type === "study" ? "bg-emerald-400" : event.event_type === "appointment" ? "bg-cyan-400" : "bg-violet-400"}`} aria-hidden="true" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <p className="font-medium text-slate-200">{event.label}</p>
                  <time className="text-xs text-slate-500">{formatDate(event.occurred_at)}</time>
                </div>
                <p className="mt-1 text-sm text-slate-400">{event.detail}</p>
                <p className="mt-1 text-xs uppercase tracking-wider text-slate-600">{event.status.replaceAll("_", " ")}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export type { TimelineEvent };
