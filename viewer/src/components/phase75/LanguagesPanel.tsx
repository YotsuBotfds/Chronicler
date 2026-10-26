import { useMemo, useState } from "react";
import type { LanguagesField } from "../../types";
import {
  changesAt, decodeWords, etymology, familyTreeAt, glossary, howLabel, languageStatusAt, namesFor, nativeNameAt,
  phonologyKnownAt, type LanguageWord,
} from "../../lib/languages";

const KIND_LABELS: Record<string, string> = {
  civ: "People",
  region: "Land",
  settlement: "Town",
  faith: "Faith",
  person: "Person",
};

function Etymology({ field, wordId, words, turn }: {
  field: LanguagesField; wordId: number; words: LanguageWord[]; turn: number;
}) {
  // Its forms through the sound changes recorded by `turn` (later ones are not shown).
  const steps = etymology(field, wordId, words);
  return (
    <ol className="phase75-etymology" aria-label="Etymology">
      {steps.map((step) => (
        <li key={step.word.id}>
          <span className="phase75-account-source">{step.language.name}</span>
          <span className="phase75-account-tags"> {howLabel(step.word.how)} (turn {step.word.turn})</span>
          {step.word.parts.length > 0 && (
            <span> from {step.word.parts.map(([form, gloss]) => `${form} '${gloss}'`).join(" + ")}</span>
          )}
          <ul className="phase75-etymology-forms">
            {step.forms.filter((f) => f.turn <= turn).map((f) => (
              <li key={`${f.turn}-${f.form}`}>
                <strong>{f.form}</strong> <span>turn {f.turn}</span>
                {f.change && <em> ({f.change})</em>}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}

/**
 * Inspector section for the optional `languages` field: the family tree, a
 * language's glossary of names at the current turn, an entity's names in
 * every language that knows it, and a name's etymology (its forms through
 * each sound change, back through loans and inheritance to its coining).
 */
export function LanguagesPanel({
  field,
  turn,
  selected = null,
}: {
  field: LanguagesField | undefined;
  turn: number;
  /** The pinned region or civ, by index. */
  selected?: { kind: "region" | "civ"; ref: number } | null;
}) {
  const words = useMemo(() => (field ? decodeWords(field) : []), [field]);
  // The languages known at the turn, with their status then (the field is the end-of-run record).
  const tree = useMemo(() => (field ? familyTreeAt(field, turn) : []), [field, turn]);
  const [chosen, setChosen] = useState<number | null>(null);
  const [wordId, setWordId] = useState<number | null>(null);
  if (!field || tree.length === 0) {
    return null;
  }
  const living = tree.find((node) => languageStatusAt(node.language, turn) === "living")?.language.id
    ?? tree[0].language.id;
  const langId = chosen !== null && tree.some((node) => node.language.id === chosen) ? chosen : living;
  const language = field.languages.find((l) => l.id === langId) ?? tree[0].language;
  const names = selected ? namesFor(field, selected.kind, selected.ref, turn, words) : [];
  const rows = glossary(field, language.id, turn, words);
  // A word coined after the turn (chosen at a later one) has no etymology yet.
  const showWord = wordId !== null && words.some((w) => w.id === wordId && w.turn <= turn) ? wordId : null;
  const native = nativeNameAt(field, language, turn, words);
  const changes = changesAt(language, turn).length;
  return (
    <div className="phase75-languages" aria-label="Languages">
      {names.length > 0 && (
        <div aria-label="Names of the selection">
          <div className="phase75-stat-row">
            <span>Names</span>
            <strong>{names.length} language{names.length !== 1 ? "s" : ""}</strong>
          </div>
          <ul className="phase75-account-list">
            {names.map((n) => (
              <li key={n.word.id}>
                <button type="button" className="phase75-link-button" onClick={() => setWordId(n.word.id)}>
                  {n.form}
                </button>
                <span className="phase75-account-source"> {n.language.name}</span>
                {n.own && <span className="phase75-account-tags"> (its own people)</span>}
                {n.gloss && <em> '{n.gloss}'</em>}
                <span> · {howLabel(n.word.how)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <label className="phase75-field">
        <span>Language</span>
        <select
          value={language.id}
          onChange={(e) => {
            setChosen(Number(e.target.value));
            setWordId(null);
          }}
        >
          {tree.map(({ language: l, depth }) => (
            <option key={l.id} value={l.id}>
              {"  ".repeat(depth)}{l.name} ({languageStatusAt(l, turn)}{l.status !== "reconstructed" ? `, from turn ${l.turn}` : ""})
            </option>
          ))}
        </select>
      </label>
      <p className="phase75-detail-copy">
        {native ? `${native} to its speakers. ` : ""}
        {language.origin === "secession" || language.origin === "separation" || language.origin === "prehistory"
          ? `Daughter of ${field.languages.find((l) => l.id === language.parent)?.name ?? "?"} (${language.origin}). `
          : ""}
        {/* The exported inventory is the final one; a later sound change may have altered it. */}
        Sounds: {phonologyKnownAt(language, turn)
          ? `${language.phonology.consonants} / ${language.phonology.vowels}`
          : "Unavailable at this turn"}.
        {" "}{changes} sound change{changes !== 1 ? "s" : ""} by turn {turn}.
      </p>
      <ul className="phase75-account-list" aria-label="Glossary">
        {rows.slice(0, 40).map((row) => (
          <li key={row.name.word.id}>
            <span className="phase75-account-tags">{KIND_LABELS[row.kind] ?? row.kind}</span>{" "}
            <button type="button" className="phase75-link-button" onClick={() => setWordId(row.name.word.id)}>
              {row.name.form}
            </button>
            <span> {row.canonical}</span>
            {row.name.gloss && <em> '{row.name.gloss}'</em>}
          </li>
        ))}
      </ul>
      {showWord !== null && <Etymology field={field} wordId={showWord} words={words} turn={turn} />}
    </div>
  );
}
