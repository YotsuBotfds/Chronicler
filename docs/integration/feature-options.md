# Feature options in Batch Lab and live new-world setup

Lane RS6 of the recovery and skills phase. Batch Lab and the live setup form can
request the experimental livelihoods switches and the prerequisites they depend
on. Nothing is selected by default. A request with no `features` field behaves
exactly as before.

Source:

- `src/chronicler/feature_catalog.py`: the catalog and the validation.
- `src/chronicler/live.py`: lobby message, `start` and `batch_start` validation,
  forwarding.
- `viewer/src/lib/featureCatalog.ts`: the strict reader and the selection rules.
- `viewer/src/components/FeatureOptions.tsx`: the section.

Tests: `tests/test_feature_catalog.py` (offline chunk `feature-options`) and the
viewer tests `featureCatalog.test.ts`, `FeatureOptions.test.tsx` and
`FeatureRequests.test.tsx`.

## The catalog

`lobby_feature_catalog(args)` is sent as `feature_catalog` in the lobby `init`
message (`{"type": "init", "state": "lobby", ...}`). The UI and the server read
the same catalog, so they cannot drift. Its shape (`schema_version` 1):

| Field | Meaning |
| --- | --- |
| `features[]` | One entry per CLI parser destination. Fields: `key`, `flag`, `label`, `help`, `kind` (`bool` or `choice`), `choices` (a mode's choices, the first being the run's default once its switch is on), `default` (always `null`: not forwarded), `parent` (the switch a mode belongs to), `requires`, `group` (`Livelihoods` or `Prerequisites`), `experimental`. |
| `settings` | Server settings a request cannot change (`cities`, `techniques`, `no_household_mobility_liquid_requirement`), with what each means. |
| `surfaces.live`, `surfaces.batch` | What a request inherits on that surface: `agents`, `agent_modes` (just the server's mode for live; all four for Batch Lab), `values` (catalog keys the server's command line already sets), `settings` (true or false), `new_worlds_only`. |

Where the entries come from:

- **Livelihoods.** The entries are generated from the registry:
  `LIVELIHOODS_SWITCHES`, `LIVELIHOODS_ARG_KEYS` (a mode belongs to the switch
  declared before it), `LIVELIHOODS_CHOICES` and `_HELP`. A switch added to the
  registry appears in the catalog on its own.
- **Prerequisites.** These are listed in `PREREQUISITES`: `grain_reserves`,
  `public_grain_shipments`, `grain_storage` (with `grain_storage_policy`),
  `scholarship` and `academy_services`.
- **Flags, help and choices.** These are read from the CLI parser itself.

Each requirement is an object with a `reason`. It is one of:

- `{"agents": [...]}`
- `{"feature": key}`
- `{"choice": key, "values": [...]}`: the mode, or its first choice when unset,
  is one of these values.
- `{"setting": name}`
- `{"any": [...]}`

`REQUIREMENTS` declares them for every boolean entry. A mode requires its switch.

## Agreement with the run's own checks

The run's checks stay authoritative: `livelihoods._check_prerequisites` and the
prerequisite checks in `main._configure_run`. `REQUIREMENTS` is a declaration,
and a test holds it to those checks.

`test_catalog_requirements_agree_with_the_run` checks every boolean entry. For
each one it builds the smallest selection the catalog accepts. It then varies
that selection:

- every agent mode;
- each prerequisite dropped;
- each mode value of each selected switch;
- each setting flipped.

That makes 135 selections. Each one runs through the real configuration path
twice: the CLI and batch path (`_configure_run` on a new world) and the live
path (`_live_world` and then `_configure_run`). The agent bridge and ecology
runtime are replaced by a sentinel that marks "accepted". The catalog's verdict
must equal the run's verdict on every case.

`test_agreement_check_detects_wrong_declarations` shows that the check catches
a missing requirement, an invented one and a wrong agent mode.
`test_every_boolean_feature_declares_requirements_over_known_terms` fails when a
registry switch has no declared requirements. This is deliberate: when a new
switch is merged, add its row to `REQUIREMENTS`.

The server is stricter than the CLI in one place. It refuses a mode requested
without its switch, because on a new world that mode would have no effect. The
CLI accepts and ignores such a mode.

## Requests and validation

Both surfaces accept an optional `features` object, `{key: true | false |
"choice"}`. It goes in the `start` message for live and in `batch_start.config`
for Batch Lab.

`validate_features` refuses the request before anything starts when:

- `features` is not an object;
- a key is not a catalog key;
- a value has the wrong type: switches must be booleans (not `1` or `"true"`),
  and modes must be one of their choices;
- a requirement is unmet for any feature that is on, whether requested or
  inherited from the server's command line.

An agent-mode failure names the mode the run would use. For example:
`'workshops' (--workshops) requires --agents hybrid (this run uses --agents off)`.

On top of that:

- **Live `start`.** The surface is the server's command line
  (`LiveServer.feature_args`, set by `run_live`). `features` cannot be combined
  with `resume_state`, because options apply to new worlds only. A refusal is an
  `error` reply, and the server stays in the lobby.
- **Batch Lab.** The surface is the config's `agents`, or else the server's.
  The server's prerequisites come from `_client_defaults` and the config, in the
  same lookup the batch worker uses. A key may not appear both in `features` and
  at the top level of the config. A refusal is a `batch_error`, and no thread
  starts.

## Forwarding

Requested values are set on the run's namespace by `feature_catalog.apply_features`,
exactly as the CLI parser sets them. `feature_cli_arguments` gives the
equivalent flags, and the tests compare the two.

- **Batch Lab.** The values are set on the batch worker's namespace. Every child
  run copies that namespace.
- **Batch manifest.** `batch_manifest.json` records them through
  `simulation_config`. Livelihoods and prerequisite keys are recorded only when
  they are not None.
- **Live.** The values are set on the CLI namespace before `_live_world`, so the
  world, `execute_run` and checkpoints (`simulation_config`) all see them. If the
  run still refuses the requested switches with a `ValueError`, the server
  reopens the lobby with an `error` naming the reason, and the namespace is
  restored. A refusal without `features` fails the run, as it did before.

## Correction: live worlds and their prerequisites

Before this change, `_live_world` applied the expansion and livelihoods switches
before `--academy-services`, `--grain-storage` and `--public-grain-shipments`.
Those three were applied later, in `execute_run`. As a result,
`--live --learning-cohorts` and `--live --grain-convoys` were always refused,
even with their prerequisites given.

`_apply_live_prerequisites` now applies those three first, with
`_configure_run`'s own checks. `execute_run` applies them again, and each setter
keeps the state it already applied. Without those flags, the world is unchanged.
The agreement test's live path covers this, and it fails if the helper is
disabled.

## Viewer

"Experimental features (off by default)" is a collapsible section in:

- Batch Lab (`BatchPanel`);
- the shell's setup form (`phase75/SetupRail`, the live new-world setup in use);
- the legacy `SetupLobby`.

How the section behaves:

- **Hidden** when the server sent no catalog (an older server).
- **A notice** when the catalog is malformed. The reader refuses missing or
  mistyped fields, unknown requirement kinds and unknown referenced keys. A
  missing surface setting counts as unknown, not false.
- **Switches** are checkboxes. A switch whose requirements are unmet is disabled,
  with the reason in its description.
- **Modes** are a select shown only while their switch is on. The run's default
  choice is marked, and only a non-default choice is sent.
- **Dropping a prerequisite** drops whatever depends on it.
- **Batch Lab** also offers the runs' agent mode. It is sent as `agents` only
  when changed.
- **Summary.** The section lists the selected flags and any values the server's
  command line already sets.
- **Resumed saves.** While a saved world is loaded, the section is disabled with
  a note, and no `features` are sent.
- **Phone width.** Text and selects wrap.

`viewer/src/__fixtures__/featureCatalog.json` is the catalog for
`--live --agents hybrid`. `test_viewer_fixture_has_the_shape_the_server_sends`
checks its shape. To regenerate it:

```sh
PYTHONPATH=src python -c "import json; from chronicler.main import _build_parser; \
from chronicler.feature_catalog import lobby_feature_catalog; \
print(json.dumps(lobby_feature_catalog(_build_parser().parse_args(['--live', '--agents', 'hybrid'])), indent=2, ensure_ascii=False))" \
> viewer/src/__fixtures__/featureCatalog.json
```

## Limits

- Only boolean and choice options are offered. `--grain-storage-work-budget` and
  `--household-mobility-liquid-requirement` (numbers) are not. The mobility
  requirement is a server setting the live surface reports.
- The live agent mode is the server's `--agents`. Batch Lab can change it per
  batch. Hybrid runs still need the native extension.
- Other expansion switches (health care, harvest forecasts and others) are not
  in the catalog. Batch Lab still accepts them at the top level of the config,
  as before.
- Offering a switch does not qualify it. The switches remain experimental and
  default off.
