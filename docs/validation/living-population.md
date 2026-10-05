# Terminal living-population validation

The regression report measures territorial civilization survival and living
population separately. Territory, an `alive` flag, or a civilization population
floor cannot prove that any residents remain.

## Terminal evidence

- In hybrid mode, sum final `world_state.regions[].population` only when
  `world_state.turn` explicitly equals `metadata.total_turns`. Count all regions,
  including uncontrolled regions.
- Other modes and legacy bundles require a native agent aggregate at exactly
  `metadata.total_turns`. Undated hybrid region counts also require this fallback.
- An explicit empty terminal native aggregate means zero agents. Never substitute
  the last nonempty, earlier, or later aggregate for terminal evidence.
- Counts must be explicit nonnegative integers. Booleans, negative or fractional
  values, malformed region or native aggregate containers, missing evidence, and
  mismatched terminal turns cannot establish a pass.
- An explicit malformed world-state container is unknown, even if a native
  aggregate exists. An absent world state remains eligible for the legacy
  terminal-aggregate route. Malformed validation sidecars cannot supply native
  evidence; valid dated hybrid regions can still supply population evidence.
- Aggregate turn keys must be canonical nonnegative decimal strings. Malformed
  keys cannot contribute satisfaction, occupation, Gini, or population evidence.

## Decisions and diagnostics

Both strict and calibrated regression decisions require a positive known terminal
population for every run. This is a minimal existence check, not a viable-size,
growth, food-security, or healthy-world threshold. No simulation rule or population
floor changes.

The report preserves territorial survival fields and adds
`final_living_population_by_seed`, `final_living_population_counts`,
`living_population_ok`, `extinct_world_count`, `extinct_world_fraction`,
`population_unknown_run_count`, and `population_evidence_run_fraction`.
Per-seed evidence records its source, terminal turn, and any rejection reason.
Unknown evidence is distinct from extinction; the extinction fraction uses only
measured runs. A batch with unknown evidence still fails the living-population
check.

Existing input-free regression cases may still report `SKIP`; the full profile
rejects that status. Such cases need not contain per-seed population diagnostics.

The full profile requires regression to pass. The subset profile keeps regression
informational under its existing contract: a subset overall pass does not certify
population survival or simulation balance.

## Compatibility

Existing report fields and CLI interfaces remain available. Older bundles lacking
trustworthy terminal evidence may newly fail closed instead of receiving a pass.
This intentional validation change does not alter their simulation or reinterpret
missing evidence as extinction. A verified terminal native aggregate remains the
legacy compatibility route.

These contracts are tested with literal authored counts and deliberately
misleading territorial/alive metadata. They do not claim a new simulation cohort,
reproduction of historical population results, or a repair to population balance.
