/**
 * Civilizations as the viewer shows them at a snapshot.
 *
 * The values come from the history row at or before the snapshot
 * (lib/civRows), never from the end-of-run world state: a civilization with
 * no row yet is not yet founded there, so it has no values to show, takes no
 * place in rankings, chips or summaries and is not the default focus. Its
 * inspector says so ("Unavailable"). Without any history (a live session
 * before its first turn) the world state is the present and is shown.
 *
 * Turn convention: the scrubber's turn T shows snapshot T, the state after
 * turn T - 1 (chronicler/historical_context.py, `AsOf.at_snapshot`).
 */
import type { Bundle, TurnSnapshot } from "../types";
import { civRowAt, type CivRowAt } from "./civRows";

/** A civilization with values at the snapshot. */
export interface CivilizationView {
  founded: true;
  name: string;
  population: number;
  military: number;
  economy: number;
  culture: number;
  stability: number;
  treasury: number;
  asabiya: number;
  techEra: string;
  leaderName: string;
  leaderTrait: string;
  values: string[];
  goal: string;
  regions: string[];
  alive: boolean;
  /** "Active", "Fallen" or "Fallen (final record, turn N)". */
  status: string;
}

/** A civilization the history does not hold yet at the snapshot. */
export interface PendingCivilizationView {
  founded: false;
  name: string;
  values: string[];
  goal: string;
  status: "Not yet founded";
}

export type CivilizationEntry = CivilizationView | PendingCivilizationView;

export function isFounded(entry: CivilizationEntry): entry is CivilizationView {
  return entry.founded;
}

export function civilizationStatus(found: CivRowAt): string {
  if (!found.recorded) {
    return `Fallen (final record, turn ${found.turn})`;
  }
  return found.row.alive === false || found.row.regions.length === 0 ? "Fallen" : "Active";
}

/** Every world civilization at `snapshot`, in world order. */
export function buildCivilizationViews(bundle: Bundle | null, snapshot: TurnSnapshot | null): CivilizationEntry[] {
  if (!bundle) {
    return [];
  }
  const hasHistory = bundle.history.length > 0;
  return bundle.world_state.civilizations.map((civilization): CivilizationEntry => {
    const found = snapshot ? civRowAt(bundle.history, civilization.name, snapshot.turn) : null;
    if (!found && hasHistory) {
      return {
        founded: false,
        name: civilization.name,
        values: civilization.values,
        goal: civilization.goal,
        status: "Not yet founded",
      };
    }
    // A dead civilization leaves later snapshots (bundle version 5): show its
    // final row, with no regions.
    const snap = found ? (found.recorded ? found.row : { ...found.row, alive: false, regions: [] }) : null;
    return {
      founded: true,
      name: civilization.name,
      population: snap?.population ?? civilization.population,
      military: snap?.military ?? civilization.military,
      economy: snap?.economy ?? civilization.economy,
      culture: snap?.culture ?? civilization.culture,
      stability: snap?.stability ?? civilization.stability,
      treasury: snap?.treasury ?? civilization.treasury,
      asabiya: snap?.asabiya ?? civilization.asabiya,
      techEra: snap?.tech_era ?? civilization.tech_era,
      leaderName: snap?.leader_name ?? civilization.leader.name,
      leaderTrait: snap?.trait ?? civilization.leader.trait,
      values: civilization.values,
      goal: civilization.goal,
      regions: snap?.regions ?? civilization.regions,
      alive: snap?.alive ?? civilization.regions.length > 0,
      status: found ? civilizationStatus(found) : civilization.regions.length > 0 ? "Active" : "Fallen",
    };
  });
}
