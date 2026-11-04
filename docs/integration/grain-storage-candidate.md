# Public grain storage candidate

Storage is an opt-in, version-1 public-granary asset. Enable it with
`--agents hybrid --grain-reserves --grain-storage`. `--grain-storage-policy`
selects `neglect`, `maintain` or `expand`; `--grain-storage-work-budget` is a
finite 0–4 farmer-equivalent work per region per turn. The defaults are
`neglect` and zero work. These choices are model assumptions, not calibrated
policy recommendations. Saved storage is dormant with agents off; a newly
explicitly enabled storage run requires hybrid mode and public granaries.

At the first successful economy tick, each granary inherits a condition-1
asset with built capacity equal to the greater of its existing public grain
and four times its current regional Phase-2 food demand. Capacity and grain
are model food-goods units, condition is in [0, 1], and each tick wears
condition by 0.01. Effective capacity is built capacity times condition;
spoilage adds up to 0.07 to the normal rate as condition falls to zero.
Four delivered work restores 0.10 condition after wear, capped at 1; twelve
work adds the greater of four units or 25% of built capacity. Partial work
persists. The asset, condition and unfinished work remain in the region through
conquest or abandonment; custody changes and condition continues to wear.

Before the native economy, the plan reserves only physical regional timber
left free after merchant commitments, limited by the policy budget, remaining
batch work and available owner treasury. Delivered work is bounded by native
farmer-equivalent labor available after city and health deductions and reduces
that turn's land-production labor. This is an aggregate quantity, not a
roster of identified workers. Each delivered work consumes one timber and two
whole treasury units, rounded up per region. Only delivered work is charged;
unused reserved timber returns after native execution. A failed native call
rolls back the timber hold, without promising to undo a native kernel's work.

Public release and spoilage occur in Phase 2. After later arrivals, the Phase-10
capacity settlement caps the requested reserve target and returns excess public
grain to the regional market as a recorded `storage_returned` flow. That return
is available for a later native consumption step; it is not retroactively eaten
in the earlier Phase-2 food account. The storage receipt records source turn,
region and owner indices, policy, requested and delivered work, timber held,
used and returned, treasury paid, before/after condition and capacity,
unfinished progress, requested and feasible targets, and capacity returned.
The snapshot exposes the persisted assets, policies and latest completed
receipts under `grain_reserves.storage`; old bundles without that field leave
storage unknown.

Exact checkpoints persist the asset, policy, work progress and receipts and
must be written at completed turn boundaries, never while a work plan is
pending. A checkpoint resume preserves its configuration; conflicting storage
flags are rejected. A saved state JSON is a legacy, non-exact resume. The
native partial-expansion control compared continuation of Python state,
native checkpoint bytes, observations and RNG across three subsequent turns.

## Constructed evidence

The real native controls use declared constructed worlds, not held-out natural
runs. With a 2,000-unit public reserve and 1,000 market grain, four paid work
used four timber and eight treasury, moved condition from 0.50 to 0.59 after
wear, and left more public grain than neglect while reducing current native
production. In an empty-reserve, empty-market case with eight treasury, paid
maintenance reduced native consumption and sufficiency while neither policy
released public grain. The same intervention can therefore preserve existing
stores or worsen a present shortfall; these cases do not establish a general
policy ranking.

A separate damaged-asset case with explicitly constructed volatile harvest
history recorded target 200, feasible target 1.9 and 89.43 units returned to
the market. An earlier damaged-opening example did return grain but failed the
requested-target-cap precondition because it had no recorded harvest
variability and the procurement rule requested no excess target. The later
fixture supplies that history; it is not evidence of a naturally occurring
shock or a calibrated outcome.

The default-off comparison used seed 42 for eight turns in off, hybrid, shadow
and demographics-only modes, with M2 receipts disabled in both runs. Independent
M1 and candidate native wheels produced identical retained artifacts and RNG
traces: 39 artifacts and 24 native turn states across the four pairs, without
stripping export fields. This is bounded evidence, not a 200-seed gate, a
full-CI result or proof of general balance. The source inverse independently
checks reviewed lineage and does not establish runtime parity.

## Reproducing and reading the recorded example

The recorded labelled example was launched by the following generator in the
existing integration environment. It constructs its initial world explicitly,
uses seed 42 and writes the example output and checkpoints under the shared
`examples/labelled/stored-harvest/maintain` directory; rerunning it replaces
those output files. The environment and paths are local to this workspace.

```bash
/workspace/shared/chronicler-crisis/envs/m3-integration/bin/python \
  /workspace/shared/chronicler-crisis/m3-integration/generate-labelled-example.py
```

To load the existing recorded bundle and inspect its first receipt from the
integration checkout:

```bash
cd /workspace/Chronicler-crisis-integration
PYTHONPATH=src:. /workspace/shared/chronicler-crisis/envs/m3-integration/bin/python -c \
  'from chronicler.bundle_codec import load_bundle; b = load_bundle("/workspace/shared/chronicler-crisis/m3-integration/examples/labelled/stored-harvest/maintain/chronicle_bundle.json"); print(b["history"][0]["grain_reserves"]["storage"]["receipts"][0])'
```

The generator passes `--agents hybrid --grain-reserves --grain-storage`,
`--simulate-only`, and `--checkpoint-every 2`; it supplies the constructed
world and per-region policy in Python. Its result must not be presented as an
ordinary CLI-generated initial world. The checkpoint and example evidence are
workspace artifacts, not a promise that a different build will resume them
without the checkpoint identity checks.
