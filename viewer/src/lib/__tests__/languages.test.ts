import { describe, expect, it } from "vitest";
import { sampleLanguages, WORD_COLUMNS } from "../../__fixtures__/languagesField";
import {
  canonicalName, changesAt, decodeWords, etymology, familyTree, familyTreeAt, formAt, glossary, howLabel,
  languageStatusAt, namesFor, nativeNameAt, phonologyKnownAt,
} from "../languages";

describe("the languages field as of a turn", () => {
  it("knows the languages born by then, their status then and their changes by then", () => {
    const field = sampleLanguages();
    const [kethani, , dorrathi] = field.languages;
    expect(familyTreeAt(field, 49).map((node) => node.language.name)).toEqual(
      ["Kethani", "Proto-Highland", "Dorrathi"]);
    expect(familyTreeAt(field, 50).map((node) => node.language.name)).toContain("Free Iron Peaks");
    expect(familyTree(field).map((node) => node.language.name)).toContain("Free Iron Peaks");
    expect(languageStatusAt(kethani, 39)).toBe("living");
    expect(languageStatusAt(kethani, 40)).toBe("extinct");
    expect(languageStatusAt(field.languages[1], 0)).toBe("reconstructed");
    expect(changesAt(dorrathi, 59)).toHaveLength(1);  // the prehistoric one
    expect(changesAt(dorrathi, 60)).toHaveLength(2);
    expect(phonologyKnownAt(dorrathi, 59)).toBe(false);
    expect(phonologyKnownAt(dorrathi, 60)).toBe(true);
    expect(phonologyKnownAt(kethani, 0)).toBe(false);  // its turn-20 change
  });

  it("reads a language's own name for its people at a turn, as the export reads it at the end", () => {
    const field = sampleLanguages();
    const words = decodeWords(field);
    expect(nativeNameAt(field, field.languages[0], 100, words)).toBe(field.languages[0].native);
    // The name's form at a turn: a sound change after it is not applied.
    const changed = { ...field, words: field.words.map((row) => (row[0] === 3
      ? row.map((value, index) => (index === 8 ? [[0, "Kethaniki", null], [30, "Ketheniki", 0]] : value))
      : row)) };
    const changedWords = decodeWords(changed);
    expect(nativeNameAt(changed, changed.languages[0], 29, changedWords)).toBe("Kethaniki");
    expect(nativeNameAt(changed, changed.languages[0], 30, changedWords)).toBe("Ketheniki");
    // No civilization ever spoke the proto-language.
    expect(nativeNameAt(field, field.languages[1], 100, words)).toBeNull();
  });
});

describe("languages field", () => {
  it("decodes words by their named columns and tolerates a reordered layout", () => {
    const field = sampleLanguages();
    const words = decodeWords(field);
    expect(words).toHaveLength(7);
    expect(words[1]).toMatchObject({ lang: 0, kind: "region", ref: 0, how: "native" });
    const order = [...WORD_COLUMNS].reverse();
    field.word_columns = order;
    field.words = field.words.map((row) => order.map((name) => row[WORD_COLUMNS.indexOf(name)]));
    expect(decodeWords(field)[1].forms[1][1]).toBe("Ashkelvor");
  });

  it("reads a name as it stood at a turn", () => {
    const words = decodeWords(sampleLanguages());
    expect(formAt(words[1], 10)).toBe("Ashkelvora");
    expect(formAt(words[1], 25)).toBe("Ashkelvor");
    expect(formAt(words[2], 10)).toBeNull(); // not coined yet
    expect(formAt(words[5], 0)).toBe("Gorat Litar II");
  });

  it("lists every language's name for an entity, its own people's first", () => {
    const field = sampleLanguages();
    const early = namesFor(field, "region", 0, 35);
    expect(early.map((n) => [n.language.name, n.form, n.own])).toEqual([
      ["Kethani", "Ashkelvor", true],
      ["Dorrathi", "Askelbor", false],
    ]);
    const late = namesFor(field, "region", 0, 70);
    expect(late[0]).toMatchObject({ form: "Eskelbor", own: true, gloss: "green plain" });
    expect(namesFor(field, "civ", 0, 0).find((n) => n.language.id === 2)?.gloss).toBe("plain people");
    expect(namesFor(field, "person", "Warchief Gorath|0", 0)[0].gloss).toBe("war chief");
  });

  it("follows a name back through inheritance and borrowing to its coining", () => {
    const steps = etymology(sampleLanguages(), 6);
    expect(steps.map((s) => `${s.language.name}:${s.word.how}`)).toEqual([
      "Free Iron Peaks:inherited", "Dorrathi:substrate", "Kethani:native",
    ]);
    expect(steps[1].forms[1]).toEqual({ turn: 60, form: "Eskelbor", change: "a o u > e e i when the next syllable has i" });
    expect(steps[2].word.parts).toEqual([["ashkel", "green"], ["vor", "plain"]]);
  });

  it("orders the family tree and the glossary", () => {
    const field = sampleLanguages();
    expect(familyTree(field).map((n) => `${n.depth}:${n.language.name}`)).toEqual([
      "0:Kethani", "0:Proto-Highland", "1:Dorrathi", "2:Free Iron Peaks",
    ]);
    expect(glossary(field, 2, 70).map((r) => `${r.kind}:${r.canonical}:${r.name.form}`)).toEqual([
      "civ:Kethani Empire:Telsor", "region:Verdant Plains:Eskelbor", "person:Warchief Gorath:Gorat Litar II",
    ]);
    expect(canonicalName(field, "region", 0)).toBe("Verdant Plains");
    expect(howLabel("substrate")).toBe("kept from the earlier local name");
    // A faith word names its faith by permanent identity when the bundle's
    // table can (lib/faiths): its ref and coining turn, else the field's list.
    const label = (ref: number, coined: number) => (ref === 4 ? `Faith of X (founded turn ${coined - 1})` : null);
    expect(canonicalName(field, "faith", 4, label, 30)).toBe("Faith of X (founded turn 29)");
    expect(canonicalName(field, "faith", 5, label, 30)).toBe(canonicalName(field, "faith", 5));
  });
});
