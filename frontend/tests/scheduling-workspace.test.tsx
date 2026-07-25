import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SchedulingWorkspace } from "@/features/scheduling/scheduling-workspace";

describe("SchedulingWorkspace", () => {
  it("shows referral intake, review controls, confidence, and a synthetic queue", () => {
    render(
      <SchedulingWorkspace
        currentRole="scheduler"
        initialReferrals={[
          {
            id: "ref-1",
            referral_number: "REF-SYN-0001",
            patient_id: "patient-syn-1",
            source_text: "Routine CT abdomen. Authorization approved.",
            requested_exam: "CT abdomen",
            modality: "CT",
            body_region: "abdomen",
            status: "ready",
            completeness_status: "complete",
            extraction_confidence: 0.95,
          },
        ]}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "New synthetic referral" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Synthetic patient UUID")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Synthetic referral text"),
    ).toBeInTheDocument();
    expect(screen.getByText("REF-SYN-0001")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Extract and validate REF-SYN-0001" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Human review remains mandatory for detected ambiguity; identity-conflict detection is planned.",
      ),
    ).toBeInTheDocument();
  });

  it("hides scheduling mutation controls from auditors", () => {
    render(<SchedulingWorkspace currentRole="auditor" initialReferrals={[]} />);

    expect(
      screen.getByText("Your current role has read-only scheduling access."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create referral" }),
    ).not.toBeInTheDocument();
  });
});
