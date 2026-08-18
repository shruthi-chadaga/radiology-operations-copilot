import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReportEditor } from "@/features/pacs/report-editor";

const authoredText = {
  indication: "Synthetic indication",
  findings: "Synthetic findings",
  impression: "Synthetic impression",
};
const correctedText = {
  indication: "Synthetic corrected indication",
  findings: "Synthetic corrected findings",
  impression: "Synthetic corrected impression",
};
const draft = { id: "report-1", study_id: "study-1", status: "draft", current_version_number: 1, finalized_by: null, finalized_at: null, created_at: "2026-08-07T00:00:00Z", updated_at: "2026-08-07T00:00:00Z", versions: [{ id: "version-1", version_number: 1, kind: "draft", author_id: "reader-1", ...authoredText, correction_reason: null, created_at: "2026-08-07T00:00:00Z" }] };
const finalized = { ...draft, status: "finalized", current_version_number: 2, finalized_by: "reader-1", finalized_at: "2026-08-07T01:00:00Z", versions: [...draft.versions, { ...draft.versions[0], id: "version-2", version_number: 2, kind: "final" }] };
const corrected = { ...finalized, current_version_number: 3, updated_at: "2026-08-07T02:00:00Z", versions: [...finalized.versions, { ...draft.versions[0], id: "version-3", version_number: 3, kind: "correction", ...correctedText, correction_reason: "Synthetic correction reason" }] };

describe("ReportEditor", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
      const payload = url.endsWith("/finalize") ? finalized : url.endsWith("/correction") ? corrected : draft;
      return Promise.resolve({ status: 200, ok: true, json: async () => payload });
    }));
  });

  it("saves an authored draft, finalizes it, and creates an edited immutable correction", async () => {
    render(<ReportEditor studyId="study-1" canWrite />);
    fireEvent.change(await screen.findByLabelText("Indication"), { target: { value: authoredText.indication } });
    fireEvent.change(screen.getByLabelText("Findings"), { target: { value: authoredText.findings } });
    fireEvent.change(screen.getByLabelText("Impression"), { target: { value: authoredText.impression } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(screen.getByText("Saved to the immutable report history.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/report/draft"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ ...authoredText, expected_version_number: 1 }),
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Finalize authored report" }));
    await waitFor(() => expect(screen.getByText("v2 · final")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/finalize"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ expected_version_number: 1 }),
      }),
    );

    const correctionButton = screen.getByRole("button", { name: "Create correction version" });
    expect(correctionButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Indication"), { target: { value: "" } });
    fireEvent.change(screen.getByPlaceholderText("Correction reason"), { target: { value: "Synthetic correction reason" } });
    expect(correctionButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Indication"), { target: { value: correctedText.indication } });
    fireEvent.change(screen.getByLabelText("Findings"), { target: { value: correctedText.findings } });
    fireEvent.change(screen.getByLabelText("Impression"), { target: { value: correctedText.impression } });
    fireEvent.change(screen.getByPlaceholderText("Correction reason"), { target: { value: "  Synthetic correction reason  " } });
    expect(correctionButton).not.toBeDisabled();
    fireEvent.click(correctionButton);
    await waitFor(() => expect(screen.getByText("v3 · correction")).toBeInTheDocument());
    expect(screen.getByText("v2 · final")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/correction"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({
          ...correctedText,
          correction_reason: "Synthetic correction reason",
          expected_version_number: 2,
        }),
      }),
    );
  });

  it("omits a version when starting a not-yet-started report", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (!options?.method) return Promise.resolve({ status: 404, ok: false, json: async () => ({}) });
      return Promise.resolve({ status: 200, ok: true, json: async () => draft });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReportEditor studyId="study-1" canWrite />);
    fireEvent.change(await screen.findByLabelText("Indication"), { target: { value: authoredText.indication } });
    fireEvent.change(screen.getByLabelText("Findings"), { target: { value: authoredText.findings } });
    fireEvent.change(screen.getByLabelText("Impression"), { target: { value: authoredText.impression } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/report/draft"),
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify(authoredText),
      }),
    ));
  });

  it("fails closed when the report has no current version", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 200, ok: true, json: async () => ({ ...draft, current_version_number: null }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReportEditor studyId="study-1" canWrite />);
    expect(await screen.findByRole("button", { name: "Finalize authored report" })).toBeDisabled();
  });

  it("shows a stale-version detail without retrying the finalization", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (!options?.method) return Promise.resolve({ status: 200, ok: true, json: async () => draft });
      return Promise.resolve({ status: 409, ok: false, json: async () => ({ detail: "Synthetic stale report version" }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReportEditor studyId="study-1" canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "Finalize authored report" }));
    await waitFor(() => expect(screen.getByText("Synthetic stale report version")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining("/finalize"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_version_number: 1 }),
      }),
    );
  });
});
