import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PacsOperationsWorkspace } from "@/features/pacs/pacs-operations-workspace";

describe("PacsOperationsWorkspace", () => {
  it("shows node health, metadata-only inventory, transfers, and no destructive controls", () => {
    render(
      <PacsOperationsWorkspace
        currentRole="pacs_admin"
        initialNodes={[
          {
            id: "source-1",
            name: "Source Orthanc",
            node_type: "source",
            dicom_ae_title: "SOURCE_PACS",
            active: true,
            last_health_status: "healthy",
            last_health_at: "2026-07-19T12:00:00Z",
          },
        ]}
        initialStudies={[
          {
            id: "study-1",
            node_id: "source-1",
            study_instance_uid: "1.2.3.synthetic",
            accession_number: "ACC-SYN-0001",
            patient_id: "SYN-0001",
            study_description: "Synthetic transfer object",
            series_count: 1,
            instance_count: 2,
          },
        ]}
        initialTransfers={[]}
      />,
    );

    expect(
      screen.getByText("Non-destructive PACS adapter"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Source Orthanc" }),
    ).toBeInTheDocument();
    expect(screen.getByText("healthy")).toBeInTheDocument();
    expect(screen.getAllByText("ACC-SYN-0001")).toHaveLength(2);
    expect(
      screen.getByText("Metadata only — no pixels stored in PostgreSQL"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /delete/i }),
    ).not.toBeInTheDocument();
  });

  it("hides PACS mutation controls from auditors", () => {
    render(
      <PacsOperationsWorkspace
        currentRole="auditor"
        initialNodes={[]}
        initialStudies={[]}
        initialTransfers={[]}
      />,
    );

    expect(
      screen.getByText("Your current role cannot create PACS transfers."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Queue transfer" }),
    ).not.toBeInTheDocument();
  });
});
