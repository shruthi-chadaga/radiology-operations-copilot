import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  ImagingWorklist,
  type WorklistItem,
} from "@/features/pacs/imaging-worklist";

function makeItem(overrides: Partial<WorklistItem> = {}): WorklistItem {
  return {
    id: "item-1",
    patient_id: null,
    pacs_patient_id: "SYN-PAT-1",
    patient_name: "Synthetic Patient One",
    patient_birth_date: null,
    accession_number: "ACC-SYN-100",
    modality: "CT",
    study_description: "Synthetic CT abdomen",
    study_date: "20260801",
    workflow_status: "ready_for_review",
    priority: "routine",
    assigned_reader_id: null,
    report_status: "none",
    scheduled_at: null,
    received_at: null,
    pacs_study_id: "study-uuid-1",
    appointment_id: null,
    ...overrides,
  };
}

describe("imaging worklist accessibility", () => {
  it("activates a work item with Enter from keyboard focus", () => {
    const onSelect = vi.fn();
    const items = [
      makeItem(),
      makeItem({ id: "item-2", accession_number: "ACC-SYN-200" }),
    ];
    render(<ImagingWorklist items={items} onSelect={onSelect} />);

    const row = screen.getByRole("row", { name: /ACC-SYN-200/ });
    row.focus();
    fireEvent.keyDown(row, { key: "Enter" });

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(items[1]);
  });

  it("activates a work item with Space from keyboard focus", () => {
    const onSelect = vi.fn();
    render(<ImagingWorklist items={[makeItem()]} onSelect={onSelect} />);

    const row = screen.getByRole("row", { name: /ACC-SYN-100/ });
    row.focus();
    fireEvent.keyDown(row, { key: " " });

    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("exposes every row with a descriptive accessible name", () => {
    const onSelect = vi.fn();
    render(
      <ImagingWorklist
        items={[
          makeItem(),
          makeItem({
            id: "item-2",
            accession_number: "ACC-SYN-200",
            patient_name: "Synthetic Patient Two",
          }),
        ]}
        onSelect={onSelect}
      />,
    );

    expect(
      screen.getByRole("row", { name: /ACC-SYN-100/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("row", { name: /Synthetic Patient Two/ }),
    ).toBeInTheDocument();
  });

  it("marks rows as keyboard-focusable selection targets", () => {
    const onSelect = vi.fn();
    render(<ImagingWorklist items={[makeItem()]} onSelect={onSelect} />);

    const row = screen.getByRole("row", { name: /ACC-SYN-100/ });
    expect(row).toHaveAttribute("tabindex", "0");
  });
});
