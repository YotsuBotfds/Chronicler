# Documentation map

Current guidance lives in a few files; nearly everything else is a dated record
that describes the source, platform and qualification it actually tested.
Treat dated records as evidence, not instructions.

## Start here

| Document | Use it for |
| --- | --- |
| [RECOVERY.md](RECOVERY.md) | Current source identity, private archives, safe restoration, open gates. |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Setup, test lanes, native builds, gate commands. |
| [CONTINUATION.md](CONTINUATION.md) | Continuation ledger: current state on top, dated handoffs below. |
| [local-simulate-view-resume.md](local-simulate-view-resume.md) | Walkthrough: simulate, view, resume exactly. |
| [superpowers/progress/phase-6-progress.md](superpowers/progress/phase-6-progress.md) | Milestone ledger (newest entries first). |
| [../AGENTS.md](../AGENTS.md) | Contracts and working rules for agents. |

## Simulation systems

One reference per system in [`integration/`](integration/). Code comments
link to these by path, so keep their names stable.

- **Polities and conflict:** [diplomacy](integration/diplomacy.md),
  [campaigns, battles, occupation](war/campaigns-battles-occupation.md),
  [maritime](integration/maritime.md), [nomads](integration/nomads.md),
  [great-person agendas](integration/great-person-agendas.md),
  [agent movements](integration/agent-movements.md).
- **Settlement and economy:** [cities](integration/cities.md),
  [city markets](integration/city-markets.md), [guilds](integration/guilds.md),
  [bulk trade and crafts](integration/bulk-trade-crafts.md),
  [money and credit](integration/money-credit.md),
  [domestic credit](integration/domestic-credit.md),
  [production ledger](integration/production-ledger.md),
  [contact ledger](integration/contact-ledger.md).
- **Food and population:** [farmland and climate](integration/farmland-climate.md),
  [grain reserves](integration/grain-reserves.md),
  [hunger mortality](integration/hunger-mortality.md),
  [food accounting](integration/food-accounting.md),
  [population entities](integration/population-entities.md),
  [healthy migration](integration/healthy-migration.md),
  [refugee routing](integration/refugee-routing.md),
  [epidemiology](integration/epidemiology.md),
  [health care](integration/health-care.md).
- **Culture and knowledge:** [techniques](integration/techniques.md),
  [languages](integration/languages.md),
  [historiography](integration/historiography.md),
  [scholarship](integration/scholarship.md),
  [permanent faiths](integration/permanent-faiths.md),
  [ritual gatherings](integration/ritual-gatherings.md),
  [causal provenance](integration/causal-provenance.md).
- **Livelihoods and commons (experimental, every switch default off):**
  [staffed public workshops](integration/workshops.md),
  [household food allocation](integration/food-allocation.md),
  [timber stock](integration/timber-stock.md),
  [grain convoys](integration/grain-convoys.md),
  [commons rules](integration/commons-rules.md),
  [learning cohorts](integration/learning-cohorts.md),
  [workshop finance and payroll](integration/workshop-finance.md),
  [relocation costs](integration/relocation-costs.md),
  [household purchases (design, left open)](integration/household-purchases-design.md),
  [local budgets](integration/local-budgets.md),
  [clearing protection](integration/clearing-protection.md),
  [workshop apprenticeship](integration/apprenticeship.md),
  [repair projects](integration/repair-projects.md),
  [recovery crews](integration/recovery-crews.md),
  [maintenance obligation](integration/maintenance-obligation.md),
  [veteran reintegration](integration/veteran-reintegration.md),
  [remittances and the diaspora ledger](integration/remittances.md),
  [workshop operating wear](integration/operating-wear.md),
  [timber supply (woodcutting expeditions)](integration/timber-supply.md),
  [household food retail (design)](integration/household-retail-design.md),
  [feature options in Batch Lab and live setup](integration/feature-options.md); plans in
  [sprint 1](superpowers/roadmaps/livelihoods-commons-sprint1.md),
  [sprint 2](superpowers/roadmaps/livelihoods-commons-sprint2.md) and the
  [recovery-skills phase](superpowers/roadmaps/recovery-skills-phase.md)
  ([screens](superpowers/progress/recovery-skills-screens.md)) and the
  [productive-recovery phase](superpowers/roadmaps/productive-recovery-phase.md)
  ([board](superpowers/progress/productive-recovery.json),
  [checkpoint-1 screens](superpowers/progress/productive-recovery-screens-cp1.md),
  [checkpoint-1 examples](superpowers/progress/productive-recovery-examples.md),
  [checkpoint-2 screens, draft](superpowers/progress/productive-recovery-screens-cp2.md)).
- **World generation:** [geography 2.0](integration/geography-2.md),
  [procedural gates](integration/procedural-gates.md).

## Validation and qualification

[Validation integrity](integration/validation-integrity.md),
[the validation module split](integration/validation-split.md),
[ablation oracles](integration/ablation-oracles.md),
[community anchoring](integration/community-anchoring.md),
[spec communities](integration/spec-communities.md), the `needs-*` and
`oracle-followups` notes in `integration/`, [`validation/`](validation/),
the [Python qualification supervisor](integration/python-qualification-supervisor.md)
and the [parent-extra archive](integration/parent-extra-archive.md).

## Runs, checkpoints and narration

[Checkpoint continuation](integration/checkpoint-continuation.md),
[checkpoint replay](checkpoint-replay.md),
[live what-if](integration/live-what-if.md),
[history forensics](integration/history-forensics.md),
[example worlds](integration/exploring-example-worlds.md),
[world laboratory](integration/exploring-world-laboratory.md), and the
narration notes ([coverage](integration/narration-coverage.md),
[provenance](integration/narration-provenance.md),
[system expansion](integration/narration-system-expansion.md)).

## Viewer

[`viewer/`](viewer/) holds the inspector and demonstration-page guides;
[viewer systems](integration/viewer-systems.md) covers the system panels and
map layers. Feature views: [granaries](integration/granary-view.md),
[transactions](integration/transactions-view.md),
[scientific claims](integration/scientific-claims-view.md),
[research agendas](integration/scientific-research-view.md),
[expansion inspectors](integration/expansion-inspectors.md),
[city institutions](integration/city-institution-history.md),
[entity search](integration/historical-entity-search.md),
[feature options in Batch Lab and live setup](integration/feature-options.md). Commands and pages are in
[`viewer/README.md`](../viewer/README.md).

## Default-off experiments

[`experiments/`](experiments/), [`governance/`](governance/),
[`a01/`](a01/), the `expansion-*`, `crisis-*`, `*-candidate` and
`*-preregistration` notes in `integration/`, and the
[crisis roadmap](integration/crisis-recovery-roadmap.md). A detached kernel or
recorded result does not activate or qualify a production feature.

## Performance and CI

[`performance/`](performance/) holds measurements and preregistrations.
[`workflows/`](workflows/) holds closed CI qualification workflows; tests pin
these `.yml.in` copies byte for byte against `.github/workflows/`.

## Historical records

- `superpowers/`: phase roadmaps, milestone plans and specs, audits (including
  the April 2026 audits that used to sit at the repository root), analytics
  and prompts from the March–October 2026 build-out.
- Dated `integration/*-2026-*` reports, ledgers and JSON evidence, plus
  [`handoffs/`](handoffs/).

These keep their original paths, commands and machine-specific locations.
[RECOVERY.md](RECOVERY.md) explains which locations are portable.

## Removed paths

The 2026-11-04 cleanup removed superseded static prototypes and dead viewer code.
Main commit `bd1693f` still holds them; recover any file with
`git show bd1693f:<path>`:

- `prototype/` (including `prototype/gpt5/`) and `viewer/antigravity-prototype/`:
  static shell prototypes from the M62b planning, superseded by the viewer.
- `viewer/src/components/Layout.tsx`: the original M11 layout, which nothing imported.
- `docs/plans/2026-03-12-civilization-chronicle-generator.md`: a byte-identical
  copy of the file in `superpowers/plans/`.

The same cleanup moved docs-only scripts to [`scripts/archive/`](../scripts/archive/README.md);
`build_learning_fixture.py` and `generate_viewer_fixture.py`, which generate
checked-in viewer fixtures, are back in `scripts/`.
