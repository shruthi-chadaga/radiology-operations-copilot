"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { z } from "zod";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SessionUserSchema = z
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
  .strict();

export type SessionUser = z.infer<typeof SessionUserSchema>;

type SessionContextValue = {
  user: SessionUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  clear: () => void;
};

const SessionContext = createContext<SessionContextValue>({
  user: null,
  loading: false,
  refresh: async () => undefined,
  clear: () => undefined,
});

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/me`, {
        credentials: "include",
      });
      if (!response.ok) {
        setUser(null);
        return;
      }
      setUser(SessionUserSchema.parse(await response.json()));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <SessionContext.Provider
      value={{ user, loading, refresh, clear: () => setUser(null) }}
    >
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  return useContext(SessionContext);
}
