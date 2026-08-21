import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/components/session-context";
import { IncidentReviewPanel } from "@/features/pacs/incident-review-panel";

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
    if (url.endsWith("/api/v1/incidents")) {
      return jsonResponse({ items: [] });
    }
    throw new Error(`Unexpected request: ${url}`);
  }) as unknown as typeof fetch;
}

describe("system_admin approval surface", () => {
  it("renders the incident review panel for system_admin without PACS write access", async () => {
    stubSession("system_admin");
    render(
      <SessionProvider>
        <div aria-label="pacs-ops-surface">
          <IncidentReviewPanel />
        </div>
      </SessionProvider>,
    );

    expect(
      await screen.findByText("No open incidents require review."),
    ).toBeInTheDocument();
  });

  it("hides evidence recovery from roles that cannot approve", async () => {
    stubSession("auditor");
    render(
      <SessionProvider>
        <IncidentReviewPanel />
      </SessionProvider>,
    );

    await screen.findByText("No open incidents require review.");
    expect(
      screen.queryByRole("button", { name: "Recover evidence" }),
    ).not.toBeInTheDocument();
  });
});
