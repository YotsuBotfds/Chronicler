import { describe, expect, it } from "vitest";
import type { GuildSnapshotRow, TurnSnapshot } from "../../types";
import { factionShares } from "../civRows";
import { cityGuildLabel, guildOfCity, guildsAt, privilegesLabel } from "../guilds";

const guild = (fields: Partial<GuildSnapshotRow>): GuildSnapshotRow => ({
  id: 0, name: "the Smiths' Guild of X", city: 4, region: "X", kind: "craft", masters: 5,
  wealth: 2, monopoly: false, say: false, ...fields,
});

const snapshot = (rows: GuildSnapshotRow[] | null): TurnSnapshot =>
  ({ turn: 10, civ_stats: {}, region_control: {}, relationships: {},
     ...(rows ? { guilds: { guilds: rows, dissolved: 0, burghers: {}, counters: {} } } : {}) }) as unknown as TurnSnapshot;

describe("guilds helpers", () => {
  it("finds a city's guild only where the snapshot records one", () => {
    const at = snapshot([guild({ id: 1, city: 4 }), guild({ id: 2, city: 9, kind: "merchant" })]);
    expect(guildsAt(at).map((row) => row.id)).toEqual([1, 2]);
    expect(guildOfCity(at, 9)?.kind).toBe("merchant");
    expect(guildOfCity(at, 5)).toBeNull();
    expect(guildsAt(snapshot(null))).toEqual([]);
    expect(guildsAt(null)).toEqual([]);
  });

  it("names privileges and threats as the table shows them", () => {
    expect(privilegesLabel(guild({}))).toBe("none");
    expect(privilegesLabel(guild({ monopoly: true, say: true, charter: 2, levy: true })))
      .toBe("monopoly, say in dues, guild charter, levied");
    const at = snapshot([guild({ city: 4, monopoly: true }), guild({ city: 5, kind: "merchant" })]);
    expect(cityGuildLabel(at, 4)).toBe("craft: monopoly");
    expect(cityGuildLabel(at, 5)).toBe("merchant");
    expect(cityGuildLabel(at, 6)).toBe("-");
  });

  it("orders faction influence as the simulation declares the factions", () => {
    expect(factionShares({ clergy: 0.1, burgher: 0.2, military: 0.3, merchant: 0.2, cultural: 0.2 })
      .map(([name]) => name)).toEqual(["military", "merchant", "cultural", "clergy", "burgher"]);
    expect(factionShares({ military: 0.5, merchant: 0.5 })).toEqual([["military", 0.5], ["merchant", 0.5]]);
    expect(factionShares(undefined)).toEqual([]);
  });
});
