import type { ReactNode } from "react";
import type { Bundle, TurnSnapshot } from "../../types";
import { leagueRecordAt, readGuildLeagues, type LeagueChange, type LeagueFrame } from "../../lib/guildLeagues";

const units = (milli: number) => (milli / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 });
const REASON: Record<string, string> = {
  guild_dissolved: "its guild dissolved", city_fallen: "its city fell", lord_changed: "its city changed lord",
  war_between_members: "two members' realms went to war", too_few_members: "fewer than two members remained",
  one_realm: "every remaining member is of one realm", dormant: "no recorded trade between members for 20 turns",
  switched_off: "the switch was turned off",
};
const CLAIM: Record<string, string> = { levy: "levy share of the dues", sack: "plunder of a sack" };

/** The completed turn's guild-league record only; never reads final-world state. */
export function GuildLeagues({ bundle, snapshot, currentTurn }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const reading = readGuildLeagues(bundle, snapshot, currentTurn);
  const at = snapshot?.turn ?? currentTurn;
  const heading = <h3>Guild leagues{reading.record !== null ? ` · snapshot ${reading.record.source_turn + 1}` : ""}</h3>;
  const section = (body: ReactNode) => <section className="systems-section" aria-label="Guild leagues">{heading}{body}</section>;
  if (reading.state === "disabled") {
    return section(<p className="systems-note">Guild leagues are off in this run (--guild-leagues not recorded): no guild body crosses a border.</p>);
  }
  if (reading.state === "absent") {
    return section(<p className="systems-note">No guild-league record at snapshot {at}: unknown, not zero.</p>);
  }
  if (reading.state === "malformed") {
    const why = leagueRecordAt(snapshot, regions.length, civs.length).reason ?? "unreadable";
    return section(<p className="systems-note">The guild-league record at snapshot {at} was rejected as malformed: {why}. Nothing is shown from it.</p>);
  }
  const r = reading.record!;   // the three readings without a record returned above
  if (reading.state === "unobserved") {
    return section(<p className="systems-note">Simulation turn {r.source_turn} was not observed: leagues, dues and claims that turn are unknown, not zero.</p>);
  }
  const intro = <p className="systems-note">Simulation turn {r.source_turn}, mode {r.mode}. Guilds of cities in different realms whose regions traded (merchant deliveries the economy recorded) pool part of their purses; {r.mode === "dues_only"
    ? "the dues-only control pays no claim."
    : "the fund pays a member city's purse only for a loss recorded in its history (a levy's share of the dues, a sack's plunder)."} One member per realm; ids are never reused.</p>;
  if (reading.state === "recorded_zero") {
    return section(<>{intro}<p className="systems-note">No league held money or changed and no dues or claims this turn (recorded zero; {r.frame!.candidates} candidate pairs, {r.frame!.links} links held).</p></>);
  }
  const city = (id: number, region: number) => `${regions[region]?.name ?? `Region ${region}`} (city ${id})`;
  const realm = (i: number) => civs[i]?.name ?? `Civ ${i}`;
  return section(<>{intro}<Frame frame={r.frame!} source={r.source_turn} city={city} realm={realm} /></>);
}

function change(c: LeagueChange, cityOf: (id: number) => string): string {
  const who = c.city === null ? "" : cityOf(c.city);
  if (c.kind === "founded") return `League ${c.league} is founded by ${who}`;
  if (c.kind === "joined") return `${who} joins league ${c.league}`;
  if (c.kind === "left") return `${who} leaves league ${c.league}: ${REASON[c.reason ?? ""] ?? c.reason}`;
  const money = c.unclaimed_milli ? `${units(c.unclaimed_milli)} unclaimed (no member left)`
    : `${units(c.returned_milli ?? 0)} returned to the members' purses`;
  return `League ${c.league} dissolves: ${REASON[c.reason ?? ""] ?? c.reason}; ${money}`;
}

function Frame({ frame, source, city, realm }: {
  frame: LeagueFrame; source: number; city: (id: number, region: number) => string; realm: (i: number) => string;
}) {
  const regionOf = new Map<number, number>();
  frame.leagues.forEach((l) => l.members.forEach((m) => regionOf.set(m.city, m.region)));
  const cityOf = (id: number) => regionOf.has(id) ? city(id, regionOf.get(id)!) : `city ${id}`;
  return <>
    {frame.leagues.length === 0 ? <p className="systems-note">No league this turn (recorded zero).</p>
      : <table className="systems-table" aria-label={`Guild leagues at snapshot ${source + 1}`}>
        <thead><tr><th>League</th><th>Members (realm)</th><th>Fund at start</th><th>Dues in</th><th>Claims paid</th>
          <th>Returned</th><th>Fund at end</th><th>Cap</th></tr></thead>
        <tbody>{frame.leagues.map((l) => <tr key={l.league}>
          <td>{l.league} (since {l.founded_turn}){l.dissolved ? `, dissolved: ${REASON[l.dissolved]}` : ""}</td>
          <td>{l.members.length === 0 ? "none" : l.members.map((m) => `${city(m.city, m.region)} (${realm(m.lord)})`).join("; ")}</td>
          <td>{units(l.fund_open_milli)}</td><td>{units(l.dues_milli)}</td><td>{units(l.payouts_milli)}</td>
          <td>{units(l.returned_milli)}{l.unclaimed_milli ? ` (+${units(l.unclaimed_milli)} unclaimed)` : ""}</td>
          <td>{units(l.fund_close_milli)}</td><td>{units(l.cap_milli)}</td>
        </tr>)}</tbody>
      </table>}
    {frame.payouts.length === 0 ? <p className="systems-note">No member's loss was recorded this turn: no claim (recorded zero).</p>
      : <table className="systems-table" aria-label={`League claims at snapshot ${source + 1}`}>
        <thead><tr><th>League</th><th>City</th><th>Recorded loss</th><th>Loss</th><th>Paid to the city's purse</th><th>Event</th></tr></thead>
        <tbody>{frame.payouts.map((p) => <tr key={`${p.league}-${p.city}-${p.kind}`}>
          <td>{p.league}</td><td>{cityOf(p.city)}</td><td>{CLAIM[p.kind]}</td><td>{units(p.loss_milli)}</td>
          <td>{units(p.paid_milli)}</td><td>{p.event_id || "Unknown"}</td>
        </tr>)}</tbody>
      </table>}
    {frame.changes.length > 0 ? <ul className="systems-list" aria-label={`League changes at snapshot ${source + 1}`}>
      {frame.changes.map((c, i) => <li key={i}>{change(c, cityOf)}</li>)}</ul> : null}
    <p className="systems-note">{frame.dues.length} member{frame.dues.length === 1 ? "" : "s"} paid dues this turn; {frame.candidates} candidate pairs; {frame.links} links held.</p>
  </>;
}
