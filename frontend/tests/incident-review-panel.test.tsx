import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Mock } from "vitest";

import { SessionProvider } from "@/components/session-context";
import { IncidentReviewPanel } from "@/features/pacs/incident-review-panel";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const approval = {
  id: "approval-1",
  proposal_id: "proposal-1",
  approver_id: "user-om",
  approver_role: "operations_manager",
  decision: "approved",
  decision_reason: "Synthetic fresh health evidence",
  policy_snapshot: { approval_is_not_execution: true },
  created_at: "2026-08-20T10:00:00Z",
};

const pendingProposal = {
  id: "proposal-1",
  incident_id: "incident-1",
  requested_action: "RETRY_TRANSFER",
  proposer_id: "user-pa",
  proposer_role: "pacs_admin",
  rationale: "Review the synthetic outage",
  policy_snapshot: {},
  status: "pending",
  created_at: "2026-08-20T09:00:00Z",
  decided_at: null,
  approval: null,
};

const supersededProposal = {
  ...pendingProposal,
  id: "proposal-2",
  status: "superseded",
  decided_at: "2026-08-20T09:30:00Z",
  approval: null,
};

const approvedProposal = {
  ...pendingProposal,
  status: "approved",
  decided_at: "2026-08-20T09:15:00Z",
  approval,
};

function makeIncident(proposals: unknown[]) {
  return {
    id: "incident-1",
    incident_number: "INC-SYN-001",
    transfer_job_id: "job-1",
    study_id: "study-1",
    source_node_id: "node-1",
    destination_node_id: "node-2",
    category: "connectivity",
    severity: "high",
    status: "open",
    approval_state: "pending",
    retry_candidate: true,
    requires_human_review: true,
    confidence: 1,
    rule_code: "CONNECTIVITY_RETRY_REQUIRES_APPROVAL",
    redacted_summary: "Destination unavailable during synthetic transfer",
    evidence: { classification_rule: "CONNECTIVITY" },
    created_at: "2026-08-20T08:00:00Z",
    updated_at: "2026-08-20T09:00:00Z",
    proposals,
  };
}

function stubSession(role: string, userId = "user-om") {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/v1/auth/me")) {
      return jsonResponse({
        id: userId,
        email: `${role}@example.local`,
        display_name: `Synthetic ${role}`,
        role,
      });
    }
    if (url.endsWith("/api/v1/incidents")) {
      return jsonResponse({ items: [makeIncident([pendingProposal])] });
    }
    throw new Error(`Unexpected request: ${url}`);
  }) as unknown as typeof fetch;
}

function renderPanel() {
  return render(
    <SessionProvider>
      <IncidentReviewPanel />
    </SessionProvider>,
  );
}

beforeEach(() => {
  stubSession("operations_manager");
});

describe("incident review panel strict schemas", () => {
  it("renders incidents returned in the documented contract", async () => {
    renderPanel();
    expect(
      await screen.findByText(/INC-SYN-001 · connectivity/),
    ).toBeInTheDocument();
  });

  it("rejects unexpected fields instead of rendering them silently", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return jsonResponse({
          id: "user-om",
          email: "om@example.local",
          display_name: "Synthetic OM",
          role: "operations_manager",
        });
      }
      if (url.endsWith("/api/v1/incidents")) {
        const incident = makeIncident([]) as Record<string, unknown>;
        incident.executive_summary_ai = "untrusted generated narrative";
        return jsonResponse({ items: [incident] });
      }
      throw new Error(`Unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderPanel();
    await waitFor(() => {
      expect(
        screen.getByText("Incident review data could not be loaded."),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/untrust/)).not.toBeInTheDocument();
  });

  it("shows a superseded proposal as inactive and offers a fresh proposal form", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return jsonResponse({
          id: "user-pa",
          email: "pa@example.local",
          display_name: "Synthetic PA",
          role: "pacs_admin",
        });
      }
      if (url.endsWith("/api/v1/incidents")) {
        return jsonResponse({ items: [makeIncident([supersededProposal])] });
      }
      throw new Error(`Unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderPanel();
    expect(await screen.findByText(/superseded/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Propose review" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve/i }),
    ).not.toBeInTheDocument();
  });

  it("does not offer approve or reject on an already-approved proposal", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return jsonResponse({
          id: "user-sa",
          email: "sa@example.local",
          display_name: "Synthetic SA",
          role: "system_admin",
        });
      }
      if (url.endsWith("/api/v1/incidents")) {
        return jsonResponse({ items: [makeIncident([approvedProposal])] });
      }
      throw new Error(`Unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderPanel();
    expect(await screen.findByText("approved")).toBeInTheDocument();
    expect(
      screen.getByText(/Approval evidence: approved by/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve evidence/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^reject$/i }),
    ).not.toBeInTheDocument();
  });

  it("loads incidents for an authorized system_admin", async () => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return jsonResponse({
          id: "user-sa",
          email: "sa@example.local",
          display_name: "Synthetic SA",
          role: "system_admin",
        });
      }
      if (url.endsWith("/api/v1/incidents")) {
        return jsonResponse({ items: [] });
      }
      throw new Error(`Unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    renderPanel();
    expect(
      await screen.findByText("No open incidents require review."),
    ).toBeInTheDocument();
    expect((global.fetch as Mock).mock.calls.length).toBeGreaterThan(0);
  });

  it("records an approval decision with the entered reason and refreshes", async () => {
    const postCalls: Array<{ url: string; body: unknown }> = [];
    global.fetch = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/auth/me")) {
          return jsonResponse({
            id: "user-sa",
            email: "sa@example.local",
            display_name: "Synthetic SA",
            role: "system_admin",
          });
        }
        if (
          url.endsWith("/api/v1/incidents") &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse({ items: [makeIncident([pendingProposal])] });
        }
        if (
          url.endsWith("/api/v1/incidents/proposals/proposal-1/approve") &&
          init?.method === "POST"
        ) {
          postCalls.push({ url, body: JSON.parse(String(init.body)) });
          return jsonResponse({ status: "approved" });
        }
        throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
      },
    ) as unknown as typeof fetch;

    const promptSpy = vi
      .spyOn(window, "prompt")
      .mockReturnValue("Synthetic fresh health evidence");
    try {
      renderPanel();
      fireEvent.click(
        await screen.findByRole("button", { name: "Approve evidence" }),
      );
      await screen.findByText(
        /Approval recorded\. Execution remains disabled in this slice\./,
      );
      expect(postCalls).toHaveLength(1);
      expect(postCalls[0].body).toEqual({
        decision_reason: "Synthetic fresh health evidence",
      });
    } finally {
      promptSpy.mockRestore();
    }
  });

  it("does not POST a decision when the reason prompt is cancelled or blank", async () => {
    let approveCalls = 0;
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/auth/me")) {
        return jsonResponse({
          id: "user-sa",
          email: "sa@example.local",
          display_name: "Synthetic SA",
          role: "system_admin",
        });
      }
      if (url.endsWith("/api/v1/incidents")) {
        return jsonResponse({ items: [makeIncident([pendingProposal])] });
      }
      if (url.endsWith("/api/v1/incidents/proposals/proposal-1/approve")) {
        approveCalls += 1;
        return jsonResponse({ status: "approved" });
      }
      throw new Error(`Unexpected request: ${url}`);
    }) as unknown as typeof fetch;

    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("   ");
    try {
      renderPanel();
      fireEvent.click(
        await screen.findByRole("button", { name: "Approve evidence" }),
      );
      expect(approveCalls).toBe(0);
      expect((global.fetch as Mock).mock.calls.length).toBeGreaterThan(0);
    } finally {
      promptSpy.mockRestore();
    }
  });
});
