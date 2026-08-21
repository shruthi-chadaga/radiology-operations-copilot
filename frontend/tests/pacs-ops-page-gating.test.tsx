import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/components/session-context";
import PacsOpsPage from "@/app/pacs-ops/page";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function stubSession(role: string) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/v1/auth/me")) {
      return jsonResponse({
        id: `user-${role}`,
        email: `${role}@example.local`,
        display_name: `Synthetic ${role}`,
        role,
      });
    }
    if (url.endsWith("/api/v1/pacs/nodes")) return jsonResponse({ items: [] });
    if (url.endsWith("/api/v1/pacs/studies"))
      return jsonResponse({ items: [] });
    if (url.endsWith("/api/v1/imaging/worklist"))
      return jsonResponse({ items: [], generated_at: "2026-08-21T00:00:00Z" });
    if (url.endsWith("/api/v1/incidents")) return jsonResponse({ items: [] });
    throw new Error(`Unexpected request: ${url}`);
  }) as unknown as typeof fetch;
}

describe("pacs-ops page role gating", () => {
  it("renders the incident approval console for system_admin", async () => {
    stubSession("system_admin");
    render(
      <SessionProvider>
        <PacsOpsPage />
      </SessionProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Incident approval console" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Sign in with an imaging-authorized local account."),
    ).not.toBeInTheDocument();
  });

  it("does not render the approval console for pacs_admin", async () => {
    stubSession("pacs_admin");
    render(
      <SessionProvider>
        <PacsOpsPage />
      </SessionProvider>,
    );

    expect(
      await screen.findByText("Unified imaging worklist"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Incident approval console" }),
    ).not.toBeInTheDocument();
  });

  it("shows the unauthorized banner for scheduler without the console", async () => {
    stubSession("scheduler");
    render(
      <SessionProvider>
        <PacsOpsPage />
      </SessionProvider>,
    );

    expect(
      await screen.findByText(
        "Sign in with an imaging-authorized local account.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Incident approval console" }),
    ).not.toBeInTheDocument();
  });
});
