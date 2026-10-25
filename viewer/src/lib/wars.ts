/**
 * Read-only helpers for the campaign layer (`history[n].campaign`): wars,
 * armies, battles and occupations as the bundle records them.
 */
import type { CampaignBattle, CampaignWar, TurnSnapshot } from "../types";
import { buildSegments, civInitials, CONTESTED_COLOR, type StripRow } from "./systems";

const DARK_INK = "#0b0b0b";
const LIGHT_INK = "#f0efec";

/** Who leads a war at a snapshot: score > 0 favours the attacker (score runs -100..100). */
export function warLeader(war: CampaignWar): string | null {
  if (war.score > 0) {
    return war.attacker;
  }
  if (war.score < 0) {
    return war.defender;
  }
  return null;
}

/** War identity across snapshots: one war per war key and start turn. */
export function warId(war: CampaignWar): string {
  return `${war.war}@${war.start_turn}`;
}

export function warTitle(war: CampaignWar): string {
  return `${war.attacker} vs ${war.defender}`;
}

export function warAim(war: CampaignWar): string {
  const aim = war.aim.replace(/_/g, " ");
  return war.aim_region ? `${aim} of ${war.aim_region}` : aim;
}

/**
 * One strip row per war, in order of declaration. A segment spans the turns
 * one side led on war score (its colour and initials) or the score stood level.
 */
export function warRows(history: TurnSnapshot[], color: (civ: string) => string): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  const wars = new Map<string, CampaignWar>();
  for (const snapshot of history) {
    for (const war of snapshot.campaign?.wars ?? []) {
      if (!wars.has(warId(war))) {
        wars.set(warId(war), war);
      }
    }
  }
  return [...wars.entries()]
    .sort((left, right) => left[1].start_turn - right[1].start_turn || left[0].localeCompare(right[0]))
    .map(([id, first]) => {
      const states = history.map((snapshot) => snapshot.campaign?.wars.find((war) => warId(war) === id) ?? null);
      const keys = states.map((war) => (war ? `lead\u0000${warLeader(war) ?? ""}` : null));
      const segments = buildSegments(turns, keys).map((segment) => {
        const leader = segment.key.slice("lead\u0000".length) || null;
        const covered = states.slice(segment.from, segment.to + 1).filter((war): war is CampaignWar => war !== null);
        const scores = covered.map((war) => war.score);
        const range = scores.length ? `score ${Math.min(...scores)} to ${Math.max(...scores)}` : "";
        return {
          start: segment.start,
          end: segment.end,
          color: leader ? color(leader) : CONTESTED_COLOR,
          label: `${warTitle(first)} (${warAim(first)}): ${leader ? `${leader} leads` : "level"},`
            + ` turns ${segment.start}-${segment.end - 1}${range ? ` · ${range}` : ""}`,
          text: leader ? civInitials(leader) : "level",
          textColor: leader ? DARK_INK : LIGHT_INK,
        };
      });
      return { id, label: warTitle(first), segments };
    });
}

/** Every battle recorded up to `turn`, latest first. */
export function battlesUpTo(history: TurnSnapshot[], turn: number): CampaignBattle[] {
  const battles: CampaignBattle[] = [];
  for (const snapshot of history) {
    if (snapshot.turn > turn) {
      break;
    }
    battles.push(...(snapshot.campaign?.battles ?? []));
  }
  return battles.sort((left, right) => right.turn - left.turn || left.name.localeCompare(right.name));
}

/** Soldiers lost on each side in the given battles. */
export function battleLosses(battles: CampaignBattle[]): number {
  return battles.reduce((sum, battle) => sum + battle.attacker_losses + battle.defender_losses, 0);
}

/** True when any snapshot carries the campaign field. */
export function hasCampaignRecord(history: TurnSnapshot[]): boolean {
  return history.some((snapshot) => snapshot.campaign != null);
}
