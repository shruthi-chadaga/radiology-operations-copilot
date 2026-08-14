import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportEditor } from "@/features/pacs/report-editor";

const draft = { id: "report-1", study_id: "study-1", status: "draft", current_version_number: 1, finalized_by: null, finalized_at: null, created_at: "2026-08-07T00:00:00Z", updated_at: "2026-08-07T00:00:00Z", versions: [{ id: "version-1", version_number: 1, kind: "draft", author_id: "reader-1", indication: "", findings: "", impression: "", correction_reason: null, created_at: "2026-08-07T00:00:00Z" }] };
const finalized = { ...draft, status: "finalized", current_version_number: 2, finalized_by: "reader-1", finalized_at: "2026-08-07T01:00:00Z", versions: [...draft.versions, { ...draft.versions[0], id: "version-2", version_number: 2, kind: "final" }] };

describe("ReportEditor", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (!options) return Promise.resolve({ status: 404, ok: false, json: async () => ({}) });
      return Promise.resolve({ status: 200, ok: true, json: async () => url.endsWith("/finalize") ? finalized : draft });
    }));
  });

  it("saves an authored draft and finalizes it as a new immutable version", async () => {
    render(<ReportEditor studyId="study-1" canWrite />);
    fireEvent.change(await screen.findByLabelText("Findings"), { target: { value: "Synthetic findings" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(screen.getByText("Saved to the immutable report history.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Finalize authored report" }));
    await waitFor(() => expect(screen.getByText("v2 · final")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/report/draft"), expect.objectContaining({ method: "POST", credentials: "include" }));
  });
});
