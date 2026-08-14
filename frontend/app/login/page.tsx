"use client";

import { FormEvent, useState } from "react";
import { z } from "zod";

const LoginResponseSchema = z
  .object({
    user: z
      .object({
        id: z.string(),
        email: z.string(),
        display_name: z.string(),
        role: z.enum([
          "scheduler",
          "pacs_admin",
          "operations_manager",
          "auditor",
          "system_admin",
        ]),
      })
      .strict(),
  })
  .strict();

export default function LoginPage() {
  const [message, setMessage] = useState<string>("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("Signing in…");
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/auth/login`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: data.get("email"),
            password: data.get("password"),
          }),
        },
      );
      if (!response.ok) {
        setMessage(
          "Login failed. Check the configured local demo credentials.",
        );
        return;
      }
      const login = LoginResponseSchema.parse(await response.json());
      window.location.assign(
        login.user.role === "scheduler" ? "/scheduling" : "/pacs-ops",
      );
    } catch {
      setMessage(
        "Login failed because the API response was unavailable or invalid.",
      );
    }
  }

  return (
    <section className="mx-auto max-w-lg rounded-2xl border border-slate-800 bg-slate-900/70 p-8">
      <p className="text-sm font-medium text-cyan-300">
        Seeded local accounts only
      </p>
      <h2 className="mt-2 text-2xl font-bold">Sign in</h2>
      <form onSubmit={submit} className="mt-6 space-y-5">
        <label className="block text-sm font-medium">
          Email
          <input
            required
            name="email"
            type="email"
            defaultValue="scheduler@example.local"
            className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none focus:border-cyan-400"
          />
        </label>
        <label className="block text-sm font-medium">
          Password
          <input
            required
            name="password"
            type="password"
            className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none focus:border-cyan-400"
          />
        </label>
        <button className="w-full rounded-xl bg-cyan-400 px-4 py-3 font-semibold text-slate-950 hover:bg-cyan-300">
          Sign in to local demo
        </button>
        <p aria-live="polite" className="text-sm text-slate-400">
          {message}
        </p>
      </form>
    </section>
  );
}
