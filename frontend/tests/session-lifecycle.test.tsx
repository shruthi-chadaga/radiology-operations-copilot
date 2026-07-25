import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionControls } from "@/components/session-controls";
import { SessionProvider, useSession } from "@/components/session-context";
import { PacsOperationsWorkspace } from "@/features/pacs/pacs-operations-workspace";

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function SessionContextProbe() {
  const { user } = useSession();
  return <span>{user?.role ?? "anonymous"}</span>;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("session lifecycle", () => {
  it("accepts a system_admin session returned by the backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: "admin-1",
          email: "admin@example.local",
          display_name: "Synthetic System Admin",
          role: "system_admin",
        }),
      ),
    );

    render(
      <SessionProvider>
        <SessionContextProbe />
      </SessionProvider>,
    );

    expect(await screen.findByText("system_admin")).toBeInTheDocument();
  });

  it("clears loaded PACS data when an expired-session logout returns 401", async () => {
    let loggedOut = false;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/api/v1/auth/logout")) {
          loggedOut = true;
          return jsonResponse({}, 401);
        }
        if (url.endsWith("/api/v1/auth/me")) {
          return loggedOut
            ? jsonResponse({}, 401)
            : jsonResponse({
                id: "pacs-admin-1",
                email: "pacs@example.local",
                display_name: "Synthetic PACS Admin",
                role: "pacs_admin",
              });
        }
        if (url.endsWith("/api/v1/pacs/nodes")) {
          return jsonResponse({
            items: [
              {
                id: "source-1",
                name: "Source Orthanc",
                node_type: "source",
                dicom_ae_title: "SOURCE_PACS",
                active: true,
                last_health_status: "healthy",
                last_health_at: null,
              },
            ],
          });
        }
        if (url.endsWith("/api/v1/pacs/studies"))
          return jsonResponse({ items: [] });
        if (url.endsWith("/api/v1/pacs/transfers"))
          return jsonResponse({ items: [] });
        throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SessionProvider>
        <SessionControls />
        <PacsOperationsWorkspace />
      </SessionProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Source Orthanc" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Logout" }));

    await waitFor(() => {
      expect(
        screen.queryByRole("heading", { name: "Source Orthanc" }),
      ).not.toBeInTheDocument();
    });
    expect(
      await screen.findByRole("link", { name: "Login" }),
    ).toBeInTheDocument();
  });
});
