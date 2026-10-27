# Narration provenance (2026-10)

Branch `feat/narration-provenance` from `main` `13f735a`. Narration, the
bundle's narration fields, tooling and the viewer: every simulation output
byte is identical ([Identity](#identity)).

An external review noted that readable prompt lines for all 252 event types
([narration-coverage.md](narration-coverage.md)) do not show that the prose
is right. It recommended tying each generated passage to the event and
account ids behind it. Now every fact line a narrator receives carries a
stable id. Each chronicle entry records the facts its narrator was given and
the facts each of its sentences cites. A deterministic audit checks those
records against the bundle and the prose. No LLM was called on this branch:
the mechanical narrator and scripted fake clients stand in for one.

Code: `src/chronicler/narration_provenance.py` (new: ids, fact sheets,
citation parsing, the entity names, the bundle form),
`src/chronicler/narration_audit.py` (new: the checker and its CLI),
`narrative.py` (tagged prompts, entries' provenance, the mechanical
narrator's spans, the per-turn narrator), `narration_context.py`
(`standing_state_facts`), `historiography.py` (tagged account lines,
`passage_parts`, `fact_text`), `languages.py` (tagged name lines,
`passage_parts`), `artifacts.py`, `models.py`
(`ChronicleEntry.provenance`, `PassageProvenance`), `bundle.py`,
`narration_inputs.py`, `main.py` (`--citations` / `--no-citations`, the
per-turn entries, `--narrate` output), `batch_manifest.py` (the flag is not
a simulation argument). Viewer: `lib/narrationSources.ts`,
`components/phase75/ChronicleSources.tsx` and `chronicle-sources.css`
(lazy), `lazyPanels.ts`, `AppShell.tsx`, `types.ts`.

## 1. Fact ids

Ids are scoped to one bundle. Each one names a record the bundle holds, or a
value read from one, by that record's own identity. No new identity scheme
sits beside them.

| id | names |
| --- | --- |
| `e<i>` | `events_timeline[i]`; the event's own `event_id` (`<turn>:<type>:<n>`) is that record's |
| `n<i>` | `named_events[i]` |
| `<chronicler>/e<i>` | an in-world account: the historiography account id is `<chronicler>/<event_id>` (`court:<civ>`, `temple:<faith>`, `seat:<n>`); event ids can hold spaces (`Mass Migration`), so the id names the event by its timeline index |
| `p<agent id>` | a named character, by its agent id; `p:<name>\|<born turn>` (the languages layer's person key, spaces as `_`) for one without an agent id (not seen in runs: the narrated characters are agent-born) |
| `art<id>` | `world_state.artifacts` by `artifact_id` |
| `s<S>.<what>.<key>` | a value of history snapshot `S`, the state after turn `S - 1`: `ruler.c<i>`, `war.c<i>-c<j>`, `movement.<id>`, `reform.<id>`, `city.<id>`, `guild.<id>`, `burghers.c<i>`, `seat.<id>`, `food.r<i>`, `urban.c<i>`, `settlement.<id>`; ids are the snapshot rows' own |
| `d<S1>-<S2>.<key>` | a change between snapshots `S1` and `S2`: `c<i>.<stat>` or `r<i>` (a region's controller); the BEFORE and AFTER summaries |
| `w<a>-<b>` | the events of turns `a..b` as the prompt counts them ("Also recorded ... (not listed)"); `w<a>-<b>.mood` the population mood their agent events give |
| `o<T>.<what>` | an observation describing completed turn `T`: `displacement`, `trade_dependency`; the per-turn narrator's `civ.c<i>`, `rival.c<i>`, `governance` |
| `L.<k><ref>` | in-world names of a languages entity: `c` civ, `r` region, `s` settlement, `f` faith, `p` person (index in `languages.persons`) |
| `k<j>` | the entry's own `causal_links[j]` (type-pair links, bundles without recorded provenance) |

`c<i>` and `r<i>` are indices in `world.civilizations` and `world.regions`
(the project's identity rule). `e<i>` indexes the timeline, which only
grows during a run. The in-run narration, `--narrate BUNDLE` and live range
narration all index the same list, the bundle's `events_timeline`
(`narration_inputs` passes it). Re-narrating a saved bundle therefore cites
the same records: `test_narrate_bundle_gives_the_same_ids_as_the_run`.

## 2. What an entry records

`ChronicleEntry.provenance` (omitted while None):

```json
{"v": 1, "narrator": "mechanical", "as_of": 35,
 "facts": [["e280", 30], "e339", ["e374", 39, "r"], ["court:2/e293", 31], ...],
 "names": [3, 7, 12],
 "spans": [[0, 112, ["e280", "e318", "e339"]], [113, 177, ["e293"]], ...]}
```

* `as_of`: the last completed turn the passage narrates. For a curated
  moment this is its last turn (`AsOf.after`). For a per-turn entry it is the
  turn narrated (the entry's `turn` is the next one, as before).
* `facts`: what the narrator was given, in prompt order. A bare id is dated
  `as_of`; `[id, turn]` carries its date; `[id, turn, "r"]` marks a fact
  given as retrospective, in the prompt's AFTER (for foreshadowing) or
  LATER CONSEQUENCES sections. Folded repeats of a listed line and the
  founding a line says news came from are facts of that line. A character's
  date is that of its latest dated deed, memory or bond, so a later record
  that leaks into a character block shows.
* `names`: the characters, civilizations, regions and faiths the facts
  name (§5).
* `spans`: `[start, end, [ids]]` over the entry's `narrative`. These are
  exact for the mechanical narrator (each sentence, chain and account
  telling, with the records it was built from). For an LLM they are its
  bracketed citations (§4).

**Bundle form.** Most passages of a run name the same peoples and places.
In the file, `names` are indices into one table, the top-level
`narration_provenance: {"version": 1, "names": [...]}` field
(`compact_entries` at bundle assembly and in the `--narrate` output file).
`expand_entries` reads them back, and `fact_rows` reads facts in either
form. Bundles without narration (simulate-only runs, older bundles) have
neither field, so their bytes are unchanged.

Which facts count as given:

* LLM narrators: every tagged line of the prompt.
* The mechanical narrator: the records its sentences were built from. It
  does not read the prompt, and the prompt's account block and its "In
  their own words" passage choose accounts differently.
* An LLM failure (batch result missing, sequential exception, per-turn
  exception): the fallback's mechanical facts, marked `mechanical`.

## 3. Prompts

Every fact line ends with its ids:

```
- [turn 30] famine: Famine strikes Iron Peaks, devastating Selurian Republic (importance 8; 5 more alike, turns 33-35: Frostholm Tundra, Verdant Plains, Thornwood, Amber Valley) [e280]
- [turn 1] Selurian Republic places itself under ... -> [turn 34] King Spearhart spends political capital ... [e18, e94, e330, e332]
- Rulers: Selurian Republic: Chancellor Tomelord (capital Ashara Desert, in The Northern Coalition); ... [s36.ruler.c3, s36.ruler.c2, s36.ruler.c0]
  - the Selurian chronicles: “Zishudri [Thornwall Confederacy] exposed funding separatists in Qushtu Dirki [Iron Peaks].” [court:3/e293]
- Thornwall Confederacy stability fell from 55 to 14 [d29-34.c2.stability]
- General Cael [bold] (Kethani Empire) [active]: [p42]
- Cael and Mira (rival, since turn 7) [p42, p43]
```

The prompt then asks for citations (`narration_provenance.CITE_INSTRUCTION`,
plus one clause in the system prompt):

> SOURCES: every fact above ends with its id in square brackets, e.g. [e12]
> or [e12, n3]. After each sentence, write the ids of the facts it draws on
> in square brackets, e.g. "The walls of the city fell [e12]." Cite only ids
> listed above, and name only people, peoples, places and faiths the facts
> name. The brackets are removed before the chronicle is shown.

The per-turn local narrator's prompt is tagged the same way (rule 8 of its
list). The tags go at the end of each line, so line text and every existing
substring the tests check is unchanged. `--no-citations`
(`NarrativeEngine(citations=False)`) sends untagged prompts with no request.
The facts given are recorded either way.

Measured with `scripts/narration_prompts.py capture` on the same saved
bundles, base `13f735a` against this branch (tokens at 4 characters):

| | template 1234, 300 turns (50 prompts) | procedural 32 x 10, seed 11, 150 turns (25) |
| --- | ---: | ---: |
| mean characters (tokens) | 8,853 -> 9,968 (2,213 -> 2,492), +12.6% | 10,028 -> 11,267 (2,507 -> 2,817), +12.4% |
| max characters | 10,720 -> 11,921 | 11,855 -> 13,227 |
| tagged lines per prompt | 51.8 | 57.8 |
| new prompts without tags and request, equal to base | 50 of 50 | 25 of 25 |

The request itself is 430 characters, 4.3-4.9 points of the 12.5%; the
tags are the rest. With `--no-citations`
the capture is byte-identical to base (sha256 `e2c3c378f82eacdf`). These are
agents-off runs; a hybrid prompt also tags its character lines.

## 4. LLM citations

`parse_citations` removes every bracket that holds only ids, together with
the space before it, so `fell [e12].` becomes `fell.`. Adjacent groups
(`[e1][e2]`, `[e1] [e2]`) count as one citation. Brackets that hold
anything else (`[turn 4]`) stay. Each citation's span is the sentence it
follows, or the part after the previous citation, plus the full stop after
the bracket. Ids are kept as written, valid or not, and the audit judges
them. The entry's `narrative` is the cleaned prose, so `chronicle.md` and the
viewer show no markers. The sequential narrator's style excerpt is cleaned
prose too.

## 5. Named entities

`EntityUniverse` lists the names of a run's civilizations (and their short
forms, "Kethani"), regions, faiths ("Faith of Kethani"), great persons and
rulers (from the world and every snapshot's `leader_name`, also without
their title: "Ulveth"). Matching is case-sensitive, longest form first, on
word boundaries. At narration time the sheet records the canonical names
that its fact lines (LLM) or fact records (mechanical: an event's
description, line, actors, civs and places; an account's chronicler, text
and lost archive's region; an entity's in-world names) mention. The audit
builds the same universe from the bundle (`from_bundle`) and looks for these
names in the prose. A name the run does not know (an invented person, a
movement or city name) is outside the check.

## 6. The audit

`python -m chronicler.narration_audit BUNDLE [BUNDLE ...] [--narrated FILE]
[--json OUT] [--show N] [--exit-zero]`. Library: `audit_bundle(bundle,
universe=None, narrated=None)`, `audit_entry(index, entry, records,
universe)`. `--narrated` checks a `--narrate` output file, which holds no
timeline, against its source bundle. The exit code is 1 when any entry is
flagged. No LLM or network is used.

| flag | when |
| --- | --- |
| `unsupplied_citation` | a cited id names a record of the bundle but was not given |
| `unknown_citation` | a cited id names nothing in the bundle and was not given |
| `future_citation` | a cited fact is dated after `as_of` and was not given as retrospective |
| `future_supplied` | a fact dated after `as_of` was given outside a retrospective section (a builder leak) |
| `unsupplied_name` | the prose names a character, civilization, region or faith that no given fact names |
| `stray_marker` | a fact id is left in the shown prose (a citation written another way, "(e12)") |
| `unresolved_fact`, `date_mismatch` | a given fact the bundle does not hold, or holds with another date |
| `bad_span` | a span outside the prose or out of order |
| `uncited_sentence`, `uncovered_text` | mechanical entries: a sentence without facts, or prose outside every span |

A retrospective citation is allowed and counted. For LLM entries, sentences
without a citation are counted, not flagged. Entries without provenance are
counted only.

**Mechanical narration.** Four runs (`--agents off --narrator mechanical`,
no native extension): template seeds 42 and 7 (200 turns), 1234 (300 turns)
and procedural 32 x 10 seed 11 (150 turns). Together they have 143 entries,
4,191 facts, 2,773 spans and 3,020 sentences: **0 flags**, 0 sentences
without a fact. The names check reads 1,805 / 1,766 / 2,766 / 1,663 entity
mentions (59 / 67 / 98 / 121 entities), and every one is named by a given
fact. Planting one unnamed place per entry is flagged 34 / 32 / 50 / 25
times out of 34 / 32 / 50 / 25.

**Synthetic LLM** (scripted fake clients over the template 1234 bundle, 50
moments):

| | entries | citations | flags |
| --- | ---: | ---: | --- |
| faithful (retells two event lines with their ids) | 50 | 100 | none |
| flawed (adds an earlier record not given, a later one, `e999999`, a place no fact names, "(e1)") | 50 | 299 | unsupplied_citation 99, unknown_citation 50, future_citation 49, unsupplied_name 45, stray_marker 50 |

These match what was planted. The last moment has no later record to cite,
and five prompts name every place.

## 7. Viewer

A narrated chronicle card has a "Sources (N)" toggle. It opens the
passage's sources from a lazily loaded chunk (`ChronicleSources`, 4.9 kB and
1.0 kB CSS). The cited facts come first, then, on request, every other fact
given. Each source has a turn link (an event also opens in the event
inspector), its kind and its record resolved from the bundle: event and
landmark text, chronicler and event, character and artifact names, the civ
or region a state or change id keys. A fact dated after the scrubbed turn
(a retrospective one) is counted and shown once its turn has passed, as
elsewhere in the viewer. The entry chunk grows by 756 bytes (307,379 ->
308,135; gzip -9 96,633 -> 96,902), and the main CSS by 55. A turn link to a
turn before the passage's last also hides the card, since a curated passage
appears once its last turn has passed. There is no per-sentence
highlighting.

## Cost

Bundles: base `13f735a` against this branch, the same runs.

| run | bundle bytes | provenance | per entry |
| --- | --- | ---: | ---: |
| template 42, 200 turns, 34 entries | 3,074,202 -> 3,106,869 (+1.06%) | 30,871 + 1,296 table | 908 |
| template 7, 200 turns, 34 | 3,485,690 -> 3,519,640 (+0.97%) | 31,981 + 1,469 | 941 |
| template 1234, 300 turns, 50 | 6,196,764 -> 6,248,991 (+0.84%) | 49,328 + 2,175 | 987 |
| procedural 32 x 10 seed 11, 150 turns, 25 | 13,823,641 -> 13,862,614 (+0.28%) | 35,777 + 2,822 | 1,431 |
| size-guard world (`tests/test_bundle.py`: seed 1, 500 turns, default per-turn narrator, dummy client), 500 entries | 7,722,755 -> 7,966,555 (+3.2%) | | about 490 |

The size guard stays at 10.5 MB. Before the bundle form (bare ids, the names
table) the size-guard world grew by 538 KB, half of it the same names
repeated every turn.

Time: the size-guard world's wall time (500 turns, the per-turn narrator with
a dummy client that costs nothing) is 11.7 / 12.0 s on base and 12.4 / 12.5 s
here (two alternated runs each). The extra 0.5-0.7 s is mostly the names scan
of each fact line. Names are matched by first word (`EntityUniverse`)
instead of a compiled alternation regex, which had to be rebuilt whenever a
person was born (216 of 500 turns) and cost 0.9 s. The two give the same
mentions on 11,290 prompt, prose and event texts.

## Identity

No-Rust venv (Python 3.13.17, `uv sync --frozen`, `chronicler_agents`
absent), `PYTHONHASHSEED=0`, `13f735a`'s exported `src` on `PYTHONPATH`
against this branch.

* `scripts/turn_speed_identity.py`, cases `off_s42`, `off_s7`,
  `proc48_off_s7` (`--simulate-only`): 33 files, 0 differences (bundles
  decoded and raw with `generated_at` blanked).
* `--simulate-only --agents off`, template seeds 1234 and 99 (200 turns),
  procedural 32 x 10 seed 11 (100 turns), `scripts/cities_identity.py
  compare`: 9 / 9 / 15 files, 0 differences. Bundle sha256 with
  `generated_at` blanked: `d3687ad11e670a44`, `bfcbeb5b5d6784a3`,
  `0e4631745ceebbcc`, the same on both sides.
* `--narrator mechanical --agents off`, the four runs of §6:
  `scripts/narration_identity.py compare` (everything but the narration):
  8 / 8 / 8 / 14 files, 0 differences. `chronicle.md` is byte-identical in
  all four: the mechanical text does not change. The bundles are identical
  apart from the entries' `provenance` and the `narration_provenance` table.

No simulation, snapshot, timeline or sidecar byte changes. The narration
identity scripts (`narration_identity.py`, `historiography_identity.py`,
`languages_identity.py`) now treat the new fields as narration.

## Tests

Linux, Python 3.13.17, no-Rust venv; Node 22.22.0.

* `tests/test_narration_provenance.py` (27, in the oracle lane's narration
  chunk). It covers the citation grammar and parsing, fact ids by identity,
  event id and content, entity forms, and mechanical provenance passing the
  audit on four worlds (template seeds 42, 7, 1234 and a procedural 16 x 5,
  60 turns), with spans tiling the prose and ids naming the bundle's
  records. Re-narrating a bundle gives the run's ids. Tagged prompts, a
  faithful fake LLM passing, and a flawed one flagged for bad, future and
  unknown citations, an unnamed place and a stray marker. Retrospective
  citations are allowed, the batch path and its mechanical fallback are
  covered, and `--no-citations` sends untagged prompts. A sequential failure
  falls back with mechanical provenance. Character, relationship, mood and
  settlement ids are checked, and a leaked later deed is flagged. Further
  cases: hand-made provenance (future facts, names, dates, spans, gaps), the
  CLI and `--narrated`, per-turn provenance, simulate-only carrying none,
  and the names table round trip.
* Changed: `test_historiography.py` and `test_languages.py` (the import
  guards admit `narration_provenance.py`; the flag-on identity helpers treat
  provenance as narration); `tests/test_bundle.py` (size note).
* `python -m pytest -q -n 2 -m "not slow"` over the narration, history,
  live, bundle, main, batch, checkpoint and validation files (28 files):
  850 passed, 7 skipped.
* The full no-Rust suite, `python -m pytest -q -n 2 -m "not slow"`
  (`chronicler_agents` absent: native suites skip): 6,363 passed, 251
  skipped, 526 subtests.
* `python scripts/run_python_oracle_checks.py`: PASS in 92.7 s (narration
  chunk 171 passed in 6.0 s).
* Viewer: `npm ci`; `npm test -- --maxWorkers=2` 426 passed in 54 files (new:
  `lib/__tests__/narrationSources.test.ts`,
  `components/phase75/__tests__/ChronicleSources.test.tsx`); `npm run lint`
  clean; `npm run build` passes.

## Not done, limits

* No LLM was called. Whether a real model cites reliably, how often it
  cites, and whether the tags or the request change its prose are untested.
  `--no-citations` gives back the previous prompts exactly.
* No native build or hybrid run. The agent context's ids (characters,
  relationships, settlements, observations) are covered by unit tests only.
* The names check covers names the run knows. It does not judge claims
  ("won" against "lost"), numbers or invented names, and an LLM may cite a
  fact it was given while misstating it.
* Gap summaries (`GapSummary`, "N events, dominated by T") carry no
  provenance. They are counts with no names; the BEFORE/AFTER changes a
  prompt gives are `d` facts.
* Era reflections and the live per-turn stream are not covered. The live
  `turn` messages carry the per-turn text, not its provenance; live range
  narration sends its entry with provenance.
* The viewer lists sources per passage and does not highlight sentences.
  It has no browser QA (jsdom tests only).
