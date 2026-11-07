# Harvest, canopy and basin history

`--harvest-cover` is an opt-in B4 consumer of L3's settled timber stock;
`--harvest-cover-mode record_only` records the same proposals and changes no
canopy. It requires `--agents hybrid --timber-stock`. Both are off by default.
The mode is fixed across exact resume; the feature may be explicitly ended.

After all Phase 2 timber harvesters have settled, each region's standing wood
is summed over its positive-capacity timber slots. If standing/effective
capacity is below 0.30, a gap of `0.05 * (0.30 - ratio)` canopy fraction is
proposed. Applied loss never lowers canopy below the level that supports the
fullest slot's standing wood: healthy canopy times stock/reference capacity.
Multiple timber slots share one canopy. These are declared modelling constants,
not calibrated effects. There is no second timber stock, no new clearing sink,
no draw and no second regeneration authority. L3 still owns standing wood;
Phase 9 ecology still owns canopy regeneration and its existing lag. Existing
watershed routing reads the resulting cover in the normal dated turn order.
Forest cover changes after Phase 2 affect the next production turn.

The completed-turn record names source turn, slots, stock, capacity, ratio,
supported canopy, proposed and applied gap, and canopy before/after. A frame
that did not settle is null, distinct from measured zero and no timber stands.
The reader refuses misdated records and identities that do not close. Historical
snapshots read their own saved frame rather than final-world ecology.

The B5 basin view adds arrows for the saved downstream graph and a table of
upstream/downstream region links. Dashed arrows mark borders only when both
controllers exist in that snapshot's `region_control`. Missing controllers and
coordinates remain unknown. Derived outflow uses the conserved watershed
account's residual, not inferred damage or a causal attribution. Both ends are
keyboard-accessible region links. Older bundles without coordinates retain the
table; bundles without B4 records retain their established panels.

Validation uses development worlds, deterministic contract tests, native exact
resume and default-off comparisons. Bounded screens are not qualification; no
200-seed or procedural qualification is authorized by these additions.
