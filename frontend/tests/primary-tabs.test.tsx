import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PrimaryTabs } from "@/components/primary-tabs";

describe("PrimaryTabs", () => {
  it("makes the imaging workspace primary while preserving scheduling automation", () => {
    render(<PrimaryTabs currentPath="/pacs-ops" />);

    const imaging = screen.getByRole("link", { name: "Imaging Workspace" });
    const scheduling = screen.getByRole("link", {
      name: "Scheduling Automation",
    });

    expect(imaging).toHaveAttribute("aria-current", "page");
    expect(scheduling).not.toHaveAttribute("aria-current");
    expect(imaging).toHaveAttribute("href", "/pacs-ops");
    expect(scheduling).toHaveAttribute("href", "/scheduling");
  });
});
