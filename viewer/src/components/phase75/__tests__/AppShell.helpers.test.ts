import { describe, expect, it } from "vitest";
import { buildTradeLinks, percentToTurn, turnToPercent } from "../appShellHelpers";

describe("AppShell helpers", () => {
  it("respects an empty timeline trade-route snapshot over final world relationships", () => {
    const centroids = {
      Alpha: { x: 100, y: 120 },
      Beta: { x: 280, y: 260 },
    };

    const finalWorldRelationships = {
      Alpha: { Beta: { disposition: "friendly", trade_volume: 12 } },
      Beta: { Alpha: { disposition: "friendly", trade_volume: 12 } },
    };

    expect(
      buildTradeLinks(centroids, finalWorldRelationships, ["Alpha", "Beta"], []),
    ).toEqual([]);
  });

  it("builds trade links directly from timeline route pairs when available", () => {
    const centroids = {
      Alpha: { x: 100, y: 120 },
      Beta: { x: 280, y: 260 },
    };

    const links = buildTradeLinks(centroids, null, ["Alpha", "Beta"], [["Alpha", "Beta"]]);
    expect(links).toHaveLength(1);
    expect(links[0].key).toBe("Alpha--Beta");
  });

  it("maps the scrubber percent scale back to 1-based turns", () => {
    expect(percentToTurn(0, 10)).toBe(1);
    expect(percentToTurn(0.5, 10)).toBe(6);
    expect(percentToTurn(1, 10)).toBe(10);
  });

  it("maps turns to a 0-100 percent range", () => {
    expect(turnToPercent(1, 10)).toBe(0);
    expect(turnToPercent(10, 10)).toBe(100);
  });
});
