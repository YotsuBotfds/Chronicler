import { useState } from "react";

/**
 * The first page of `rows`, growing by `size` on each `showMore`.
 * `more` is how many rows are still hidden (0 when all are shown).
 */
export function usePaged<T>(rows: readonly T[], size: number) {
  const [limit, setLimit] = useState(size);
  return {
    shown: rows.slice(0, limit),
    more: Math.max(0, rows.length - limit),
    showMore: () => setLimit((current) => current + size),
  };
}
