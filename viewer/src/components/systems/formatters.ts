/**
 * Display formatters shared by the systems panels. Each body is the one most
 * panels already copied locally; a panel whose local formatter differs keeps
 * its own.
 */

/** A recorded number at display precision, or "Unknown" when it is absent. */
export const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

/** As `show`, but an absent value reads "Not observed". */
export const notObserved = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Not observed" : value.toLocaleString(undefined, { maximumFractionDigits: digits });

/** A share (0..1) as a percentage at display precision. */
export const percent = (share: number, digits = 3) =>
  `${(share * 100).toLocaleString(undefined, { maximumFractionDigits: digits })}%`;

/** A record code (`snake_case`) as words; absent text is empty. */
export const words = (text: string | null | undefined) => (text ?? "").replace(/_/g, " ");
