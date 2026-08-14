import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { SessionControls } from "@/components/session-controls";
import { SessionProvider } from "@/components/session-context";
import { SyntheticDataBanner } from "@/components/synthetic-data-banner";
import { WorkspaceTabs } from "@/components/workspace-tabs";

import "./globals.css";

export const metadata: Metadata = {
  title: "Radiology Operations Copilot",
  description:
    "Synthetic local-first radiology imaging and scheduling operations workspace.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-slate-100 antialiased">
        <SessionProvider>
          <SyntheticDataBanner />
          <header className="border-b border-slate-800 bg-slate-950/90">
            <div className="mx-auto max-w-7xl px-5 py-5">
              <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
                <Link
                  href="/pacs-ops"
                  className="group focus-visible:outline-cyan-400"
                >
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">
                    Imaging operations workspace
                  </p>
                  <h1 className="mt-1 text-xl font-bold tracking-tight group-hover:text-cyan-100">
                    Radiology Operations Copilot
                  </h1>
                </Link>
                <SessionControls />
              </div>
              <WorkspaceTabs />
              <nav
                aria-label="Shared operations"
                className="mt-4 flex flex-wrap gap-5 text-sm text-slate-400"
              >
                <span>Exceptions</span>
                <span>Audit Log</span>
                <span>Analytics</span>
                <span>Rules &amp; Settings</span>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-7xl px-5 py-8">{children}</main>
          <footer className="mx-auto max-w-7xl border-t border-slate-800 px-5 py-6 text-xs leading-5 text-slate-500">
            This application is a synthetic portfolio prototype for healthcare
            operations workflow demonstration. It is not a production clinical
            system, medical device, diagnostic tool, or substitute for qualified
            healthcare and technical professionals. Do not enter real patient
            information.
          </footer>
        </SessionProvider>
      </body>
    </html>
  );
}
