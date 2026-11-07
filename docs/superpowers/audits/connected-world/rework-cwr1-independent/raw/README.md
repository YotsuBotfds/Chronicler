# Partial independent CWR1 raw review

**Procedural first-world readback passes: twelve arms × 120 completed turns.**
This packet covers retained p4201 artifacts only, plus one bounded admission
and a development-pilot coverage diagnostic. The full 144-run held screen is
still running. No held causal comparison, whole-cohort completion or
qualification is claimed. Template t4101 raw readback remains pending.

Runtime: `b45c1e99572d4d6a60fb01fbd75cb7688aa54e93` at
`/workspace/cwr-held-runtime`. Closed-row identity:
`98c7bb2accb18b04e68f0585780ba58f85f03ece77c987d82ff67ceb7d9370a8`.
The immutable frozen runtime, protocol and cohort were not changed. All raw
inputs remain outside Git in
`/workspace/evidence/cwr-evaluation/held-cwr1-b45c1e99-v1/`.

The reader imports only the frozen `chronicler.bundle_codec` to decode saved
history deltas, plus PyArrow 26 to read whole IPC sidecars. The only loaded
Chronicler modules are `chronicler` and `chronicler.bundle_codec`; no
`chronicler_agents` module was imported or simulator instantiated. Production
extractors, report helpers and simulation decisions are never called.

## What was independently checked

- All 1,440 completed snapshots have the requested world, scale and dates.
  Raw regional food-availability shortfall, existing epidemic-authority
  deaths, person-turns and supporting observations agree with each closed
  metric row. Epidemic care tick/pathogen diagnostics reconcile with that
  authority without adding overlapping mortality quantities together.
- Actual rules-3 control/frame dates, applied personal and D3 components,
  would-be personal scores, signed merge/clamp when component samples are
  complete, native combined receipt dates/counts, actual information-gate
  Boolean versus would-be masks, work/training decisions and unknown work
  costs, and disabled trade-control implications. D3 remains active in
  record-only; a combined native change is not attributed to one component.
- Public-health factual fields use the preceding X1 frame. The density-only
  added susceptibility factor is 1; legacy uses its declared classified-share
  formula. Current configuration provenance and prior factual provenance are
  distinct. Arrival ratios stay null until the prior rolling 20 fully covered
  writes are complete; X1 region/total count closure and count bounds hold.
- Native food stocks/flows, required nonnegative integer population counts,
  public releases and local public balance observations, owned-food stock
  flows, ration composition and local transaction receipt closure. Native
  availability and observed household access remain separate. Missing retail
  observations remain unknown; positive free food in `no_relief` is retained.
  No globally conserved cash system, housing mechanism or motive is inferred.
- Full Arrow byte hashes, source dates, enum/driver declarations read as data,
  per-turn migration origin/destination flows and native death counts, and
  event-level stable-ID birth/death chronology. Death/birth IDs do not repeat
  within a world, and later events do not reuse a dead actor's ID. Initial
  living IDs, complete households and arbitrary target references are not
  reconstructed from an event file. Famine/war-cause deaths stay unrecorded.

## Explicit limits

Bounded inputs remain bounded evidence. Of 1,440 procedural frame turns,
**656** signed merges can be fully recomputed from exported components;
**784** have capped components and remain unverified at that level. AD has
only 6 complete-component turns and 114 capped-component turns. Counts,
observed samples and combined native receipts are still checked. The
reader does not invent unseen rows or treat input counts as realized causal
effects. Source/native tests and exact-resume evidence are separate gates.

X1 snapshots export regional totals and events, not every person's residence
row. Unclassified trip/unexplained relocations can also advance residence
clocks. Thus bounds and count closure do not independently reconstruct or
prove all unique recent-arrival IDs. The reviewed single writer and lifecycle
tests supply that separate contract. Legacy `newborn_rows` is never used as
a verified birth authority. Different physical worlds are never compared as
though they were identical trajectories.

## Timing budget and retained receipts

| Readback | Actual CPU seconds |
| --- | ---: |
| One AD-p4201 decode/Arrow admission | 4.112537 |
| Twelve p4201 full raw checks | 53.284009 |
| One pilot AD-p19 coverage trace | 4.079712 |
| **Cumulative** | **61.476258** |
| Remaining within 120-CPU-second lane budget | **58.523742** |

Each job was one sequential process with single-thread controls. The first
batch took 53.300 seconds wall time. Peak RSS belongs to the audit process,
not a simulation performance claim. The CPU guard subtracts prior receipts
before allowing a later batch; no limit was raised to conceal contention.

[Admission](admission-AD-p4201.json), [p4201 readback](readback-p4201.json) and
[coverage diagnostic](coverage-pilot-AD-p19.json) preserve observations,
hashes, resource scope and no-native-import proof. The checker writes only
its own new receipt, flushes partial results, retains failures and refuses
an already existing destination. Producer data and the registry are untouched.

## Why boundary all does not mean observed access everywhere

`household_retail._qualifying` (frozen source 785–800) considers every region
under boundary `all` but admits only a controller belonging to a ruler with
regions. The sticky `_update_boundary` (975–1012, called before Phase 2)
closes an enrolled region when it has no controller. Thus the eligibility
recipe is fixed, while realized enrollment/coverage can respond to world
history. It is not a frozen replay schedule or every populated region.

The retained official-pilot AD-p19 diagnostic independently reproduces all
**248** unknown populated region-turns. Every one has an absent retail frame
row, no recorded open enrollment interval and no Phase 2 retail record; none
has a same-turn closure event in its retained log. Their dated public-granary
owner is −1, recorded only as custody evidence, never asserted to be political
ownership. Final `world_state` controller fields are not consulted. The raw
evidence does not identify an individual historical controller or imply that
these people received no food. It explains why a fixed boundary recipe does
not supply a complete household-access observation. Complete access remains
unknown; observed subtotals remain useful within their stated coverage.

## Reproduction

Run a batch only after all twelve named first-world metric rows have closed
successfully. The decoder must come from the independently reviewed frozen
checkout. Example for p4201, with a new receipt destination:

```sh
PYTHONPATH=/workspace/cwr-held-runtime/src RAYON_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  /workspace/cw-b3-offline/bin/python check.py \
  --checkout /workspace/cwr-held-runtime \
  --directory /workspace/evidence/cwr-evaluation/held-cwr1-b45c1e99-v1 \
  --stratum p --expected-source b45c1e99572d4d6a60fb01fbd75cb7688aa54e93 \
  --previous-receipt /path/to/admission-AD-p4201.json \
  --receipt /new/path/readback-p4201.json
```

For t4101 supply `--stratum t` only after closure, with all three prior
resource receipts. The remaining budget is computed cumulatively. Six
constructed selftests cover all control modes, signed merges/caps, rolling
T−1 reads, invalid source/food/count observations, positive no-relief free
food and stable-ID/driver guards. Run `python selftest.py`; these tests do not
import the codec, native code or any simulation module.
