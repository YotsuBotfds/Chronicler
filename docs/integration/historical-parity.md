# Historical parity (2026-10)

Branch `fix/historical-parity` from `main` `fc01d6e` (PR #44). Narration,
curation, live transport and viewer only: every simulation output byte is
identical ([Identity](#identity)). An external review reported six defects;
each was reproduced on `fc01d6e` with a test before it was fixed
([Findings](#findings)).

Code: `src/chronicler/historical_context.py` (new: the as-of convention and
its record/view), `narrative.py`, `curator.py`, `artifacts.py`,
`narration_inputs.py` (new: bundle inputs shared by `--narrate` and live
range narration), `transport_contract.json` and `transport.py` (new: the
transport contract), `live.py`, `bundle_codec.py`, `main.py`; viewer
`lib/transport.ts`, `lib/civilizationViews.ts` (new), `lib/bundleCodec.ts`,
`lib/bundleLoader.ts`, `hooks/useBundle.ts`, `hooks/useLiveConnection.ts`,
`App.tsx`, `components/phase75/AppShell.tsx`; fixture
`viewer/src/__fixtures__/transport_bundle.json` (built by
`scripts/build_transport_fixture.py`).

## Turn and phase convention

Turn `T` runs while `world.turn == T`. Everything it records carries `T`:
`Event.turn`, `NamedEvent.turn`, `GreatPerson.born_turn` and `death_turn`,
`GreatPersonDeed.turn`, a memory's `turn`, a bond's `formed_turn`, an
artifact's `origin_turn`. When the turn ends `world.turn` becomes `T + 1`
and the snapshot taken then is labelled `TurnSnapshot.turn == T + 1`. So
snapshot `S` holds the state after turn `S - 1`, the state at the start of
turn `S`.

`historical_context.AsOf(turn, phase)` names a point:

| point | knows records dated | its snapshot |
| --- | --- | --- |
| `AsOf.after(T)` (`Phase.END`) | `<= T` | `T + 1` |
| `AsOf.before(T)` (`Phase.START`) | `<= T - 1` | `T` |

Both reduce to `AsOf.completed`, the last completed turn. The snapshot used
is the latest labelled `<= completed + 1`, never a later one
(`snapshot_as_of`). Readers:

| reader | point |
| --- | --- |
| curated narration of a moment covering turns `a..b` | `AsOf.after(b)` |
| a curator gap covering turns `a..b` | `AsOf.before(a)` to `AsOf.after(b)` |
| the "BEFORE this moment" summary | `AsOf.at_snapshot(anchor)` |
| the viewer at scrubber turn `T` (rankings, inspector) | snapshot `T`: `AsOf.at_snapshot(T)` |
| a live `turn` message after turn `T` | snapshot `T + 1`: `AsOf.after(T)` |

`HistoricalRecord` indexes a run's record once (snapshots, events, great
persons, the world, and the agent bridge's values); `record.view(as_of)`
returns an immutable `HistoricalView`: the snapshot, the great persons born
by then (`CharacterAsOf`, frozen, read-only mappings), and lookups for
Gini, displacement, trade dependency, settlements, relationships, dynasties
and artifacts.

**Observations.** Some inputs are not dated records but observations taken
when the record was read, normally after the last turn: a person's needs,
arc phase and summary, memory intensities, bond sentiments, final role and
civilization; the bridge's Gini, displacement and trade dependency; an
artifact's holder and owner; the dynasty registry's flags.
`observed_through` is the completed turn they describe (by default the
world's last completed turn). A view uses them only when its completed turn
is at or after that turn. Before it:

* a person is listed only once born; their status is `active` until their
  recorded end (`death_turn`, or for an exile or ascension without one, the
  last dated deed); deeds, memories and bonds are those dated by then;
  undated (legacy string) deeds are left out;
* memories keep only those whose final intensity is at least "fading"
  (intensities only decay, so they were at least that strong); "vivid" is
  said only when the final value is vivid, "fading" never;
* bonds formed by then and dissolved later (`dissolved_edges_by_turn`) are
  live bonds then; sentiment is left out;
* a hostage is a hostage only from the dated `hostage_taken` event naming
  them; before it they have their former role and civilization (latest
  dated deed, else origin);
* dynasty counts are of members born by then; a split is the dated
  `dynasty_split` event;
* needs, arc phase/summary, displacement and trade dependency are left
  out; Gini is the snapshot's;
* settlements are the snapshot's (`active_settlements` and
  `region_control`), not the final world's;
* artifacts are those made by then and still standing at the end, found by
  their maker and place of making and described as "made in R by X".

Future information appears only in sections the prompt labels as such:
"AFTER this moment (for foreshadowing)" and "LATER CONSEQUENCES recorded by
the simulation (after these turns)". Views never carry it. Characters'
memory choice among past memories still ranks by final intensity (the
content is past; only the order uses the later value).

`build_agent_context_for_moment` without a `view` (direct callers) builds
one from its arguments with `observed_through=None`: the caller vouches
that the values describe the moment, as a per-turn caller would; the dated
filters still apply.

## Transport contract

`src/chronicler/transport_contract.json` is the single list. Python reads
it in `chronicler/transport.py`; the viewer imports the same file in
`viewer/src/lib/transport.ts` (Vite resolves the import; `tsc -b` accepts
it).

* `snapshot_fields`: the `TurnSnapshot` fields every snapshot has;
* `snapshot_systems`: its optional per-system summaries (`campaign`,
  `contact`, `epidemics`, `finance`, `diplomacy`, `techniques`, `maritime`,
  `gp_agendas`, `nomads`, `cities`, `agent_movements`, `guilds`, `food`,
  `migration`);
* `bundle_systems`: `historiography`, `languages`;
* `bundle_carriers`: `pruned_civ_stats`;
* `turn_message_keys`: what a live `turn` message adds (`type`,
  `chronicle_text`, `events`, `named_events`).

Paths: a static upload decodes the file; the Batch Lab's `batch_load_bundle`
validates it (`live._validate_legacy_live_bundle`, which now keeps the
bundle systems) and sends `bundle_loaded`; streaming sends an `init` and one
`turn` message per turn (each row built from the contract's fields by
`snapshotFromMessage`, so `guilds` and every later system arrive) and, at the
end, `completed` with `systems` (the run's historiography and languages,
read from the written bundle); a reconnect `init` carries the history rows
(the server strips turn-message keys) and the bundle systems.
`tests/test_historical_parity.py` checks the lists against `TurnSnapshot`
(adding an optional snapshot field without listing it fails) and the Python
adapters against the fixture; `useLiveConnection.parity.test.ts` drives the
static, Batch Lab, streaming and reconnect paths with the same fixture and
compares every snapshot key and bundle system with the static upload.

Live range narration and `--narrate BUNDLE` read a bundle-shaped dict the
same way (`narration_inputs.from_bundle`): the restored history, the world,
the great persons (living with an agent id, dead or retired with a recorded
end), the curator's named characters and arc map, and the in-world indexes.
Live range narration now gets the world (artifacts, belief names, the
event timeline for later consequences and food crises) and the curator's
arc map; a live session world that does not validate is skipped with a
warning.

## Live server authentication

The server still binds to `localhost`. A WebSocket handshake is accepted
only when:

1. its `Origin` is an allowed viewer origin: `http://localhost`,
   `http://127.0.0.1` or `http://[::1]` on port 5173 (`npm run dev`) or 4173
   (`npm run preview`), plus each `--live-origin ORIGIN` (repeatable) for a
   viewer served elsewhere. A request without `Origin` (browsers always send
   one) is a local non-browser client and still needs the token;
2. its URL query carries this session's token (`?token=...`), compared in
   constant time. The token is `secrets.token_urlsafe(18)`, new per server.

Anything else gets HTTP 403 before the upgrade, so no `init` (world state)
or command reaches it. The token gates the whole control protocol: start,
batch, narration, pause commands.

Launch flow (unchanged steps): `chronicler --live` prints

```
Lobby ready on ws://localhost:8765 (session token required)
Open viewer: http://localhost:5173/?ws=ws://localhost:8765&token=<token>
```

Open that link with the viewer's dev (or preview) server running. The
viewer reads `ws` and `token` from its URL and opens
`ws://localhost:8765/?token=<token>`; reconnects reuse it. An old link
without the token is refused; after two refused attempts the viewer shows
"Could not connect to the live server..." with this hint. A viewer on
another port (Vite picked 5174 because 5173 was busy) needs
`--live-origin http://localhost:5174`.

## Malformed version-6 bundles

Both codecs check every `history_delta` patch against the format and raise
`BundleDecodeError` (Python: a `ValueError`) naming the snapshot and the
problem: `~l` must be a list of `[index < length, patch]`, `~n` a length up
to the list's, `~t` a list, `~d` existing keys, `~o` the object's keys once
each, `~r` alone; list keys never in an object patch, reserved keys never
against a scalar; `history_delta` a list of objects. Valid bundles decode
as before. The viewer's loader turns the error into the diagnostic
`INVALID_HISTORY_DELTA` ("Invalid bundle history: history_delta[3]: ...");
`useBundle` ends the loading state in `finally` whatever fails. Live mode's
`batch_load_bundle` reports it as `batch_error` "Failed to load bundle:
...".

## Findings

Each reproduced on `fc01d6e` (tests in `tests/test_historical_parity.py`,
`tests/test_historical_parity_processes.py` and the viewer tests below
failed there).

1. **Future people and deeds in narration: reproduced.** A turn-10 moment
   of civ A listed `General Borun (A) [active]` born at turn 300, a deed of
   turn 400, a memory of turn 420, a rival bond formed at turn 350 and the
   final needs; a general who died at turn 200 was left out. On a real
   500-turn hybrid bundle (seed 42) re-narrated with `--narrate`: 14
   moments listed characters, with 40 deed, memory or relationship lines
   dated after the moment and 5 characters shown dead or retired before
   their recorded death; after: 0 and 0. The live and `--narrate` paths
   rendered "Displacement: 0%" for every moment without any bridge value.
2. **Curator gaps: both reproduced.** A population change made during a
   gap's last turn was missing from its summary (`stat_deltas == {}`);
   `stat_deltas` key order followed the set's hash order: the summary's
   bytes differed under `PYTHONHASHSEED` 1, 2 and 3.
3. **Viewer future civ statistics: reproduced.** A civ first recorded at
   turn 61 had a chip at turn 1 and, selected, showed the end-of-run leader
   and values with status "Not yet founded".
4. **Live/static parity: reproduced.** Streaming dropped `guilds` (and any
   field not in the hand-written list); `batch_load_bundle` and the
   reconnect `init` dropped `historiography` and `languages` (Python), and
   the viewer's live `init` dropped them again; live range narration got no
   world.
5. **Any WebSocket origin: reproduced.** `Origin: https://untrusted.example`
   with no token received the lobby `init`.
6. **Malformed v6 deltas: reproduced.** In the viewer a non-list `~l`
   threw inside the file reader's handler, leaving `loading` true with no
   error; an out-of-range index or a key order naming a missing key loaded
   silently with holes. In Python the same patches raised `IndexError`,
   `TypeError` or `KeyError`, and a non-list `history_delta` or a list
   snapshot decoded without error.

## Identity

Python 3.13.17 without the native extension (`chronicler_agents` absent),
`PYTHONHASHSEED=0`, `main` `fc01d6e` source on `PYTHONPATH` against this
branch, same interpreter and arguments.

* `--simulate-only --agents off`: template seeds 42, 7, 1234 (200 turns)
  and a procedural world seed 11 (80 turns): all 36 files byte-identical;
  the bundles (only `metadata.generated_at` replaced) hash
  `3b2c199c…10e8`, `2f244c57…f1ee`, `a546fafd…d347` and `b573337f…12e2` on
  both sides.
* `--narrator mechanical --agents off`, seeds 42 and 7 (200 turns):
  everything but the narration identical (`scripts/narration_identity.py
  compare`: 8 files each); `chronicle.md`, chronicle entries and gap
  summaries identical (these runs' moments tile the timeline, so every gap
  is empty). Prompts: 32 of 34 and 33 of 34 differ, in the artifact lines
  (made by then and described by their making) and the era register of 3
  moments (read from the snapshot after the moment).
* `--narrate` of a saved 500-turn hybrid bundle (seed 42, `--narrator
  mechanical`): chronicle entries identical; 17 of 49 gap summaries change
  values (the gap's last turn counts), all gap civs in name order; all 50
  prompts change: the displacement line is gone (no bridge value), deeds,
  memories, relationships and arc phases dated or observed later are gone,
  5 character statuses and 1 mule window are those of the moment, the
  settlements and urbanisation trend are the snapshot's, artifacts are
  described by their making.

Narrated bundles therefore change in `gap_summaries` (values where a gap
had a last-turn change; key order) and, with an LLM narrator, in prose
following the prompt changes above. No simulation output changes.

## Tests

* Python: `tests/test_historical_parity.py` (in the oracle lane's
  `narration` chunk) and `tests/test_historical_parity_processes.py` (hash
  seeds in child processes; origin and token over real sockets; outside the
  lane, which blocks both). `tests/test_live_integration.py` connects with
  the session token.
* Viewer: `lib/__tests__/transport.test.ts`,
  `lib/__tests__/bundleCodecMalformed.test.ts`,
  `hooks/__tests__/useLiveConnection.parity.test.ts`,
  `hooks/__tests__/useBundleMalformed.test.ts`,
  `components/phase75/__tests__/AppShell.founding.test.tsx`.
* Results: `python scripts/run_python_oracle_checks.py` PASS in 126.2 s
  (narration chunk 139 passed); the 25 narration, history, live, codec,
  bundle and main test files (including the two above and
  `test_live_integration.py`) 654 passed, 4 skipped; viewer `npm test --
  --maxWorkers=2` 352 passed in 44 files (303 in 39 on `fc01d6e`), `npm run
  lint` and `npm run build` pass.
* Entry chunk 777,454 -> 780,900 bytes (gzip 228,757 -> 230,110).

## Not done

* No native build and no hybrid run: the hybrid evidence re-narrates a
  bundle written by an earlier `main` build; the inline (end-of-run) API
  narration with live bridge values is covered by unit tests only. No LLM
  was called; prose quality is untested.
* No simulation gate (none needed: no simulation change).
* Viewer: the overview snapshot selector still shows the first snapshot
  when the scrubber precedes the history; other panels (systems tabs,
  languages) were not audited for end-of-run values beyond the civilization
  views; no browser QA.
* Final great-person fields with no dated record (the role and civilization
  an exile ends with, an ascension without a deed) are inferred from the
  last dated deed or left out; the record does not date every lifecycle
  change, so an exile who returned shows as active throughout.
* The curator's own scoring still uses the final active characters and arc
  map (it selects which moments to tell; it puts nothing in a prompt).
* Live streaming sends `historiography` and `languages` only at completion
  (they are exported after the run); a viewer reconnecting mid-run gets
  them then.
* Token and origin checks protect the WebSocket only; anything else on the
  machine that can read the CLI output or the viewer URL has the token.
