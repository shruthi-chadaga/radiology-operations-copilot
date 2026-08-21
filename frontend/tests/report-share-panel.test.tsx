import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/components/session-context";
import {
  ReportSharePanel,
  type ShareEntry,
} from "@/features/pacs/report-share-panel";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const shareA: ShareEntry = {
  id: "share-1",
  report_id: "report-1",
  study_id: "study-1",
  recipient_label: "Referring clinic",
  status: "active",
  created_by: "user-1",
  created_at: "2026-08-21T10:00:00Z",
  expires_at: "2026-08-23T10:00:00Z",
  revoked_at: null,
};

const shareB: ShareEntry = {
  ...shareA,
  id: "share-2",
  recipient_label: "External audit copy",
  status: "revoked",
  revoked_at: "2026-08-22T09:00:00Z",
};

function stubFetch(shares: ShareEntry[], created?: unknown) {
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/imaging/reports/report-1/shares")) {
      if (method === "GET") return jsonResponse({ items: shares });
      if (method === "POST") {
        if (created) return jsonResponse(created, 201);
        return jsonResponse({ detail: "conflict" }, 409);
      }
    }
    throw new Error(`Unexpected request: ${url} ${method}`);
  }) as unknown as typeof fetch;
}

describe("report share panel", () => {
  it("lists allowlisted recipients with strict schema and hides tokens", async () => {
    stubFetch([shareA, shareB]);
    render(
      <SessionProvider>
        <ReportSharePanel reportId="report-1" canWrite />
      </SessionProvider>,
    );

    expect(await screen.findByText("Referring clinic")).toBeInTheDocument();
    expect(screen.getByText("External audit copy")).toBeInTheDocument();
    expect(screen.getByText(/revoked/i)).toBeInTheDocument();
    // List payloads never contain tokens: no code/token value is rendered.
    expect(document.querySelector("code")).toBeNull();
  });

  it("shows the one-time token exactly once after creation", async () => {
    stubFetch([shareA], {
      ...shareA,
      id: "share-3",
      recipient_label: "Cardiology second read",
      token: "one-time-token-abc123",
    });
    render(
      <SessionProvider>
        <ReportSharePanel reportId="report-1" canWrite />
      </SessionProvider>,
    );

    fireEvent.change(await screen.findByLabelText("Recipient label"), {
      target: { value: "Cardiology second read" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create share link" }));

    await waitFor(() => {
      expect(
        screen.getByText(/Copy this link token now — it is shown only once/),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("one-time-token-abc123")).toBeInTheDocument();
  });

  it("revokes an active share and reflects the new state", async () => {
    let current = [shareA];
    global.fetch = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/v1/auth/me")) {
          return jsonResponse({
            id: "user-1",
            email: "pacs_admin@example.local",
            display_name: "Synthetic PACS Admin",
            role: "pacs_admin",
          });
        }
        if (
          url.endsWith("/api/v1/imaging/reports/report-1/shares") &&
          method === "GET"
        ) {
          return jsonResponse({ items: current });
        }
        if (
          url.endsWith("/api/v1/imaging/reports/shares/share-1") &&
          method === "DELETE"
        ) {
          current = [
            {
              ...shareA,
              status: "revoked",
              revoked_at: "2026-08-22T10:00:00Z",
            },
          ];
          return jsonResponse(current[0]);
        }
        throw new Error(`Unexpected request: ${url} ${method}`);
      },
    ) as unknown as typeof fetch;
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(
      <SessionProvider>
        <ReportSharePanel reportId="report-1" canWrite />
      </SessionProvider>,
    );

    try {
      fireEvent.click(await screen.findByRole("button", { name: "Revoke" }));
      await waitFor(() => {
        expect(screen.getByText(/Share revoked\./)).toBeInTheDocument();
      });
      expect(confirmSpy).toHaveBeenCalled();
    } finally {
      confirmSpy.mockRestore();
    }
  });

  it("rejects unexpected fields in the API response instead of rendering them", async () => {
    stubFetch([
      {
        ...shareA,
        ai_generated_summary: "untrusted narrative",
      } as unknown as ShareEntry,
    ]);
    render(
      <SessionProvider>
        <ReportSharePanel reportId="report-1" canWrite />
      </SessionProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/could not be loaded/i)).toBeInTheDocument();
    });
  });

  it("renders a read-only notice for roles without write access", async () => {
    stubFetch([shareA]);
    render(
      <SessionProvider>
        <ReportSharePanel reportId="report-1" canWrite={false} />
      </SessionProvider>,
    );

    expect(await screen.findByText("Referring clinic")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create share link" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Revoke" }),
    ).not.toBeInTheDocument();
  });
});
