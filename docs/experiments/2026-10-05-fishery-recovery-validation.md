# Completed fishery harvest/rest validation and transfer scope

The follow-up validates the existing default-off feature from commit
`90ad340aef7380a890677bc8fa1f623ea5c08909`. It adds validation/packaging code and
evidence; no simulation mechanics or defaults change. Public baseline is exactly
`edf72991cad58d6670b1f382c33d50d903a6054a`, including PR13. No comparison with
the private frozen `b665e198` candidate is supported.

## Fixed fixture and reproducibility

One coastal region, seed 42, base fish yield 1, carrying capacity 3000, population
1000, initial fish goods inventory 2000, temperate climate, and existing seasonal
yield rules. Current feature parameters remain `reserve_turns=8`,
`recovery_rate=.04`, `harvest_fraction=.25`, `reference_workers=200`.

The same prescribed snapshot has 800 farmers on turns 0–19 and zero on turns
20–39; remaining residents are scholars, with zero wealth. It runs real
`compute_economy()` first and `tick_ecology()` second on each of 40 turns. This is
a controlled Phase 2 → Phase 9 harness, not `run_turn()` or a demographic tick.
Famine population loss is overridden to zero **only in this fixture**, equally
in all runs, to preserve fixed inputs. The famine predicate, cooldown, events,
and stability effect remain active. No routes or merchants exist. No LLM or
external service is used.

Fresh processes load (1) clean untouched public main, (2) the branch with the
feature disabled, (3) the enabled branch, and (4) an enabled run saved/reloaded at
turn 20. Disabled traces and canonical old-schema state hashes match untouched
main at **every turn**. Only additive experiment schema fields are excluded from
hash comparison. Save/reload reproduces the entire uninterrupted enabled trace.

```bash
.venv/bin/python scripts/validate_fishery_recovery.py \
  --baseline-src /path/to/clean/edf7299/checkout/src \
  --output /tmp/fishery-recovery-40.json
.venv/bin/python -m pytest tests/test_fishery_recovery_validation.py \
  tests/test_fishery_experiment.py -q
```

Committed raw evidence is
[`fishery-stock-recovery-40.json`](evidence/fishery-stock-recovery-40.json).

## Results

| Measure | Untouched main / feature off | Feature on |
|---|---:|---:|
| Stock after 20 harvest turns | Renewable stock not modeled | 0.10839436017442522 |
| Stock after 20 rest turns | Renewable stock not modeled | 0.6059081371364894 |
| Actual food production, all 40 turns | 16000 | 2307.8202663344277 |
| Biomass harvest debit, worker-yield units | Not modeled | 2365.630591760788 |
| Biological replenishment, worker-yield units | Not modeled | 1735.0836111791712 |
| Discarded catch credit at turn 20 | Not modeled | 57.81032542636012 |
| Yield-famine predicate turns | None | 7–19 |
| Famine-event turns, subject to cooldown | None | 7, 12, 17 |
| Stockpile sufficiency below 1 | 24–39 | 5–39 |
| Maximum goods ledger residual | 0 | 0 |
| Maximum biomass ledger residual | Not modeled | 1.137e-13 |
| Maximum combined ledger residual | Not modeled | 9.095e-13 |

All stock, recovery, catch, production, goods, and sufficiency values are finite.
Stock stays in [0,1], rest replenishes monotonically, and all 20 rest turns have
zero harvest and zero actual production. The on feature enforces actual goods
production ≤ the previous ecology tick's catch debit on every turn.

Absent yield famine during rest **does not imply adequate food**. With zero
workers, the existing experiment exposes potential per-worker yield while
harvesting nothing; stockpile sufficiency remains below 1. The distinction also
appears on turns 5–6, when stockpile shortage precedes the yield-famine predicate.
This stress fixture establishes the accounting and feedback mechanism; it does
not establish realism, demographic benefit, or readiness for default promotion.

## Conservation and phase boundary

Biomass capacity is 1600 worker-yield units. At each ecology tick:

```text
old biomass + biological replenishment = new biomass + current catch debit
```

At Phase 2, the **prior** catch funds production. Any unconverted credit is
discarded, and the current ecology catch remains a separate pending catch credit
until the next Phase 2. The combined ledger checks:

```text
initial biomass + initial goods + accumulated replenishment
  = current biomass + current goods + current pending catch credit
    + accumulated consumption + storage loss + cap overflow
    + floor-correction ledger loss + transit loss + in-transit change
    + discarded catch
```

The turn-20 prior catch credit of 57.81032542636012 becomes discarded catch
because the resting workforce produces no goods. Final pending catch and goods
are zero. Harvest debit = actual goods production + discarded catch within
floating-point tolerance.

Every trace row includes actual ledger terms, cargo=0, pending deliveries=0,
and residuals. Cap overflow is exercised in the off control; floor corrections,
transit, cargo, and deliveries are zero by construction. This does not test
nonzero native cargo/delivery conservation. No full-world or full-hybrid claim
is inferred from the controlled zero-buffer case.

## Finalized interfaces and persistence

The [interface manifest](2026-10-05-fishery-stock.md#interface-manifest) remains
unchanged: default-off `fishery_experiment`, persisted `fishery_stocks`,
`fishery_yield_ratios`, and `fishery_catch_budgets`; lagged Phase 2 effective-yield
input and actual-production cap; current Phase 9 catch patch to native agent
`resource_yields` after recomputation. Permanent degradation yields are retained.

Python world JSON supports config, stocks, ratios, budgets, goods inventory,
and existing ecological state. The new turn-20 fixture proves their next-phase
use matches uninterrupted execution after reattaching **prescribed inputs**.
A separate saved-disabled-memory fixture proves disabling preserves and ignores
memory, re-enabling exposes the saved catch credit, and removing the fish slot
resets stock/ratio/budget to 1/1/None. Legacy loading remains supported by the
earlier fixture. Transient current yields are still excluded from saves.

Full hybrid continuation is explicitly **unvalidated**. The fixture has no
native agent pool, agent RNGs, merchant cargo, or native pending-delivery buffer
to restore. Native catch forwarding and production-cap integration retain the
earlier focused compiled-extension evidence.

## Independent review and preserved evidence

Fresh Tier 3 reviewer `review_recovery_results` independently reran the small
source controls, reconstructed the ledgers, and corroborated all results, the
Python boundary resume, and four focused fixtures. No blocking issue remained.
The owner ran 142 focused feature/validation tests, including earlier native
fixtures, with no failures or skips. The original 548-test and Rust records
remain historical evidence, not a claim of a repeated broad suite.

The earlier pair, validation record, and runtime inventory stay byte-identical
to commit `90ad340`; they are retained in Git history and in the scoped backup.
The supplemental evidence records their hashes.

## Safe local backup and transfer

`scripts/package_fishery_experiment.py` packages a **clean committed** isolated
branch. The archive contains only changed tracked source/tests/scripts/docs,
the baseline-to-final Git patch, an incremental bundle requiring exact `edf7299`,
transfer instructions, and a SHA-256 manifest. It validates every intermediate
commit's path/mode scope and requires a linear branch from the baseline. All tar
members are regular relative files, and every payload is checked without
extraction. Archive and sidecars refuse to overwrite existing files or symlinks.

It excludes `.git` config, credentials/security files, `.env`, `.venv`, caches,
toolchains, compiled binaries, untracked files, and unrelated branches/history.
The bundle preserves the experiment commits without being a full repository
backup. Rebuilding the native extension is required on the receiving machine.

```bash
.venv/bin/python scripts/package_fishery_experiment.py \
  --output chronicler-agents/target/transfer/fishery-stock-scoped.tar.gz
```

Fresh Tier 4 reviewer `review_transfer_scope` reviews packaging scope and restore
claims independently. Preflight findings prompted intermediate-history validation
and no-overwrite creation for all three outputs. Final archive verification is
reported with the delivered archive manifest. No upload, public push, merge,
credential change, or default promotion is authorized or performed.
