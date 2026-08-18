import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ImagingWorklist } from "@/features/pacs/imaging-worklist";
import { PatientTimeline } from "@/features/pacs/patient-timeline";

const item = {
  id: "item-1",
  patient_id: "patient-1",
  pacs_patient_id: "SYN-0001",
  patient_name: "Aster Example",
  patient_birth_date: "1980-01-01",
  accession_number: "ACC-SYN-0001",
  modality: "CT",
  study_description: "Synthetic CT abdomen",
  study_date: "20260807",
  workflow_status: "ready_for_review",
  priority: "urgent",
  assigned_reader_id: null,
  report_status: "not_started",
  scheduled_at: null,
  received_at: "2026-08-07T09:20:00Z",
  pacs_study_id: "study-1",
  appointment_id: "appointment-1",
};

describe("Imaging Workspace projection", () => {
  it("shows worklist status and priority while keeping assignment optional", () => {
    render(<ImagingWorklist items={[item]} onSelect={() => undefined} />);

    expect(
      screen.getByRole("heading", { name: "Unified imaging worklist" }),
    ).toBeInTheDocument();
    expect(screen.getByText("URGENT")).toBeInTheDocument();
    expect(
      within(screen.getByRole("row", { name: /Aster Example/ })).getByText(
        "Ready for review",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Unassigned")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show assignment" }));
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
  });

  it("renders a metadata-only longitudinal timeline", () => {
    render(
      <PatientTimeline
        patientName="Aster Example"
        externalPatientId="SYN-0001"
        events={[
          {
            event_type: "study",
            event_id: "study-1",
            occurred_at: "2026-08-07T09:20:00Z",
            label: "Study received",
            detail: "ACC-SYN-0001",
            status: "ready_for_review",
          },
        ]}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Patient timeline" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Study received")).toBeInTheDocument();
    expect(screen.getByText("Metadata only")).toBeInTheDocument();
  });
});
