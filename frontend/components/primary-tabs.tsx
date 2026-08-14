import Link from "next/link";

const tabs = [
  { href: "/pacs-ops", label: "Imaging Workspace" },
  { href: "/scheduling", label: "Scheduling Automation" },
] as const;

export function PrimaryTabs({ currentPath }: { currentPath: string }) {
  return (
    <nav
      aria-label="Primary operations workspaces"
      className="grid gap-3 sm:grid-cols-2"
    >
      {tabs.map((tab) => {
        const active = currentPath.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-2xl border px-5 py-4 text-sm font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400 ${
              active
                ? "border-cyan-400/70 bg-cyan-400/10 text-cyan-100 shadow-[0_0_30px_rgba(34,211,238,0.08)]"
                : "border-slate-700 bg-slate-900/70 text-slate-300 hover:border-slate-500 hover:text-white"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
