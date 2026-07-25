"use client";

import Link from "next/link";
import { useState } from "react";

import { AuthorizationBadge } from "@/components/authorization-badge";
import { useSession } from "@/components/session-context";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function SessionControls() {
  const { user, loading, refresh, clear } = useSession();
  const [message, setMessage] = useState("");

  async function logout() {
    setMessage("Signing out…");
    clear();
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
      await refresh();
      if (!response.ok) {
        setMessage(`Logout failed (${response.status}).`);
        return;
      }
      setMessage("");
    } catch {
      setMessage("Logout failed because the API is unavailable.");
    }
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <AuthorizationBadge />
      {loading ? null : user ? (
        <button
          type="button"
          className="text-slate-300 hover:text-white"
          onClick={() => void logout()}
        >
          Logout
        </button>
      ) : (
        <Link className="text-slate-300 hover:text-white" href="/login">
          Login
        </Link>
      )}
      <span className="sr-only" aria-live="polite">
        {message}
      </span>
    </div>
  );
}
