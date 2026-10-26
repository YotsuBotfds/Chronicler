/**
 * Read-only helpers for guilds (`history[n].guilds`; `--guilds`). A guild's
 * identity is its index in the world's guild list; its city is a settlement
 * id (`CitySnapshotRow.id`). Nothing here infers a value the bundle does not
 * record: a guild absent from a snapshot is not living there.
 */
import type { GuildSnapshotRow, TurnSnapshot } from "../types";

/** Running totals shown under the guilds table (`guilds_state.COUNTER_KEYS`). */
export const GUILD_COUNTERS: [string, string][] = [
  ["founded", "Guilds founded"],
  ["privileges", "Privileges won"],
  ["levies", "Levies"],
  ["threats", "Threats to privileges"],
  ["movements", "Guild movements"],
  ["charters", "Guild charters"],
];

/** The living guilds at a snapshot, or [] (none, or a run without guilds). */
export function guildsAt(snapshot: TurnSnapshot | null | undefined): GuildSnapshotRow[] {
  return snapshot?.guilds?.guilds ?? [];
}

/** The living guild of a city at a snapshot, or null. */
export function guildOfCity(snapshot: TurnSnapshot | null | undefined, city: number): GuildSnapshotRow | null {
  return guildsAt(snapshot).find((row) => row.city === city) ?? null;
}

/** Its privileges and their threats, as the table shows them. */
export function privilegesLabel(row: GuildSnapshotRow): string {
  const parts: string[] = [];
  if (row.monopoly) parts.push("monopoly");
  if (row.say) parts.push("say in dues");
  if (row.charter != null) parts.push("guild charter");
  if (row.levy) parts.push("levied");
  return parts.length ? parts.join(", ") : "none";
}

/** A city's guild in one cell: its kind and privileges, "-" without one. */
export function cityGuildLabel(snapshot: TurnSnapshot | null | undefined, city: number): string {
  const guild = guildOfCity(snapshot, city);
  if (!guild) return "-";
  const privileges = privilegesLabel(guild);
  return privileges === "none" ? guild.kind : `${guild.kind}: ${privileges}`;
}
