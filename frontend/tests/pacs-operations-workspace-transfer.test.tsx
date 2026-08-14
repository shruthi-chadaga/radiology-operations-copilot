import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  PacsOperationsWorkspace,
  type PacsNode,
  type PacsStudy,
} from "@/features/pacs/pacs-operations-workspace";

const nodes: PacsNode[] = [
  {
    id: "node-source",
    name: "Synthetic source",
    node_type: "source",
    dicom_ae_title: "SYN_SOURCE",
    active: true,
    last_health_status: "healthy",
    last_health_at: null,
  },
  {
    id: "node-destination",
    name: "Synthetic destination",
    node_type: "destination",
    dicom_ae_title: "SYN_DESTINATION",
    active: true,
    last_health_status: "healthy",
    last_health_at: null,
  },
];

const studies: PacsStudy[] = [
  {
    id: "study-first-uuid",
    node_id: "node-source",
    study_instance_uid: "1.2.3.1",
    accession_number: "ACC-FIRST",
    patient_id: "SYN-PATIENT-1",
    patient_name: "Synthetic First",
    patient_birth_date: null,
    patient_sex: null,
    study_date: "20260814",
    study_description: "Synthetic first study",
    modality: "CT",
    series_count: 1,
    instance_count: 1,
  },
  {
    id: "study-second-uuid",
    node_id: "node-source",
    study_instance_uid: "1.2.3.2",
    accession_number: "ACC-SECOND",
    patient_id: "SYN-PATIENT-2",
    patient_name: "Synthetic Second",
    patient_birth_date: null,
    patient_sex: null,
    study_date: "20260814",
    study_description: "Synthetic second study",
    modality: "MR",
    series_count: 1,
    instance_count: 1,
  },
];

const acceptedTransfer = {
  id: "transfer-1",
  source_node_id: "node-source",
  destination_node_id: "node-destination",
  study_id: "study-second-uuid",
  status: "queued",
  retry_count: 0,
  maximum_retries: 3,
  correlation_id: "correlation-1",
};

describe("PacsOperationsWorkspace transfer form", () => {
  it("adopts a late explicit preselection when embedded studies arrive", () => {
    const { rerender } = render(
      <PacsOperationsWorkspace embedded nodes={nodes} studies={[]} canWrite />,
    );

    const studySelect = screen.getByRole("combobox", {
      name: "Synthetic study",
    });
    rerender(
      <PacsOperationsWorkspace
        embedded
        nodes={nodes}
        studies={studies}
        canWrite
        preselectedStudyId="study-second-uuid"
      />,
    );

    expect(studySelect).toHaveValue("study-second-uuid");
    expect(
      screen.getByText("Selected synthetic study: ACC-SECOND"),
    ).toBeInTheDocument();
  });

  it("preselects and submits the study UUID rather than an accession or another study", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string, options?: RequestInit) => {
        if (options?.method === "POST") {
          return Promise.resolve({
            ok: true,
            status: 201,
            json: async () => acceptedTransfer,
          });
        }
        if (url.endsWith("/nodes")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ items: nodes }),
          });
        }
        if (url.endsWith("/studies")) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ items: studies }),
          });
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ items: [] }),
        });
      });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <PacsOperationsWorkspace
        embedded
        nodes={nodes}
        studies={studies}
        canWrite
        preselectedStudyId="study-second-uuid"
      />,
    );

    const studySelect = screen.getByRole("combobox", {
      name: "Synthetic study",
    });
    expect(studySelect).toHaveValue("study-second-uuid");
    expect(
      screen.getByText("Selected synthetic study: ACC-SECOND"),
    ).toBeInTheDocument();

    fireEvent.submit(studySelect.closest("form")!);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/pacs/transfers"),
        expect.objectContaining({ body: expect.any(String) }),
      ),
    );
    const transferRequest = fetchMock.mock.calls.find(
      ([url, options]) =>
        url.endsWith("/api/v1/pacs/transfers") && options?.method === "POST",
    );
    const submitted = JSON.parse(transferRequest?.[1].body as string) as {
      study_id: string;
    };
    expect(submitted.study_id).toBe("study-second-uuid");
    expect(submitted.study_id).not.toBe("ACC-SECOND");
    expect(submitted.study_id).not.toBe("study-first-uuid");
  });
});
