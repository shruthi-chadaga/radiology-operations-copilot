import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PrimaryTabs } from "@/components/primary-tabs";

describe("PrimaryTabs", () => {
  it("renders the two automation domains as prominent navigation tabs", () => {
    render(<PrimaryTabs currentPath="/scheduling" />);

    const scheduling = screen.getByRole("link", {
      name: "Scheduling Automation",
    });
    const pacs = screen.getByRole("link", { name: "PACS/RIS Automation" });

    expect(scheduling).toHaveAttribute("aria-current", "page");
    expect(pacs).not.toHaveAttribute("aria-current");
    expect(scheduling).toHaveAttribute("href", "/scheduling");
    expect(pacs).toHaveAttribute("href", "/pacs-ops");
  });
});
