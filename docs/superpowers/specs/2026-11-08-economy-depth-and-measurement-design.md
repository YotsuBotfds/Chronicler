# Economy Depth and Measurement — Design Spec
> **Status:** Proposed (not started)
> **Date:** 2026-11-08
> **Tasks:** DEP-6, DEP-7, DEP-8, DEP-9, CON-8
> **Depends on:** PIN-1 (DEC-1 option A) for DEP-6 and DEP-8, because `simulation.py`, `economy.py`, `main.py`, `batch_manifest.py`, `economy.rs` and `tick.rs` are enforced pins. DEP-9 and CON-8 do not depend on it. COR-1 owns the hash-seed sweep test that DEP-9 wires into CI. CON-1 owns the switch registry that DEP-8 reuses.
> **Feeds:** DEP-1 (saturating stats), the 200-seed gate, any later "grand run".
> **Source:** docs/superpowers/audits/2026-11-08-streamlining-scout.md (+ scouts 04, 17, 21, 26, 29, 31, 32)

## 1. Goal and scope
- **DEP-6** `--closed-money` (default off, agent mode only): merchants pay the treasury tax, the tithe is debited once, merchant trade income comes from buyers, and a per-turn money-supply identity is recorded.
- **DEP-7** `--household-access` (default off, observation only): per-household food access and welfare primaries for screens.
- **DEP-8** `--feature-profile NAME`: named, validated feature stacks.
- **DEP-9** Validation hygiene: seed-registry enforcement, a multiplicity correction, hash-seed sweep CI, a scheduled smoke regression, a real multiprocessing test.
- **CON-8** Screen-runner unification, reduced in scope (section 2).
- Not in scope: changing any default; promoting DEP-6/7 (they need the 200-seed gate); deleting frozen screens.

## 2. Current behaviour (verified)
- **Tax.** Rust `treasury_tax = tax_rate * mw` from merchant wealth (`chronicler-agents/src/economy.rs:2331-2335`). Python credits it to the treasury (`simulation.py:1801-1823`, called at `simulation.py:2188`). No agent is debited; `wealth_accounting.py:64` says so.
- **Tithe twice.** Priests get `TITHE_RATE * tithe_base / priests` as income (`economy.rs:2337`, `tick.rs:1632-1633`; Python signal at `agent_bridge.py:1003-1007`). The treasury also gets `int(TITHE_RATE * compute_tithe_base)` once clergy influence is at threshold (`factions.py:420-428`). Same base, nobody debited. **Confirmed.**
- **Merchant fiat.** `trade_income = total_delivered_value / merchant_count` (`economy.rs:2162-2184`), paid as income (`tick.rs:1618-1620`, region signal). `merchant.rs` has no wealth writes (scout 21, not re-read). **Audit nuance:** A4 titled trade (`cargo_purchase`, `money.py:75-80`) already makes merchants pay owners for food; only the margin leg is fiat.
- **Seam already supports the needed shapes.** `money.py` has collections (agents pay a treasury, `money.py:361-365`, `:665`), aliases onto native codes (`NATIVE_ALIASES`, `:90-98`) and pairwise payments (`PAIRWISE_PURPOSES`, `:80`, native `settle_pairs`, `wealth_transfer.rs:319`). Treasury-to-agents is whitelisted (`TREASURY_AGENT_PURPOSES`, `:104`). So tax and tithe need **no Rust change**.
- **Agent money.** One f32 per agent, clamped [0,100], 2% decay (`agent.rs:229-230`). Other fiat sources exist (base income, mine and trade bonuses: scout 04), so "closed" means closed for the three legs above, plus a declared mint/burn table for the rest.
- **L2 frames.** Native rows give per-region `shortfall`, `below_floor`, `fully_fed`, poorer/richer-half and child shortfall (`provisioning.rs:73-100`, `:329-339`). Python keeps only scarce-region rows, totals over non-retail regions, and a capped sample (`food_allocation.py:125-181`). Household retail adds `priced_out_persons`, `priced_out_deficit` per region (`provisioning.rs:505-508`, `household_retail.py:137`). Nothing reports per-household access in one place.
- **Presets** set tuning only (`tuning.py:450-461`, `main.py:2327`). Batch manifests record `SIMULATION_ARG_KEYS` (`batch_manifest.py:56`). `validate_features` already checks a features dict (`feature_catalog.py:512-529`) and the batch path takes a `features` object (`:532-542`).
- **Validation.** Gate is `full` (200 seeds x 500 turns, seeds 42-241; `m53b_run_validation.py:90-103`) and forces `PYTHONHASHSEED=0` (`:97`). `seed_registry.json` marks that range `restricted_gate` (entry `gate200-t`) but no validation module reads it. Needs oracle has 5 pairings (`validation_io.py:170-176`) and an exact one-sided sign test per pairing (`:1858`, reported at `:2159`); no correction. `run_needs_oracle_best_of` (`validation_io.py:2398`) selects the best candidate per seed. **Audit claim wrong:** a weekly schedule already runs the `full` profile (`validation-gate.yml`, `schedule` block, default profile `full`); what is missing is a cheap per-push or nightly drift check and a baseline fetch.
- **Screens. Audit claim largely wrong.** `screen_runner.py` is already the unification: its docstring says it lifted the skeleton from `productive_recovery_screens.py` and `livelihoods_screens.py`, which "stay frozen" (`screen_runner.py:1-26`). `connected_world_screens.py` and all `cw_*_screen.py` already call `SR.*` (264 `SR.Outcome` uses). By AST, only 18 + 6 top-level names are shared with the frozen files, 1 byte-identical, and those files are frozen on purpose. Real saving: close to zero lines.

## 3. Design
### DEP-6 closed money
New `closed_money.py` + `closed_money_state.py` (pydantic, backfilled defaults; sub-state absent when off). Catalog switch `closed_money`, requires `--agents hybrid`. Aggregate / agents-off worlds have no agent wealth: the switch is refused there and treasuries keep their documented fiat sources.
1. **Tax.** At the `simulation.py:2188` site, if on: build a collection bill purpose `merchant_tax` (alias of an existing native code, batch = `civ`) with one line per merchant, `floor(TAX_RATE * wealth * 1000)` milli from one fresh wealth read. `money.pay` is the only settlement step. Its `MoneyBook` lives in `ClosedMoneyState` (`pay` requires a book, `money.py:572`). For a `civ_treasury` payee, `pay` already credits whole units and keeps the sub-unit carry in `book.carry`, through `_credit_treasury` and then `_move_treasury` (`money.py:487-506`, called at `:678-682`). Nothing else credits the treasury, and there is no separate tax carry; this replaces `_treasury_tax_carry`. Observations read the receipt (`treasury_units`, flows' `carry_before`/`carry_after`). The fiat credit from `economy_result.treasury_tax` is skipped. A second settlement of the same (turn, purpose, batch) is refused by `book.settled`.
2. **Tithe once (one funded collection).** For each civilisation and turn: $D$ = `TITHE_RATE * tithe_base` (milli, floored). With $f$ = `closed_money.tithe_priest_fraction` ([CALIBRATE], default 0.5):
   - **Requests.** The priest request is $P = f \cdot D$ if the civilisation has at least one priest in the pool snapshot the signal is built from, else 0. The treasury request is $T = (1 - f) \cdot D$ if last turn's clergy influence is at `TITHE_THRESHOLD` (a declared one-turn lag), else 0. A part that is not requested is not collected; the merchants keep it.
   - **Collection.** One `tithe_collection` collection bill (batch = civilisation) funds both parts from the civilisation's merchants. Lines are weighted by wealth and capped at each merchant's wealth, so the collected $C \le P + T$. The bill is settled by `money.pay` in `agent_bridge` before the Arrow build, so the signal can use the result. The two payees are the `civ_treasury` (credited and carried by `pay` itself) and a per-civilisation priest escrow purse. When $C < P + T$, both parts scale in proportion: $P_c = \lfloor C \cdot P / (P + T) \rfloor$, $T_c = C - P_c$.
   - **Signal.** `priest_tithe_share` = $P_c$ / priest count, with the count taken from the same snapshot. This is the only priest tithe income: the fiat share computed from `TITHE_RATE * base / priests` is replaced, and the `factions.py:424-428` treasury tithe is skipped while the switch is on.
   - **Escrow residual.** After the tick, the escrow holds $P_c$ minus the shares actually paid. Priests who died or moved before the wealth phase are not paid. The residual is paid to the civilisation treasury from the escrow through `money.pay` (purpose `priest_tithe_residual`), so it is a transfer, not a mint. The paid count comes from the tick. If no counter exposes it today, adding one is a Rust output field, which is not persisted and does not change the layout fingerprint (an open question in section 8).
   - **Refusals.** A refused bill moves nothing (`pay`). The civilisation then gets a zero priest signal and no treasury tithe that turn, and the refusal is recorded. With zero merchants, $C = 0$.
   - **Identity.** Payer loss (merchant wealth, milli) equals priest credits plus treasury units × 1000 plus the change in `book.carry`, plus the change in the escrow residual.
3. **Merchant margin.** Stage B (separate PR). In the same Phase 2 window, `trade_income` for a region is not paid as income: buyers in the destination region pay it by a pairwise `cargo_sale` bill (`settle_pairs`, batch disjoint from A4's), payers are non-merchant households of the destination region weighted by wealth, payees are the origin region's merchants equally. A payer who cannot pay limits the payment (a real budget constraint; the shortfall is recorded as `margin_unfunded`). `economy_result.merchant_trade_incomes` is zeroed for settled regions so Rust does not pay it twice.
4. **Identity.** `wealth_accounting` gets a `money_supply` frame per turn: `opening + mint - burn = closing`, with `opening/closing = sum(agent wealth) + sum(treasury)`. Mint table: farmer/soldier/scholar/priest base income, merchant fiat remainder, birth endowment, the declared treasury fiat sources (scout 04 list). Burn table: decay, ceiling refusal, estates, treasury sinks. Native rows already itemize the agent side (`native.balance_closure`). The three closed legs must net to exactly zero; the full identity is a diagnostic (`strict` only for legs).
5. **FFI/persist.** v1 adds no Rust fields, so no checkpoint layout-version bump. If Stage C later adds native mint/burn counters, it bumps the state version at `ffi/mod.rs:656-662` (unverified details) and keeps a reader for old checkpoints.

### DEP-7 household access
Observation-only Python module `household_access.py` (livelihoods-style package contract: `_active`, `snapshot_summary`; default off, requires `--food-allocation`). Definitions, per region and world, per turn:
- `calories_met_share = allocated / alive` (rations; 1.0 = full ration, `provisioning.rs:318-339`).
- `shortfall_depth = shortfall / alive` and `below_floor_share`.
- `priced_out_person_turns` (retail regions: `priced_out_persons`), cumulative, with `priced_out_deficit`.
- poorer-half vs richer-half shortfall ratio; child shortfall share.
Welfare primaries for screens: `P1 = shortfall person-turns per 1,000` (poorer half) and `P2 = priced-out person-turns per 1,000`; care and food are paired as one welfare number `deaths + shortfall` only after the owner picks weights (open question). v1 reads existing frames (no Rust change), so all-region denominators come from non-retail totals plus retail rows; where a region has neither, it is `None`, not 0. Surface: `livelihoods.household_access` in the history row (`snapshot_summary`), a lazy extractor in `analytics.generate_report` (scout 17 finding 9), and `viewer/src/lib/householdAccess.ts` modelled on `foodAllocation.ts`. A Rust decile-band extension is deferred (Stage 2, layout bump).

### DEP-8 profiles
New `feature_profiles.py`: `PROFILES: dict[str, dict]` for `classic` (every catalog bool false, choices at their first value: the identity reference), `new-world` (what the CLI gives now), `agent-economy` (hybrid plus timber_supply, commons_rules, workshop_payroll, maintenance_obligation, grain_reserves), `connected-full`, `controls`. `main.py` pre-parses `--feature-profile`, runs `validate_features(profile, surface)` and calls `parser.set_defaults(**features)`, so any explicit flag overrides. The batch config takes `feature_profile` and stores both the name and the expanded dict in the manifest (new key, omitted when unset, like the other optional keys at `batch_manifest.py:268`). `--preset` is untouched.

### DEP-9 validation hygiene
- **Seed registry.** `scripts/check_seed_registry.py` + a gate pre-check: gate seeds must equal a `restricted_gate` entry; no `run` entry may reuse a restricted range except those labelled `development`; fix the stale m58b note.
- **Multiplicity.** `validation_multiplicity.py::holm_adjust`. Family = the 5 needs-pairing sign-test p-values per snapshot method (`validation_io.py:2159`). Phase 1 is report-only (`holm_p` beside `sign_test_p`; PASS unchanged). Switching PASS to use it is a correction with its own `NEEDS_ORACLE_METHOD_VERSION` bump and rebaseline.
- **best_of.** Keep the function and the re-export (`validation_oracles.py` hash is pinned; the goldens list it). Add a deprecation docstring, and a test that no gate path imports it.
- **Hash-seed sweep.** `m53b --hash-seed N` (default 0, identical). CI job runs a small seeded world under `PYTHONHASHSEED` 0,1,2,random and compares digests (needs COR-1 first, or it fails on the known `war_requisition` order).
- **Scheduled smoke.** New `regression-smoke.yml`, nightly: 4 template seeds x 100 turns hybrid, compares metric summaries to a committed fixture. Cost unmeasured; measure in the PR (budget: under 15 runner-minutes).
- **Real multiprocessing test** for `batch.py:120-133`, outside the oracle lane (the guard blocks child processes): own CI step.

### CON-8
Re-scoped: (a) add `tests/test_screen_frozen_evidence.py` pinning the SHA-256 of `productive_recovery_screens.py` and `livelihoods_screens.py` so "frozen" is enforced; (b) rule in docs: new screens declare `SR.Screen`s only; (c) no change to `screen_runner.py` unless a pilot/held pair is not in flight (its file hash is in `source.txt` and compared between pilot and held, `screen_runner.py:1140-1160`). Unspent cohorts exist (`cw3-held-t`, reserve entries), so edits to it invalidate their pilots.

## 4. Compatibility
Everything is default off and absent from old bundles. Old checkpoints load without the new sub-states (backfill). Manifest key `feature_profile` is optional. No flag is removed.

## 5. Pins and preflight
Enforced: `simulation.py`, `economy.py`, `main.py`, `batch_manifest.py`, `economy.rs`, `tick.rs`, `tuning.py` (academy / livelihoods inverse fixtures). Plan: DEP-6 and DEP-8 hook edits wait for PIN-1; new modules are unpinned. "References found" only: `feature_catalog.py`, `money.py`, `wealth_accounting.py`, `food_allocation.py`, `analytics.py`, `factions.py`, `validation_io.py`, `validation_oracles.py`, `batch.py`, `m53b_run_validation.py`, `screen_runner.py`, `seed_registry.json`, workflows. `seed_registry.json` is inside the registry hash (`tests/test_screen_runner.py:1066-1072`): edit only the `unresolved` text if the hash excludes it; otherwise leave it (verify first).

## 6. Classification
DEP-6, DEP-7: new default-off features, not corrections; off-state must be byte-identical (`scripts/turn_speed_identity.py`). DEP-8, DEP-9 phase 1, CON-8: tooling, identity proofs in the plan. Changing PASS rules is a correction.

## 7. Tests
`tests/test_closed_money.py`, `test_household_access.py`, `test_feature_profiles.py`, `test_validation_multiplicity.py`, `test_seed_registry_check.py`, `test_batch_parallel_real.py`, `test_screen_frozen_evidence.py`; extend `test_feature_matrix.py` (catalog byte-identity must stay).

## 8. Risks
Taxing merchant stock (5%/turn) will pull merchant wealth down and shift migration and occupation switching: the evaluation must measure that. Held evaluation design for DEP-6/7: seeds from unspent registry cohorts reserved first (new registry entries), 2-3 primaries (tithe/treasury leg residual = 0; merchant wealth Gini; poorer-half shortfall per 1,000), equal-cost pairing against a control that removes the same total money by fiat, then the 200-seed gate before promotion.

Open question for the tithe leg: the plan needs the number of priests the tick actually paid, to compute the escrow residual. If no existing counter gives it, add a tick output counter. The priest escrow uses the existing `escrow` account kind (`money.py:106`, `money.escrow(order)` at `:268`), passed to `pay` through `escrows=`. Review (2026-11-08) corrected two defects in this design: a duplicate treasury credit next to `money.pay`, and an unfunded priest share.

## 9. Size
About +900 lines Python, +250 TS, +150 tests-lines per feature; 6 PRs.
