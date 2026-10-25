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

/** A word's display form at a turn (null before it was coined or after it was replaced). */
export function formAt(word: LanguageWord, turn: number): string | null {
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
  return form + word.tail;
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

/** The canonical name of an entity a word names. */
export function canonicalName(field: LanguagesField, kind: string, ref: number | string): string {
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
                         words?: LanguageWord[]): Array<{ kind: string; canonical: string; name: EntityName }> {
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
      canonical: canonicalName(field, w.kind, w.ref),
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
