import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SyntheticDataBanner } from "@/components/synthetic-data-banner";

describe("SyntheticDataBanner", () => {
  it("warns users not to enter real patient information", () => {
    render(<SyntheticDataBanner />);

    expect(screen.getByRole("status")).toHaveTextContent(
      "Synthetic portfolio environment. Do not enter real patient information.",
    );
  });
});
