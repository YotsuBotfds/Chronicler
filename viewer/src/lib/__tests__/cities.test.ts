import { describe, expect, it } from "vitest";
import citiesFixture from "../../__fixtures__/cities_bundle.json";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../types";
import {
  charterLabel, cityHistory, cityKeys, cityRankRows, cityRecord, cityRow, citySeries, rankLabel,
} from "../cities";
import { presentSystems } from "../systems";

const cities = citiesFixture as unknown as Bundle;
const systems = systemsFixture as unknown as Bundle;

describe("cities helpers", () => {
  it("lists every city once, in order of first appearance", () => {
    expect(cityKeys(cities.history).map((key) => key.id)).toEqual([1, 3, 2, 5, 4]);
    expect(cityKeys(systems.history)).toEqual([]);
  });

  it("draws each city's rank over the snapshots it lived in", () => {
    const rows = cityRankRows(cities.history, cityKeys(cities.history));
    const fallen = rows.find((row) => row.label === "Verdant Plains Settlement 2")!;
    // Founded in turn 120: first recorded by the snapshot that closes it.
    expect(fallen.segments[0].start).toBe(121);
    expect(fallen.segments[fallen.segments.length - 1].end).toBeLessThanOrEqual(166);
    const first = rows.find((row) => row.id === "1")!;
    expect(first.segments.map((segment) => segment.text)).toContain("great city");
  });

  it("leaves turns a city did not live as gaps, never zero", () => {
    const series = citySeries(cities.history, 5, "purse", (row) => row.wealth);
    expect(series.find((row) => row.turn === 100)!.purse).toBeNull();
    expect(series.find((row) => row.turn === 130)!.purse).not.toBeNull();
    expect(series.find((row) => row.turn === 200)!.purse).toBeNull();
    expect(cityRow(cities.history[0], 1)).toBeNull();
  });

  it("reads a city's recorded moments up to the scrubbed turn, latest first", () => {
    expect(cityRecord(cities, 5)?.fallen_turn).toBe(165);
    const all = cityHistory(cities, 5, 250);
    expect(all.map((moment) => moment.kind)).toEqual(["fell", "famine", "founded"]);
    expect(all.every((moment) => moment.event !== null)).toBe(true);
    expect(cityHistory(cities, 5, 150).map((moment) => moment.kind)).toEqual(["famine", "founded"]);
    expect(cityHistory(systems, 1, 250)).toEqual([]);
  });

  it("names ranks and charters in the simulation's order", () => {
    expect([1, 2, 3].map(rankLabel)).toEqual(["town", "city", "great city"]);
    expect([0, 1, 2, 3].map(charterLabel)).toEqual(["none", "market rights", "self-government", "free city"]);
  });

  it("is a system of the bundle only when a snapshot records cities", () => {
    expect(presentSystems(cities.history, cities.events_timeline)).toEqual(["cities"]);
    expect(presentSystems(systems.history, systems.events_timeline)).not.toContain("cities");
  });
});
