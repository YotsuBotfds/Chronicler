// Reading the optional `historiography` bundle field: the in-world
// chroniclers' accounts of events (docs/integration/historiography.md).
// Every account tells a real event (its event_id); its transforms are the
// recorded biases (omit, inflate, minimize, claim, blame, praise, condemn,
// divine).

import type { HistoriographyField } from "../types";

export interface AccountTransform {
  kind: string;
  detail: Record<string, unknown>;
}

export interface EventAccount {
  id: string; // "<chronicler>/<event_id>"
  eventId: string;
  chronicler: string;
  chroniclerName: string;
  turn: number;
  stance: string;
  transforms: AccountTransform[];
  cited: string[];
  text: string;
  /** "told", "silent" (omitted), "lost" (its archive was destroyed) or "plain" (told as it happened). */
  status: "told" | "silent" | "lost" | "plain";
  lostTurn: number | null;
  lostCause: string | null;
}

export interface EventAccounts {
  accounts: EventAccount[];
  divergence: string[];
}

const LOSS_PHRASES: Record<string, string> = {
  sack: "sacked",
  conquest: "conquered",
  collapse: "lost in the collapse",
  fire: "burned",
  quake: "thrown down by an earthquake",
  flood: "flooded",
  plague: "emptied by plague",
  desecration: "desecrated",
  absorption: "scattered when the realm was absorbed",
  // Seats of learning (--scholarship): a fallen seat's archive.
  flight: "thinned on its scholars' flight",
  abandonment: "left behind when its seat fell",
};

export function lossPhrase(cause: string | null): string {
  return (cause && LOSS_PHRASES[cause]) || "lost";
}

function column(field: HistoriographyField, row: unknown[], name: string): unknown {
  const index = field.account_columns.indexOf(name);
  return index >= 0 ? row[index] : undefined;
}

/** Decode every account row of the field (unknown columns are ignored). */
export function decodeAccounts(field: HistoriographyField): EventAccount[] {
  const names = new Map(field.chroniclers.map((c) => [c.id, c.name]));
  return field.accounts.map((row) => {
    const eventId = String(column(field, row, "event_id") ?? "");
    const chronicler = String(column(field, row, "chronicler") ?? "");
    const rawTransforms = (column(field, row, "transforms") as unknown[] | undefined) ?? [];
    const transforms = rawTransforms.map((t) => {
      const [kind, detail] = t as [string, Record<string, unknown>];
      return { kind, detail: detail ?? {} };
    });
    const text = String(column(field, row, "text") ?? "");
    const lostTurn = (column(field, row, "lost_turn") as number | null | undefined) ?? null;
    return {
      id: `${chronicler}/${eventId}`,
      eventId,
      chronicler,
      chroniclerName: names.get(chronicler) ?? chronicler,
      turn: Number(column(field, row, "turn") ?? 0),
      stance: String(column(field, row, "stance") ?? "neutral"),
      transforms,
      cited: ((column(field, row, "cited") as string[] | undefined) ?? []).map(String),
      text,
      status: lostTurn !== null ? "lost" : text ? "told" : "silent",
      lostTurn,
      lostCause: (column(field, row, "lost_cause") as string | null | undefined) ?? null,
    };
  });
}

/**
 * The accounts as known at `turn`. The field is exported after the run, so
 * its losses are the final ones: a copy lost after `turn` still stands
 * there (told, or silent), and the `lost` divergence holds only while one
 * copy is lost by then and another stands. The other kinds read the texts,
 * which a loss does not change.
 */
export function accountsAsOf(entry: EventAccounts, turn: number): EventAccounts {
  let changed = false;
  const accounts = entry.accounts.map((account): EventAccount => {
    if (account.lostTurn === null || account.lostTurn <= turn) {
      return account;
    }
    changed = true;
    return { ...account, status: account.text ? "told" : "silent", lostTurn: null, lostCause: null };
  });
  if (!changed) {
    return entry;
  }
  const divergence = entry.divergence.filter((kind) => kind !== "lost");
  if (accounts.some((a) => a.status === "lost") && accounts.some((a) => a.status !== "lost")) {
    divergence.push("lost");
  }
  return { accounts, divergence: divergence.sort() };
}

/**
 * All accounts of one event (notable rows first, then plain tellings) and how
 * they diverge; with `upToTurn`, as known then (`accountsAsOf`).
 */
export function accountsForEvent(
  field: HistoriographyField | undefined,
  eventId: string | undefined,
  decoded?: EventAccount[],
  upToTurn?: number,
): EventAccounts | null {
  if (!field || !eventId) {
    return null;
  }
  const names = new Map(field.chroniclers.map((c) => [c.id, c.name]));
  const accounts = (decoded ?? decodeAccounts(field)).filter((a) => a.eventId === eventId);
  for (const [chronicler, eventIds] of Object.entries(field.plain ?? {})) {
    if (eventIds.includes(eventId)) {
      accounts.push({
        id: `${chronicler}/${eventId}`,
        eventId,
        chronicler,
        chroniclerName: names.get(chronicler) ?? chronicler,
        turn: accounts[0]?.turn ?? 0,
        stance: "plain",
        transforms: [],
        cited: [],
        text: "",
        status: "plain",
        lostTurn: null,
        lostCause: null,
      });
    }
  }
  if (accounts.length === 0) {
    return null;
  }
  const contested = field.contested.find((c) => c.event_id === eventId);
  const entry = { accounts, divergence: contested?.divergence ?? [] };
  return upToTurn === undefined ? entry : accountsAsOf(entry, upToTurn);
}

/** "The Kethani chronicles" for the start of a sentence. */
export function capitalized(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}
