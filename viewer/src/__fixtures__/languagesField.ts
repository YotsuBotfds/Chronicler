// Synthetic `languages` bundle field for viewer tests (shape of
// chronicler.languages.export; names are illustrative).
import type { LanguageInfo, LanguagesField } from "../types";

export const WORD_COLUMNS = ["id", "lang", "kind", "ref", "turn", "how", "source", "parts", "forms", "tail", "until"];

const phonology = (order: string): LanguageInfo["phonology"] => ({
  consonants: "p t k m n s l r", vowels: "a e i o u", onsets: [], finals: "n s l r",
  syllables: ["CV", "CVC"], order, join: "word", stress: "initial",
});

export function sampleLanguages(): LanguagesField {
  return {
    version: 1,
    enabled_turn: 0,
    counts: { changes: 2 },
    languages: [
      { id: 0, name: "Kethani", parent: null, family: 0, origin: "founding", turn: 0, status: "extinct",
        last_spoken: 40, style: "maritime", civs: [], native: "Kethaniki", phonology: phonology("mh"),
        changes: [[20, "apocope", "final short vowels are lost", 12, null, false]] },
      { id: 1, name: "Proto-Highland", parent: null, family: 1, origin: "proto", turn: 0, status: "reconstructed",
        last_spoken: null, style: "mountain", civs: [], native: null, phonology: phonology("hm"), changes: [] },
      { id: 2, name: "Dorrathi", parent: 1, family: 1, origin: "prehistory", turn: 0, status: "living",
        last_spoken: null, style: "mountain", civs: [1], native: "Grumvar", phonology: phonology("hm"),
        changes: [[0, "lenition", "p t k > b d g between vowels", 9, null, true],
          [60, "umlaut", "a o u > e e i when the next syllable has i", 7, null, false]] },
      { id: 3, name: "Free Iron Peaks", parent: 2, family: 1, origin: "secession", turn: 50, status: "living",
        last_spoken: null, style: "mountain", civs: [2], native: null, phonology: phonology("hm"), changes: [] },
    ],
    word_columns: WORD_COLUMNS,
    words: [
      [0, 0, "root", "green", 0, "native", null, [], [[0, "ashkel", null]], "", null],
      [1, 0, "region", 0, 0, "native", null, [["ashkel", "green"], ["vor", "plain"]],
        [[0, "Ashkelvora", null], [20, "Ashkelvor", 0]], "", null],
      [2, 2, "region", 0, 30, "substrate", 1, [], [[30, "Askelbor", null], [60, "Eskelbor", 1]], "", null],
      [3, 0, "civ", 0, 0, "native", null, [["kethani", "Kethani"], ["ki", "people"]], [[0, "Kethaniki", null]], "", null],
      [4, 2, "civ", 0, 0, "descriptive", 3, [["tel", "people"], ["sor", "plain"]], [[0, "Telsor", null]], "", null],
      [5, 2, "person", "Warchief Gorath|0", 0, "native", null, [["gorat", "Gorath"], ["litar", "war chief"]],
        [[0, "Gorat Litar", null]], " II", null],
      [6, 3, "region", 0, 50, "inherited", 2, [], [[50, "Askelbor", null]], "", null],
    ],
    civs: [
      { civ: 0, name: "Kethani Empire", lang: [[0, 0]] },
      { civ: 1, name: "Dorrathi Clans", lang: [[0, 2]] },
      { civ: 2, name: "Free Iron Peaks", lang: [[50, 3]] },
    ],
    regions: [
      { region: 0, name: "Verdant Plains", speech: [[0, 0], [40, 2]],
        story: [[0, "settled", 0], [30, "ruled", 1], [40, "shift", 2]] },
    ],
    settlements: [],
    faiths: [],
    persons: [{ key: "Warchief Gorath|0", name: "Warchief Gorath", civ: 1, role: "ruler" }],
  };
}
