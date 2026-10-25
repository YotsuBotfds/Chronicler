import { describe, expect, it } from "vitest";
import { sampleLanguages, WORD_COLUMNS } from "../../__fixtures__/languagesField";
import {
  canonicalName, decodeWords, etymology, familyTree, formAt, glossary, howLabel, namesFor,
} from "../languages";

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
  });
});
