import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StudyWorklist } from "@/features/pacs/study-worklist";

const study = {
  id: "study-1",
  node_id: "source-1",
  study_instance_uid: "1.2.3.synthetic",
  accession_number: "ACC-SYN-0001",
  patient_id: "SYN-0001",
  patient_name: "Synthetic^Example",
  patient_birth_date: "19700101",
  patient_sex: "O",
  study_date: "20260719",
  study_description: "Synthetic CT abdomen",
  modality: "CT",
  series_count: 3,
  instance_count: 148,
};

describe("Imaging Workspace worklist", () => {
  it("prioritizes clinical study fields and keeps infrastructure details secondary", () => {
    render(
      <StudyWorklist
        studies={[study]}
        nodes={[
          {
            id: "source-1",
            name: "Source Orthanc",
            node_type: "source",
            dicom_ae_title: "SOURCE_PACS",
            active: true,
            last_health_status: "healthy",
            last_health_at: null,
          },
        ]}
        onSelectStudy={() => undefined}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Imaging Worklist" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Synthetic CT abdomen")).toBeInTheDocument();
    expect(screen.queryByText("Source Orthanc")).not.toBeInTheDocument();
    expect(screen.queryByText(/148 instances/)).not.toBeInTheDocument();
  });

  it("reveals storage and content counts only when technical details are requested", () => {
    render(
      <StudyWorklist
        studies={[study]}
        nodes={[
          {
            id: "source-1",
            name: "Source Orthanc",
            node_type: "source",
            dicom_ae_title: "SOURCE_PACS",
            active: true,
            last_health_status: "healthy",
            last_health_at: null,
          },
        ]}
        onSelectStudy={() => undefined}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Show technical details" }),
    );
    expect(screen.getByText("Source Orthanc")).toBeInTheDocument();
    expect(screen.getByText("3 series · 148 instances")).toBeInTheDocument();
  });
});
