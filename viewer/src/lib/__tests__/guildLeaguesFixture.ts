/**
 * A D1b guild-league record for the reader and panel tests: the turn-119 record of a
 * development run (procedural 32x10 seed 13, hybrid, --guild-leagues), trimmed to two
 * leagues with regions and realms renumbered for a four-region, four-realm bundle.
 */
export const frame = {
  turn: 119,
  leagues: [
    { league: 2, founded_turn: 49, members: [
      { guild: 3, city: 5, region: 0, lord: 0, joined_turn: 49, dues_milli: 4616, payouts_milli: 0 },
      { guild: 7, city: 11, region: 1, lord: 3, joined_turn: 49, dues_milli: 1761, payouts_milli: 0 }],
      fund_open_milli: 6000, dues_milli: 0, payouts_milli: 0, returned_milli: 0, unclaimed_milli: 0,
      fund_close_milli: 6000, cap_milli: 6000, dissolved: null },
    { league: 4, founded_turn: 68, members: [
      { guild: 10, city: 15, region: 2, lord: 1, joined_turn: 68, dues_milli: 1687, payouts_milli: 57 },
      { guild: 12, city: 20, region: 3, lord: 2, joined_turn: 68, dues_milli: 2779, payouts_milli: 0 }],
      fund_open_milli: 4349, dues_milli: 117, payouts_milli: 57, returned_milli: 0, unclaimed_milli: 0,
      fund_close_milli: 4409, cap_milli: 6000, dissolved: null },
    { league: 1, founded_turn: 20, members: [], fund_open_milli: 2500, dues_milli: 0, payouts_milli: 0,
      returned_milli: 2500, unclaimed_milli: 0, fund_close_milli: 0, cap_milli: 0, dissolved: "war_between_members" },
  ],
  dues: [
    { league: 4, guild: 10, city: 15, milli: 35 },
    { league: 4, guild: 12, city: 20, milli: 82 },
  ],
  payouts: [{ league: 4, guild: 10, city: 15, kind: "levy", loss_milli: 57, paid_milli: 57, event_id: "118:guild_levy:0" }],
  changes: [{ league: 1, kind: "dissolved", guild: null, city: null, reason: "war_between_members", returned_milli: 2500,
    unclaimed_milli: null }],
  links: 28, candidates: 6,
};

export const empty = { turn: 119, leagues: [], dues: [], payouts: [], changes: [], links: 3, candidates: 0 };

export function record(changes: Record<string, unknown> = {}) {
  return {
    schema_version: 1, stage: "D1b", mode: "mutual", source_turn: 119, frame, next_league: 6, dissolved: [],
    dissolved_dropped: 0, counters: { turns: 120 }, log: [], log_dropped: 0, parameters: {}, ...changes,
  };
}
