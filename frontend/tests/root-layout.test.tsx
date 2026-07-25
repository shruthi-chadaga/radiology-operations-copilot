import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuthorizationBadge } from "@/components/authorization-badge";

describe("AuthorizationBadge", () => {
  it("does not claim a role before backend authentication succeeds", () => {
    render(<AuthorizationBadge />);

    expect(screen.getByText("Not signed in")).toBeInTheDocument();
    expect(screen.queryByText("Role: demo viewer")).not.toBeInTheDocument();
  });
});
