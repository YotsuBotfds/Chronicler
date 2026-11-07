import { expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../types";
import { guildLeaguesOn, leagueRecordAt, readGuildLeagues } from "../guildLeagues";
import { empty, frame, record } from "./guildLeaguesFixture";

const snap = (turn: number, livelihoods: unknown): TurnSnapshot => ({ turn, livelihoods } as unknown as TurnSnapshot);
const bundle = (history: TurnSnapshot[]) =>
  ({ history, world_state: { regions: [{}, {}, {}, {}], civilizations: [{}, {}, {}, {}] } }) as unknown as Bundle;
const on = (r: unknown) => ({ schema_version: 1, guild_leagues: r });

it("keeps the six readings distinct", () => {
  const plain = snap(120, { schema_version: 1 });
  expect(readGuildLeagues(bundle([plain]), plain).state).toBe("disabled");
  const recorded = snap(120, on(record()));
  expect(readGuildLeagues(bundle([recorded]), recorded).state).toBe("recorded");
  expect(readGuildLeagues(bundle([recorded, plain]), plain).state).toBe("absent");
  const bad = snap(120, on(record({ stage: "D1a" })));
  expect(readGuildLeagues(bundle([bad]), bad).state).toBe("malformed");
  const unobserved = snap(120, on(record({ frame: null })));
  expect(readGuildLeagues(bundle([unobserved]), unobserved).state).toBe("unobserved");
  const zero = snap(120, on(record({ frame: empty })));
  expect(readGuildLeagues(bundle([zero]), zero).state).toBe("recorded_zero");
  expect(guildLeaguesOn([plain, recorded])).toBe(true);
  expect(guildLeaguesOn([plain])).toBe(false);
});

it("refuses inconsistent records with a reason", () => {
  const [a, b] = frame.leagues;
  const twoOfOneRealm = { ...a, members: [a.members[0], { ...a.members[1], lord: 0 }] };
  const cases: [Record<string, unknown>, RegExp][] = [
    [{ frame: { ...frame, leagues: [{ ...b, fund_close_milli: 1 }] } }, /does not close/],
    [{ frame: { ...frame, leagues: [twoOfOneRealm] } }, /two members of one realm/],
    [{ frame: { ...frame, leagues: [{ ...a, league: 9 }] } }, /malformed league row/],
    [{ frame: { ...frame, payouts: [{ ...frame.payouts[0], paid_milli: 58 }] } }, /more than the recorded loss/],
    [{ mode: "dues_only" }, /dues-only control paid a claim/],
    [{ frame: { ...frame, dues: frame.dues.slice(1) } }, /dues or claims differ/],
    [{ frame: { ...frame, changes: [{ ...frame.changes[0], reason: "bored" }] } }, /without a declared reason/],
    [{ frame: { ...frame, turn: 118 } }, /misdated/],
  ];
  for (const [change, reason] of cases) {
    const got = leagueRecordAt(snap(120, on(record(change))), 4, 4);
    expect(got.record).toBeNull();
    expect(got.reason).toMatch(reason);
  }
});
