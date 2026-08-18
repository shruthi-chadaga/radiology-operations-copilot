import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { IncidentReviewPanel } from "@/features/pacs/incident-review-panel";

const fetchMock = vi.fn();
const promptMock = vi.fn();

vi.mock("@/components/session-context", () => ({
  useSession: () => ({
    user: {
      id: "manager-1",
      email: "manager@example.local",
      display_name: "Operations Manager",
      role: "operations_manager",
    },
    loading: false,
  }),
}));

const incident = {
  id: "incident-1",
  incident_number: "PACS-INC-001",
  category: "connectivity",
  severity: "medium",
  status: "pending_approval",
  approval_state: "pending",
  retry_candidate: true,
  redacted_summary: "DestinationUnavailable: transfer request failed",
  proposals: [
    {
      id: "proposal-1",
      requested_action: "RETRY_TRANSFER",
      proposer_id: "operator-1",
      status: "pending",
      rationale: "Review the destination outage",
      approval: null,
    },
  ],
};

describe("IncidentReviewPanel", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    promptMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("prompt", promptMock);
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ items: [incident] }),
    });
  });

  it("shows a pending proposal and records a separately reasoned approval", async () => {
    promptMock.mockReturnValue("Fresh destination health evidence reviewed");
    render(<IncidentReviewPanel />);

    expect(await screen.findByText(/PACS-INC-001/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve evidence" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/api/v1/incidents/proposals/proposal-1/approve",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(promptMock).toHaveBeenCalledWith("Approval reason");
  });

  it("keeps the no-execution boundary visible", async () => {
    render(<IncidentReviewPanel />);

    expect(
      await screen.findByText(
        /never retries a transfer or performs remediation/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /retry transfer/i }),
    ).not.toBeInTheDocument();
  });
});
