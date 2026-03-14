import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RegionMap } from "../RegionMap";

const REGIONS_WITH_COORDS = [
  { name: "Plains", terrain: "plains", x: 0.3, y: 0.5 },
  { name: "Desert", terrain: "desert", x: 0.7, y: 0.3 },
];

const REGIONS_NULL_COORDS = [
  { name: "Region A", terrain: "forest", x: null, y: null },
  { name: "Region B", terrain: "mountain", x: null, y: null },
  { name: "Region C", terrain: "plains", x: null, y: null },
];

describe("RegionMap", () => {
  it("renders SVG with region labels", () => {
    render(<RegionMap regions={REGIONS_WITH_COORDS} />);
    expect(screen.getByText("Plains")).toBeTruthy();
    expect(screen.getByText("Desert")).toBeTruthy();
  });

  it("renders with null coordinates using circle layout", () => {
    render(<RegionMap regions={REGIONS_NULL_COORDS} />);
    expect(screen.getByText("Region A")).toBeTruthy();
    expect(screen.getByText("Region B")).toBeTruthy();
    expect(screen.getByText("Region C")).toBeTruthy();
  });

  it("renders empty state when no regions", () => {
    render(<RegionMap regions={[]} />);
    const svg = document.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("renders with controller coloring when provided", () => {
    render(
      <RegionMap
        regions={REGIONS_WITH_COORDS}
        controllers={{ Plains: "CivA", Desert: null }}
      />
    );
    expect(screen.getByText("Plains")).toBeTruthy();
  });
});
