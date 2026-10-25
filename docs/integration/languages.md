# In-world languages and names

Branch `feat/languages` from `origin/main` at `baabafb` (Wave 6). Code:
`src/chronicler/languages_phonology.py` (sound systems and sound change),
`src/chronicler/languages.py` (the layer, the bundle field, `NameIndex`),
hooks in `main.py` (switch, per-turn observation, narration, bundle),
`models.py` (world slot, state sidecar), `narrative.py` (prompt block,
mechanical gloss), `historiography.py` (accounts in their chroniclers' own
names), `bundle.py`, `live.py`, `scripts/m53b_run_validation.py`
(forwarding) and `scripts/languages_identity.py` (identity proofs). Viewer:
`viewer/src/lib/languages.ts`, `viewer/src/components/phase75/LanguagesPanel.tsx`.

Every people speaks a language with its own sounds. Languages change by
regular sound laws, split into daughters when a community is cut off, and
borrow words along contact. Each language names the civs, regions,
settlements, faiths and persons its speakers know. The narrator can tell a
moment from a people's side: what they call themselves, what their
neighbours call them, and the older name a conquered valley keeps.

> As the Thornwall chronicles tell it: "In the glorious reign of Seren
> Litarivo [Warchief Seren], Tēlsor [Kethani Empire] is extinguished; its
> last land falls to Lirvanor [Thornwall Confederacy], a great triumph for
> the Lirvanor."

The canonical names stay the identifiers. Entity names feed simulation RNG
keys (`stable_hash_int(..., civ.name)` in many modules), so nothing is
renamed; the viewer and the event timeline show the canonical names as
before. This layer adds endonyms, exonyms and their histories beside them.

Like the historiography, the layer is **observational**. The simulation
decides; the layer reads what happened. With it on or off, the simulation
state, snapshots, timeline, RNG streams, `state.json`, the historiography
sidecar and the validation reports are byte-identical. Only the narration
prose and an optional bundle field change ([Outcome identity](#outcome-identity)).

## Contract

* **Reads only.** `observe_turn(world)` runs in `execute_run` after each
  completed turn, right after the historiography observation. It reads
  civs, regions (controller, cultural identity, adjacency, settlements),
  leaders, great persons, the belief registry, active wars and the contact
  ledger's rows (`pairs`, `edges`). It writes only into the slot and builds
  none of the world's caches (it reads the ledger rows directly, not
  `pair_map()`/`edge_map()`). No simulation module imports it (a test pins
  the importers to `main`, `models`, `live`).
* **Deterministic, never a simulation stream.** Every choice is a draw from
  `stable_hash_int("languages", seed, ...)`, keyed by ids and turns, not by
  order of calls. Neither module imports `random` or `numpy` (tested);
  `random.getstate()` and NumPy's global state are unchanged across an
  observation (tested).
* **Identity.** Civs are indices into `world.civilizations`, regions
  indices into `world.regions`, faiths faith ids, settlements settlement
  ids. Persons, which have no id, are keyed by canonical name and the turn
  they appeared (`"Warchief Seren|0"`). Languages and words are indices
  into the layer's own lists.
* **Independent of the historiography.** Neither layer reads the other's
  state. The narration combines them: `AccountIndex(..., names=NameIndex)`
  renders a chronicler's quoted text in its own language's names. Without
  a `NameIndex` the historiography's output is unchanged (tested).

## Languages

**Founding.** At the first observed turn each civ gets a phonological
style: from its domains when they name one (maritime, mountain, forest,
desert, steppe), else from its capital's terrain (the keys of
`geography.PHONOLOGIES`). Founding civs that share a style form one
family: a reconstructed proto-language ("Proto-Desert") whose daughters
already differ by one or two prehistoric sound changes. A style held by one
civ gives a single founding language.

**Sound system** (`proto_phonology`, drawn per style):

* a consonant inventory (a style's core plus a draw of its extras, one core
  consonant sometimes missing) and five or three vowels, some long;
* syllable templates (`CV`, `CVC`, `V`, `CCV`, `CCVC`) with weights,
  allowed two-consonant onsets, codas and word-final consonants (a fifth of
  languages end every word in a vowel);
* initial or penultimate stress, modifier-head or head-modifier order,
  compounds as one word or two ("Su Ashara"), a linking vowel and a repair
  strategy (epenthesis or deletion).

**Lexicon.** 78 naming morphemes in five classes: core (river, hill, ford,
new, green, people, ...), trade (iron, gold, salt, market, ship, harbor,
way, bridge), people (town, house, horse), war (fort, wall, war, king,
queen, chief, lord) and faith (god, holy, priest, temple). Roots are built
from the templates and repaired to the phonotactics; suffix-like morphemes
(people, town, land, ford, fort, holy) have one syllable.

Words are stored as segment strings, one character per segment (`θ`, `ʃ`,
`ā`, `ə`, ...). `roman()` spells them for display ("th", "sh", "ā"; a glide
after a vowel is written as a vowel: `kaj` -> "Kai").

## Sound change

Each living language undergoes one regular change every 25 to 55 turns
(`choose_change`): a candidate that fits its sound system, alters at least
two roots and was not applied before, drawn by weight. It applies to every
word of the language, roots and names alike, and is recorded with its
turn, description and word count. The sound system is then updated (merged
segments removed; new segments, codas, finals and onsets read from the
roots).

| Kind | Changes |
| --- | --- |
| Lenition | p t k > b d g between vowels; b d g > v dh gh between vowels; z > r between vowels |
| Final | final devoicing; loss of final short vowels (apocope); loss of final stops |
| Palatal | k g > ch j before i e; t > ts and s > sh before i |
| Vowels | umlaut (a o u > e e i before i); long-vowel raising (ē ō > ī ū); ā > ō; lowering in closed syllables; unstressed vowels > schwa; mergers (o > u, e > i); shortening, lengthening in open syllables; monophthongization (ai au > ē ō), diphthongization (ē ō > ei ou) |
| Clusters | syncope of short unstressed medial vowels; the first of two consonants lost, lengthening the vowel; nasal assimilation; initial clusters simplified; prothesis before s + consonant |
| Mergers and losses | th > t, dh > d, gh > g, kh > h, sh > s, q > k, ts > s, v > w, j > zh, ng > n; h lost; s > h before consonants and finally; w lost before o, u; p t k > f th kh initially |

A word keeps its history: `forms` lists the coined form and each later
form with the change that made it. A daughter starts with copies of its
parent's current words (`inherited`) and changes on its own from then on.

**Wave spread.** When a language makes a change, each living language of
the same family in contact with it (weighted contact 2 or more) takes the
same change with p = min(0.6, contact / 20), if its sound system has it.
Sisters in contact keep sharing changes; separated ones drift apart.

## Splits

* **Secession.** A new civ whose regions were last held by another civ (no
  event parsing: the layer remembers each region's last controller, so the
  Python and native politics paths are treated alike) speaks a daughter of
  the language of its capital region. If that region already speaks a
  dialect no state speaks, the dialect becomes the new state's language.
  The breakaway regions' speech moves to the daughter.
* **Long separation.** A province cut off from its people's state for 100
  turns grows its own dialect, named after its region ("Amber Valley Upper
  Thornwall"). Cut off means an exclave (no path to the capital through the
  civ's own land) or a conquered province that keeps the language of a
  people still ruling land elsewhere. Contact-ledger flow of 2 or more
  between the province and its home land keeps it in the fold. A change of
  ruler restarts the count.
* **Restoration.** A civ restored under an earlier civ's name speaks that
  civ's language again; an extinct language returns to life.
* A language is extinct when no living civ and no ruled region speaks it.
  Extinct languages stop changing; their names survive in other languages.

## Contact

Contact between two civs is the contact ledger's decayed flows between
their regions (`pairs`: goods, migrants, soldiers, pilgrims, weighted
1/1/0.25/2 as the ledger's `CONTACT_WEIGHTS`), plus 0.5 per shared border
and a war flag. Without the ledger, borders and wars only.

* **Loanwords.** Each turn, for each language pair and channel, a borrower
  takes one word of the channel's class from the donor with p = 0.02 v /
  (v + 5) (v: the channel's flow; borders count as migrants): goods bring
  trade words, migrants everyday words, soldiers war words, pilgrims
  religious words. The loan is adapted to the borrower's sounds
  (`adapt`: each segment mapped to the nearest one by place, manner and
  voicing, then repaired) and replaces the old root, which is kept with its
  `until` turn.
* **Exonyms.** A people names each living civ it borders, fights or has
  contact of 1 or more with. With p = 0.35 + 0.5 x (share of peaceful
  flows), minus 0.2 at war, it borrows the neighbour's self-name; otherwise
  it coins a descriptive name from the neighbour's homeland ("sand people",
  "sea people").

## Names

**Civs.** A people named after a proper stem calls itself stem + "people"
("Kethani" -> Kithaniki); a people named in plain words keeps two of them
(Thornwall -> Lirvanor, 'thorn wall'). One modifier is kept when short
("Greater Selurian").

**Regions** (toponym layering). Canonical names are read as morphemes:
English words through a small vocabulary ("Verdant Plains" -> green +
plain, "Thornwood" -> thorn + wood, "Frostholm Tundra" -> ice + land),
other words as proper stems ("Ashara"), at most two parts.

* A people names land it holds, borders or trades with. Its own land, or
  land nobody lives in, it names from its own lexicon.
* Land where another people lives it names after theirs: borrowed and
  adapted, or (p = 0.3) translated.
* A conqueror without a name for the land takes over the local one
  (`substrate`).
* When the region's people shift to the ruler's language (its cultural
  identity changes), the name they had stays, adapted: an earlier name of
  the ruler's own gives way to it. The name then drifts with its new
  language. A shift to a daughter of the old language is a dialect change,
  not a shift.

**Settlements** (agent modes) are named by the region's people at
founding: region + town, new town, river ford, high fort, sea harbor, or
the reigning ruler's name + town. A later ruler of another language takes
the name over.

**Faiths** are named in their founder's language (holy + founder's stem,
new for a reformed faith). Civs that follow a faith borrow its name.

**Persons.** Rulers and active great persons get their name adapted to
their civ's language (at most three syllables) and their title translated
(Warchief -> war chief, Empress -> great queen, High Priestess -> high
priest), in the language's word order: Warchief Seren is "Seren Litarivo"
in Thornwall. A regnal ordinal is kept after the name. Persons' names drift
with the language, so by turn 222 the Thornwall say "Seren Literif".

## Narration

`NameIndex` reads the bundle field. Names are read as they stood at a
turn: a word's form then, the language a civ or region spoke then, the
local names a region had before.

* **Prompt.** `NarrativeEngine` prompts gain an `IN-WORLD NAMES` block
  after the accounts: up to six of the moment's civs, regions, persons,
  settlements and faiths, each with its own people's name and meaning, the
  names used by the other peoples in the moment, and a former local name.
  It tells the narrator to keep the canonical names authoritative and to
  gloss a native name at first use.
* **Mechanical chronicle.** `mechanical_narrative` appends "In their own
  tongues: ..." for up to two civs or regions per moment, each once per
  chronicle. Also used when an LLM call fails.
* **In-world accounts.** With both layers on, each chronicler's quoted text
  uses its own language's names (court: its civ's; temple: its faith's
  founder's), the canonical name in brackets at first mention:
  "Rasaliri [Amber Valley] (capital of Tēlsor [Kethani Empire]) is
  occupied". Account selection and ids are unchanged.
* **`--narrate <bundle>`** and the live viewer's "narrate this range" use
  the field when the bundle has it (`--no-languages` ignores it). Old
  bundles narrate as before. The curator is unchanged.
* Not covered: the per-turn local narrator prompt during a run.

## Bundle field

`bundle["languages"]` is added last, only when the layer is on. Bundles
without it keep their bytes; no version bump (it carries its own
`version`).

Abridged, from the seed-42 run below:

```json
{"version": 1, "enabled_turn": 0, "counts": {"changes": 32, "changes:spread": 5, "loans:trade": 13, "region:substrate": 2, ...},
 "languages": [..., {"id": 4, "name": "Thornwall", "parent": null, "family": 4, "origin": "founding", "turn": 0,
   "status": "living", "last_spoken": null, "style": "forest", "civs": [2], "native": "Lirvanor",
   "phonology": {"consonants": "f v m w th t s n l r sh", "vowels": "a e i o u", "onsets": ["sl"],
                 "finals": "f m w t s n l r", "syllables": ["CV", "CVC", "V"], "order": "hm", "join": "word",
                 "stress": "penult"},
   "changes": [[42, "long_backing", "ā > ō", 8, null, false], [88, "shortening", "long vowels shorten", 25, null, false],
               [114, "apocope", "final short vowels are lost", 30, null, false], ...]}, ...],
 "word_columns": ["id", "lang", "kind", "ref", "turn", "how", "source", "parts", "forms", "tail", "until"],
 "words": [..., [435, 4, "region", 5, 4, "loan", 410, [], [[4, "Rasaliri", null], [114, "Rasalir", 2], [222, "Raselir", 5]], "", null], ...],
 "civs": [..., {"civ": 2, "name": "Thornwall Confederacy", "lang": [[0, 4]]}, ...],
 "regions": [..., {"region": 5, "name": "Amber Valley", "speech": [[0, 3], [23, 4], [50, 5], [150, 7]],
   "story": [[0, "ruled", 1], [0, "settled", 3], [9, "ruled", 2], [23, "shift", 4], [50, "dialect", 5], [50, "ruled", 4], [150, "dialect", 7]]}, ...],
 "settlements": [], "faiths": [...], "persons": [{"key": "Warchief Seren|0", "name": "Warchief Seren", "civ": 2, "role": "ruler"}, ...]}
```

`words` holds compact rows (`word_columns`, append only): roots and names.
`how` is native, loan, calque, substrate, inherited or descriptive;
`source` is the word it came from; `parts` the morphemes it was built
from, with their meanings; `forms` the display forms with the turn and the
index of the change that made each (forms that look the same are folded).
`tail` is shown after the name (a regnal ordinal); `until` is the turn a
word was replaced. `story` entries are `ruled` (civ index), `settled`,
`shift` and `dialect` (language id).

**Viewer.** `Bundle.languages?` is an optional type; `lib/languages.ts`
decodes rows by column name. The AppShell right inspector gains a
**Languages** section when the field is present: the pinned region's or
civ's names in every language that knows it at the current turn (its own
people's first), a language selector in family-tree order, the language's
glossary at that turn, and an etymology view per name (each language it
passed through, how it got there, and its forms through each sound change
back to its morphemes). Bundles without the field show nothing new.

## Persistence and the switch

`--languages` / `--no-languages`. New worlds use
`DEFAULT_ENABLED_FOR_NEW_WORLDS` (on); live mode's new worlds follow it. A
supplied or resumed world keeps its own setting; an explicit flag switches
it (on: languages are founded at that turn; off: dropped). The gate runner
forwards an explicit flag (`m53b_run_validation.py --languages /
--no-languages`).

The state lives on `WorldState._languages` (a `LanguagesSlot`,
equality-neutral, outside `model_dump`), so the serializer has no dormant
field to omit. `WorldState.save`, `WorldState.load` and the compact
checkpoint writer carry it in a sidecar: `state.json` ->
`state.languages.json`.

* Old saves (no sidecar) load with the layer off.
* A sidecar of another turn is not trusted: languages are founded afresh at
  the loaded turn, with a warning.
* Saving with the layer off removes a stale sidecar.
* Live mode resumes from a client-sent state dict, without a sidecar, and
  starts without languages.

Draws are keyed by ids and turns, and the derived lookups are rebuilt after
a load, so a resumed run writes exactly what an uninterrupted one writes
(tested).

## Default: on for new worlds

The layer started default-off and was switched on once the proofs below
held, on the same grounds as the historiography: it changes nothing the
simulation or its gates read.

* **Outcome-neutral, proven.** `state.json`, snapshots, timeline, memories,
  agent events, the historiography sidecar, RNG streams and validation
  reports are byte-identical with it on, for agents off and hybrid, against
  the base commit and in three subset gates. AGENTS.md keeps experimental
  *simulation* features default-off until qualified; no oracle, decision or
  stream can see this layer.
* **Cheap.**
  * About 4% run time on the 500-turn guard world (21.5 s against 20.6 s,
    three alternating runs each); about 4 ms per turn on a 48-region,
    10-civ procedural world.
  * The bundle grows by 1.4% on the subset and stays within the 24 MB guard
    (17.66 MB native, 18.28 MB no-Rust).
  * The sidecar averages 135 KB per 200-turn subset run.
* **Tested.** 34 focused tests (in the offline lane), the frozen
  exact-trajectory oracles rerun with it on, base-commit identity in both
  agent modes, three subset gates and a CLI resume.

**What does change by default**, all of it narration:

* The bundle gains the field; a `state.languages.json` sidecar is written.
* Curated narration (`--narrator api|gemini|mechanical`, `--narrate`)
  gains the names block in prompts and the "In their own tongues" gloss in
  the mechanical chronicle; quoted in-world accounts use their
  chroniclers' own names. The curated moments are the same.

`--no-languages` restores the previous output byte for byte. The frozen
benchmark workloads (`scripts/benchmark_headless.run`) pin it off, as they
pin the historiography; a test runs them with it on.

## Outcome identity

1. **Frozen exact-trajectory oracles, with the layer on.**
   `test_frozen_oracles_hold_with_languages_on` runs the three frozen
   corrected workloads with languages kept: every turn's snapshot, events
   and narration hash and the ordered RNG trace match the unchanged
   fixtures. `test_performance_equivalence`, `test_governance_dormancy` and
   `test_turn_artifact_lifecycle` pass unchanged with the pin.
2. **In-suite run identity.**
   * `test_flag_on_changes_no_simulation_output` (40 turns, mechanical
     narrator) checks every snapshot and every file except the narration;
     the bundle is identical apart from the field and the entries' prose.
   * `test_native_hybrid_run_is_outcome_identical_with_the_flag`: the same
     for a 20-turn native hybrid run.
   * `test_flag_off_never_runs_the_layer` forbids `observe_turn`, `export`
     and `NameIndex` while off.
   * `test_observation_reads_only` checks that the world dump, random and
     NumPy state and the world caches are untouched.
   * `test_resume_from_a_checkpoint_continues_identically`: a run resumed
     from a mid-run checkpoint writes the same sidecar, field and state.
3. **Against the base commit** (`scripts/languages_identity.py`). Base
   `baabafb` is exported with `git archive` and run with its own source on
   `PYTHONPATH`; same interpreter and native extension (built from this
   tree; no Rust change), `PYTHONHASHSEED=0`, `--narrator mechanical`. The
   set: template seeds 42, 7 and 1234 (agents off 300 turns, hybrid 200),
   plus a procedural 48 x 10 world, seed 7 (off 200, hybrid 120).

   | Comparison | Result |
   | --- | --- |
   | base vs `--no-languages` (`compare`) | 80 files, 0 differences |
   | base vs default (on) (`compare --languages`) | 80 files, 0 differences; 8 sidecars only in new; 8 `chronicle.md` narrations differ; 8 bundles identical apart from `languages` and the entries' `narrative` |

   "Identical" covers `state.json`, `state.historiography.json`, the memory
   streams, `agent_events.arrow` and the bundle: world state, every history
   snapshot, `pruned_civ_stats`, the event timeline, named events, the
   curated chronicle entries (turns, events, chains, roles, account ids),
   gap summaries, the historiography field, era reflections and metadata.
   `compare --languages` also checks that every word's language and source,
   every language's parent and every civ and region index in NEW resolve.
4. **Subset gates** (20 seeds x 200 turns, hybrid, `--parallel 1`): base
   `baabafb`, the branch with `--no-languages` and the branch with the
   default. All three **PASS** with identical oracle statuses: artifacts and
   regression PASS (strict); cohort, community, era and needs PASS; arcs
   FAIL (informational, as on base); determinism SKIP. The three
   `validate_report_subset.json` and gate decisions are identical once the
   batch directory is normalized.

   | Comparison | Result |
   | --- | --- |
   | base vs off | 2,184 files, 0 differences |
   | off vs on | 2,184 files, 0 differences; 20 sidecars only in on; bundles identical apart from `languages` and the entries' prose |

5. **CLI resume.** Seed 42, 300 turns straight, against 150 turns then
   `--resume` to 300: `state.json`, `state.languages.json`,
   `state.historiography.json` and the field are identical.

## Results

| Check (Linux, Python 3.13, shared 4-core host) | Result |
| --- | --- |
| `pytest -m "not slow" -n 2` (extension built from this tree; compiled `AgentSimulator`, `EcologySimulator`, `PoliticsSimulator` verified) | **5,939 passed, 3 skipped** (34 of them in `tests/test_languages.py`) |
| `pytest -m slow -n 2` (same build; includes the 500-turn bundle guard with the layer on) | **11 passed, 3 skipped** |
| No-Rust lane (fresh virtualenv without `chronicler_agents`, `pytest -q -n 2`, slow included) | **5,737 passed, 205 skipped** (the native hybrid identity test skips) |
| `scripts/run_python_oracle_checks.py` (now including `tests/test_languages.py` in `systems-2`) | **PASS**: 1,942 passed, 11 skipped, 2 deselected; guard PASS, no native module loaded, no blocked I/O; 79.5 s; `systems-2` 27.1 s of its 110 s |
| Viewer: `npm test -- --maxWorkers=2`, `npm run lint`, `npm run build` | 229 tests passed (+10), lint clean, build passes (the existing large-chunk warning remains) |
| 500-turn bundle-size guard (`seed=1, turns=500, civs=5, regions=10`, agents off) | native 17.66 MB with the layer (field 0.20 MB; 17.47 MB off); no-Rust 18.28 MB (field 0.21 MB; 18.07 MB off); the 24 MB guard holds and is unchanged |
| Run time (guard world, native, alternating) | on 21.9 / 21.4 / 21.1 s, off 21.0 / 20.3 / 20.4 s (means 21.5 and 20.6 s, +4%) |
| `cargo test` | not run: no Rust change |

**Per 200-turn hybrid run** (the 20-seed subset, defaults):

* **Languages.** 5.8: 2.7 founding, 0.65 reconstructed protos with 1.3
  daughters, 1.15 separation dialects (all exclaves); no secessions in
  these runs. 1.1 languages go extinct.
* **Change.** 18.9 sound changes, 1.0 of them spread between sisters.
* **Contact.** 33 loanwords (trade 16.9, migrants and borders 14.9,
  soldiers 0.9, pilgrims 0.3). Exonyms: 5.0 borrowed self-names, 6.2
  descriptive.
* **Names.** 94 persons; place names: 10.6 native, 13.2 borrowed, 5.3
  translated, 9.0 inherited, 0.1 substrate (most conquerors already know
  the land's name by loan); 7.1 settlements; 16 faiths in their founders'
  tongues and 7.2 borrowed by followers. 2.0 language shifts.
* **Size.** The field averages 76 KB (at most 102 KB), +1.4% on the bundle;
  the sidecar averages 135 KB. On the 48 x 10 procedural identity world
  (seed 7, 200 turns, agents off: 24 languages, 3,212 words) the field is
  340 KB, 1.0% of a 33 MB bundle; the sidecar 620 KB.

## Seed 42 examples

From the default-on identity run: template world, seed 42, 300 turns,
`--agents off --narrator mechanical`, `PYTHONHASHSEED=0`.

**1. The family tree** (turn: origin; the changes each language made):

```
Proto-Desert (reconstructed)
├── Ashkari (prehistory; extinct after turn 112)
│     q > k (prehistoric); sh > s (t35, from Selurian); unstressed vowels > schwa (t40);
│     p t k > b d g between vowels (t71, from Selurian); b d g > v dh gh between vowels (t94)
└── Selurian (prehistory; extinct after turn 146)
      kh > h (prehistoric); sh > s (t35); schwa (t40, from Ashkari); lenition (t71);
      spirantization (t94, from Ashkari); first of two consonants lost (t112)
      └── Western Stormbreak Cliffs (secession, t56; extinct after turn 237)
            b d > v dh (t86); v > w (t114); q > k (t155); k > ch before i e (t199)
Kethani (founding; extinct after turn 23, no changes)
Thornwall (founding; living)
      ā > ō (t42); long vowels shorten (t88); final short vowels lost (t114); s > sh before i (t145);
      v > f finally (t191); umlaut (t222); t > th initially (t263)
└── Upper Thornwall (secession, t50; living)
      s > sh before i (t98); t > ts before i (t152); s > h (t190); umlaut (t222, from Thornwall);
      h lost (t225); ē ō > ei ou (t258); lowering (t284)
      └── Amber Valley Upper Thornwall (separation, t150; spoken in Amber Valley)
            long vowels shorten (t194); final short vowels lost (t235); t > th initially (t273)
```

Ashkari and Selurian, sisters in contact, shared four changes (wave
spread); Thornwall and Upper Thornwall shared one.

The procedural identity world (48 regions, 10 civs, seed 7, 200 turns,
agents off) grows two families and two isolates, with chains of
secessions:

```
Proto-Steppe: Quserai (> Bruwick Bog Quserai, separation t146); Tosikhan (> Southern Jadun Fields, t39
  > Lower Besekhan Vale, t50; > Greater Tosikhan, t54); Khitekani (extinct t34); Sakhuguri (> Free Majak
  Vale, t50, extinct t131 > Eastern Majak Vale, t102; > Western Sakhuguri, t81)
Proto-Woodland: Wodeth; Wofideth (> Lower Wofideth, t59 > Fafewen Weald Lower Wofideth, separation t188;
  > Jimujak Expanse Wofideth, separation t160); Hatoyan; Geniwyn (> Northern Khorai Steppe, t45;
  > Western Fimiwyn Forest, t118)
Thavigrimi; Pythysi
```

The Tosikhan call themselves *Thūsishanrus*; their breakaways say
*Tusishanrus* (Greater Tosikhan) and *Jadunrus* (Southern Jadun Fields,
after its region's stem).

**2. A region's names across conquests.** Amber Valley, 'gold valley':

| Turn | What happened | Its people's name |
| --- | --- | --- |
| 0 | Kethani land | Kethani *Rathaliri* (ratha 'gold' + liri 'valley') |
| 4 | Thornwall, a neighbour, borrows the name | (Thornwall *Rasaliri*) |
| 9 | Thornwall takes the valley; Kethani extinguished | Rathaliri (the people still speak Kethani) |
| 23 | The people shift to Thornwall; Kethani dies out | Thornwall *Rasaliri* |
| 50 | Upper Thornwall secedes with it | Upper Thornwall *Rasaliri* (inherited) |
| 150 | A century as an exclave: its own dialect | Amber Valley Upper Thornwall *Rasaliri* |
| 235 | Final short vowels lost | *Rasalir* |

Meanwhile the Thornwall court's form went Rasaliri > Rasalir (t114) >
Raselir (t222, umlaut), and Upper Thornwall's Rasaliri > Raseliri (t222).

Stormbreak Cliffs shows the substrate rule. Selurian settlers named it
*Hi Shahdi* ('storm cliff'); it became *Hi Sahde* in their Western
Stormbreak Cliffs daughter. Thornwall had its own name, *Lonarnae*, from
when the cliffs were empty, and kept it after conquering them (t222). When
the people shifted to Thornwall (t237), the local name stayed: Thornwall
*I Sata*, adapted from Hi Sahde, replaced Lonarnae.

**3. A narrated passage** (the mechanical chronicle; the same moment from
the base commit reads "In the glorious reign of Warchief Seren, Kethani
Empire is extinguished; ..."):

> In their own words: As the Thornwall chronicles tell it: "In the glorious
> reign of Seren Litarivo [Warchief Seren], Tēlsor [Kethani Empire] is
> extinguished; its last land falls to Lirvanor [Thornwall Confederacy], a
> great triumph for the Lirvanor." As the Thornwall chronicles tell it: "In
> the glorious reign of Seren Litarivo [Warchief Seren], Rasaliri [Amber
> Valley] (capital of Tēlsor [Kethani Empire]) is occupied by The Second
> Warband of Lirvanor [Thornwall Confederacy], a great triumph for the
> Lirvanor."
>
> In their own tongues: Selurian Republic, Zisiruri to themselves
> ('Selurian people'), Zisu in Ashkari. Kethani Empire, Kithaniki to
> themselves ('Kethani people'), Kisamiki in Ashkari.

The Thornwall call the Kethani *Tēlsor*, 'plain people', a descriptive
exonym; the Ashkari borrowed the Kethani self-name (*Kisamiki*).

From the prompt of the moment at turns 72-77, two chroniclers name the same
peoples differently:

```
- the Ashkari chronicles (blame, minimize): "Zeeskare [Ashkari Nomads] places itself under the
  protection of Zesudre [Thornwall Confederacy] as a client; it was an alliance between equals; ..."
- the Thornwall chronicles (inflate): "Tēlwusu [Ashkari Nomads] places itself under the protection
  of Lirvanor [Thornwall Confederacy] as a client, a great triumph for the Lirvanor."

IN-WORLD NAMES (...):
- Thornwall Confederacy: they call themselves "Lirvanor" (Thornwall, 'thorn wall'); Ashkari "Zesudre" ('plain people'); ...
- Ashkari Nomads: they call themselves "Zeeskare" (Ashkari, 'Ashkari people'); Thornwall "Tēlwusu" ('sea people'); ...
- Verdant Plains: its people say "Sorner" (Upper Thornwall, 'green plain'); Ashkari "Sermire"; Selurian "Sudre Du"
```

Loanwords in this run (20; 13 by trade, 7 by migration and borders): Ashkari
took 'gold', 'bridge' and 'salt' from Thornwall; Selurian took 'way' and
'bridge' from its own daughter Western Stormbreak Cliffs; Upper Thornwall
took 'iron' (now *tserta*) from Selurian.

## What was cut, and limits

* **Names are glosses.** Canonical names stay in the simulation, timeline
  and viewer; the layer never renames.
* **One name per language and entity.** No competing names within a
  language (court against people), except that a coinage gives way to the
  local name at a language shift. Rivers and seas are not named.
* **Persons do not translate.** Their names are adapted, not given new
  meanings; English-compound canonical names ("Driftmere") become long
  adapted stems cut to three syllables.
* **Morphology is minimal.** Compounding only: no inflection, no grammar,
  no sentences. The narrator gets names and meanings, not text in the
  languages.
* **Separation is mostly exclaves.** Template worlds often give a civ two
  regions that are not adjacent, so such a civ's outlying region becomes a
  dialect after a century (about one per 200-turn subset run). Conquered
  provinces assimilate within about 15 turns, so their dialects are rare.
* **Calibration is illustrative.** Change intervals, borrowing rates and
  thresholds shape names only.
* **No retroactive history.** Old saves and bundles get no languages; a
  world switched on mid-run is founded at that turn, and its existing civs
  are founding cultures.
* **Not run.** The full 200-seed gate (not needed: the simulation is
  unchanged and the subset reports are identical) and live-mode browser QA.
