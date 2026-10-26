/**
 * The transport contract: what a bundle and the live protocol carry.
 *
 * The lists come from `src/chronicler/transport_contract.json`, the file the
 * Python side reads (`chronicler/transport.py`). A static upload, the Batch
 * Lab's `bundle_loaded` message, live `init` and `turn` messages and the
 * reconnect `init` all go through these helpers, so each carries every
 * snapshot system and bundle system the contract names. See
 * docs/integration/historical-parity.md.
 */
import contract from "../../../src/chronicler/transport_contract.json";
import type { Bundle, TurnSnapshot } from "../types";

type SnapshotKey = keyof TurnSnapshot & string;
type BundleKey = keyof Bundle & string;

/** Fields every snapshot has. */
export const SNAPSHOT_FIELDS = contract.snapshot_fields as readonly SnapshotKey[];
/** Optional per-system summaries (absent while their system is off). */
export const SNAPSHOT_SYSTEMS = contract.snapshot_systems as readonly SnapshotKey[];
/** Optional top-level fields with their own versions. */
export const BUNDLE_SYSTEMS = contract.bundle_systems as readonly BundleKey[];
/** Top-level fields that travel with the history. */
export const BUNDLE_CARRIERS = contract.bundle_carriers as readonly BundleKey[];
/** Keys a live `turn` message adds to its snapshot. */
export const TURN_MESSAGE_KEYS = contract.turn_message_keys as readonly string[];

const SNAPSHOT_KEYS: readonly string[] = [...SNAPSHOT_FIELDS, ...SNAPSHOT_SYSTEMS];

type Message = Record<string, unknown>;

/** The history row of a live `turn` message (or a reconnect history row). */
export function snapshotFromMessage(message: Message): TurnSnapshot {
  const row: Message = {};
  for (const key of SNAPSHOT_KEYS) {
    if (message[key] !== undefined) {
      row[key] = message[key];
    }
  }
  return {
    ...row,
    turn: typeof row.turn === "number" ? row.turn : 0,
    civ_stats: (row.civ_stats ?? {}) as TurnSnapshot["civ_stats"],
    region_control: (row.region_control ?? {}) as TurnSnapshot["region_control"],
    relationships: (row.relationships ?? {}) as TurnSnapshot["relationships"],
  } as TurnSnapshot;
}

/** The bundle systems and carriers a message or bundle holds (present, not null). */
export function bundleSystemsOf(source: Message): Partial<Bundle> {
  const out: Message = {};
  for (const key of [...BUNDLE_SYSTEMS, ...BUNDLE_CARRIERS]) {
    if (source[key] !== undefined && source[key] !== null) {
      out[key] = source[key];
    }
  }
  return out as Partial<Bundle>;
}

/** The bundle of a running live session's `init` message (first connect or reconnect). */
export function bundleFromInitMessage(message: Message): Bundle {
  const history = Array.isArray(message.history) ? (message.history as Message[]) : [];
  return {
    world_state: message.world_state as Bundle["world_state"],
    history: history.map(snapshotFromMessage),
    events_timeline: (message.events_timeline as Bundle["events_timeline"]) || [],
    named_events: (message.named_events as Bundle["named_events"]) || [],
    chronicle_entries: (message.chronicle_entries as Bundle["chronicle_entries"]) || [],
    gap_summaries: (message.gap_summaries as Bundle["gap_summaries"]) || [],
    era_reflections: (message.era_reflections as Bundle["era_reflections"]) || {},
    metadata: message.metadata as Bundle["metadata"],
    ...bundleSystemsOf(message),
  };
}

/** Merge a `completed` message's bundle systems (the finished run's historiography and languages). */
export function applyCompletedMessage(bundle: Bundle, message: Message): Bundle {
  const systems = message.systems;
  if (typeof systems !== "object" || systems === null || Array.isArray(systems)) {
    return bundle;
  }
  return { ...bundle, ...bundleSystemsOf(systems as Message) };
}

/**
 * The WebSocket URL with the live session's token (`?token=`), unless it
 * already carries one. The CLI prints the viewer link with `ws` and `token`.
 */
export function withSessionToken(wsUrl: string, token: string | null): string {
  if (!token || !wsUrl) {
    return wsUrl;
  }
  try {
    const url = new URL(wsUrl);
    if (!url.searchParams.has("token")) {
      url.searchParams.set("token", token);
    }
    return url.toString();
  } catch {
    return wsUrl;
  }
}
