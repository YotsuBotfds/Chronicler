# M67 readiness from the existing governance outputs

This document is the source-backed readiness record for the Phase 8 governance
gate milestone **M67 (Governance Tuning Pass)**
(`docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md:859-940`).

The lane that produced this document adds a read-only measurement seam over the
already reviewed four-kernel harness. It adds instrumentation, **not** another
governance mechanic, PSI substitute, calibration campaign, seed sweep or scale
run. Nothing here satisfies, qualifies or partially satisfies M67.

Recorded status: **M67 acceptance is not qualified, and M67 remains blocked.**
Phase 9 (M68a, M69, M71) still requires M67 at `:1266-1280`.

## What the seam is, and what it is not

Owned paths, and only these four:

| Path | Role |
| --- | --- |
| `src/chronicler/governance_measurements.py` | Immutable measurement frame plus deterministic report/JSON renderings |
| `scripts/governance_measurement_report.py` | Standalone opt-in report. Default off; runs no example without `--run-example` |
| `tests/test_governance_measurements.py` | Measurement tests reusing existing harness fixtures and the existing example |
| `docs/governance/m67-readiness.md` | This document |

The seam reads one explicit frozen opening `HarnessCarry`, one **already
produced** `HarnessResult`, one declared origin and one source identity. It
returns one immutable `GovernanceMeasurementFrame`. It never calls
`run_kernel_frame`, never reads a `SyntheticFrame`, never consumes an
observation or a selection draw, never touches an RNG, imports nothing from the
simulation runtime, shared models, analytics, the agent bridge, native code, the
CLI registry or persistence, and mutates neither argument.

Fields extracted are only those the harness actually publishes: institution
count/type/enacted turn/legitimacy/enforcement cost/alignment/opposition,
observed enact and repeal outcomes, the source and effective turn, ruler
legitimacy, the exact political-capital numerator/denominator and its float view,
spend/accrual/request decisions, ambition outcomes with their retained
contribution counts, reign/objective/evidence-ledger state, and the G02
qualifier/office-holder/aspirant counts, positions and EMP when the result
carries them.

Provenance is preserved on every frame: `origin`, `source_identity`, `policy_id`,
`source_turn`, `effective_turn`, `opening_last_committed_turn`,
`identity_registry` and the harness `diagnostics` verbatim.

## Epoch discipline

Turn `N` is the source turn. Spend decisions and the opening-portfolio funding
quote are charged on `N`. Institutions, accrual and elite signals are effective
`N+1` and are never backdated. Each record carries both epochs, and an enactment
whose `enacted_turn` is `N` always appears with `effective_turn == N+1`.

Measured integrity checks are cross-checks, not re-simulation. Receipt surfaces
are bound to the published carry: `receipt.institutions.next_state` must equal
the published institution snapshot, the complete accrual state must equal the
published governance state, and `elite.next_ratchet_state` must equal the
published ratchet. The exact spend ledger is re-derived from the published
decisions (an approved decision must debit exactly its cost, a denied decision
must consume nothing, the chain must start at the opening balance and end at the
published spending state); request receipts must be unique and must agree with
the ordered spend ledger, while `structurally_unused` and `ineligible_mock`
records are retained exactly as published; terminal ambition outcomes must match
the source epoch, the redundant identity/type fields, and the published reign's
terminal objective and retained contribution delta. G02 counts must be
re-derivable from the published identity lists, which must form the partition G02
publishes: unique identities, the leading `elite_positions` qualifiers as holders,
and aspirants drawn in order from the non-holding suffix. Diagnostics must be
exact immutable strings. A malformed frame fails before any measurement is
published, and nothing is mutated on failure.

Repeals are counted once per actual repeal: a forced repeal publishes both a
`RepealOutcome(REPEALED)` and an `institution_repealed` event, while a neglect
repeal publishes only the event. `repeal_count` is the generic total and
`forced_repeal_count` and `neglect_repeal_count` are its per-cause parts, so a
neglect collapse is never reported as a measured zero.

## Absent output is not zero

`Metric` makes presence structural: `AVAILABLE` requires a value and forbids a
reason; `UNAVAILABLE` requires a nonempty reason and forbids a value. A measured
zero stays available and carries `0`. A missing metric is never rendered as `0`.
A **disabled** harness result is refused outright rather than measured into an
empty-but-passing frame, and an empty identity registry is reported as absent
rather than zero.

Ordering is stable: civilizations ascending by `civ_id` in the persisted identity
registry, institutions in G01 enum order, legitimacy sources in the kernel's own
declaration order, ambiguity and spending in received order, contributions in
`contribution_id` order, elite lists in the kernel's ranking order. Exact
`Fraction` balances are stored as canonical reduced numerator/denominator pairs
and survive report encoding, including residuals below float-view resolution.

## Running it

Default is off. With no flag the script imports no example module, runs no
experiment and measures nothing; it prints the deterministic notice listing every
obligation that stays unavailable.

```sh
python scripts/governance_measurement_report.py                      # default off
python scripts/governance_measurement_report.py --run-example         # text report
python scripts/governance_measurement_report.py --run-example --json  # canonical JSON frame
```

`--run-example` invokes the exact existing `examples/governance_four_kernel.py`
experiment unchanged, then measures its published result. Because that example
builds its opening carry internally, the script observes the explicit frozen
opening the example handed to the harness by wrapping `run_kernel_frame`
in-process for the duration of the call and restoring it in a `finally` block. No
kernel behaviour changes and no example source is edited. All report output is
labelled synthetic. The recorded source identity defaults to the reviewed parent
that supplied the four kernels and the harness
(`208d140d47d9f2dee0788267f79fa7276df22b42`, tree
`0762c7cff65e28ff326291ce31111b71e1d61ae3`) and is overridable with
`--revision`, `--tree` and `--source-label`.

## M67 prerequisite matrix

M67 depends on M63a, M63b, M64, M65a, M65b, M66a, M66b and M61b (`:865-871`,
`:1001`). The matrix below gives, for each prerequisite and each M67 gate, the
required input/epoch/measurement, the surface that exists in this private
candidate, the missing producer or decision lock, and the next **authorized**
dependency. Nothing in the "next" column is authorized by this lane.

| Prerequisite / gate | Required input, epoch, measurement | Existing available surface here | Missing producer / decision lock | Next authorized dependency |
| --- | --- | --- | --- | --- |
| M63a institutions (`:76-191`) | Per-civ institution snapshot at N+1 with count, type, enacted turn, legitimacy, enforcement cost, alignment, opposition; enforce/repeal outcome per turn | G01 kernel plus harness `InstitutionTurnResult`: `institution_count`, `enact_count`, `repeal_count`, per-institution records, proposal/repeal outcomes and events | 16 institution effect tables and per-turn enforcement repricing are absent; `MAX_ACTIVE_INSTITUTIONS` and thresholds are fixed, `[CALIBRATE]` constants are uncalibrated | Separate M63b calibration/representation decision; no runtime activation |
| M63a tenure (`:881`, `:898`) | Institution tenure in turns over a run; mean active count over a window | Only two turns of explicit synthetic fixtures exist | No multi-turn history, no window definition, no censoring rule | M67 preregistration of window/censoring, then a supported run producer |
| M63b effects and cap revision (`:218-293`) | Per-institution action-weight and satisfaction modifier tables; bucket ceilings under the unchanged 2.5x global cap | None. `institutional_effect_modifiers` is unavailable | No action-weight pipeline in the detached harness; modifier tables are `[CALIBRATE]` and unbuilt | M63b spec/implementation milestone; not authorized here |
| M64 commons (`:312-391`) | Per-region exploitation/sustainable-yield overshoot markers and commons-health collapse markers at N+1 | None. `commons_overshoot_marker` and `commons_collapse_marker` are unavailable | No M64 kernel exists in this checkout at all; `KAPPA_BASE`, thresholds and streak extensions uncalibrated; Rust ecology migration target not wired | M64 milestone on the M54a substrate; not a repair task for this lane |
| M65a elite metrics (`:413-496`) | Per-civ positions, qualifier, office-holder and frustrated-aspirant counts, ratchet index, EMP at N+1 | G02 kernel plus harness `EliteMetricsOutput`: `elite_positions`, `elite_qualifier_count`, `elite_office_holder_count`, `frustrated_aspirant_count`, `conspicuous_consumption_index`, `emp` | Snapshot population is a supplied synthetic row count; no agent/wealth extractor; `RATCHET_UP_RATE`/`RATCHET_DOWN_RATE`/`RATCHET_CAP` uncalibrated | M65a acceptance against a real post-agent snapshot; not authorized here |
| M65b PSI (`:517-608`, `:878`) | `MMP`, `SFD`, composite `PSI = MMP^a * EMP^b * SFD^c` at N+1 lagged, with a calibrated crisis threshold | None. `psi`, `mmp`, `sfd` and `psi_subindex_cooccurrence` are unavailable | The measured `HarnessResult` lacks the complete production MMP inputs and extractors, any urbanization or youth-bulge series, and a calibrated PSI producer. The synthetic frame does carry `AgentEliteInput.wealth` and G02 derives population from supplied living rows; neither is a production MMP input. `PSI_CRISIS_THRESHOLD` is `[CALIBRATE]` and deliberately unset | M65b implementation plus M61b extractors; explicitly out of scope |
| M65a/M65b ratchet balance (`:893-894`) | Asymmetric timescale, slow rise / fast crash / slow recovery | Only per-frame CCI and EMP scalars | No time series, no 200-seed 500-turn campaign | M67 calibration method, which is outside this task |
| M66a legitimacy and capital (`:632-719`, `:877-885`) | Per-civ ruler legitimacy distribution and exact political-capital distribution across seeds | G03 kernel plus harness accrual: per-civ legitimacy, the seven legitimacy sources in kernel order, exact opening/generated/closing capital, spend ledger | `legitimacy_distribution` and `political_capital_distribution` are unavailable; this is one observation per civ, not a distribution. Dynasty cognomen awards and victory/defeat inputs are caller-supplied and unsourced here | M66a acceptance with real dynasty/succession evidence |
| M66b ambitions (`:744-835`) | Ambition completion/failure rates and named-event rates | G04 kernel plus harness: terminal `ambition_outcomes` with contribution keys, retained contribution counts, reign objective/terminal counts and event tags | No ambition rate series; `AMBITION_MILITARY_WEIGHT`/`AMBITION_CULTURAL_WEIGHT` uncalibrated; event-chain firing at 200 seeds untested | M66b acceptance; not authorized here |
| M61b scale validation (`:871`, `:959`, `:1011`) | Validated governance behaviour at 500K-1M agents | None. `scale_qualification` is unavailable | Fixture population only; M61b is a separate held milestone on the Phase 7 scale track | M61b completion; M67 gates on it (`:1011`) |
| M67 measurement-first (`:877-885`) | `extract_governance_metrics()` in `analytics.py`: institution counts and tenure, enact/repeal rates, legitimacy/political-capital distributions, commons overshoot/collapse markers, elite counts, MMP/EMP/SFD/PSI series | Counts, elite counts, EMP scalars and exact capital are measured from the harness by this seam. `analytics.py` still has no `extract_governance_metrics` | Tenure, rates, distributions, commons markers and the MMP/EMP/SFD/PSI series still need a run producer and a producer location decision | A separately reviewed extraction milestone; this seam deliberately does not edit `analytics.py` |
| M67 regime classifiers (`:879-882`, `:925`) | Per-run frozen / highly fluctuating / complex cycling labels | Definitions recorded as preregistration only; `institutional_regime_classification` is unavailable | No classifier implemented; window, censoring, churn-count, tenure-bound, overlap and sample-size conventions are unresolved | Preregistration decision, then implementation under a later milestone |
| M67 transient-reset matrix (`:883`, `:929`) | An integration test per one-turn M63-M66 signal proving reset after consumption | None. `transient_reset_matrix` is unavailable | Requires production phase wiring and a scheduling/reservation decision this lane is not authorized to make | Production scheduling milestone; not a repair task here |
| M67 PSI predictiveness (`:887-890`, `:922`) | Crisis-crossing seeds with an outcome 10-40 turns later in >= 65% of seeds; sub-index co-occurrence in one 20-turn window in >= 50% | None. `crisis_predictiveness` and `psi_subindex_cooccurrence` are unavailable | No production PSI and no production crisis outcomes | M65b plus production wiring, then M67 |
| M67 secular-cycle recovery (`:892-895`, `:924`) | >= 60% of crisis seeds recovering within 120 turns of peak PSI | None. `secular_cycle_recovery` is unavailable | Two synthetic turns cannot show a recovery trajectory; a one-turn fixture cannot classify a regime | M67 calibration method; outside this task |
| M67 legitimacy constraint (`:903-904`, `:926`) | Governance-action success for the bottom vs top legitimacy quartile in >= 70% of seeds | None. `legitimacy_action_success_by_quartile` is unavailable | The harness receives an explicit proposal choice and executes no real action; cross-seed quartiles need a run producer | M67 after real action outcomes exist |
| M67 degenerate-condition guards (`:908-912`, `:927`) | The four documented guards (military capture, PSI+commons collapse, one-way cycle, clergy theocratic capture) | None. `degenerate_condition_guards` is unavailable | Requires production faction, clergy and commons paths that are not wired here | Production integration milestone |
| M67 runtime budget (`:928`) | Combined M63-M66 additions within the planned envelope | None | The detached harness measures no runtime and does not touch the runtime path | M67 after activation |
| M67 regression (`:915-916`, `:930`) | No regression in Phase 6/7 calibrated behaviour; Rust and `--agents=off` parity when governance inputs are neutral | Nothing changed in the runtime, so the dormancy oracle (`tests/test_governance_dormancy.py`) remains the applicable evidence | Production governance inputs remain neutral; a Rust parity claim still needs a native build this lane does not perform | Native validation, which is out of scope here |

## Obligation index (unavailable from this harness by construction)

Each key below is emitted by every measured frame as
`[unavailable] <key> = <reason>`. The reasons name the missing producer or the
decision that has not been locked; none of them is a value.

| Key | Roadmap reference | Required input / epoch | Why it stays unavailable here |
| --- | --- | --- | --- |
| `institution_tenure` | `:881`, `:898` | per-civ tenure in turns over a run / N+1 per turn | one measured frame is a single observation; no run producer |
| `enact_rate` | `:877-885` | enacted / opportunity denominator / N+1 per turn | counts exist, the denominator is an unlocked M67 decision |
| `repeal_rate` | `:877-885` | repealed / opportunity denominator / N+1 per turn | counts exist, the denominator is an unlocked M67 decision |
| `institutional_effect_modifiers` | `:284-293` | per-institution action-weight and satisfaction tables / N | no action-weight pipeline; tables unbuilt and uncalibrated |
| `legitimacy_distribution` | `:877-885` | per-civ legitimacy distribution across seeds / N+1 | single-frame extrema are reported instead |
| `political_capital_distribution` | `:877-885` | per-civ exact capital distribution across seeds / N+1 | single-frame extrema are reported instead |
| `commons_overshoot_marker` | `:878`, `:1232` | per-region overshoot markers from M64 / N+1 | no M64 kernel exists in this checkout |
| `commons_collapse_marker` | `:878`, `:1233` | per-region commons-health collapse markers / N+1 | no M64 kernel exists in this checkout |
| `psi` | `:878`, `:888-890`, `:922` | composite PSI with a calibrated crisis threshold / N+1 lagged | no M65b producer; no threshold is held |
| `mmp` | `:878`, `:889` | MMP from wealth, urbanization, youth bulge / N+1 lagged | the measured result lacks the complete production MMP inputs/extractors and the urbanization/youth-bulge series |
| `sfd` | `:878`, `:889` | SFD from governing cost / treasury / N+1 lagged | fixture treasury is synthetic, not production bookkeeping |
| `psi_subindex_cooccurrence` | `:889`, `:923` | all three sub-indices above threshold in one window / N+1 lagged | requires the MMP/SFD/PSI series |
| `crisis_predictiveness` | `:887-888`, `:922` | crisis seeds with outcomes 10-40 turns later / N+1 lagged | no production PSI or crisis outcomes |
| `secular_cycle_recovery` | `:892-895`, `:924` | recovery within 120 turns of peak PSI / N+1 lagged | a two-turn synthetic frame cannot show recovery |
| `institutional_regime_classification` | `:879-882`, `:925` | frozen / fluctuating / cycling labels per run / N+1 per turn | no classifier implemented; conventions unresolved |
| `transient_reset_matrix` | `:883`, `:929` | reset proof per one-turn M63-M66 signal / N+1 lagged | requires production phase wiring |
| `production_treasury_commits` | `:274-275`, `:281` | persisted governing-cost and treasury bookkeeping / N | the harness publishes a detached quote and commits nothing |
| `scale_qualification` | `:871`, `:959`, `:1011` | validated behaviour at 500K-1M agents / N+1 | fixture population; M61b is held |
| `legitimacy_action_success_by_quartile` | `:903-904`, `:926` | action success by legitimacy quartile / N | no real action outcomes, no cross-seed quartiles |
| `degenerate_condition_guards` | `:908-912`, `:927` | the four documented guards / N | production faction, clergy and commons paths are not wired |

## Regime classifier preregistration (definitions only)

These are the roadmap's own definitions, recorded verbatim as
**proposed preregistration requirements**. This lane implements no classifier and
chooses no convention. Two turns of synthetic fixtures cannot classify an
institutional regime, and `institutional_regime_classification` remains
unavailable.

- `frozen_stable` — "<= 1 institution change per 100 turns and mean active count >= 1."
  Requires: institution change count per 100 turns; mean active institution count.
- `highly_fluctuating` — "mean institution tenure < 10 turns with repeated enact / repeal churn."
  Requires: mean institution tenure in turns; enact / repeal churn count.
- `complex_cycling` — "repeated regime shifts with mean tenure between the two extremes and at least 2 distinct institutional configurations."
  Requires: regime shift count; mean institution tenure in turns; distinct institutional configurations observed.

Unresolved conventions, named rather than guessed (all three classifiers):

- analysis window length and alignment for "<= 1 institution change per 100 turns"
- whether "institution change" counts neglect auto-repeals, forced repeals, or both
- censoring of institutions still active at the end of the observation window
- "repeated enact / repeal churn": the repetition count that qualifies as churn
- the mean-tenure bound separating "highly fluctuating" from "complex cycling"
- aggregation level of "mean active count >= 1" (per civ, per turn, per run, per seed)
- whether one run may satisfy several regime labels, and any precedence order
- the run length, seed count and confidence rule behind ">= 10% of tested runs"

## Held, unavailable and not repairable from here

- **G05** remains permission-blocked. Its source was not accessed, reconstructed
  or substituted, and it is not a repair task authorized by this lane.
- **PSI, MMP, SFD, secular-cycle recovery, crisis predictiveness and regime
  classification** are scientific claims with no producer here. They are held
  evidence, not bugs to fix.
- The presence of the detached G01-G04 kernels is **not** production milestone
  signoff, and no calibration status is asserted.
- `docs/governance/four-kernel-harness.md` remains the authority on the harness's
  synthetic-only scope; this document does not widen it.
- M68a, M69 and M71 still list M67 as a dependency at `:1272`, `:1274` and
  `:1276`, and full Phase 8 spec drafting waits on M67 (`:1268`).

## Supplied launch contract and unresolved API decisions

The common launch contract was supplied verbatim with the task. Its binding
identities and boundaries are therefore known, and they are what this lane
implemented against:

- Accepted private candidate HEAD `208d140d47d9f2dee0788267f79fa7276df22b42`,
  tree `0762c7cff65e28ff326291ce31111b71e1d61ae3`. All baseline kernels,
  examples, roadmap, dependencies, registry and native code are read-only; this
  lane adds only its four reserved paths; no mutual imports among the three new
  lanes; independent review of actual source bytes precedes integration.
- No public writes and no activation. M71 stays blocked by its cancelled launch,
  serialization `507ef977` stays held, G05 stays permission-blocked with no
  reconstruction or substitute, and V3 stays permanently closed: no new
  scientific worlds, seed sweeps, calibration campaigns, scale runs or revival.
- The existing native object-key-order failure stays documented and full
  A01/native-byte acceptance stays withheld. No lane silently changes a reviewed
  kernel or a global Python integer digit limit.

A checked-in file with that contract is not present in this baseline, but the
absence of a file does not make supplied instructions absent, so no
"missing contract" gap is claimed here. The explicit identities this seam uses
are the reviewed policy id `synthetic-enact-repeal-mock-suppress-v1`, the
synthetic frame origin `explicit_synthetic_fixture`, and a caller-declared
`SourceIdentity` of 40-hex revision and tree plus a human label defaulting to
the accepted HEAD/tree above. `SourceIdentity` is an explicit declaration, not
an on-disk verification: nothing here contacts a repository, a network or a
Drive archive.

Open items that still need an authorized decision:

1. **The measured result does not carry its own opening carry.** `run_kernel_frame`
   publishes only the new carry, so a measurement needs the opening separately.
   The opt-in script obtains it by observing the example's call in-process; that
   wrapper is process-global while it is installed, so it is unsuitable for
   concurrent embedded use. **Decision needed:** whether a future reviewed change
   should expose the opening, or whether interception-by-wrapper becomes the
   accepted convention.
2. **`accession_pool_applied` is derived, not declared.** It is true exactly when
   the accrual opening balance differs from the post-spend balance, which only the
   harness's explicit accession carry/reset policy produces. The measurement never
   classifies a succession or chooses a transfer policy. **Decision needed:**
   whether a declared accession field is preferable.
3. **Opportunity denominators for `enact_rate` / `repeal_rate` are unlocked.** The
   seam reports counts and refuses to invent a denominator.
4. **Regime classifier conventions are unresolved**, as listed above. No default
   is provided by design.
5. **No transport limit exists for exact balances.** `ExactFraction` accepts the
   full public kernel domain and enforces only canonical reduced form with a
   positive denominator. If a future explicit transport cap is wanted, it needs an
   authorized contract rather than a hidden hard-coded bound.

## Verification to run (not claimed here)

The implementing author of this increment did not execute commands in this
checkout; no test result, log hash, exit code or milestone claim is asserted
above. The integrating owner should run, from the checkout root:

```sh
python -m pytest -q tests/test_governance_measurements.py
```

and the affected existing suites:

```sh
python -m pytest -q tests/test_governance_kernel_harness.py tests/test_institutions.py \
  tests/test_elite_metrics.py tests/test_governance_capital.py \
  tests/test_ruler_ambitions.py tests/test_governance_dormancy.py
```

The new suite covers: report values against exact public fields and a
hand-calculated wallet and counts; absent metrics versus true zeros; N versus N+1
epochs; deterministic civilization/enum/civilization ordering under input
permutation; rejection of mismatched, duplicate and misaligned identities and
epochs plus a tampered spend ledger; exact `Fraction` encoding including a
sub-float-view residual; immutable inputs and outputs; extraction invoking no
kernel and no RNG; the disabled result being refused; the default-off report
invoking no example; and byte-stable output across fresh processes with
different `PYTHONHASHSEED` values. Tests marked `slow` or `native` are unrelated
and are not part of this increment.

## Limitations

- One frame, one turn. This seam cannot produce a tenure, rate, distribution,
  co-occurrence or regime label, and does not pretend to.
- It is a reporting seam over synthetic fixtures. It is not calibration, not a
  scientific result, not M67 qualification, and not authorization for Phase 9,
  production scheduling, real enlistment, native storage or calibrated behaviour.
- It changes no reviewed kernel, no global Python digit limit, no CLI registry, no
  snapshot or bundle schema, no analytics or model surface, and no dependency.
- It runs no world generation, no fixture world, no seed campaign and no long-run
  simulation.