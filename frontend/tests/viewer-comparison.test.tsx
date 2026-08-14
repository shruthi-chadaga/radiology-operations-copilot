import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ViewerComparison } from "@/features/pacs/viewer-comparison";

const current = { study_id: "study-current", accession_number: "ACC-CURRENT", study_instance_uid: "uid-current", study_date: "20260807", modality: "CT", study_description: "Synthetic CT abdomen", is_synthetic: true, preview_available: true, representative_instance_id: "instance-current", series_count: 1, instance_count: 2 };
const prior = { ...current, study_id: "study-prior", accession_number: "ACC-PRIOR", study_date: "20260101", representative_instance_id: "instance-prior" };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(["preview"], { type: "image/png" })) }));
  vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:preview"), revokeObjectURL: vi.fn() });
});

describe("Phase 2 viewer comparison", () => {
  it("loads an authenticated current preview and explicitly selects a prior", async () => {
    render(<ViewerComparison current={current} priors={[prior]} />);
    await waitFor(() => expect(screen.getByAltText("Current synthetic preview")).toBeInTheDocument());
    expect(screen.queryByAltText("Prior synthetic preview")).not.toBeInTheDocument();
    expect(screen.getByText("Synthetic demo")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("study-current/preview/instance-current"), expect.objectContaining({ credentials: "include" }));
    fireEvent.change(screen.getByLabelText("Compare prior"), { target: { value: "study-prior" } });
    await waitFor(() => expect(screen.getByAltText("Prior synthetic preview")).toBeInTheDocument());
    expect(screen.getAllByText("Synthetic demo")).toHaveLength(2);
  });
});
