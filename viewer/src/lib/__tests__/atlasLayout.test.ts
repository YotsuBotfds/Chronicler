import { describe, expect, it } from "vitest";
import type { MapNode, RegionLike } from "../../components/phase75/appShellTypes";
import { atlasPoint, pinFrame } from "../../components/phase75/appShellHelpers";
import type { CivilizationView } from "../civilizationViews";
import {
  buildCampaignLinks, buildRegionConnections, computeAtlasLayout, computeControllerCentroids, dominantCivilization,
  sortCivilizations,
} from "../atlasLayout";

const region = (name: string, x: number | null = null, y: number | null = null): RegionLike => ({ name, terrain: "plains", x, y });
const node = (name: string, controller: string | null, x: number, y: number): MapNode => ({ region: region(name), controller, x, y });

function civ(name: string, score: number): CivilizationView {
  return { name, population: score, military: 0, economy: 0, culture: 0, stability: 0 } as unknown as CivilizationView;
}

describe("atlas layout helpers", () => {
  it("places pinned regions through the pin frame, an unpinned one at its centre", () => {
    const regions = [region("A", 0, 0), region("B", 10, 20), region("C")];
    const frame = pinFrame(regions);
    const nodes = computeAtlasLayout(regions, { A: "X", B: null }, frame);
    expect(nodes).toEqual([
      { region: regions[0], controller: "X", ...atlasPoint(0, 0, frame) },
      { region: regions[1], controller: null, ...atlasPoint(10, 20, frame) },
      { region: regions[2], controller: undefined, ...atlasPoint(5, 10, frame) },
    ]);
    expect(computeAtlasLayout([], {}, frame)).toEqual([]);
  });

  it("rings regions without pins around their controller's group", () => {
    const regions = [region("A"), region("B"), region("C")];
    const nodes = computeAtlasLayout(regions, { A: "X", B: "Y", C: "X" }, pinFrame([]));
    expect(nodes.map((entry) => [entry.region.name, entry.controller])).toEqual([["A", "X"], ["C", "X"], ["B", "Y"]]);
    // Group X sits at the top of the ellipse (angle -pi/2), its two regions 38 units from its centre.
    expect(nodes[0].x).toBeCloseTo(500);
    expect(nodes[0].y).toBeCloseTo(310 - 180 - 38);
    expect(nodes[1].x).toBeCloseTo(500);
    expect(nodes[1].y).toBeCloseTo(310 - 180 + 38);
    expect(nodes[2].x).toBeCloseTo(500);
    expect(nodes[2].y).toBeCloseTo(310 + 180 - 32);
  });

  it("chains each controller's nodes and finds their centroids", () => {
    const nodes = [node("A", "X", 0, 0), node("B", null, 50, 50), node("C", "X", 10, 20), node("D", "X", 20, 40), node("E", null, 9, 9)];
    expect(buildRegionConnections(nodes)).toEqual([
      { source: nodes[0], target: nodes[2] },
      { source: nodes[2], target: nodes[3] },
      { source: nodes[1], target: nodes[4] },
    ]);
    expect(computeControllerCentroids(nodes)).toEqual({ X: { x: 10, y: 20 } });
  });

  it("links each hostile or suspicious pair once, between known centroids", () => {
    const centroids = { A: { x: 0, y: 0 }, B: { x: 10, y: 0 }, C: { x: 0, y: 10 } };
    const relationships = {
      A: { B: { disposition: "hostile" }, C: { disposition: "friendly" }, D: { disposition: "hostile" } },
      B: { A: { disposition: "hostile" }, C: { disposition: "suspicious" } },
    };
    expect(buildCampaignLinks(centroids, relationships, ["A", "B", "C"])).toEqual([
      { key: "A--B", source: centroids.A, target: centroids.B, disposition: "hostile" },
      { key: "B--C", source: centroids.B, target: centroids.C, disposition: "suspicious" },
    ]);
    expect(buildCampaignLinks(centroids, null, ["A"])).toEqual([]);
  });

  it("ranks civilizations by their summed scores without reordering the input", () => {
    const input = [civ("Low", 1), civ("High", 9), civ("Mid", 5), civ("Mid too", 5)];
    expect(sortCivilizations(input).map((entry) => entry.name)).toEqual(["High", "Mid", "Mid too", "Low"]);
    expect(input.map((entry) => entry.name)).toEqual(["Low", "High", "Mid", "Mid too"]);
    expect(dominantCivilization(input)?.name).toBe("High");
    expect(dominantCivilization([])).toBeNull();
  });
});
