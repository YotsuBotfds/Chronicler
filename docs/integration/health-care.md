# Temporary rural impairment and spouse care

Status: default-off experimental production slice, `--health-care`, hybrid
only when explicitly enabled. Loaded state can remain dormant in other modes;
omitting the flag preserves it. This is not a disease or disability simulator.

## Scope and ownership

An adult native farmer (age at least `AGE_ADULT`, currently 20), outside a
living city's craft-sharing settlement, not travelling or enlisted at the
economy boundary, contributes manual work. A region must realize some slot
production or foraging that turn before its workers face the injury draw.
The existing economy does not assign individual farmers to individual slots:
this is regional work exposure, not an invented record of who mined ore.
Only workers still alive with the same stable ID after the native tick can
acquire an episode. Draws use an isolated native stream (offset 0x4843), not
the demographic or behavior RNG. New episodes first affect the next turn.

The initial parameters are fixed before world qualification: injury chance
0.01 per available worker-turn; impairment 0.5 worker-turn; recovery work 2;
an eligible co-resident spouse may supply 0.2 worker-turn. Natural recovery
progress is 1 per turn; care adds `min(1, 5 * care_work)`. These are game
parameters in simulation turns, not clinical recovery-time claims. The existing
biographical, resource-season and epidemic clocks have different abstractions.

An impaired patient cannot also be a caregiver. A caregiver supplies at most
one allocation, selected in patient stable-ID order, and must meet the same
rural, adult, available-farmer conditions. There is no new household registry.
Occupation changes do not erase an episode; this pilot affects manual farm
work only, so a patient currently working in another occupation has natural
recovery but no manual-work deduction or spouse-care allocation.

Lost impairment and care time is subtracted once from the region's productive
farm labor after the existing city labor allocation and before diminishing
returns. City craft input is untouched. Population and occupation counts and
all per-person food demand remain unchanged. The corresponding farmer's work
income is multiplied once by remaining availability before ordinary decay,
clamping and wealth ranking. Wealth stock, transfers, inheritance and taxes
are not separately reduced. Disease, battle resolution, mortality rates,
fertility, military rosters and migration rules are unchanged; later food,
wealth and behavioral feedback may still change those outcomes.

## State and phase contract

`WorldState.health_care` is the optional authoritative state. Sparse episodes
hold stable agent ID, onset turn, remaining recovery work and origin region.
There are no persistent slots or lifetime medical histories. The completed
summary freezes region/civ names and indices and records worker-turns lost,
care allocations, recovery progress, new episodes and recoveries. It is only
exported for the immediately completed source turn; dormant, stale, future
and missing records are unrecorded, not zeroes.

Before the goods tick, `prepare_health_care` resolves patients and spouses and
replaces native work inputs. After the native agent tick, `finish_health_care`
consumes them, removes dead IDs, advances survivors and records new injuries.
Work costs belong to the work region; active episodes follow the patient's
completed-turn location after migration. Native income consumes its inputs
once, guarded by expected stable ID so reused slots cannot inherit a loss.

The native work cache and slot-indexed income inputs are explicitly skipped
by native persistence. Their fields do not change the native state schema;
restoring an exact checkpoint rebuilds them from Python before the next goods
tick. These are turn-boundary checkpoints: a hand-made native-only checkpoint
inside preparation/economy is not a complete health continuation. The compiled
extension identity still changes, so an old binary's exact checkpoint remains
subject to the existing fail-closed identity checks. No migration waiver is
introduced. Raw state saves do not become exact native continuations.

## Preregistered acceptance and ablations

Before flag-on world probes or gates, the following are the acceptance rules.
Retain failures and do not tune parameters against confirmatory seeds.

1. Disabled: run files, snapshots, RNG behavior and native payload schemas
   match the baseline; the new state is absent. Existing aggregate/shadow
   behavior is unaffected when an old saved health state is dormant.
2. Controlled injected cohort with new injury rate zero: care retires recovery
   work sooner than no care, while care consumes the prescribed productive
   time and corresponding income. Smaller care allocations give smaller
   recovery progress, not a full benefit for an arbitrarily small payment.
3. At each assignment, productive availability plus impairment plus care is
   at most one per worker. No enlisted, urban craft-sharing, travelling,
   underage or already-impaired caregiver supplies care. Demand still follows
   living people, not reduced labor. No direct deaths or births are written.
4. Unknown/dead IDs, slot reuse, migration, spouse absence and repeated
   preparation/consumption cannot retain stale deductions. A second income
   consumption receives normal income; a second finish cannot create injuries.
5. Exact resume mid-episode and after caregiver death/movement matches a
   continuous run, including summaries and subsequent episode draws. Compare
   fresh processes and supported thread counts; hash iteration must not reach
   floating-point accumulation order.
6. Development probe: fixed template seeds 900–909, 100 turns, and procedural
   32x10 seeds 900–904, 100 turns. Report exposure, onsets, impaired/care
   person-turns, recovery with competing deaths, production, population and
   needs without selecting only surviving or treated-famine observations.
7. Held-out confirmation: template 42–61 x 200, procedural 42–61 x 200;
   paired enabled/no-care and disabled arms. Controlled-cohort tests establish
   recovery causality; natural world differences include feedback and do not
   promise identical injury cohorts. Full documented before/after gates are
   required before promotion; bounded checks do not qualify default-on use.
8. Performance: compare 100k and 1M agent cases at the same populations and
   durations, recording whole-turn CPU/wall, memory, checkpoint bytes/time and
   event volume. Persistent state scales with active episodes. This first
   implementation also keeps a transient worker list and optional dense
   income inputs; sparse persistence is not a claim of sparse total memory
   or zero additional scans. The roadmap's 2% budget is unmeasured.

## Verification standing

Focused Python controlled tests pass (5 at initial implementation). Rust
tests cover budget/eligibility, income consumption, slot reuse, stable ordering,
survivor/actual-work selection and persistence exclusion; compilation, enabled
native integration, exact resume and world gates are pending a fresh central
native build. No empirical production, balance or performance qualification
is claimed here.
