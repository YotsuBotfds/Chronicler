# RNG Hygiene, Live Governance Default and the Defaults Registry — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** COR-1, COR-2, CON-1 (inputs: DEC-2, DEC-3); new: COR-9 (Rust `stable_hash_int` repr parity)
> **Depends on:** DEC-3 (owner sign-off for the RNG correction), DEC-2 (what the "production core" is), PIN-1 (only for the enforced files in section 5)
> **Feeds:** DEP-8 (feature profiles), DEP-9 (hash-seed sweep CI), CON-4
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (+ scout reports 31, 32, 01, 08, 22)

## 1. Goal and scope

Change: (a) one `system_rng` helper, with the ten per-module `_rng` copies migrated onto it byte-for-byte; (b) a documented RNG correction: EXPAND seed, additive seeds, food-good iteration order, set-order float sums; (c) one registry of new-world switch defaults used by `main._configure_run` and `live._live_world`; (d) governance on for new live worlds; (e) a Rust/Python hash parity fix.

Not changed: any CLI flag, saved field or bundle shape; the default-off status of experimental systems; the choice of which systems are default-on (that is DEC-2, which this spec only frames); `politics_bridge.py:1193` (its `context_seed` is caller-supplied, not derived — unverified who supplies it, so left alone).

## 2. Current behaviour (verified)

- `utils.stable_hash_int` joins `_stable_serialize` parts (strings via `repr`, sets sorted) with `|` and takes the first 8 SHA-256 bytes big-endian (`utils.py:38-41`).
- Eleven helper copies build `random.Random(stable_hash_int(...))`. Nine have shape `(system, namespace, seed, turn, *parts)`: `war/common.py:88`, `diplomacy.py:248`, `maritime.py:412`, `guilds.py:171`, `cities.py:241`, `nomads.py:243`, `agent_movements.py:263`, `scholarship.py:165`. **Two differ** (audit treated them as the same): `gp_agendas.py:241` hashes `(f"gp_agenda.{label}", seed, turn, *parts)` with no system element, and `epidemiology.py:299` `_draw` hashes `(namespace, seed, turn, *parts)` and returns `.random()`. `war_rng` takes a `ctx`, not a world.
- EXPAND: `action_engine.py:198` `random.Random(world.turn * 1000 + civ_idx)`; the only draw is `rng.choice(unclaimed)` at `:215`. Confirmed: the world seed is ignored on the default path.
- Additive seeds (confirmed): `agent_bridge.py:2244` (`seed+turn+agent_id`), `:2275` (`seed+turn*7919+agent_id`); `simulation.py:1066` (`seed+turn+civ_idx+8888`), `:1067` (passes `seed+turn+civ_idx` to `artifacts.select_cultural_artifact_type`, which does `Random(seed)` at `artifacts.py:657`), `:2005` (`seed+turn*1013`); `emergence.py:226,257,396,514,603,650`; `religion.py:138` (`seed ^ civ_idx*2654435761`).
- `war_requisition._withdraw` iterates `FOOD_GOODS` (`war_requisition.py:183`), a `frozenset` (`economy.py:51`). Probed without `-I` (isolated mode ignores `PYTHONHASHSEED`, so `-I` probes see a random order each run): under `PYTHONHASHSEED` 0/1/2/3 on Python 3.13 the order is `salt,grain,fish,exotic,botanicals` / `botanicals,exotic,grain,fish,salt` / `grain,exotic,botanicals,fish,salt` / `salt,grain,botanicals,exotic,fish` (lead re-measurement, repeated three times for seed 0; this spec's first draft and the audit probes used `-I` and recorded random orders).
- **Audit gap:** the same frozenset feeds float sums and a draw-down loop in `economy.py:167,405,465,479` and `consume_from_stockpile` (`:483-492`, accumulating `total_consumed` in set order) on the default goods-economy path, plus `clamp_floor_loss` (`economy.py:442-450`). `war/occupation.py:45` loops over it but each good is independent (order-safe). `ALL_GOODS` has no other use.
- `what_if.require_hash_seed` (`what_if.py:224-228`) is called at `:360` and `:481`; `batch.py:122` uses `multiprocessing.Pool` with no start method.
- Defaults: `_configure_run` applies campaigns, mutual aid, fisheries, governance, ledger, epidemiology, finance, diplomacy, techniques, maritime, gp_agendas, nomads, cities, movements, guilds, scholarship, grain reserves, anchoring, domestic credit, historiography, languages in that order only when `fresh_world` (`main.py:1614-1884`), interleaved with non-default validation blocks (academy services, grain storage, shipments, mobility at `:1769-1836`). `live._live_world` repeats them in a **different order** (`live.py:1311-1438`: ledger first; fisheries, mutual aid, epidemiology last) and never sets governance (`rg governance live.py` is empty). Live passes the world in, so `fresh_world` is False in `execute_run` (`test_governance_runtime.py:~509` pins that supplied worlds keep their setting). There are 16 `DEFAULT_ENABLED_FOR_NEW_WORLDS = True` modules plus `CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS` (`war/params.py:32`) = the audit's 17.
- Live has extra gating the CLI expresses as errors: domestic credit `and finance is not None` (`live.py:1426`), epidemiology `and ledger on` (`:1438`), capacity-aware refugees defaulting False.
- Rust: `politics.rs:727` `stable_hash_int(&[&str])` just joins its inputs; call sites hand-build `'secession'|{}|{}|'{}'` (`:1377`, also `:1835`, `:2281`, `:2409`). Python uses `repr`, so a name with `'` or `\` hashes differently. **Audit claim "LE vs BE" is wrong as a bug:** `politics.rs:1147` uses LE on purpose; its Python twin `intelligence.py:208` also uses `"little"`.

## 3. Design

**3.1 `system_rng` (COR-1, refactor half).** In `utils.py`:

```python
def system_rng(namespace: str, world, *parts, system: str | None = None) -> random.Random:
    head = (system, namespace) if system else (namespace,)
    return random.Random(stable_hash_int(*head, world.seed, world.turn, *parts))
```
Each existing helper becomes a one-line wrapper (keeps its name for callers and tests). `gp_agendas`: `system_rng(f"gp_agenda.{label}", world, *parts)`; `epidemiology._draw`: `system_rng(namespace, world, *parts).random()`; `war_rng`: `system="war"`. Golden test pins that each wrapper equals the legacy expression for sample inputs.

**3.2 Corrections (COR-1).** Streams change; one documented correction, split by pin status:
- EXPAND: `system_rng("expand", world, civ.name)`. Civ identity note: `civ.name` is stable and matches the war streams; index is the alternative.
- Additive seeds become `system_rng(<unique namespace>, world, ...)`. Namespaces: `agent_name`, `agent_mule`, `artifact_gate`, `artifact_type`, `env_hazard`, `black_swan` etc. (full list in the plan). `religion.py:138` has no world; use `stable_hash_int("religion_doctrine", seed, civ_idx)`.
- Food order: a fixed tuple `FOOD_GOODS_ORDER = ("salt","grain","fish","exotic","botanicals")`, i.e. the **`PYTHONHASHSEED=0` order on the Python that produced the baselines**. The PR must re-derive it (`PYTHONHASHSEED=0 .venv/bin/python -c "import sys; sys.path.insert(0,'src'); from chronicler.economy import FOOD_GOODS; print(tuple(FOOD_GOODS))"`, never with `-I`) and pin it with a subprocess test that asserts the tuple equals the seed-0 iteration order, so a Python upgrade that changes set iteration fails loudly instead of silently moving baselines; CI and the baseline machine must use the same minor Python (3.13). Every existing baseline is produced with `PYTHONHASHSEED=0` (`scripts/turn_speed_identity.py:5`), so this part of the correction leaves all those baselines byte-identical and only changes processes run with other hash seeds. `war_requisition.py` gets a local tuple plus a test `set(order) == FOOD_GOODS` (no `economy.py` edit needed); `economy.py` sites follow after PIN-1.
- `clamp_floor_loss`: `math.fsum` over the per-good losses (order-independent). Last-bit change only, only when the clamp fires with two or more goods.

**Why this is a sanctioned exception to "preserve aggregate RNG behaviour":** AGENTS.md asks for preservation of snapshot/RNG behaviour absent an intentional correction. Four of the five changes are bugs against the project's own contract (the seed must drive the draw; output must not depend on the process). The EXPAND and additive changes alter every default-path run, so they need **DEC-3 owner sign-off**, a new baseline and a CONTINUATION entry, in PRs separate from refactors. Questions for the owner: (i) accept a new 200-seed baseline for all default runs; (ii) leave `emergence` (`seed + turn*K`) alone if the baseline cost seems too high — it is fragile, not currently colliding in observed ranges (unverified); (iii) relax `require_hash_seed`.

**3.3 Relaxing `require_hash_seed`.** Only after the sweep test passes at seeds 0..3 and the set-iteration audit (plan task) is signed off. The relaxation: children are spawned with an explicit `PYTHONHASHSEED=0`, the live server needs no flag, the POSIX check stays. Until then it stays.

**3.4 Defaults registry (CON-1).** New `src/chronicler/switch_defaults.py` (unpinned): a tuple of `SwitchDefault(name, module, setter, default, requires=(), enabled=callable, live_exempt=False, needs_agents_for_explicit=False)` in the **`main` order**. Functions: `resolve(entry, args, fresh_world)` and `apply_switches(world, args, *, fresh_world, agent_mode, names=None)`. `main._configure_run` calls it in three slices between its non-default validation blocks (so the interleaving stays); `live._live_world` calls it once with `fresh_world=True`. `requires` captures `domestic_credit -> finance`, `epidemiology -> contact_ledger`; explicit-on errors for agent-only switches stay in `main` (live never raised them). `feature_catalog._*_default` collapse to `registry.default(name)`; `batch_manifest` exclusion tuple derivation is deferred (enforced file; plan task is conditional on PIN-1).

Order risk: live moves from its order to main's. The setters write independent world fields, but `fisheries(new_world=True)` calibrates and epidemiology reads ledger state, so the refactor PR must prove live-world equality (section 6) before and after.

**3.5 COR-2.** Delete the `governance` exemption in the registry (`live_exempt`) so live follows the CLI. The refactor PR ships with `governance` exempt so the diff of the correction is one line.

**3.6 COR-9 (Rust parity).** Add `py_repr_str(&str) -> String` and make the helper take structured parts, or make call sites call it; match CPython quoting (use `"` when the text has `'` and no `"`; escape `\`, quote, `\n \r \t`, other controls as `\xNN`). Pin with digest constants generated from Python for names such as `Ka'lo`, `A\B`, `Zoë`. Non-ASCII non-printables are unverified and documented as out of scope. Outcome change only for such names.

## 4. Compatibility

Saved bundles and checkpoints: no field changes. Old checkpoints resume under new streams from the resume turn onward (documented in the ledger; exact-resume tests compare same-code runs). `FOOD_GOODS` stays a frozenset. Live: worlds created before the fix keep their saved `governance` (resume path untouched).

## 5. Pins and preflight (run on 28 paths)

Enforced source witness (need PIN-1 or an inverse layer): `simulation.py`, `agent_bridge.py`, `economy.py`, `scholarship.py`, `main.py`, `live.py`, `what_if.py`, `batch_manifest.py`.
Unpinned (reference-only hits, historical provenance): `utils.py`, `action_engine.py`, `war_requisition.py`, `war/common.py`, `diplomacy.py`, `maritime.py`, `guilds.py`, `cities.py`, `nomads.py`, `agent_movements.py`, `gp_agendas.py`, `epidemiology.py`, `emergence.py`, `religion.py`, `artifacts.py`, `politics_bridge.py`, `batch.py`, `feature_catalog.py`, `governance_runtime.py`, `chronicler-agents/src/politics.rs`.

So the plan has an **unpinned wave** (system_rng, EXPAND, war requisition, emergence, religion, artifacts, Rust) and a **pinned wave after PIN-1** (simulation, agent_bridge, economy, scholarship, main, live, what_if, batch_manifest). Registry creation itself is unpinned, but the call-site swap in `main.py`/`live.py` is pinned, so COR-2 and the registry adoption wait for PIN-1 (or an exact-inverse layer in `scripts/testing/reviewed_main_witness.py`). `tests/test_fisheries_mutual_aid_promotion.py:108` greps the source of `live`; it must become a behavioural test in the same PR.

## 6. Classification

| Piece | Class | Proof |
|---|---|---|
| `system_rng` and wrappers | refactor | golden-stream test; `turn_speed_identity` all 9 cases identical |
| Food order tuple (hash 0 order) | correction for hash seeds != 0 only | identity compare identical; sweep test 0..3 equal |
| EXPAND, additive seeds | correction | before/after `turn_speed_identity` (all cases expected to change) + 200-seed gate |
| `clamp_floor_loss` fsum | correction (diagnostic) | identity compare lists any differing field |
| Registry adoption in main | refactor | CLI identity; per-arg `world.model_dump_json()` equality |
| Live adoption (order change) | refactor | live-world dump equality over an arg matrix, governance exempt |
| Live governance | correction | live-vs-CLI switch parity test; CONTINUATION entry |
| Rust repr | correction (rare names) | digest constants both sides |

## 7. Tests

New: `tests/test_system_rng.py` (golden legacy-equivalence, stream isolation, uniqueness of namespaces); `tests/test_hash_seed_sweep.py` (subprocess seeds 0..3, war-requisition debit and `consume_from_stockpile`); `tests/test_switch_defaults.py` (registry order equals main's, parity of switch state between `_live_world` and a fresh CLI world, governance); `chronicler-agents` politics hash test. Changed: `test_action_engine.py` (EXPAND seed), `test_fisheries_mutual_aid_promotion.py:108`, `test_what_if.py:221`. Add to an oracle chunk with headroom.

## 8. Risks and open questions

Largest: all default-path outcomes move (DEC-3). Owner questions: sign-off; DEC-2 (is governance default-on for live at all, or does live follow a "profile"?); name key (`civ.name` vs index). Unverified: whether remaining ~130 module-level set constants hide an order-sensitive iteration (the plan adds an AST audit script and the sweep as backstop); `politics_bridge` `context_seed` source. Rollback: each PR is independent; revert the correction PR restores old streams.

## 9. Size

About +320/-150 Python lines, +80 Rust, +400 test lines, 6 PRs (3 refactor/pre, 3 correction).
