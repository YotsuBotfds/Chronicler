/**
 * Structural guards for live WebSocket messages (`turn` and a running `init`).
 *
 * These check only the containers the live bundle builders read; they do not
 * call `validateBundleStructure`, because a live `init` legitimately carries
 * partial fields. A rejected message is meant to be dropped by the caller
 * instead of being recorded (a missing `turn` would otherwise become turn 0).
 */
import { isRecord } from "./bundleValidation";

export type LiveMessage = Record<string, unknown>;
export type LiveParse = { ok: true; value: LiveMessage } | { ok: false; reason: string };

const TURN_RECORDS = ["civ_stats", "region_control", "relationships"] as const;
const TURN_ARRAYS = ["events", "named_events"] as const;

function reject(reason: string): LiveParse {
  return { ok: false, reason };
}

/** A live `turn` message: integer `turn` >= 1, record containers, optional event arrays. */
export function parseLiveTurn(msg: unknown): LiveParse {
  if (!isRecord(msg)) return reject("turn message is not an object");
  const turn = msg.turn;
  if (typeof turn !== "number" || !Number.isInteger(turn) || turn < 1) {
    return reject("turn message has no integer turn >= 1");
  }
  for (const key of TURN_RECORDS) {
    if (!isRecord(msg[key])) return reject(`turn message ${key} is not an object`);
  }
  for (const key of TURN_ARRAYS) {
    if (msg[key] !== undefined && !Array.isArray(msg[key])) return reject(`turn message ${key} is not an array`);
  }
  return { ok: true, value: msg };
}

/** A running-state live `init` message: world state, history rows with numeric turns, metadata. */
export function parseLiveInit(msg: unknown): LiveParse {
  if (!isRecord(msg)) return reject("init message is not an object");
  const world = msg.world_state;
  if (!isRecord(world)) return reject("init message world_state is not an object");
  if (!Array.isArray(world.regions)) return reject("init message world_state.regions is not an array");
  if (!Array.isArray(world.civilizations)) return reject("init message world_state.civilizations is not an array");
  if (!Array.isArray(msg.history)) return reject("init message history is not an array");
  const badRow = msg.history.findIndex((row) => !isRecord(row) || typeof row.turn !== "number" || !Number.isFinite(row.turn));
  if (badRow !== -1) return reject(`init message history[${badRow}] has no numeric turn`);
  if (!isRecord(msg.metadata)) return reject("init message metadata is not an object");
  return { ok: true, value: msg };
}
