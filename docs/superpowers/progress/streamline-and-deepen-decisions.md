# Streamline and deepen — owner decisions (2026-11-08)

On 2026-11-08 the owner accepted the recommendations for DEC-1 to DEC-8, in their own words: "Pls do recs for decisions I have no idea on this stuff just want it to be good". In the same answer they gave the go-ahead for the four corrections that need no design decision: COR-6, COR-7, COR-9 and COR-10.

Where a decision record left a sub-choice open, the lead session chose the option that changes no outcome, or the one the spec recommends. Those choices are marked **(lead)**. The owner can reverse any of them; each one names the task it affects.

| ID | Decision | Applies to | Spec |
|---|---|---|---|
| DEC-1 | **Option A: freeze the witness lane.** The owner signs the spec's six points. (1) Option A. (2) Byte-level review provenance for the ~91 witnessed files is no longer machine-enforced; the PIN-2 identity gate replaces it as the required check. (3) The ~2.75 MB of frozen copies under `tests/fixtures/frozen_pin_sources/` are never edited. (4) The freeze base is the last `main` commit before PIN-1 merges. (5) AGENTS.md and DEVELOPMENT.md wording changes in PIN-1 PR 3. (6) "Never rewrite a pinned hash" now covers fixtures and frozen copies. | PIN-2, PIN-1, then DEAD-5, FIX-1, FIX-3, FIX-10, FIX-11, CON-1, CON-3–CON-7, CON-10, CON-11, COR-5, COR-8, DEP-1–DEP-4, DEP-5, DEP-6, DEP-8 | [pin-policy](../specs/2026-11-08-pin-policy-transition-design.md) |
| DEC-2 | **Declare the 17 default-on systems the production core,** in one registry shared by the CLI, live, catalog and batch paths (CON-1). **(lead)** Governance and fisheries stay on by default, so no default outcome changes. New live worlds follow the CLI defaults (COR-2: governance on). Each system's qualification status and open calibration (for example fisheries `[CALIBRATE]`) is listed beside its registry row. A "classic" profile (DEP-8) covers runs that want them off. | CON-1, COR-2, DEP-8 | [rng-and-defaults](../specs/2026-11-08-rng-and-defaults-design.md) |
| DEC-3 | **Sign off one aggregate RNG hygiene correction** (COR-1): a `system_rng` helper, the seeded EXPAND draw, additive-seed collisions fixed, food-good iteration fixed to the seed-0 order, set-order float sums, and a PYTHONHASHSEED sweep test. Then relax `what_if.require_hash_seed`. The correction ships with a new baseline. **(lead)** Key per-civ streams by the civilization's index in `world.civilizations` (the AGENTS.md identity rule), unless the COR-1 analysis shows a name is required for saved-world stability; record the choice in the PR. | COR-1, DEP-9 hash-seed sweep | [rng-and-defaults](../specs/2026-11-08-rng-and-defaults-design.md) |
| DEC-4 | **Provenance must not decide outcomes.** Move each of the seven decision reads onto simulation state, one PR each, each with a before/after baseline. | COR-5 | [behaviour-corrections](../specs/2026-11-08-behaviour-corrections-design.md) |
| DEC-5 | **New public-health enables default to `density_only` crowding.** Saved worlds keep `legacy_displacement`. Documented as a correction. | COR-4 | [behaviour-corrections](../specs/2026-11-08-behaviour-corrections-design.md) |
| DEC-6 | **Move, not delete,** the detached harness modules to the sibling package `src/chronicler_lab/`. Sub-decision A: keep `validation_compare` and `community_admissibility` in `chronicler`, so the lab set is 27 modules. Sub-decision B: the shims live until the first tagged release after LAB-1 PR 6; PR 7 then deletes them. No `DeprecationWarning`. | LAB-1 | [lab-package-relocation](../specs/2026-11-08-lab-package-relocation-design.md) |
| DEC-7 | **Duplicate models.** Keep the legacy war model only as the `--no-campaigns` kernel for old saved worlds. Era-advance cost: **(lead)** option A, keep both rules and document them, so no default-path outcome changes; COR-3 is then only the `capability_scholarship` emit-order fix and the shared multiplier constant. Keep the Python ecology copy as the `--agents off` tick and oracle. Delete the unreachable Python relationship-formation fallback (CON-11). Generate shared constants from one source (CON-5). | COR-3, CON-11, CON-5 | [behaviour-corrections](../specs/2026-11-08-behaviour-corrections-design.md), [turn-loop](../specs/2026-11-08-turn-loop-consolidation-design.md) |
| DEC-8 | **(a) Raw run output may leave HEAD,** with a per-file SHA-256 manifest and a release asset as the retrievable copy. **(b) Host:** a GitHub release on this repository (tag `evidence-2026-11`). **(c) No history rewrite.** Evidence JSON that tests read stays in place. This session has no tool to create a release, so the upload is an owner action. The originals are removed (`git rm`) only after the asset exists and its hashes are verified. | HYG-7 | [repo-hygiene](../specs/2026-11-08-repo-hygiene-design.md) |

## Corrections approved to start

Each runs one at a time in its own PR, with a before/after baseline, two independent reviewers and a CONTINUATION entry. None is batched with a refactor.

- **COR-6, war event and casualty accounting.** All three parts are approved. (a) Flush events and losses on the early returns. (b) **(lead, spec recommendation)** Soldiers die only if people were drained. (c) **(lead)** Add `Army.natural_deaths` and book roster losses there, so "destroyed" versus "demobilized" verdicts reflect combat deaths. Part (c) changes those verdicts and the change must be visible in the baseline report.
- **COR-7, politics step 11.** Option B: delete the Rust step 11. Python output stays byte-identical; the FFI enum variant is kept.
- **COR-9, Rust `stable_hash_int` repr parity with Python.**
- **COR-10, the `gp_agendas` projected treasury respects the accumulator watermark.**

## Scope rulings made by the lead under the owner's delegation

- **FIX-7, livelihoods CLI acceptance (2026-11-09).** The implementer found that the plan's stricter checks would refuse behaviour that existing tests document as supported (spec section 8 questions).
  - **Kept.** Saved-world prerequisite checks: a switch that is on only in the saved world is refused when its prerequisites are missing, with the "pass --no-<x> to end it" message. Two fixtures that saved a workshops world without cities are made realistic. Tests that end a prerequisite while a dependent switch stays saved now end the dependent too.
  - **Dropped.** (1) Refusing a mode that differs from the saved one: changing a mode on resume stays supported, as the household-retail, recovery-crews and recovery-skills tests document (for example record_only to retail). (2) Refusing a mode given without its switch: "a mode alone does nothing" stays the documented protocol.
  - The owner can ask for either dropped part later. Each is a separate small change.

- **Wave-4 implementer questions (2026-11-09).**
  - **CON-6cd, `tick_economy` keyword.** The unused third parameter keeps its Python keyword name `season_id`. PyO3 exposes Rust parameter names as keywords, so a rename would break `season_id=` callers (lead fix `b07777d9`).
  - **FIX-10 follow-ups (new task FIX-15).** (1) When the live server cannot start, `main` exits with a non-zero status. (2) A live `batch_start` scenario name is resolved under `scenarios/` as the lobby resolves it, refusing names outside it. Both are fixes to the live entry points; no simulation outcome changes. The deferred reconnect-state merge and `client_lock` items stay deferred.
  - **CON-1, import guards (follow-up CON-1g).** The AST guards in `test_languages.py` and `test_historiography.py` are widened to also flag by-name module access through `importlib`. `switch_defaults.py` is the one allowed registry.
  - **COR-5.2, famine onset predicate.** The plan's rule applies: a crisis report counts as an onset when the region is not already in `famine_cooldown`. COR-5.5 reuses it.
  - **Out of scope.** Inlining `DEMAND_SCALE_FACTOR` (scout 01 finding 11) has no decision and is not done.

## Not decided here

- Promotion of any default-off feature still needs the 200-seed gate and a separate owner approval.
- Opening pull requests and pushing to branches other than the lead's own still need the owner.
- The ENV-5 to ENV-7 workstation tasks wait for the owner's machines.
