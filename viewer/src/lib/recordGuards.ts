/**
 * Shared structural guards for records read from bundles, checkpoints and
 * live messages.
 *
 * Each guard is the single spelling of a body that many readers used to
 * define locally; a reader imports the variant that matches its old body
 * (under its old local name) so the values it accepts do not change.
 *
 * `count` and `safeCount` differ on purpose: `count` accepts any non-negative
 * integer (including values past 2**53), `safeCount` only safe integers.
 * `integer` and `safeInteger` take an optional lower bound; do not pass them
 * directly to `Array.prototype.every`/`filter`, which would pass the index as
 * that bound. Use `count`/`safeCount` (one parameter) for callbacks.
 */

/** A plain object record: not null and not an array. */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A finite number (rejects NaN and the infinities). */
export const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/** A finite number greater than or equal to zero. */
export const amount = (x: unknown): x is number => finite(x) && x >= 0;

/** A finite integer greater than or equal to `min` (default 0). */
export const integer = (x: unknown, min = 0): x is number => finite(x) && Number.isInteger(x) && x >= min;

/** A non-negative integer; not limited to the safe-integer range. */
export const count = (x: unknown): x is number => Number.isInteger(x) && (x as number) >= 0;

/** A non-negative safe integer (at most 2**53 - 1). */
export const safeCount = (x: unknown): x is number => Number.isSafeInteger(x) && (x as number) >= 0;

/** A safe integer greater than or equal to `min` (default 0). */
export const safeInteger = (x: unknown, min = 0): x is number => Number.isSafeInteger(x) && (x as number) >= min;
