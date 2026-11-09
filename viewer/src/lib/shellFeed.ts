/**
 * The shell's timeline and feed text, built from a bundle at the scrubbed
 * turn: the snapshot shown, the run's length, era bands, narrated spans, the
 * chronicle feed and the inspector's selection line. Pure functions, moved
 * unchanged from `components/phase75/AppShell.tsx`.
 */
import type { BatchRunSummary, Bundle, NewChronicleEntry, TurnSnapshot } from "../types";
import { isLegacyBundle } from "../types";
import type { AppSurface, SelectedEntity } from "../components/phase75/appShellTypes";
import { snapshotPositionAt } from "./civRows";
import { ERA_LABELS } from "./format";

export interface ChronicleFeedItem {
  id: string;
  turn: number;
  title: string;
  body: string;
  eyebrow: string;
  accent: "gold" | "cyan" | "ember" | "stone";
  /** A narrated entry (its provenance lists the passage's sources). */
  entry?: NewChronicleEntry;
}

/**
 * The snapshot shown at `currentTurn`: the latest at or before it. Null
 * without history and before the first snapshot (a resumed run's history
 * starts late): a later snapshot never stands in, and the shell shows no
 * per-turn values there.
 */
export function findCurrentSnapshot(bundle: Bundle | null, currentTurn: number): TurnSnapshot | null {
  if (!bundle) {
    return null;
  }
  const position = snapshotPositionAt(bundle.history, currentTurn);
  return position >= 0 ? bundle.history[position] : null;
}

export function buildEraBands(history: TurnSnapshot[], maxTurn: number): { label: string; start: number; end: number }[] {
  if (history.length === 0) {
    const fallbackLabels = ["Founding", "Expansion", "Maturity", "Fracture", "Late Age"];
    const step = Math.max(1, Math.floor(maxTurn / fallbackLabels.length));
    return fallbackLabels.map((label, index) => ({
      label,
      start: Math.max(1, index * step + 1),
      end: index === fallbackLabels.length - 1 ? maxTurn : Math.min(maxTurn, (index + 1) * step),
    }));
  }

  const boundaries: { turn: number; label: string }[] = [];
  const seen = new Set<string>();
  for (const snapshot of history) {
    for (const civ of Object.values(snapshot.civ_stats)) {
      if (!seen.has(civ.tech_era)) {
        seen.add(civ.tech_era);
        boundaries.push({
          turn: snapshot.turn,
          label: ERA_LABELS[civ.tech_era as keyof typeof ERA_LABELS] ?? civ.tech_era,
        });
      }
    }
  }

  const ordered = boundaries.sort((left, right) => left.turn - right.turn);
  if (ordered.length === 0) {
    return [{ label: "Recorded Era", start: 1, end: maxTurn }];
  }

  return ordered.map((boundary, index) => ({
    label: boundary.label,
    start: boundary.turn,
    end: ordered[index + 1] ? ordered[index + 1].turn - 1 : maxTurn,
  }));
}

export function buildNarratedSpans(chronicleEntries: Bundle["chronicle_entries"] | undefined): { start: number; end: number }[] {
  if (!chronicleEntries) {
    return [];
  }

  if (isLegacyBundle(chronicleEntries)) {
    return Object.keys(chronicleEntries)
      .map((turnString) => Number(turnString))
      .filter((turn) => !Number.isNaN(turn))
      .map((turn) => ({ start: turn, end: turn }))
      .sort((left, right) => left.start - right.start);
  }

  return chronicleEntries
    .map((entry) => ({
      start: entry.covers_turns[0],
      end: entry.covers_turns[1],
    }))
    .sort((left, right) => left.start - right.start);
}

export function buildChronicleFeed(bundle: Bundle | null, currentTurn: number): ChronicleFeedItem[] {
  if (!bundle) {
    return [];
  }

  if (isLegacyBundle(bundle.chronicle_entries)) {
    const items: ChronicleFeedItem[] = [];
    for (const [turnString, reflection] of Object.entries(bundle.era_reflections)) {
      const turn = Number(turnString);
      if (!Number.isNaN(turn) && turn <= currentTurn) {
        items.push({
          id: `reflection-${turn}`,
          turn,
          title: `Reflection at Turn ${turn}`,
          body: reflection,
          eyebrow: "Era Reflection",
          accent: "gold",
        });
      }
    }

    for (const [turnString, narrative] of Object.entries(bundle.chronicle_entries)) {
      const turn = Number(turnString);
      if (!Number.isNaN(turn) && turn <= currentTurn) {
        items.push({
          id: `chronicle-${turn}`,
          turn,
          title: `Turn ${turn}`,
          body: narrative,
          eyebrow: "Chronicle",
          accent: "cyan",
        });
      }
    }

    return items.sort((left, right) => left.turn - right.turn).slice(-14);
  }

  // A curated entry narrates its moment through its last turn (the narrator
  // reads the record after it), so it appears once that turn has passed.
  const items = bundle.chronicle_entries
    .filter((entry) => entry.covers_turns[1] <= currentTurn)
    .map<ChronicleFeedItem>((entry, index) => ({
      id: `segment-${index}`,
      turn: entry.covers_turns[0],
      title: `Turns ${entry.covers_turns[0]}-${entry.covers_turns[1]}`,
      body: entry.narrative,
      eyebrow: entry.narrative_role,
      accent:
        entry.narrative_role === "climax"
          ? "ember"
          : entry.narrative_role === "resolution"
            ? "gold"
            : "cyan",
      entry,
    }));

  const reflections = Object.entries(bundle.era_reflections)
    .map(([turnString, text]) => ({
      id: `reflection-${turnString}`,
      turn: Number(turnString),
      title: `Reflection at Turn ${turnString}`,
      body: text,
      eyebrow: "Era Reflection",
      accent: "gold" as const,
    }))
    .filter((item) => !Number.isNaN(item.turn) && item.turn <= currentTurn);

  // A gap's summary counts every turn of the gap: shown once the gap has passed.
  const gaps = (bundle.gap_summaries ?? [])
    .filter((gap) => gap.turn_range[1] <= currentTurn)
    .map<ChronicleFeedItem>((gap, index) => ({
      id: `gap-${index}`,
      turn: gap.turn_range[0],
      title: `Mechanical window ${gap.turn_range[0]}-${gap.turn_range[1]}`,
      body: `${gap.event_count} events, ${gap.territory_changes} territorial shifts, dominant type ${gap.top_event_type}.`,
      eyebrow: "Mechanical Gap",
      accent: "stone",
    }));

  return [...items, ...reflections, ...gaps]
    .sort((left, right) => left.turn - right.turn)
    .slice(-14);
}

function buildRunSignalSummary(summary: BatchRunSummary | null): string {
  if (!summary) {
    return "Ranked run summaries appear here after a batch completes.";
  }
  if (summary.signal_flags.length === 0) {
    return "Balanced run with no standout anomaly signals.";
  }
  return summary.signal_flags.join(" · ");
}

export function selectionDescription(
  surface: AppSurface,
  selection: SelectedEntity | null,
  summary: BatchRunSummary | null,
  currentTurn: number,
  eventRecorded = true,
): string {
  if (surface === "batch") {
    return buildRunSignalSummary(summary);
  }
  if (!selection) {
    return "Choose a region, civilization, or event to view its recorded details.";
  }
  if (selection.kind === "event") {
    // An event pinned at a later turn is not described before it happens.
    if (!eventRecorded || (selection.turn !== undefined && selection.turn > currentTurn)) {
      return `Pinned event not yet recorded at turn ${currentTurn}.`;
    }
    return `Pinned to ${selection.label} at turn ${selection.turn ?? "?"}.`;
  }
  return `${selection.kind === "region" ? "Region" : "Focus"} selected: ${selection.label}.`;
}

export function totalTurnsFor(bundle: Bundle | null): number {
  return bundle?.metadata.total_turns ?? bundle?.history.length ?? 1;
}
