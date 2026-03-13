# M8: Custom Scenarios — Design Spec

## Overview

Custom scenarios let users define worldbuilding setups in YAML that override the default `generate_world` pipeline. The scenario file is a creative artifact — comments welcome, most fields optional, sensible defaults inherited from the generator. One new module (`scenario.py`), one new CLI flag (`--scenario`), three template files, zero changes to the simulation engine.

## Scenario File Format

YAML with all fields optional except `name`. The file is an override layer on top of `generate_world` output — anything unspecified stays as generated.

### Top-level fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `name` | str | **required** | Scenario metadata (not used in chronicle) |
| `description` | str | `""` | Author's design notes |
| `world_name` | str \| None | None | Chronicle header name. Falls back to generated `world.name` |
| `seed` | int \| None | None | Overrides CLI `--seed` |
| `num_civs` | int \| None | None | Auto-expands if fewer than `civilizations` list length |
| `num_regions` | int \| None | None | Auto-expands if fewer than `regions` list length |
| `num_turns` | int \| None | None | Overrides CLI `--turns` |
| `reflection_interval` | int \| None | None | |
| `regions` | list[RegionOverride] | `[]` | Named region injections |
| `civilizations` | list[CivOverride] | `[]` | Named civ injections |
| `relationships` | dict[str, dict[str, str]] | `{}` | Sparse, auto-symmetrized |
| `event_probability_overrides` | dict[str, float] | `{}` | Merged on top of defaults |
| `starting_conditions` | list[ConditionConfig] | `[]` | Injected at turn 0 |

### RegionOverride

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | str | yes | Identity key |
| `terrain` | str \| None | no | |
| `carrying_capacity` | int \| None | no | 1-10 |
| `resources` | str \| None | no | |

### CivOverride

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `name` | str | yes | Identity key |
| `population` | int \| None | no | 1-10 |
| `military` | int \| None | no | 1-10 |
| `economy` | int \| None | no | 1-10 |
| `culture` | int \| None | no | 1-10 |
| `stability` | int \| None | no | 1-10 |
| `treasury` | int \| None | no | >= 0 |
| `asabiya` | float \| None | no | 0.0-1.0 |
| `tech_era` | str \| None | no | Valid TechEra value (tribal, bronze, iron, classical, medieval, renaissance, industrial) |
| `domains` | list[str] \| None | no | |
| `values` | list[str] \| None | no | |
| `goal` | str \| None | no | |
| `leader` | LeaderOverride \| None | no | |

### LeaderOverride

| Field | Type | Required |
|-------|------|----------|
| `name` | str \| None | no |
| `trait` | str \| None | no |

### ConditionConfig

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `type` | str | yes | Maps to `ActiveCondition.condition_type` |
| `affected` | list[str] | yes | Maps to `ActiveCondition.affected_civs` |
| `duration` | int | yes | >= 1 |
| `severity` | int | yes | 1-10 |

### Relationship rules

- Dispositions are strings: hostile, suspicious, neutral, friendly, allied
- Auto-symmetrized: setting A->B fills in B->A if not explicitly set
- Explicit always wins over auto-symmetry — if both A->B and B->A are specified, both are honored even if asymmetric
- Only specified pairs are overridden; all other pairs stay as generated

### Example scenario file

```yaml
# Post-Collapse Minnesota — three factions in the river valleys
name: Post-Collapse Minnesota
description: Agricultural co-ops, a militarized highway authority, and university holdouts
world_name: The River Valleys

seed: 314
num_civs: 4        # 3 defined + 1 generated filler
num_regions: 6
num_turns: 80

regions:
  - name: Willmar
    terrain: plains
    carrying_capacity: 9
    resources: fertile
  - name: Benson
    terrain: plains
    carrying_capacity: 7
    resources: fertile

civilizations:
  - name: Farmer Co-ops
    economy: 8
    culture: 4
    stability: 7
    tech_era: iron
    domains: [agriculture, community]
    values: [Solidarity, Harvest]
    leader:
      name: Elder Johansson
      trait: cautious
  - name: Highway Authority
    military: 8
    economy: 5
    tech_era: iron
    domains: [warfare, commerce]
    leader:
      trait: aggressive
  - name: Carleton Enclave
    culture: 9
    economy: 3
    tech_era: classical
    domains: [knowledge, arcane]

relationships:
  Farmer Co-ops:
    Highway Authority: hostile
    Carleton Enclave: friendly
  Highway Authority:
    Carleton Enclave: suspicious

event_probability_overrides:
  drought: 0.12
  rebellion: 0.08

starting_conditions:
  - type: drought
    affected: [Farmer Co-ops]
    duration: 3
    severity: 4
```

## Architecture

### New module: `src/chronicler/scenario.py`

Three functions:

#### `load_scenario(path: Path) -> ScenarioConfig`

Read YAML file, validate with Pydantic. Raises `ValueError` with clear messages on validation failures.

**Validation rules (on load):**
- `name` is required and non-empty
- `num_civs` (if set) >= number of `CivOverride` entries
- `num_regions` (if set) >= number of `RegionOverride` entries
- `tech_era` strings must be valid TechEra enum values
- `severity` in 1-10, `carrying_capacity` in 1-10, `duration` >= 1
- Stats (population, military, economy, culture, stability) in 1-10 if provided
- `treasury` >= 0 if provided
- `asabiya` in 0.0-1.0 if provided
- `event_probability_overrides` values in 0.0-1.0, keys must exist in `DEFAULT_EVENT_PROBABILITIES` (the 10 standard event types from `world_gen.py`: drought, plague, earthquake, religious_movement, discovery, leader_death, rebellion, migration, cultural_renaissance, border_incident). Note: M7 cascade types (tech_advancement, coup, legacy, rival_fall) are NOT valid override targets — they're generated by simulation mechanics, not rolled for. The validation error message should explain this distinction to avoid confusing scenario authors.
- Effective `num_regions` >= effective `num_civs` (every civ needs at least one region)
- Relationship disposition strings must be valid Disposition enum values
- Civ names in `relationships` and `starting_conditions.affected` that reference scenario-defined civs are checked; references to filler civs get a warning (names unknown until generation)

#### `apply_scenario(world: WorldState, config: ScenarioConfig) -> None`

Mutates world in-place after `generate_world` has run. The override-only flow:

1. **Region injection:** For each `RegionOverride`, find the next unreplaced generated region. Record the old region name. Copy the generated base (preserving all fields), overwrite non-None fields from the override, set the new name. Update any `civ.regions` list entries that referenced the old region name to the new name.

2. **Civ injection:** For each `CivOverride`, first check if the override name matches an existing generated civ name — if so, patch that civ in-place (name match = patch, no slot replacement needed). Otherwise, find the next unreplaced generated civ. Record the old civ name. Copy the generated base, overwrite non-None fields, set the new name. If `leader` override exists, patch leader fields (name, trait) on the existing leader object. **Critical: update `region.controller` for all regions owned by the old civ to the new civ name.** Also update relationship keys, action_history keys, and any other references to the old civ name.

3. **Num expansion:** If scenario defines more civs than `num_civs`, or more regions than `num_regions`, the world was already generated with the expanded count (handled by `resolve_scenario_params` before generation).

4. **Relationship overrides:** For each specified pair A->B, set `world.relationships[A][B].disposition`. Auto-symmetrize: for each A->B, if B->A was not explicitly specified in the config, also set `world.relationships[B][A].disposition` to match. Explicit always wins — never overwrite an explicitly-set direction.

5. **Event probability overrides:** Merge `config.event_probability_overrides` into `world.event_probabilities` (dict update).

6. **Starting conditions:** Convert each `ConditionConfig` to `ActiveCondition` (mapping `type` → `condition_type`, `affected` → `affected_civs`) and append to `world.active_conditions`.

7. **World name:** If `config.world_name` is set, overwrite `world.name`.

**Post-apply validation:**
- Every civ has at least one region — error message must be specific: "Civ '{name}' has no regions — likely a controller name mismatch during injection" (catches bugs where controller name wasn't patched during civ swap)
- All relationship references point to existing civ names
- Starting condition `affected` civs all exist in the world

#### `resolve_scenario_params(config: ScenarioConfig, cli_args) -> dict`

Merge scenario params with CLI args. **CLI args win** over scenario defaults for `seed`, `num_turns`, `reflection_interval`. This lets users override scenario settings from the command line (e.g., `--turns 100` overrides `num_turns: 80` in YAML).

Auto-expand: `num_civs` = max(cli/scenario num_civs, len(config.civilizations)), same for regions.

Returns kwargs dict for `generate_world` and `run_chronicle`.

### CLI integration in `main.py`

New flag: `--scenario path/to/scenario.yaml`

`--scenario` and `--resume` are mutually exclusive. Resume loads saved state (scenario already applied); re-applying would double-patch.

Flow when `--scenario` is set:
1. `load_scenario(path)` — parse + validate YAML
2. `resolve_scenario_params(config, args)` — merge with CLI args
3. `generate_world(seed, num_civs, num_regions)` — normal pipeline
4. `apply_scenario(world, config)` — overrides on top
5. Print scenario name + description
6. Run simulation as usual

### Dependency

Add `PyYAML` to project dependencies (pyproject.toml).

## Scenario Templates

Three files in `scenarios/` directory:

### `scenarios/fantasy_default.yaml`

Minimal — wraps the default `generate_world` behavior with no overrides. Tests that the scenario pipeline is a no-op when nothing is overridden.

```yaml
name: Fantasy Default
description: Standard world generation with no overrides
world_name: Aetheris
```

### `scenarios/two_empires.yaml`

Two matched powers locked in a cold war. Stress-tests Lanchester combat, tech parity multipliers, rivalry system, and the action engine's war-heavy personality profiles.

```yaml
name: Two Empires
description: Two matched powers locked in a cold war across contested borderlands
world_name: The Divided Realm
seed: 99
num_civs: 2
num_regions: 6

civilizations:
  - name: Dominion of Ashar
    military: 7
    economy: 6
    stability: 6
    tech_era: iron
    domains: [warfare, conquest]
    leader:
      trait: aggressive
  - name: Thalassic League
    military: 6
    economy: 7
    culture: 6
    tech_era: iron
    domains: [maritime, commerce]
    leader:
      trait: calculating

relationships:
  Dominion of Ashar:
    Thalassic League: hostile
```

### `scenarios/golden_age.yaml`

Four peaceful civilizations in an era of trade and culture. Tests that the simulation can produce non-war chronicles with rich diplomatic and cultural content.

```yaml
name: Golden Age
description: Four civilizations in an era of peace, trade, and cultural flourishing
world_name: The Sunlit Lands
num_civs: 4
num_regions: 8

civilizations:
  - name: Aureate Republic
    culture: 8
    economy: 7
    military: 3
    domains: [knowledge, culture]
    leader:
      trait: visionary
  - name: Jade Consortium
    economy: 8
    culture: 6
    domains: [commerce, maritime]
    leader:
      trait: shrewd
  - name: Silverpeak Accord
    culture: 7
    stability: 8
    domains: [highland, mining]
    leader:
      trait: cautious
  - name: Verdant Communion
    culture: 7
    economy: 6
    stability: 7
    domains: [woodland, nature]
    leader:
      trait: visionary

relationships:
  Aureate Republic:
    Jade Consortium: friendly
    Silverpeak Accord: friendly
    Verdant Communion: allied
  Jade Consortium:
    Silverpeak Accord: friendly
    Verdant Communion: friendly
  Silverpeak Accord:
    Verdant Communion: friendly
```

## Testing Strategy

### Unit tests (`tests/test_scenario.py`)

**Loading:**
- Valid YAML loads into ScenarioConfig
- Missing `name` raises ValueError
- Invalid `tech_era` string raises ValueError
- Stats out of range raise ValueError
- Invalid disposition string raises ValueError
- Event probability override key for unknown event type raises ValueError
- num_civs < len(civilizations) raises ValueError
- num_regions < num_civs raises ValueError
- treasury < 0 raises ValueError
- duration < 1 raises ValueError

**Applying:**
- Civ injection replaces generated civs with correct names and overridden stats
- Unspecified fields on injected civs retain generated defaults
- Leader override patches name/trait without losing other leader fields
- Region injection replaces generated regions with correct names
- Region controller names updated when civ is renamed (critical test case per user flag)
- Civ.regions list entries updated when region is renamed
- Relationship overrides set correct dispositions
- Auto-symmetry fills missing direction
- Explicit asymmetric relationships both honored (A->B hostile, B->A suspicious)
- Event probability overrides merge correctly
- Starting conditions appear in world.active_conditions
- world_name override sets world.name
- Filler civs (generated, not overridden) remain untouched
- Post-apply validation catches civ with zero regions

**Param resolution:**
- CLI args win over scenario defaults
- num_civs auto-expands to fit scenario civs
- --scenario and --resume mutually exclusive

### Template tests

- Each template loads without validation errors
- Each template runs 10 turns with stub narrator, no crashes
- Turn-0 state matches: civ names, overridden stats, relationship dispositions, starting conditions present
- Two Empires: both civs hostile, both iron era, correct military stats
- Golden Age: all relationships friendly/allied, high culture stats
- Fantasy Default: world is valid, effectively a no-op (no overrides to verify)

### Integration test

- Load Two Empires template, run 20 turns, verify war events occur (hostile iron-age powers with aggressive vs calculating leaders should generate wars)

## Modules Changed

| Module | Change |
|--------|--------|
| `src/chronicler/scenario.py` | **NEW** — ScenarioConfig model, load_scenario, apply_scenario, resolve_scenario_params |
| `src/chronicler/main.py` | Add `--scenario` flag, wire scenario loading into run_chronicle flow, mutual exclusion with `--resume` |
| `pyproject.toml` | Add PyYAML dependency |
| `scenarios/*.yaml` | **NEW** — 3 template files |
| `tests/test_scenario.py` | **NEW** — unit + template + integration tests |
| `tests/test_main.py` | Add test for `--scenario` CLI flag parsing |

No changes to simulation.py, models.py, world_gen.py, or any other existing module. The scenario system is purely an input layer on top of the existing pipeline.
