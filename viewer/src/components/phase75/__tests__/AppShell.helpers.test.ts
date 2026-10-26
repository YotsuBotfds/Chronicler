import { describe, expect, it } from "vitest";
import {
  atlasPoint, buildTradeLinks, bundleWorldKind, eventKey, eventProvenance, percentToTurn, pinFrame, regionNodeRadius,
  terrainAt, turnToPercent,
} from "../appShellHelpers";

describe("AppShell helpers", () => {
  it("names a loaded bundle's world as template or procedural, not as a setup", () => {
    expect(bundleWorldKind({ geography: { seas: [] } })).toBe("Procedural world");
    expect(bundleWorldKind({})).toBe("Template world");
    expect(bundleWorldKind(null)).toBe("Template world");
  });

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

  it("fits the atlas to the pins' bounds, whatever their coordinate range", () => {
    const generated = pinFrame([{ x: 18, y: 13 }, { x: 91, y: 90 }, { x: null, y: 40 }, { x: 50, y: 50 }]);
    expect(generated).toEqual({ x0: 18, y0: 13, sx: 73, sy: 77 });
    expect(atlasPoint(18, 13, generated)).toEqual({ x: 90, y: 80 });
    expect(atlasPoint(91, 90, generated)).toEqual({ x: 910, y: 560 });
    // Hand-made 0-1 pins land on the same canvas as 0-100 pins.
    const demo = pinFrame([{ x: 0.18, y: 0.13 }, { x: 0.91, y: 0.9 }]);
    expect(atlasPoint(0.91, 0.9, demo).x).toBeCloseTo(910);
    expect(pinFrame([])).toEqual({ x0: 0, y0: 0, sx: 1, sy: 1 });
    // One pin sits in the middle of the canvas.
    const single = atlasPoint(5, 5, pinFrame([{ x: 5, y: 5 }]));
    expect(single.x).toBeCloseTo(500);
    expect(single.y).toBeCloseTo(320);
  });

  it("sizes region nodes by relative capacity under a density ceiling", () => {
    expect(regionNodeRadius(80, 80, 12)).toBe(40);
    expect(regionNodeRadius(20, 80, 12)).toBeCloseTo(40 * (0.4 + 0.6 * 0.5));
    expect(regionNodeRadius(96, 96, 100)).toBe(16);
    expect(regionNodeRadius(50, 50, 10000)).toBe(8);
    expect(regionNodeRadius(null, 0, 6)).toBeCloseTo(40 * (0.4 + 0.6 * Math.sqrt(0.5)));
  });

  it("maps turns to a 0-100 percent range", () => {
    expect(turnToPercent(1, 10)).toBe(0);
    expect(turnToPercent(10, 10)).toBe(100);
  });

  it("keys events by recorded id, falling back to turn and type", () => {
    expect(eventKey({ turn: 4, event_type: "famine", event_id: "4:famine:1" })).toBe("4:famine:1");
    expect(eventKey({ turn: 4, event_type: "famine" })).toBe("4-famine");
  });

  it("resolves recorded causes and consequences of an event", () => {
    const war = { turn: 0, event_type: "war_declared", event_id: "0:war_declared:0" };
    const battle = { turn: 3, event_type: "war", event_id: "3:war:0", causes: ["0:war_declared:0"] };
    const occupation = { turn: 3, event_type: "occupation", event_id: "3:occupation:0", causes: ["3:war:0"] };
    const legacy = { turn: 3, event_type: "trade" };
    const events = [war, battle, occupation, legacy];
    expect(eventProvenance(events, battle)).toEqual({ causes: [war], effects: [occupation] });
    expect(eventProvenance(events, legacy)).toEqual({ causes: [], effects: [] });
    // Up to a turn: the consequences recorded by then.
    const revolt = { turn: 9, event_type: "occupation_revolt", event_id: "9:occupation_revolt:0", causes: ["3:war:0"] };
    expect(eventProvenance([...events, revolt], battle, 8)).toEqual({ causes: [war], effects: [occupation] });
    expect(eventProvenance([...events, revolt], battle, 9)).toEqual({ causes: [war], effects: [occupation, revolt] });
  });

  it("gives a region's terrain at a turn from its dated transitions", () => {
    const transition = (turn: number, region: string, from: string, to: string) => ({
      turn, event_type: "terrain_transition", description: `${region} transforms from ${from} to ${to}`,
    });
    const events = [transition(40, "Green Vale", "forest", "plains"), transition(90, "Green Vale", "plains", "forest"),
                    transition(60, "Green Vale East", "hills", "plains")];
    expect(terrainAt(events, "Green Vale", "forest", 10)).toBe("forest");
    expect(terrainAt(events, "Green Vale", "forest", 40)).toBe("plains");
    expect(terrainAt(events, "Green Vale", "forest", 89)).toBe("plains");
    expect(terrainAt(events, "Green Vale", "forest", 90)).toBe("forest");
    expect(terrainAt(events, "Green Vale East", "plains", 10)).toBe("hills");
    expect(terrainAt([], "Green Vale", "forest", 10)).toBe("forest");
    // A later transition the viewer cannot read: unknown.
    expect(terrainAt([{ turn: 50, event_type: "terrain_transition", description: "Green Vale changes" }],
      "Green Vale", "forest", 10)).toBeNull();
  });
});
