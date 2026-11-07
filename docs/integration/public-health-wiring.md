# Lead integration instructions for the health lane

The health branch deliberately owns no shared catalog, schema, native or witness
files. Apply these when integrating its commit:

1. `livelihoods_state`: import `PublicHealthState`, append optional `public_health`
   field with `exclude_if=_is_none`; add the switch after `epidemic_care` and before
   `residence_ledger` (the Phase 10 writer must stay after consumers).
2. `livelihoods`: declare the bool switch, module mapping and help. Add optional
   `public_health_mode` choices `active,cost_only`, policy `evidence,shuffled` and
   `public_health_report_delay` integer 0..20 to the standard parameter forwarding,
   resume checks and parser. Default None for parameters preserves saved settings;
   the package defaults are active/evidence/0. Call `public_health.check_request`
   from the shared prerequisite checker after resolving `on(...)`. Call its
   `set_public_health_enabled` through the standard module setter.
3. Feature catalog: hybrid; requires epidemic_care, infrastructure_condition and
   residence_ledger. It additionally requires quarantine_mode closure or cost_only
   (runtime validation). Include invalid startup and exact resume cases.
4. Manifest: include the switch and three parameters only when explicitly given;
   checkpoint/gate forwarding must carry them. Rebuild the integrated reviewed
   inverse layers last, retaining historical pins.
5. `money.PYTHON_PURPOSES`: append `care_supply` (no native code, treasury only).
   No account kind or native purpose is needed. All supply flows live in
   `world.livelihoods.public_health.book` for A1 observation.
6. Register one reviewed aggregate X1 read:
   `('public_health','environment_factors','read_frame'): (1,'aggregate')`.
   Update the guard's historical assertion that all classes are `wiring` to allow
   the newly reviewed aggregate class. No direct state read is allowed.
7. Enroll `tests/test_public_health.py` in one native shard and the oracle lane;
   it is offline safe. Tests temporarily attach the new container slot and inject
   the purpose when run against pre-wiring source, so add integrated startup,
   JSON/checkpoint and compatible-all-switch coverage after the slot is wired.
8. Viewer: import and render `<PublicHealth bundle={bundle} snapshot={snapshot}
   currentTurn={currentTurn} />` alongside `<EpidemicCare>` in `EpidemicsPanel`.
   New reader and component require no shared TypeScript schema edits.

Source changes in epidemic_care, epidemiology and quarantine_rules already call
the new package's hooks. They return neutral results when the slot is absent,
so the feature-off path preserves the old calculations and outputs.

Checks on this branch before integration: C2/quarantine/epidemiology regressions
and new health tests, 141 passed and 3 skipped. This does not substitute for V4–V12
on the integrated source: real native build/tests, feature-off identity against
both references, lifecycle exact resume, catalog, browser journeys, held screen,
profiling and green exact-head CI remain to run. No held seeds have been spent.
