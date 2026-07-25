"use client";

import { useSession } from "@/components/session-context";

export function AuthorizationBadge() {
  const { user, loading } = useSession();
  const label = loading
    ? "Checking session"
    : user
      ? `Role: ${user.role.replaceAll("_", " ")}`
      : "Not signed in";
  return (
    <span className="rounded-full border border-slate-700 px-3 py-1 text-slate-300">
      {label}
    </span>
  );
}
