// Reading the optional `languages` bundle field: the world's languages and
// the names their peoples give to civs, regions, settlements, faiths and
// persons (docs/integration/languages.md). Canonical names stay the
// identifiers; these are glosses.

import type { LanguageInfo, LanguagesField } from "../types";

export type WordKind = "root" | "civ" | "region" | "settlement" | "faith" | "person";

export interface LanguageWord {
  id: number;
  lang: number;
  kind: WordKind | string;
  ref: number | string;
  turn: number;
  /** native, loan, calque, substrate, inherited, descriptive */
  how: string;
  source: number | null;
  /** [morpheme, gloss] in the word's own order. */
  parts: Array<[string, string]>;
  /** [turn, display form, change index or null]; the first row is the coined form. */
  forms: Array<[number, string, number | null]>;
  tail: string;
  until: number | null;
}

export interface EntityName {
  word: LanguageWord;
  language: LanguageInfo;
  form: string;
  gloss: string | null;
  own: boolean;
}

export interface EtymologyStep {
  word: LanguageWord;
  language: LanguageInfo;
  forms: Array<{ turn: number; form: string; change: string | null }>;
}

function column(field: LanguagesField, row: unknown[], name: string): unknown {
  const index = field.word_columns.indexOf(name);
  return index >= 0 ? row[index] : undefined;
}

/** Decode every word row of the field by its named columns. */
export function decodeWords(field: LanguagesField): LanguageWord[] {
  return field.words.map((row) => ({
    id: Number(column(field, row, "id")),
    lang: Number(column(field, row, "lang")),
    kind: String(column(field, row, "kind") ?? ""),
    ref: column(field, row, "ref") as number | string,
    turn: Number(column(field, row, "turn") ?? 0),
    how: String(column(field, row, "how") ?? "native"),
    source: (column(field, row, "source") as number | null | undefined) ?? null,
    parts: ((column(field, row, "parts") as Array<[string, string]> | undefined) ?? []),
    forms: ((column(field, row, "forms") as Array<[number, string, number | null]> | undefined) ?? []),
    tail: String(column(field, row, "tail") ?? ""),
    until: (column(field, row, "until") as number | null | undefined) ?? null,
  }));
}

function at<T>(rows: Array<[number, T]>, turn: number): T | null {
  let value: T | null = null;
  for (const [rowTurn, v] of rows) {
    if (rowTurn > turn) {
      break;
    }
    value = v;
  }
  return value;
}

/** A word's display form at a turn, without its tail (null before it was coined or after it was replaced). */
function stemAt(word: LanguageWord, turn: number): string | null {
  if (word.turn > turn || (word.until !== null && word.until <= turn)) {
    return null;
  }
  let form = word.forms[0]?.[1] ?? "";
  for (const [rowTurn, f] of word.forms) {
    if (rowTurn > turn) {
      break;
    }
    form = f;
  }
  return form;
}

/** A word's display form at a turn (null before it was coined or after it was replaced). */
export function formAt(word: LanguageWord, turn: number): string | null {
  const stem = stemAt(word, turn);
  return stem === null ? null : stem + word.tail;
}

// --- The field as of a turn ---------------------------------------------
// The field is exported after the run: its languages include those born
// later, with their final status, endonym, sound inventory and changes.

/** Languages known at `turn` (born by then; reconstructed proto-languages always), in tree order. */
export function familyTreeAt(field: LanguagesField, turn: number): FamilyNode[] {
  return familyTree(field).filter(({ language }) => language.status === "reconstructed" || language.turn <= turn);
}

/**
 * A language's status at `turn`: extinct from its `last_spoken` turn, living
 * before it. The record keeps only the latest extinction (a revival clears
 * it), so an earlier extinction followed by a revival is not shown.
 */
export function languageStatusAt(language: LanguageInfo, turn: number): string {
  if (language.status === "extinct" && language.last_spoken !== null && language.last_spoken > turn) {
    return "living";
  }
  return language.status;
}

/** Its sound changes recorded by `turn`. */
export function changesAt(language: LanguageInfo, turn: number): LanguageInfo["changes"] {
  return language.changes.filter(([changeTurn]) => changeTurn <= turn);
}

/**
 * The sound inventory is the final one: unknown at `turn` when a change
 * after it (not a prehistoric one) may have altered it.
 */
export function phonologyKnownAt(language: LanguageInfo, turn: number): boolean {
  return !language.changes.some(([changeTurn, , , , , prehistoric]) => !prehistoric && changeTurn > turn);
}

/**
 * Its speakers' name for themselves at `turn`, as the export's `native`
 * reads it at the end: the language's name, then, for the first civilization
 * (by index) that ever spoke it. Null without one.
 */
export function nativeNameAt(field: LanguagesField, language: LanguageInfo, turn: number,
                             words: LanguageWord[]): string | null {
  const civ = field.civs.find((entry) => entry.lang.some(([, lang]) => lang === language.id))?.civ;
  if (civ === undefined) {
    return null;
  }
  let name: string | null = null;
  for (const word of words) {
    if (word.lang === language.id && word.kind === "civ" && word.ref === civ) {
      name = stemAt(word, turn) ?? name;
    }
  }
  return name;
}

/** The English meaning of a word ("green plain"), following loans to their source. */
export function glossOf(field: LanguagesField, word: LanguageWord, byId: Map<number, LanguageWord>): string | null {
  if (word.kind === "person") {
    const title = word.parts.find(([, g]) => g && g === g.toLowerCase());
    return title ? title[1] : null;
  }
  let current: LanguageWord | undefined = word;
  for (let steps = 0; current && steps < 8; steps += 1) {
    if (current.parts.length > 0) {
      const glosses = current.parts.map(([, g]) => g);
      const order = field.languages.find((l) => l.id === current!.lang)?.phonology.order;
      const english = order === "hm" && glosses.length >= 2 ? [...glosses.slice(1), glosses[0]] : glosses;
      return english.join(" ");
    }
    current = current.source !== null ? byId.get(current.source) : undefined;
  }
  return null;
}

/** The language an entity's own people speak at a turn. */
export function ownLanguage(field: LanguagesField, kind: string, ref: number | string,
                            turn: number, words: LanguageWord[]): number | null {
  if (kind === "civ") {
    const rows = field.civs.find((c) => c.civ === ref)?.lang ?? [];
    return at(rows, turn) ?? rows[0]?.[1] ?? null;
  }
  if (kind === "region") {
    return at(field.regions.find((r) => r.region === ref)?.speech ?? [], turn);
  }
  const native = words.filter((w) => w.kind === kind && w.ref === ref && w.how === "native")
    .sort((a, b) => a.id - b.id)[0];
  return native ? native.lang : null;
}

/** Every language's name for an entity at a turn, its own people's first. */
export function namesFor(field: LanguagesField, kind: string, ref: number | string, turn: number,
                         words?: LanguageWord[]): EntityName[] {
  const all = words ?? decodeWords(field);
  const byId = new Map(all.map((w) => [w.id, w]));
  const own = ownLanguage(field, kind, ref, turn, all);
  const latest = new Map<number, LanguageWord>();
  for (const w of all) {
    if (w.kind === kind && w.ref === ref && formAt(w, turn) !== null) {
      latest.set(w.lang, w);
    }
  }
  const out: EntityName[] = [];
  for (const [lang, word] of latest) {
    const language = field.languages.find((l) => l.id === lang);
    if (!language) {
      continue;
    }
    out.push({ word, language, form: formAt(word, turn)!, gloss: glossOf(field, word, byId), own: lang === own });
  }
  return out.sort((a, b) => Number(b.own) - Number(a.own) || a.language.id - b.language.id);
}

/** A word's history back to its origin: each language it passed through, with its forms there. */
export function etymology(field: LanguagesField, wordId: number, words?: LanguageWord[]): EtymologyStep[] {
  const all = words ?? decodeWords(field);
  const byId = new Map(all.map((w) => [w.id, w]));
  const steps: EtymologyStep[] = [];
  let current = byId.get(wordId);
  const seen = new Set<number>();
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    const language = field.languages.find((l) => l.id === current!.lang);
    if (!language) {
      break;
    }
    steps.push({
      word: current,
      language,
      forms: current.forms.map(([turn, form, change]) => ({
        turn,
        form: form + current!.tail,
        change: change !== null ? (language.changes[change]?.[2] ?? null) : null,
      })),
    });
    current = current.source !== null ? byId.get(current.source) : undefined;
  }
  return steps;
}

export interface FamilyNode {
  language: LanguageInfo;
  depth: number;
}

/** Languages in family-tree order (each family root, then its daughters), with their depth. */
export function familyTree(field: LanguagesField): FamilyNode[] {
  const out: FamilyNode[] = [];
  const visit = (language: LanguageInfo, depth: number) => {
    out.push({ language, depth });
    for (const child of field.languages.filter((l) => l.parent === language.id)) {
      visit(child, depth + 1);
    }
  };
  for (const root of field.languages.filter((l) => l.parent === null)) {
    visit(root, 0);
  }
  return out;
}

/**
 * How a faith word's faith is shown: its permanent identity (name and
 * founding turn) from the bundle's faith table (lib/faiths), given the
 * word's ref and coining turn (an older bundle's ref is a slot, read at that
 * turn). Null falls back to the field's own list.
 */
export type FaithWordLabel = (ref: number, coined: number) => string | null;

/** The canonical name of an entity a word names. */
export function canonicalName(field: LanguagesField, kind: string, ref: number | string,
                              faithLabel?: FaithWordLabel, coined = 0): string {
  if (kind === "faith" && faithLabel && typeof ref === "number") {
    const label = faithLabel(ref, coined);
    if (label) {
      return label;
    }
  }
  switch (kind) {
    case "civ":
      return field.civs.find((c) => c.civ === ref)?.name ?? `civ ${ref}`;
    case "region":
      return field.regions.find((r) => r.region === ref)?.name ?? `region ${ref}`;
    case "settlement":
      return field.settlements.find((s) => s.id === ref)?.name ?? `settlement ${ref}`;
    case "faith":
      return field.faiths.find((f) => f.faith === ref)?.name ?? `faith ${ref}`;
    case "person":
      return field.persons.find((p) => p.key === ref)?.name ?? String(ref);
    default:
      return String(ref);
  }
}

/** A language's names (not roots) in use at a turn, grouped in a fixed kind order. */
export function glossary(field: LanguagesField, lang: number, turn: number,
                         words?: LanguageWord[],
                         faithLabel?: FaithWordLabel): Array<{ kind: string; canonical: string; name: EntityName }> {
  const all = words ?? decodeWords(field);
  const byId = new Map(all.map((w) => [w.id, w]));
  const language = field.languages.find((l) => l.id === lang);
  if (!language) {
    return [];
  }
  const order = ["civ", "region", "settlement", "faith", "person"];
  const rows: Array<{ kind: string; canonical: string; name: EntityName }> = [];
  for (const w of all) {
    if (w.lang !== lang || w.kind === "root" || formAt(w, turn) === null) {
      continue;
    }
    rows.push({
      kind: w.kind,
      canonical: canonicalName(field, w.kind, w.ref, faithLabel, w.turn),
      name: { word: w, language, form: formAt(w, turn)!, gloss: glossOf(field, w, byId), own: false },
    });
  }
  return rows.sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || a.canonical.localeCompare(b.canonical));
}

const HOW_LABELS: Record<string, string> = {
  native: "coined",
  loan: "borrowed",
  calque: "translated",
  substrate: "kept from the earlier local name",
  inherited: "inherited",
  descriptive: "descriptive",
};

export function howLabel(how: string): string {
  return HOW_LABELS[how] ?? how;
}
