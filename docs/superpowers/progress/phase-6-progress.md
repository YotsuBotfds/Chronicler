# Phase 6+7 Progress — Living Society + Depth Track

> Forward-looking decisions and active items only. Implemented/merged content lives in git history.
>
> **Last updated:** 2026-10-26 (`fix/procedural-open-items`, merged with `main` `18a05be`: named characters reopened (living caps, one per 50 agents of a civ, held within a batch; agent-born promotion artifacts at chance 0.15), calls to arms and federation defence only within reach, faction and merchant accuracy bonuses only toward civs in contact, the Gini summed exactly (machine-independent); restorations' excess traced to larger realms, lower stability and hybrid counter-restorations (documented, not changed; the black-market per-region repeat measured and not shipped); golden oracles rolled forward (`open_items`); template full gate PASS strict, NO REGRESSION (needs 171 of 200, artifacts 1.77), procedural full gate PASS strict, NO REGRESSION (needs 91 of 100, artifacts 2.41, fiscal crises 1.40 -> 1.59).) Before: 2026-10-26 (`feat/scholarship`, from `main` `fc01d6e`, merged with `b8f0243`: seats of learning behind `--scholarship`, default off (academies, temple schools, libraries; scholars, upkeep, strikes, flight with techniques and archives; a fifth healthy-world migration driver in Rust); template full 200 x 500 and procedural full 100 x 300 with the switch on PASS strict, NO REGRESSION against main; switch off byte-identical to `fc01d6e` and `b8f0243` (9-case matrix); courts' and temples' accounts lost 20% -> 15%; technique counts within noise; kept off at the review bar.) Before: 2026-10-26 (`fix/historical-parity` from `main` `fc01d6e`: narration, curation, live transport and viewer only; every simulation output byte identical. All six review findings reproduced on `fc01d6e` and fixed. Open: no native/hybrid run, no LLM, no browser QA.) Before: 2026-10-26 (`perf/turn-speed`, from `main` `b3ad9a4`, merged with `c8f7eb4`: turns faster with every output byte identical (9-case identity matrix after each of 11 commits, subset gate 42-61 reproduced): process CPU per turn 2.64x at 52k agents, 2.12x at 22k, 1.11x on procedural 48 x 10, 1.17x on the gate world; exact spatial drift in lanes of 8 agents per cell, field-level `exclude_if` instead of wrap serializers (pydantic floor 2.12), a short OpenBLAS idle spin, politics op batches, knowledge propagation and an id -> slot table in five native phases, fishery counts, schema-name reads and memory-stream text; found: `compute_gini`'s `np.dot` gives different bits with different OpenBLAS thread counts above 10,000 values (not changed); open: drift still 71% of the native tick at 52k, marriage, governance, checkpoint serialization, GC). Before: 2026-10-26 (`feat/procedural-gates`, merged with `main` `b3ad9a4`: the gate runner's `--worldgen procedural` profile, a 32-region, 10-civ world per seed, subset 20 x 200 and full 100 x 300 (a procedural seed costs 3.2 template seeds of CPU; the full profile runs in 40-45 minutes on three workers, 2.5 GB validation peak); the artifact oracle counts per starting civ, not a fixed 4 (template reports byte-identical), reports name non-template worlds and the comparator will not mix them; on `main` the procedural full gate failed artifacts only (5.38 per starting civ per 100 turns, artworks over half) because an aggregate merchant hub needed 3 live trade partners, every other civ on templates but ordinary among ten (hub civ-turns 74-84% against 2-8%); a hub now trades with every other living civ, at least three: procedural full gate on the merged head PASS strict (artifacts 2.00; `b3ad9a4` without the fix FAIL, 5.32), template full gate on the merged head PASS strict, NO REGRESSION against `b3ad9a4` (8 of 200 worlds differ; migration 0.0635, rebellion 0.0330, needs 174 of 200, 0 extinct); template-vs-procedural system table; open: calls to arms across the map with war-chest borrowing (fiscal crises 3.7 times the template rate per civ), accuracy bonuses toward civs never met, pretender restorations, the 50-character native registry (both worlds), epidemic deaths per head 1.7 times, spiritual need; slow procedural smoke test through the gate path). Before: 2026-10-26 (`fix/movements-narration-polish`, from `main` `2dd47d4`: movements founded with no members (every movement stood empty in the snapshot after its founding turn, because its founders joined on the next tick, and emptied movements stood until the 5-turn fade: 427 of 7,395 living snapshots in subsets 42-61 and 62-81) fixed: founders enrolled natively at founding (`found_movement`, no draw), a founding nobody can join not made, a movement with no member left ended at once; 0 empty snapshots after (82,037 in the full gate); subsets PASS, NO REGRESSION; full gate PASS strict, NO REGRESSION against the guilds report (needs lower bound 0.196 -> 0.191, binding 0.178 -> 0.170, migration 0.0634, rebellion 0.0368 -> 0.0329, 0 extinct); narration and chronicles only, simulation state identical: a founding sparked by news of a like movement's won demand cites it (about one per run), chroniclers tell guild formations, charters and risings, the curator fills untold stretches longer than two even spacings (template 42 longest untold 30 -> 18 turns, procedural 18 -> 12). Before: 2026-10-26 (`feat/narration-coverage`, merged with `main` `aa0f655`: narration only; the curated narrator's prompts list at most 12 events (plus 4 for unshown turning points), fold repeats and count the rest, and carry a STANDING STATE (rulers, wars, movements and martyred leaders, reforms, cities, guilds and burghers, food with its recorded dearth or famine) and LATER CONSEQUENCES; labels for the 14 types recorded without a description, 4 misleading descriptions reworded; curator chain bonus x0.4, routine kinds at importance, turning points up, frequent kinds down, one-great-event cluster score, landmark-only diversity exemption; prompts 22.0k -> 10.7k / 101.5k -> 16.2k / 23.6k -> 10.6k characters (template 500, procedural 48x10 400, template 300), every turning point in a selected moment listed; viewer: food crises at their snapshot (76% shown a turn early), unobserved regions last, wares to two decimals, creed legend, martyred leaders, movement record note; simulation byte-identical). Before: 2026-10-26 (`feat/guilds`, merged with `main` `11238d5`: guilds, burghers and movement news behind `--guilds`, on by default after its full gate: city guilds (craft guilds where wares are made, merchant guilds where merchants and craftworkers reach 4) with privileges granted with charters (a wares monopoly with market rights, a say in dues with self-government), a share of city commerce and help with walls; levies, revoked charters, sacks, occupations and repealed guild charters raise movements of a new `guild` creed (members through `movement_id`) whose reform is a lasting guild charter under Merchant Courts; a burgher faction (`FactionType.BURGHER`, appended) in realms with chartered or free cities or guilds (trade, low tolls, charters, order); movement foundings, risings, reforms and crackdowns as information packets (type 4) in the region and, at half intensity, its neighbours, never displacing other packets; news of a like movement elsewhere raises joining (up to x2) and founding (up to x2): over 40 paired worlds significant movements +16% and risings +34%, foundings +4% (within noise); subsets 42-61 and 62-81 PASS, NO REGRESSION; full gates PASS strict, NO REGRESSION against trade-crafts (needs lower bound 0.177 -> 0.201) and, merged, against needs-followups (0.204 -> 0.196, binding 0.168 -> 0.178, migration 0.0644, rebellion 0.0368, 0 extinct); `--no-guilds` byte-identical to `main` (88 files). Before: 2026-10-26 (`fix/needs-followups`, merged with `main` `2ef3097`: needs oracle method 3 adds a binding component, pairs across a need's threshold (lower agent below, partner at or above, gap above 0.05) with their own seed-clustered lower bound, required in the full profile and informational in the subset profile (too noisy there); subset verdicts with the terms on PASS 6 of 6 (main and head); full rules on the subsets: terms on 5 of 6, zeroed FAIL 6 of 6, 59 of 60 shuffles FAIL; newborns start from the birth parent's needs (youngest-minus-adult gap 0.02-0.09 -> under 0.01; spiritual now binds 24%); a move no longer blocks autonomy restoration (good-condition binding 5.3% -> 1.4%); hunger mid range still fails the needs subset 42-61; full gate PASS strict, NO REGRESSION against the trade-crafts report (needs method 3 176 of 200, binding +0.192 lower bound +0.168, migration 0.0642, rebellion 0.0360, 0 extinct). Before: 2026-10-26 (`feat/bulk-trade-crafts`, merged with `main` `f5425dc`: merchant loads by mode of travel (2 overland, 5 by river, 10 by sea) filled while the next load earns the one-load threshold against committed deliveries; mines and forests saturate on their own capacity (deposit, woodland), not the farmland's; a ninth good, wares, made in cities from timber and ore, used everywhere (material need), traded, counted in city commerce; against `main` `f5425dc`: food delivered to famine regions +22% / +27% (template / procedural), city import share 1.12 -> 1.41% / 1.38 -> 2.11%, merchant income +58%, herding 0.80 -> 0.64; most loads stay under one unit (thin markets); subsets 42-61 and 62-81 PASS, NO REGRESSION; full gate PASS strict, NO REGRESSION against the movements-on report (needs 190 of 200, migration 0.0615, rebellion 0.0388, latest satisfaction 0.627, 0 extinct); with every switch off and agents off byte-identical to `main`; golden fixtures unchanged. Before: 2026-10-26 (`feat/movements-2`: movements slice 2 and movements on by default: a granted demand enacts a lasting reform (poor relief with Commons Management, home rule with Written Law and a city charter, toleration or a church reform that ends a Holy Inquisition) whose covered agents read their creed need with a 0.3 credit; repeal by a collapsed or forced-out institution, a new ruler, the opposing faction, unpaid upkeep or a new Inquisition, and restoration movements; leaders promoted natively from the boldest member, crowned by a secession; viewer Movements tab; grievance recalibrated for the corrected needs (material 0.45, autonomy 0.50: 20.5 movements and 3.0 significant per 500-turn template world, none founded where conditions are good, against 26.9 and 5.2 with the old thresholds); full gate with the switch on PASS strict, NO REGRESSION against needs calibration (migration 0.0629, rebellion 0.0409, needs 188 of 200, 0 extinct); switch off byte-identical (88 files and the 42-61 subset gate). `fix/needs-calibration`: the agents' needs follow their conditions (faster decay and restoration, condition pressures, new `harsh_rule` and `raided_this_turn` batch columns; social restored only by bonds in the agent's region; social and autonomy thresholds 0.35) and bind under bad conditions (safety in contested regions at war 32%, material in famine 44%, social without a co-resident bond 26%, autonomy under persecution 37%; good conditions 0.8-2.9%, autonomy 5.7%) against at most 0.2% before; a social deficit pushes migration (driver code 18) instead of staying; full gate PASS strict, NO REGRESSION against farmland (migration 0.0626, rebellion 0.0385, needs 190 of 200, 0 extinct); with the terms zeroed the needs oracle still passes 3 of 3 subsets (target not met). `feat/farmland-climate`: diminishing returns to farm labour (output per farmer falls as farmers crowd the land's arable capacity, raised by farming techniques and irrigation; farmer income follows; the agents-off famine check reads food per head) and regional climate (the global phase keeps half its crop and water effects as the long trend, the rest comes as bad harvest years of clusters of neighbouring regions); hunger terms raised part way (deaths famine 0.50 -> 1.00, births 0.30 -> 0.45; the mid-range 1.50 / 0.60 failed the needs subset 42-61); template famines 11.5 -> 8.1 turns, 20+-turn episodes 30% -> 11%, turns with three quarters of a world in famine 15.6% -> 6.7%; golden oracles rolled forward; full gate PASS strict, NO REGRESSION against the hunger head (migration 0.0610, needs method 2 182 of 200, 0 extinct). `fix/needs-oracle-power`: the needs oracle pools every snapshot and pairing (need gap 0.1, matching otherwise unchanged) and passes on a seed-clustered 95% lower bound of net concordance plus the 60% seed fraction; main subsets 42-61, 62-81, 82-101 PASS (+0.18, +0.20, +0.33), routing `--no-cities` 62-81 FAIL -> PASS, `--agent-movements` 42-61 PASS; needs shuffled in cells FAIL 15 of 15 (method 1 passed 10); need terms zeroed in Rust not reliably caught (1 of 3); comparator flags a method change instead of a new failure; full gate not run. `feat/agent-movements`: movements grounded in people behind `--agent-movements`, default off: per-agent membership (a Rust pool and snapshot column), commons, liberty and sect creeds founded where grievances cluster, recruitment through bonds, co-residence and settlements, demands, reforms, refusals, crackdowns with martyrs, risings, secession through the shared free-city transfer, schisms through the religion path; switch off byte-identical (88 files and the subset gate 42-61); subset gates 42-61, 62-81 and 82-101 PASS / NO REGRESSION with it on (needs 16 -> 12, 13, 14); full gate not run. `feat/city-markets`: merchant routing by price for every good, market packets and a committed-cargo tally against herding (food to short regions 62% -> 80%); cities as markets (city farmers' labour, craft demand, sieges cut supply); viewer Cities tab; cities on by default for new worlds after a full gate with them on: PASS strict, NO REGRESSION against main `3355289` and Wave 8 (migration 0.0580, rebellion 0.0308, needs 189 of 200, 0 extinct). `fix/navigation-famine-labels`: maritime navigation reads the known navigation techniques (full gate PASS strict, NO REGRESSION against Wave 8: migration 0.0576, rebellion 0.0314, needs 196 of 200, 0 extinct); food-crisis reports labelled famine (below 0.6 for a season) or dearth with unchanged effects; mass_migration carries its migration driver. `feat/cities` from `integrate/wave-7` `bcf14d8`, merged with `main` `a95e4d7` (Wave 8 defaults): cities as historical actors behind `--cities`, default off: M56a settlements grown into towns and cities with commerce, dues, charters, urban revolts and free cities, sacks, walls and falls, a Rust urban pull migration driver; switch off byte-identical (88 files); subset gates 42-61 and 62-81 PASS / NO REGRESSION with it on, before and after the merge. Before: `feat/defaults-wave8`: great-person agendas, maritime and nomads on by default for new worlds; full gate PASS strict, NO REGRESSION against Wave 7 (migration 0.0576, rebellion 0.0317, needs 194 of 200, 0 extinct). `integrate/wave-7`: `feat/healthy-migration`: frontier (land, farmers), wage-gap and chain migration behind their own gates, net of life-course roots; calibrated on the merged world, full gate PASS with migration 0.0570 (strict floor). `fix/food-logistics`: merchants route food by the destination's food price; subsistence floor; locust rate 0.15 -> 0.02. `fix/needs-oracle-confound`: the needs oracle pairs autonomy only among agents that have not rebelled. `fix/leftover-persecution`: persecution follows the current ruler every turn Merged with `main` plus `feat/viewer-systems`: `feat/viewer-systems` from `main` `6e6fae6`: viewer tabs for wars, food, nomads, agendas, governance and the contact ledger; six thematic map layers; viewer-only `food` and `migration` snapshot fields. `feat/languages` from `main` `baabafb`: in-world languages and names, observational, on by default. 2026-10-24: `fix/food-logistics`: merchants route food by the destination's food price; the goods economy gets M34's subsistence floor; locust swarms recalibrated 0.15 -> 0.02 per eligible turn; merged with `integrate/wave-6`. `fix/needs-oracle-confound`: the needs oracle's autonomy pairing leaves out prior rebels; the offline oracle lane runs in four guarded chunks. `fix/agenda-preaching`: great-person agendas' rebellion tail traced to left-over persecution intensity; prophets kept out of persecution and foreign faiths' realms. `feat/historiography` on `integrate/wave-5`: in-world chroniclers and archives, observational, on by default; techniques on by default; great-person agendas and nomads default off; bundle version 5 prunes dead civs from history snapshots; dead civs earn no income Merged with `main` after `feat/hunger-mortality`: hunger kills and lowers births in agent modes, graded by severity: deaths of the young, the old and the poor up to +55% in a sustained total famine (famine death rate 1.54 -> 1.96 times fed), births down by up to 10% in dearth and 37% in famine, a rebound after, epidemic susceptibility and fatality follow measured hunger, a dearth weighs a third of a famine in unrest; the `--agents off` famine toll scales with severity; golden oracles rolled forward; full gate PASS strict, NO REGRESSION against city markets (migration 0.0554, rebellion 0.0301, needs 186 of 200, 0 extinct). `feat/agent-movements`: movements grounded in people behind `--agent-movements`, default off: per-agent membership (a Rust pool and snapshot column), commons, liberty and sect creeds founded where grievances cluster, recruitment through bonds, co-residence and settlements, demands, reforms, refusals, crackdowns with martyrs, risings, secession through the shared free-city transfer, schisms through the religion path; switch off byte-identical (88 files and the subset gate 42-61); subset gates 42-61, 62-81 and 82-101 PASS / NO REGRESSION with it on (needs 16 -> 12, 13, 14); full gate not run. `feat/city-markets`: merchant routing by price for every good, market packets and a committed-cargo tally against herding (food to short regions 62% -> 80%); cities as markets (city farmers' labour, craft demand, sieges cut supply); viewer Cities tab; cities on by default for new worlds after a full gate with them on: PASS strict, NO REGRESSION against main `3355289` and Wave 8 (migration 0.0580, rebellion 0.0308, needs 189 of 200, 0 extinct). `fix/navigation-famine-labels`: maritime navigation reads the known navigation techniques (full gate PASS strict, NO REGRESSION against Wave 8: migration 0.0576, rebellion 0.0314, needs 196 of 200, 0 extinct); food-crisis reports labelled famine (below 0.6 for a season) or dearth with unchanged effects; mass_migration carries its migration driver. `feat/cities` from `integrate/wave-7` `bcf14d8`, merged with `main` `a95e4d7` (Wave 8 defaults): cities as historical actors behind `--cities`, default off: M56a settlements grown into towns and cities with commerce, dues, charters, urban revolts and free cities, sacks, walls and falls, a Rust urban pull migration driver; switch off byte-identical (88 files); subset gates 42-61 and 62-81 PASS / NO REGRESSION with it on, before and after the merge. Before: `feat/defaults-wave8`: great-person agendas, maritime and nomads on by default for new worlds; full gate PASS strict, NO REGRESSION against Wave 7 (migration 0.0576, rebellion 0.0317, needs 194 of 200, 0 extinct). `integrate/wave-7`: `feat/healthy-migration`: frontier (land, farmers), wage-gap and chain migration behind their own gates, net of life-course roots; calibrated on the merged world, full gate PASS with migration 0.0570 (strict floor). `fix/food-logistics`: merchants route food by the destination's food price; subsistence floor; locust rate 0.15 -> 0.02. `fix/needs-oracle-confound`: the needs oracle pairs autonomy only among agents that have not rebelled. `fix/leftover-persecution`: persecution follows the current ruler every turn Merged with `main` plus `feat/viewer-systems`: `feat/viewer-systems` from `main` `6e6fae6`: viewer tabs for wars, food, nomads, agendas, governance and the contact ledger; six thematic map layers; viewer-only `food` and `migration` snapshot fields. `feat/languages` from `main` `baabafb`: in-world languages and names, observational, on by default. 2026-10-24: `fix/food-logistics`: merchants route food by the destination's food price; the goods economy gets M34's subsistence floor; locust swarms recalibrated 0.15 -> 0.02 per eligible turn; merged with `integrate/wave-6`. `fix/needs-oracle-confound`: the needs oracle's autonomy pairing leaves out prior rebels; the offline oracle lane runs in four guarded chunks. `fix/agenda-preaching`: great-person agendas' rebellion tail traced to left-over persecution intensity; prophets kept out of persecution and foreign faiths' realms. `feat/historiography` on `integrate/wave-5`: in-world chroniclers and archives, observational, on by default; techniques on by default; great-person agendas and nomads default off; bundle version 5 prunes dead civs from history snapshots; dead civs earn no income Merged with `main` after `perf/bundle-headroom`: bundle version 6 writes the history as changes between snapshots and drops `world_state`'s copy of the timeline and named events; decoded it is the version-5 bundle byte for byte; size guard 22.67 -> 8.61 MB no-Rust and 21.55 -> 7.89 MB native, guard 24 -> 10.5 MB; simulation outputs byte-identical. `feat/farmland-climate`: diminishing returns to farm labour (output per farmer falls as farmers crowd the land's arable capacity, raised by farming techniques and irrigation; farmer income follows; the agents-off famine check reads food per head) and regional climate (the global phase keeps half its crop and water effects as the long trend, the rest comes as bad harvest years of clusters of neighbouring regions); hunger terms raised part way (deaths famine 0.50 -> 1.00, births 0.30 -> 0.45; the mid-range 1.50 / 0.60 failed the needs subset 42-61); template famines 11.5 -> 8.1 turns, 20+-turn episodes 30% -> 11%, turns with three quarters of a world in famine 15.6% -> 6.7%; golden oracles rolled forward; full gate PASS strict, NO REGRESSION against the hunger head (migration 0.0610, needs method 2 182 of 200, 0 extinct). `fix/needs-oracle-power`: the needs oracle pools every snapshot and pairing (need gap 0.1, matching otherwise unchanged) and passes on a seed-clustered 95% lower bound of net concordance plus the 60% seed fraction; main subsets 42-61, 62-81, 82-101 PASS (+0.18, +0.20, +0.33), routing `--no-cities` 62-81 FAIL -> PASS, `--agent-movements` 42-61 PASS; needs shuffled in cells FAIL 15 of 15 (method 1 passed 10); need terms zeroed in Rust not reliably caught (1 of 3); comparator flags a method change instead of a new failure; full gate not run. `feat/agent-movements`: movements grounded in people behind `--agent-movements`, default off: per-agent membership (a Rust pool and snapshot column), commons, liberty and sect creeds founded where grievances cluster, recruitment through bonds, co-residence and settlements, demands, reforms, refusals, crackdowns with martyrs, risings, secession through the shared free-city transfer, schisms through the religion path; switch off byte-identical (88 files and the subset gate 42-61); subset gates 42-61, 62-81 and 82-101 PASS / NO REGRESSION with it on (needs 16 -> 12, 13, 14); full gate not run. `feat/city-markets`: merchant routing by price for every good, market packets and a committed-cargo tally against herding (food to short regions 62% -> 80%); cities as markets (city farmers' labour, craft demand, sieges cut supply); viewer Cities tab; cities on by default for new worlds after a full gate with them on: PASS strict, NO REGRESSION against main `3355289` and Wave 8 (migration 0.0580, rebellion 0.0308, needs 189 of 200, 0 extinct). `fix/navigation-famine-labels`: maritime navigation reads the known navigation techniques (full gate PASS strict, NO REGRESSION against Wave 8: migration 0.0576, rebellion 0.0314, needs 196 of 200, 0 extinct); food-crisis reports labelled famine (below 0.6 for a season) or dearth with unchanged effects; mass_migration carries its migration driver. `feat/cities` from `integrate/wave-7` `bcf14d8`, merged with `main` `a95e4d7` (Wave 8 defaults): cities as historical actors behind `--cities`, default off: M56a settlements grown into towns and cities with commerce, dues, charters, urban revolts and free cities, sacks, walls and falls, a Rust urban pull migration driver; switch off byte-identical (88 files); subset gates 42-61 and 62-81 PASS / NO REGRESSION with it on, before and after the merge. Before: `feat/defaults-wave8`: great-person agendas, maritime and nomads on by default for new worlds; full gate PASS strict, NO REGRESSION against Wave 7 (migration 0.0576, rebellion 0.0317, needs 194 of 200, 0 extinct). `integrate/wave-7`: `feat/healthy-migration`: frontier (land, farmers), wage-gap and chain migration behind their own gates, net of life-course roots; calibrated on the merged world, full gate PASS with migration 0.0570 (strict floor). `fix/food-logistics`: merchants route food by the destination's food price; subsistence floor; locust rate 0.15 -> 0.02. `fix/needs-oracle-confound`: the needs oracle pairs autonomy only among agents that have not rebelled. `fix/leftover-persecution`: persecution follows the current ruler every turn Merged with `main` plus `feat/viewer-systems`: `feat/viewer-systems` from `main` `6e6fae6`: viewer tabs for wars, food, nomads, agendas, governance and the contact ledger; six thematic map layers; viewer-only `food` and `migration` snapshot fields. `feat/languages` from `main` `baabafb`: in-world languages and names, observational, on by default. 2026-10-24: `fix/food-logistics`: merchants route food by the destination's food price; the goods economy gets M34's subsistence floor; locust swarms recalibrated 0.15 -> 0.02 per eligible turn; merged with `integrate/wave-6`. `fix/needs-oracle-confound`: the needs oracle's autonomy pairing leaves out prior rebels; the offline oracle lane runs in four guarded chunks. `fix/agenda-preaching`: great-person agendas' rebellion tail traced to left-over persecution intensity; prophets kept out of persecution and foreign faiths' realms. `feat/historiography` on `integrate/wave-5`: in-world chroniclers and archives, observational, on by default; techniques on by default; great-person agendas and nomads default off; bundle version 5 prunes dead civs from history snapshots; dead civs earn no income Merged with `main` after `feat/hunger-mortality`: hunger kills and lowers births in agent modes, graded by severity: deaths of the young, the old and the poor up to +55% in a sustained total famine (famine death rate 1.54 -> 1.96 times fed), births down by up to 10% in dearth and 37% in famine, a rebound after, epidemic susceptibility and fatality follow measured hunger, a dearth weighs a third of a famine in unrest; the `--agents off` famine toll scales with severity; golden oracles rolled forward; full gate PASS strict, NO REGRESSION against city markets (migration 0.0554, rebellion 0.0301, needs 186 of 200, 0 extinct). `feat/agent-movements`: movements grounded in people behind `--agent-movements`, default off: per-agent membership (a Rust pool and snapshot column), commons, liberty and sect creeds founded where grievances cluster, recruitment through bonds, co-residence and settlements, demands, reforms, refusals, crackdowns with martyrs, risings, secession through the shared free-city transfer, schisms through the religion path; switch off byte-identical (88 files and the subset gate 42-61); subset gates 42-61, 62-81 and 82-101 PASS / NO REGRESSION with it on (needs 16 -> 12, 13, 14); full gate not run. `feat/city-markets`: merchant routing by price for every good, market packets and a committed-cargo tally against herding (food to short regions 62% -> 80%); cities as markets (city farmers' labour, craft demand, sieges cut supply); viewer Cities tab; cities on by default for new worlds after a full gate with them on: PASS strict, NO REGRESSION against main `3355289` and Wave 8 (migration 0.0580, rebellion 0.0308, needs 189 of 200, 0 extinct). `fix/navigation-famine-labels`: maritime navigation reads the known navigation techniques (full gate PASS strict, NO REGRESSION against Wave 8: migration 0.0576, rebellion 0.0314, needs 196 of 200, 0 extinct); food-crisis reports labelled famine (below 0.6 for a season) or dearth with unchanged effects; mass_migration carries its migration driver. `feat/cities` from `integrate/wave-7` `bcf14d8`, merged with `main` `a95e4d7` (Wave 8 defaults): cities as historical actors behind `--cities`, default off: M56a settlements grown into towns and cities with commerce, dues, charters, urban revolts and free cities, sacks, walls and falls, a Rust urban pull migration driver; switch off byte-identical (88 files); subset gates 42-61 and 62-81 PASS / NO REGRESSION with it on, before and after the merge. Before: `feat/defaults-wave8`: great-person agendas, maritime and nomads on by default for new worlds; full gate PASS strict, NO REGRESSION against Wave 7 (migration 0.0576, rebellion 0.0317, needs 194 of 200, 0 extinct). `integrate/wave-7`: `feat/healthy-migration`: frontier (land, farmers), wage-gap and chain migration behind their own gates, net of life-course roots; calibrated on the merged world, full gate PASS with migration 0.0570 (strict floor). `fix/food-logistics`: merchants route food by the destination's food price; subsistence floor; locust rate 0.15 -> 0.02. `fix/needs-oracle-confound`: the needs oracle pairs autonomy only among agents that have not rebelled. `fix/leftover-persecution`: persecution follows the current ruler every turn Merged with `main` plus `feat/viewer-systems`: `feat/viewer-systems` from `main` `6e6fae6`: viewer tabs for wars, food, nomads, agendas, governance and the contact ledger; six thematic map layers; viewer-only `food` and `migration` snapshot fields. `feat/languages` from `main` `baabafb`: in-world languages and names, observational, on by default. 2026-10-24: `fix/food-logistics`: merchants route food by the destination's food price; the goods economy gets M34's subsistence floor; locust swarms recalibrated 0.15 -> 0.02 per eligible turn; merged with `integrate/wave-6`. `fix/needs-oracle-confound`: the needs oracle's autonomy pairing leaves out prior rebels; the offline oracle lane runs in four guarded chunks. `fix/agenda-preaching`: great-person agendas' rebellion tail traced to left-over persecution intensity; prophets kept out of persecution and foreign faiths' realms. `feat/historiography` on `integrate/wave-5`: in-world chroniclers and archives, observational, on by default; techniques on by default; great-person agendas and nomads default off; bundle version 5 prunes dead civs from history snapshots; dead civs earn no income)

---

## Communities as M53 oracle 1 specifies them (2026-10-28, `feat/spec-communities`)

> **Last updated:** 2026-10-28 (`feat/spec-communities` from `main` `ac74e5a`; validation only, the simulation byte-identical. Added: community oracle method 2, which keeps method 1 as its deciding legacy component and adds M53 oracle 1 as specified, judged by the spec's criteria; and cohort method 6, method 5 with those communities as the member cohort of every component. Results on `main`'s simulation: about a tenth of the agents are members (method 1: nine in ten), 3.1 (template) and 5.4 (procedural) communities a seed, median size 5. No community stays within 5% of its region (regions hold about 40 agents), so the spec component fails and stays informational. Two thirds of members now find a matched control. The kin roots give the spec's members 0.988 and 0.996; the community anchor gives them 0.912 against 0.907 for non-members, so M53's anchoring claim is still not reproduced. Three full gates PASS strict, NO REGRESSION, every metric delta 0, `rebaseline_required` for community 1 -> 2 and cohort 5 -> 6.)

Details and evidence:
[`docs/integration/spec-communities.md`](../../integration/spec-communities.md).

- **Detection** (`chronicler/validation_communities.py`): friend,
  co-religionist and kin edges with positive sentiment between living
  agents of one region, weighted by sentiment; method 1's label
  propagation; kept with 5+ members, a friend or co-religionist edge and
  one memory tuple (event type, turn, valence) held by 80%. Bond codes come
  from `ffi_constants.BOND_TYPES`, checked against the Rust enum and, with
  the extension, against the native kin behaviour.
- **Region share** is a community's size over its region's living agents
  at the snapshot, for every community; 0 of 26,228 (flag-on) and 2 of
  36,945 (default gates) communities stay within 5%. Restating it for small
  worlds is a separate decision.
- **Pre-registration** before any gate, from probes of `main` on other
  seeds: every prediction held but the template count (predicted more
  likely to fail; 3.13 passed).
- **Identity and tests**: 9-case matrix 399 files, 0 differences; old
  methods re-score `main`'s results exactly; `cargo test` 1,070 passed;
  not-slow 6,777 passed, 3 skipped; oracle lane PASS (2,754 passed).
- **Open**: the region-share criterion; why the anchor misses the spec's
  members although they hold more ties; the observational cohort component
  remains non-discriminating.

---

## Domestic credit through real lenders (2026-10-28, `feat/domestic-credit`)

> **Last updated:** 2026-10-28 (`feat/domestic-credit` from `main` `ac74e5a`. Added: a default-off switch `--domestic-credit` (needs finance and an agent pool) that makes the realm's merchant agents, guilds and cities finance's domestic lender: they fund domestic loans from their wealth (half their assets less their claims, a quarter always kept), receive interest and repayments pro rata to their claims and lose what defaults write off; merchant wealth moves through a native call, and losers gain grievance (merchants' satisfaction inside the social cap, cities' grievance, a guild threat). Off is byte-identical to `main`; on resumes exactly; the books balance every turn under `CHRONICLER_CHECK_RESOURCES=1`. Template full 200 x 500 and procedural full 100 x 300 with the switch on PASS strict, EXPLORATORY NO REGRESSION against main. Kept off: open decisions on early-game credit, war chests and a debt treadmill in a few worlds.)

Details and evidence:
[`docs/integration/domestic-credit.md`](../../integration/domestic-credit.md).

- **Lenders and flows** (`domestic_credit.py`, hooks in `finance.py`;
  native `credit.rs`). Merchants lend by home region from the live pool,
  guilds and cities from their purses. Claims sit on credit lines keyed by
  the loan; interest, principal, capitalized interest and write-offs are
  split pro rata in whole units. Merchant flows reach the pool at the end
  of the fiscal tick; what cannot be applied stays due (persisted). The
  abstract revenue-times-influence capacity is gone.
- **Consequences.** Finance's domestic-default consequences are kept.
  Merchants of losing regions gain a grievance (up to 0.10 satisfaction,
  `creditor_grievance` region column); losing cities gain grievance;
  guilds and cities that lost a tenth of their assets record the
  repudiation, and for a guild it is a threat (a guild movement may rise).
  Loan and default events name the lenders.
- **Identity and conservation.** Switch off: 9-case matrix, 399 files, 0
  differences (default and explicit `--no-domestic-credit`). Switch on: 5
  checkpoint cases, 195 resume points, 5,352 files, 0 differences. 40
  checked worlds balanced every tick and equal their unchecked runs.
- **Paired worlds** (20-40 seeds, 200-500 turns). Early domestic credit
  halves; merchant wealth +5% to +26%; procedural worlds lend at home what
  they borrowed abroad (domestic +64% to +102%, foreign -22% to -31%) and
  default a quarter less; template worlds borrow abroad more (foreign
  share +0.13 to +0.17); all-agent wealth Gini +0.007 to +0.009; merchant
  satisfaction about -0.009; migration and rebellion unchanged within
  their spread. Pre-registration: 1a, 3, 5, 7 held, 6 mostly; 1b and 4 did
  not; 2 held in template worlds only.
- **Gates** (frozen tree `2a08828`): template full PASS strict, needs and
  cohort methods of fork design 2 against a fresh main gate (satisfaction
  -0.004, migration -0.4%, rebellion +7.9%, not an effect in 40 paired
  worlds); procedural full PASS strict (satisfaction +0.001, migration
  +0.5%, rebellion -6.4%). Informational: the template needs ablation's
  low-power safety pairing reads 1.071 [0.877, 1.266] against main's 1.230.
- **Open**: a debt treadmill in a few worlds (lenders' assets grow with the
  interest, so a state at the debt ceiling rolls over indefinitely and its
  cities' purses, which have no ceiling, grow to thousands: 4 of 200
  template worlds); early-game credit (other wealthy agents as lenders, or
  a capped abstract lender for young states); war-chest borrowing from rich
  merchants; the merchant tax is not debited from the agents; no viewer
  view of who holds the debt.

---

## Community anchoring and fork design 2 (2026-10-28, `feat/community-anchoring`)

> **Last updated:** 2026-10-28 (`feat/community-anchoring` from `main` `b1c9274`. Added: a default-off community anchoring term (`--community-anchoring`), where positive same-region bonds with a shared memory, at least one of them non-kin, lower the odds of acting on a reason to move (no draw; persisted in checkpoints; off is byte-identical to `main`). Also added: a `community_anchor` ablation arm and fork design 2, under which procedural full gates fork every 20 turns from turn 100 (needs method 8, cohort method 5; design-1 arms keep methods 7 and 4). Results: with design 2 the procedural needs ablation passes (material 1.119 [1.093, 1.145]). The anchor at its calibrated strength gives the oracle's members 0.909 (template) and 0.941 (procedural) against M53's at most 0.85. Agents with four ties get 0.873 and 0.899, also failing the pre-registered restated band. Matching the M53 number takes about twice the anchor and cuts all migration by 16%, so it is not adopted. The switch stays off; M53 oracle 4's anchoring claim is recorded as not reproduced; the causal components stay reported only.)

Details and evidence:
[`docs/integration/community-anchoring.md`](../../integration/community-anchoring.md).

- **Term** (`chronicler-agents/src/community.rs`, `behavior.rs`). The anchor
  is 0.120143 x counted ties / 4, subtracted from the migrate utility when
  the gate is open. It never closes the gate, and never touches rebellion,
  switching or staying. The strength was calibrated from the midpoint of
  the spec's band through the decision model, before any run with the
  switch on (pre-registration in the doc, section 3).
- **Switch off**: identical to `main`. The 9-case turn-speed matrix
  compared 399 files, template batches 1,110 files and procedural batches
  351 files, all with 0 differences. Switch on: exact resume at every turn
  (3 cases, 157 resume points, 0 differences).
- **Gates with the switch on** (template full 200 x 500, procedural full
  100 x 300): every required oracle passes in both. Migration falls 5.3%
  (procedural) and 6.8% (template), as predicted. Template worlds end less
  concentrated (HHI -0.015). Rebellion and population show no detectable
  change.
- **Open**: community detection as oracle 1 specifies it (edge types,
  within a region, the kin code, the size criteria), as a new community
  oracle method. The oracle's members are about nine in ten agents today,
  so the cohort oracle cannot discriminate. Template safety power stays at
  0.66 (reported).

---

## Ablation oracles (2026-10-27, `feat/ablation-oracles`)

> **Last updated:** 2026-10-27 (`feat/ablation-oracles` from `main` `2106ef2`, fast-forwarded to `8a68658`, merged with `7c44ed8` (PR #59) and `9d82e77` (PR #60, simulation and validator inputs identical to `7c44ed8`): a default-off native decision ablation (`--decision-ablation needs|kin_roots|placebo --ablation-start-turn T`: no random draw, persisted in checkpoints, every output byte-identical when unset) and gate arms forked from exact checkpoints of the plain batch (every 100 turns, 20-turn window, cohorts fixed at the fork), on by default in the full profile, opt-in in subsets; needs oracle method 7 and cohort method 4 add the ablations to methods 6 and 3 as causal evidence, reported but not yet required: the gate is decided by method 6's observational verdict and cohort method 3 (labelled non-discriminating), as on `main`; `--require-causal-oracles` / `CAUSAL_ORACLES_REQUIRED` (off) makes the ablations decide; synthetic worlds without the effect, age-confounded or reversed pass the ablations in 0 of 1,000 batches at every scale, power at +20% 97-99% (needs, full) and at -20% 100% (cohort); causal evidence on `main`: template full needs PASS (+12% to +47%), cohort FAIL (members' migration 0.988 [0.984, 0.993] against the spec's at most 0.85); procedural full needs FAIL (material -> migration +6.7% [-5.3%, +18.7%], the other four pass), cohort FAIL (0.996); the four kept gate reports re-score to template full PASS, procedural full PASS, template subset PASS, procedural subset FAIL (needs, as `main`), each `main`'s own verdict; methods 6 and 3 re-score every batch exactly, the comparator flags `rebaseline_required`; the two default arms cost 0.6 (procedural) to 1.2 (template) times the plain batch. Open decisions: kin anchoring against the M53 15-30% claim; the power of the procedural material pairing.)

`feat/ablation-oracles` from `main` `2106ef2` (PR #57), fast-forwarded to
`8a68658` (PR #58) and merged without rebase with `7c44ed8` (PR #59) and
`9d82e77` (PR #60, permanent faith ids: simulation, events and validator
inputs identical to `7c44ed8`, so the gate evidence stands).
Details and evidence:
[`docs/integration/ablation-oracles.md`](../../integration/ablation-oracles.md).

- **Switch** (`scale.rs` `DecisionAblation` in `TickOptions`): `needs`
  zeroes the need utility modifiers and the autonomy drift term, `kin_roots`
  drops the marriage and home-bond part of a migrant's roots, `placebo`
  moves the decision draws to another stream; four Gumbel draws per agent
  either way (common random numbers). Persisted with `TickOptions`
  (`persist_struct!`, the checkpoint layout changes); Python sends it only
  when asked. Unset: 9-case turn-speed matrix 399 files, 0
  differences against `7c44ed8`; `--checkpoint-turns` 258 files, 0
  differences; resume identity with each arm on 0 differences (3 cases,
  157 resume points).
- **Oracles**: per pairing the rate ratio of the fixed cohort's events with
  and without the term, seed-clustered ratio-estimator bound (Student t),
  pre-registered direction and minimum effect (needs +10%: M49 tier 2;
  cohort -15%: M53 oracle 4). Needs method 7 keeps method 6 as its
  observational component, cohort method 4 keeps method 3; both ablations
  are labelled "causal evidence (not yet required)" in the report, the gate
  decision and the summary.
- **Gate rules**: the observational components decide (as `main`); with
  `--require-causal-oracles` the needs ablation decides the full profile
  (the observational verdict the subset, which cannot measure safety) and
  the kin-roots ablation the cohort oracle in every profile. Tests cover
  both modes.
- **Gates** (fresh roots, `d6b63e5`, run with the causal verdicts
  required; reports re-scored under the revised rules from the kept
  components and `main`'s method 6 / 3 results on the same batches):
  template full PASS (causal required: FAIL, cohort), procedural full PASS
  (FAIL, needs material 1.067 [0.947, 1.187] and cohort 0.996), template
  subset PASS (FAIL, cohort 0.974), procedural subset FAIL on needs as on
  `main` (FAIL, needs and cohort 1.000). Against `7c44ed8`'s mine-soil
  reports every metric delta 0, NO REGRESSION, both method changes
  flagged. Placebo arm: no pairing passes anywhere, full-scale ratios
  0.93-1.13. A template subset gate run afresh on the revised code with
  `--ablation-oracles` PASS: ablation components equal the earlier run's,
  cohort observational equal to `main`'s method 3.
- **Open decision 1, kin anchoring**: the kin roots move members'
  migration by 1.2% in template worlds and 0.4% in procedural ones
  (non-members 2.0% and 0.5%): at most 0.06 of roots, against the
  voluntary pulls only. Strengthen the anchoring or restate the M53 claim
  by a new pre-registration; until then method 3 decides.
- **Open decision 2, procedural material power**: few procedural agents
  are short of material goods (3.6 a fork; the synthetic model assumed 20)
  and they migrate a lot either way; the interval [-5.3%, +18.7%] holds
  both no effect and the minimum. Raise the exposure (more forks or seeds,
  power measured on the real cohort sizes) or examine the term in
  procedural worlds before the needs ablation decides procedural gates.
- **Cost**: the two default arms add about 87% to the template full
  gate's batch and validation (50-61 minutes in all) and 42% to the
  procedural one (30 minutes); forks 2-4 s each; checkpoints 1.2 GB
  (template) and 0.75 GB (procedural) until forked.
- **Tests**: cargo 1,061 / 2 ignored (Rust unchanged by the revision);
  not-slow 6,716 / 3 skipped before merging `9d82e77`; on the merged tree
  focused tests 462 passed, oracle lane PASS 97.4 s.
- **Open**: the two decisions; subsets' needs verdict stays observational;
  in-process forks.

## Permanent faith identity (2026-10-27, `feat/permanent-faiths`)

> **Last updated:** 2026-10-27 (`feat/permanent-faiths` from `main` `7c44ed8`: each faith has a permanent id, its index in `WorldState.faiths` (name, founding turn, founding civ, a sect's movement and leader, parent, the native slot it holds or held, the turn it gave the slot up), never reused; native code and per-turn fields keep slots, records that outlive a turn carry the permanent id (movements, reforms, conversion objectives, seats, temple texts and chroniclers, faith words, the history's reform rows); faiths founded before the first recycle keep id == slot; older saves, checkpoints and bundles get the table rebuilt from their Schism events (live faiths id == slot, dated recycled-slot references mapped, untraceable slots marked unresolved); conversion objectives and seats corrected (they read the church that took a recycled slot), with no decision changed in any measured world; a branch regression (values that are not faiths, such as the 255 sentinel, mapped as ids, closing a faithless temple's school under `--scholarship`) found by the identity runs and fixed; on the final tree `66f3072` the turn-speed matrix is 399 files, 0 differences (with `--scholarship`, 1: a languages faith list), 80 recycling worlds (119 slots given up: 65 with the defaults, 54 with `--scholarship`) equal `main` in every simulation output, with differences only in the languages and historiography layers; checkpoints 117 resume points, 4,686 files, 0 differences; viewer Faiths tab, faiths named by name and founding turn.; template full 200 x 500 PASS strict, NO REGRESSION, validator inputs identical to `main` in all 200 worlds (129 recycles in 84); procedural full 100 x 300 PASS strict, NO REGRESSION, validator inputs identical in all 100 (280 recycles in 92))

`feat/permanent-faiths` from `main` `7c44ed8` (PR #59). Details and
evidence: [`docs/integration/permanent-faiths.md`](../../integration/permanent-faiths.md).

- **Audit** (section 2 there): every place a faith is named by slot,
  live or historical. Historical and now permanent: `Movement.faith`,
  `schism_from`/`_to`, a schism's `successor`, `Reform.faith`, the history's
  reform rows, `conversion_faith_id` (agendas, ambitions), `Seat.faith`,
  `Temple of faith <id>` texts, temple chroniclers (`temple:<id>`), faith
  words, narration names and provenance ids. Live and still slots: the
  registry, region/civ/temple faith fields, the native pool and tables,
  conversion, persecution, pilgrimages, holy war. Agent events keep the
  native slot (resolvable by the table's tenure). Validation sidecars hold
  no faith ids.
- **Design**: `faiths.py` (`found`, `release`, `uid_of`, `slot_of`,
  `live_slot`, `same_faith`, `holder_at`, `ensure`, `reconstruct`,
  `upgrade_bundle`); founding in `world_gen`, `religion.detect_schisms`,
  `agent_movements._schism`; `ensure` at each turn and on load; id 255
  reserved. No Rust or `persist.rs` change.
- **Compatibility**: state files, older checkpoints
  (`--resume-allow-mismatch`) and bundles read for narration or the viewer
  rebuild the table; a `main` checkpoint resumed by the branch matches
  `main`'s straight run after the projection (resume label and languages
  faith list aside). Bundle size: +3.2 KB for a 20-faith world; the 10.5 MB
  guard passes.
- **Corrections**: spread-faith agendas preached for and were fulfilled by
  the church that took the prophet's faith's slot; conversion ambitions
  likewise; scholarship seats counted as the persecutor's faith. Tests with
  slot-semantics controls. Never fired in the measured worlds (all
  simulation outputs equal to `main`). Template full gate (200 x 500, against `main`'s
  method 6 / cohort 3 report): PASS strict, NO REGRESSION, every metric delta
  0.0, validator inputs identical in all 200 worlds; 129 slots given up in
  84 of them. Procedural full gate (100 x 300): PASS strict, NO
  REGRESSION, every delta 0.0, validator inputs identical in all 100 worlds;
  280 slots given up in 92.
- **Regression found and fixed on the branch** (`66f3072`): the first
  version mapped values that are not faiths (255, a temple's -1) as
  permanent ids; a temple school of a faithless temple lost its temple and
  fell (template seed 51 and procedural seed 44 with `--scholarship`
  diverged from `main`). `live_slot` and `same_faith` now pass them through;
  both worlds match `main` again.
- **Identity** (final tree): `turn_speed_identity.py compare --faith-ids`
  drops the table and projects the new id fields back to slots. Matrix: 9
  cases, 399 files, 0 differences; with `--scholarship`, 1 (the languages
  faith list of the one case that recycles). Template 42-61 x 500 and
  procedural 32 x 10 42-61 x 300, defaults and `--scholarship` (80 worlds,
  17,120 files, 119 slots given up in 52 worlds): equal in every state,
  event, snapshot, sidecar and agent event; only `languages` (a vanished
  faith stays named; same-name sects coin their own words) and
  `historiography` (temple chroniclers of a recycled slot's church keyed by
  permanent id) differ, and only in worlds that recycle.
  `checkpoint_identity.py` (new recycling case plus two): 117 resume
  points, 4,686 files, 0 differences.
- **Narration**: mechanical narration of the recycling world, 34 entries,
  1,648 facts, 0 audit flags; `main`'s bundle narrated by the branch: the
  same narratives, 0 flags (the audit now rebuilds an older bundle's table
  as the narrator does; 3 false name flags before).
- **Viewer**: Faiths tab (each church once, as known at the scrubbed turn:
  founding, origin, parent, slot, vanished and successor), reforms and
  sects named by name and founding turn, faith words too; older bundles
  rebuilt; entry chunk +190 B, faith code in a 4.89 kB lazy chunk.
- **Tests**: Python native not slow 6,687 passed, 3 skipped; slow 12
  passed, 3 skipped; oracle lane PASS (124.4 s, `faiths` chunk 18 passed);
  no-Rust lane 6,430 passed, 261 skipped; `cargo test --locked` 1,053
  passed, 2 ignored; viewer 439 passed, lint and build pass.
- **Open**: agent events keep slots; an older bundle's `temple:<slot>`
  chronicler ids are kept; two faiths of one name read alike in prose;
  rebuilding older tables depends on the Schism wording; the general event
  log shows the raw temple text; corrections reproduced by tests only; no
  browser QA, Windows or macOS run.

## Mine-soil ordering (2026-10-27, `fix/mine-soil-ordering`)

> **Last updated:** 2026-10-27 (`fix/mine-soil-ordering` from `main` `2106ef2`, merged with `8a68658` (PR #58): the mines' soil charge (PR #52) recomputed the target crew after the soil step's overpopulation loss while the ledger and the documented rule take it from before, so a crowded region whose loss crossed a multiple of three paid N/(N-1) of the rule and `CHRONICLER_CHECK_RESOURCES=1` raised (`main`: 14 of 100 procedural full-gate worlds, 4 of 40 template worlds; with `--grain-reserves` 7 of 31); the charge now reads the ratio from before the step, as documented (behavioural correction, Rust only, no new state); zero raises in 100 procedural, 40 template and 31 granary worlds; only the worlds where `main` fired change (procedural 14 of 100, template 20 of 200 validator inputs); template full 200 x 500 and procedural full 100 x 300 PASS strict, NO REGRESSION against `main`'s method 6 / cohort 3 reports. Open: the reserve depletion still divides by the crew after the whole tick.)

`fix/mine-soil-ordering` from `main` `2106ef2` (PR #57), merged without
rebase with `8a68658` (PR #58). Details and evidence:
[`docs/integration/production-ledger.md`](../../integration/production-ledger.md)
section 13 (correction note in section 6).

- **Finding** (PR #58's resource checks): `tick_ecology_with_ledger`
  recorded `mine_crew_ratio` before the soil step, and the step took the
  overpopulation loss and then recomputed the ratio for the charge. Where
  the loss moved the effective capacity across a multiple of three, the
  crew fell by one: `main` seed 64 turn 27 charged 16/15 of the rule;
  `8a68658` with `--grain-reserves`, seed 42 turn 128, 12/11 (`main`'s seed
  42 runs clean). Recorded over `main`: 16 mismatches in 14 of 100
  procedural worlds (42-141 x 300), 6 in 4 of 40 template worlds (42-81 x
  500), all in crowded regions (1-22 above the potential), crews 3-22, 0.0001-0.0215
  extra soil each.
- **Fix (a), the charge on the crew before the step**: the ore was mined
  on the land as it stood before Phase 9; recomputing after the
  overpopulation loss charged crowding twice (its own loss and a smaller
  divisor, 5-50% more soil for the same ore) and made the rule depend on
  the order of two terms. (b), recording the crew the charge used, would
  have kept trajectories by documenting that artifact. The ratio is taken
  once and both the charge and the ledger read it.
- **Effect**: worlds without a crossing are bit for bit unchanged. Matched
  procedural 42-141: 86 of 100 identical in every file, the 14 that differ
  are exactly those where `main` fired, from that turn (8 with population
  changes, 6 soil-only for 5-33 region-turns); soil differs in 0.31% of
  region-turns, final population 53,741 -> 53,807. Template 42-81: 4 differ,
  soil only (30 of 160,000 region-turns), population identical. Full gates'
  manifests: template 180 of 200 worlds with identical validator inputs (9
  with different events), procedural 86 of 100 (the same 14 seeds). With
  `--grain-reserves` 24 of 31 identical (the 7 that fired). Turn-speed
  matrix (9 cases) 399 files, 0 differences; checkpoint resume identity
  (`hybrid_s42`, `proc32_hybrid_s11`, checks on) PASS, 0 differences; no
  native state added.
- **Gates** (fresh roots, against the oracle follow-ups' `99bfb7d`
  reports, `2106ef2`'s simulation and extension): template full PASS
  strict, NO REGRESSION (needs +0.1656 -> +0.1648, 154 -> 156 of 200,
  binding +0.191 -> +0.186; cohort 200 / 200; migration 0.0635 -> 0.0634,
  rebellion 0.0329 -> 0.0330; 0 extinct); procedural full PASS strict, NO
  REGRESSION (needs +0.0910 -> +0.0892, 72 of 100 both, binding +0.134 ->
  +0.136; cohort 100 / 100; migration 0.0755 -> 0.0755, rebellion 0.0387 ->
  0.0386; 0 extinct).
- **Tests** cargo 1,053 / 2 ignored (2 new, both failing on `main`'s
  source); not-slow 6,669 / 3 skipped; slow 12 / 3; no-Rust 6,412 / 261;
  oracle lane PASS 108.6 s; the native ledger test gains the seed-64 world
  (fails on `main`).
- **Open**: the reserve depletion (PR #51) divides by the target crew after
  the whole tick, the soil charge by the crew before it; they differ only
  where the tick's soil or water change crosses a multiple of three.
  Aligning them is a separate correction.

## Public granaries (2026-10-27, `feat/grain-reserves`)

> **Last updated:** 2026-10-27 (`feat/grain-reserves` from `main` `6da8fe5`: stock-target public granaries behind `--grain-reserves`, default off; rulers buy real surplus (own market, realm within three steps, then neighbours across permitted routes) at market prices from the treasury, store it with spoilage and release it before mortality reads the shortfall; the resource checks balance the granaries; switch off byte-identical to `main` (9-case matrix, hybrid batch, procedural); checkpoints with it on 0 differences; paired worlds: severe shortage -1.6/-1.7 pts, deaths per agent-turn -1.5%/-4%, procedural population +6%; template full 200 x 500 and procedural full 100 x 300 gates with it on PASS strict, EXPLORATORY NO REGRESSION (needs 172 of 200 and 79 of 100 seeds; `main` 154, 72); the template subset 42-61's needs oracle fails with it on (material pairing); the production ledger's mines' soil check stops some procedural worlds with `CHRONICLER_CHECK_RESOURCES=1`, `main`'s too (native ordering, not fixed here). Kept off.)

`feat/grain-reserves` from `main` `6da8fe5`. Details and evidence:
[`docs/integration/grain-reserves.md`](../../integration/grain-reserves.md).

- **Audit**: no actor plans ahead. Market stock is the residual of the
  harvest, the ration and merchants' trips; the five-turn storage cap and
  spoilage destroy 9-11% of the food (three to five times what merchants
  carry) while 9-16% of the demand goes unmet; the surplus within reach of
  a shortfall covers 11% of it on template worlds (31% procedural).
- **Design**: one granary per region, kept by its ruler. Target `min(4, 6
  x cv) x demand` from the capped harvest swing; procurement in Phase 10
  of surplus beyond merchants' commitments and four turns of the market's
  need, at the selling market's price, at most 10% of the treasury above
  20; the merchants' route graph (war, embargo, disposition, suspensions,
  blockade, siege); 5% transit decay; release in Phase 2 before any reader
  of the sufficiency (to a full meal from at least half the target, else
  to the famine line); 3% spoilage; conquest, occupation and siege take
  their shares; three events with provenance ids.
- **Switch**: world-stored (`WorldState.grain_reserves`, omitted while
  off), CLI, live default, gate runner, batch manifest, checkpoint
  switches; dormant under `--agents off`; old saves load.
- **Identity**: switch off and `--no-grain-reserves` byte-identical to
  `main` (9-case `turn_speed_identity` matrix 399 files each, hybrid batch
  182 files apart from the manifest's run identity, procedural 92 files);
  checkpoint matrix with it on and `CHRONICLER_CHECK_RESOURCES=1`: 7 cases,
  253 resume points, 0 differences.
- **Effects** (paired, template 40 x 300 / procedural 20 x 200): severe
  shortage -1.6 / -1.7 pts, dearth +1.1 / +1.6, sustained famine unchanged;
  deaths per 1,000 agent-turns -0.25 (SE 0.11) / -0.72 (0.23); procedural
  mean population +37 (11); food price volatility -0.019 (0.007) / -0.011
  (0.008); no fiscal measure moves beyond noise; template merchants' food
  departures -8%. Granaries hold 12-17% of their targets; spoilage about
  equals release (0.6-1.0% of the food demand).
- **Gates** (switch on): template full 200 x 500 PASS strict, EXPLORATORY
  NO REGRESSION (needs 0.174, 172 of 200 seeds; `main` 0.166, 154);
  procedural full 100 x 300 PASS strict, EXPLORATORY NO REGRESSION (needs
  0.130, 79 of 100; `main` 0.091, 72); subsets: procedural PASS (`main`
  fails), template 42-61 fails the needs oracle (`main` passes; material
  pairing 0.33 -> 0.04), template 62-81 fails on both (with it on also rebellion
  0.0179, below the regression floor; informational in a subset).
- **Mines' soil check**: with `CHRONICLER_CHECK_RESOURCES=1` the first
  procedural full run stopped at seed 42's turn 128: the native soil step
  computes the mines' crew after the overpopulation degradation, its ledger
  before (PR #52's ordering). Recorded over seeds 42-72: 10 mismatches in 7
  of 31 worlds with it on, 3 in 3 on `main`; every granary and other
  production check passed. Gate rerun without the checks; its 100 worlds'
  granary ledgers balance offline (167,933 rows).
- **Tests**: `tests/test_grain_reserves.py` (21; oracle chunk
  `grain-reserves`); `-m "not slow"` 6,655 passed, `-m slow` 12 passed,
  oracle lane PASS 95.5 s, cargo 1,051 passed.
- **Open**: scarce real surplus, spoilage as fast as release, the 20-seed
  template subsets, the mines' soil ordering (a correction of its own),
  state shipments outside the merchant systems, release in place only,
  grain only, no viewer panel.

---
## Oracle follow-ups (2026-10-27, `fix/oracle-followups`)

> **Last updated:** 2026-10-27 (`fix/oracle-followups` from `main` `3c3775d`, fast-forwarded to `6da8fe5`: validation tooling only, no simulation change; cohort oracle method 3 (each member against its matched control while both live; differential deaths biased method 2's effects by up to |d| 0.22 in synthetic nulls, method 3 within 0.010; method 2 re-scorable exactly); needs oracle method 6 (method 5's verdict plus an informational spiritual -> migration pairing; method 5 re-scorable exactly); age matching measured and not adopted (a 5-year match removes a synthetic age confound that passes method 5 in 90% of nulls, but keeps 8-11% of informative pairs and fails both full gates' seed fraction); the cohort verdict found unable to fail (every synthetic world passes, reversed included); template full 200 x 500 and procedural full 100 x 300 PASS strict, NO REGRESSION against the method 5 baselines, cohort 2 -> 3 and needs 5 -> 6 the only differences; template subset PASS; procedural subset needs FAIL as on `main` since PR #52.)

`fix/oracle-followups` from `main` `3c3775d` (PR #55), fast-forwarded to
`6da8fe5` (PR #56). Details and evidence:
[`docs/integration/oracle-followups.md`](../../integration/oracle-followups.md).

- **Cohort oracle and deaths**: members die more than their matched
  controls over a window (31% / 28% of rows, template full), mostly members
  without a matched control (77%); matched pairs die alike and migrate alike
  (1.066 / 1.065 per window). Synthetic nulls (realistic sizes, 20 x 20 x
  200 per world): method 2's per-snapshot d +0.032 with the observed
  mortality, +0.221 / -0.210 when members / others die more; method 3
  within 0.010 of zero, true effects recovered. **Cohort method 3**: matched
  pairs over the turns both lived; members without a control left out.
- **The cohort verdict cannot fail**: every synthetic world passes under
  both methods (null, effect, reversed: 100%), from best-of-18 snapshots,
  either behaviour and the larger effect of the two. A redesign is open.
- **Age in needs pairs**: the higher-need agent is older in 65-68% of pairs;
  a linear age term explains +0.006 of +0.091 (procedural) and +0.026 of
  +0.169 (template), but pairs within 5 years carry little of the
  concordance and pairs a generation apart most. Synthetic (40 x 100 per
  world): an age confound passes method 5 in 90% of nulls, a 5-year age
  match in 0%; the match detects a real effect in 2-25%. Real, 5 years:
  template full +0.106 pooled / +0.027 binding (93 of 200 seeds), procedural
  full +0.036 / -0.040 (47 of 100); only 40 years passes the template gate.
  **Not adopted** (too much power lost); method 5's verdict unchanged; its
  age dependence is the owners' decision.
- **Spiritual**: drives migration (push below 0.30) and sect recruitment;
  conversion does not read it; only migration is in the event stream.
  **Needs method 6** reports spiritual -> migration beside the verdict:
  template full +0.054 (lb +0.024), binding +0.081 (+0.038); procedural
  full +0.102 (+0.066), binding +0.134 (+0.088); no power at subset scale.
  77-84% of its informative pairs are cross-faith; persecution drives
  12-22% of the lower agent's migrations. Not required; gate decision later.
- **Gates** (frozen `99bfb7d`, fresh extension `99c1e1d5...e12f`): template
  full PASS strict, NO REGRESSION, needs +0.166 (+0.144), 154 of 200,
  cohort 200 / 200; procedural full PASS strict, NO REGRESSION, needs +0.091
  (+0.066), 72 of 100, cohort 100 / 100; each lists only cohort 2 -> 3 and
  needs 5 -> 6, other oracles JSON-equal to the baselines, deltas 0.0.
  Template subset PASS; procedural subset FAIL (needs +0.046, lb -0.021, 11
  of 20), which `main`'s own oracle gives on the same batch. Every batch
  re-scored by `main`'s validator: NO REGRESSION, the old versions equal
  `main`'s results field for field.
- **Tests**: focused validation suites 559 passed; oracle lane PASS 93.5 s
  (2,656 passed); `pytest -m "not slow"` 6,647 passed, 3 skipped.
- **Open**: cohort verdict redesign; method 5's age dependence; founders'
  ages absent from sidecars; spiritual not separated from persecution or
  checked against zeroed terms; procedural subset 42-61 needs FAIL on
  `main`.

## Narration provenance (2026-10-27, `feat/narration-provenance`)

> **Last updated:** 2026-10-27 (`feat/narration-provenance` from `main` `13f735a`: narration, tooling and viewer only; every simulation output byte identical (33 + 33 simulate-only files, bundle hashes equal; mechanical narration: chronicle.md identical, bundles identical apart from the new provenance fields). Every fact line a narrator receives ends with a stable id (`e<i>` timeline index, `n<i>`, `<chronicler>/e<i>` accounts, `p<agent id>`, `s<S>.<what>.<key>` snapshot values, `d<S1>-<S2>` changes, `w`, `o`, `L.`, `art`, `k`); each chronicle entry records the facts given (dated, retrospective marked) and each sentence's citations, exact for the mechanical narrator, parsed from bracketed ids (and removed) for an LLM; `python -m chronicler.narration_audit` flags unsupplied, unknown and future citations, future facts given outside the AFTER/LATER sections, names no given fact names, stray markers; mechanical narration of four worlds 0 flags; viewer "Sources" per chronicle card (lazy chunk; entry +756 B). Open: no LLM, no native/hybrid run, no browser QA.)

`feat/narration-provenance` from `main` `13f735a`. Details and evidence:
[`docs/integration/narration-provenance.md`](../../integration/narration-provenance.md).

- **Ids**: existing identities only: events by their index in the bundle's
  `events_timeline` (the record keeps its `event_id`), named events by
  index, in-world accounts as `<chronicler>/e<i>` (the account id is
  `<chronicler>/<event_id>`; event ids can hold spaces), characters by agent
  id, artifacts by `artifact_id`, snapshot values and changes by snapshot
  turn and the rows' own ids (civs and regions by world index), counted
  windows, observations, in-world names. Stable across in-run, `--narrate`
  and live range narration (one timeline).
- **Provenance** (`ChronicleEntry.provenance`): `as_of`, facts given (`id`
  dated `as_of`, `[id, turn]`, `[id, turn, "r"]` retrospective), the
  characters, civs, regions and faiths they name (bundle: indices into one
  `narration_provenance.names` table), spans `[start, end, ids]`. Curated
  bundles +0.28% to +1.06% (0.9-1.4 KB per entry); the size-guard world's
  500 per-turn entries 7.36 -> 7.60 MB (guard 10.5).
- **Prompts**: tags at line ends and a SOURCES request; +12.5% characters
  (about 300 tokens); stripped of both they equal the base prompts, and
  `--no-citations` reproduces the base capture byte for byte.
- **Audit**: mechanical narration of template 42, 7, 1234 and procedural
  32 x 10 (143 entries, 4,191 facts, 2,773 spans): 0 flags; names check
  over 1,663-2,766 mentions per run, every planted unnamed place flagged
  (141 of 141); scripted flawed LLM: unsupplied 99, unknown 50, future 49,
  unnamed place 45, stray marker 50; faithful LLM: none.
- **Tests**: `tests/test_narration_provenance.py` (27, oracle narration
  chunk); oracle lane PASS 92.9 s; full no-Rust `-m "not slow"` 6,362
  passed, 251 skipped; viewer 426 passed, lint, build.
- **Open**: no LLM called (citation reliability untested), no native or
  hybrid run, gap summaries and era reflections carry no provenance, the
  names check covers only names the run knows, no sentence highlighting or
  browser QA.

---

## Procedural drift (2026-10-27, `fix/procedural-drift`)

> **Last updated:** 2026-10-27 (`fix/procedural-drift` from `main` `7bb2bd4`, merged with `db5eff4` and `13f735a`: needs oracle method 5 (outcomes counted while both matched agents live; method 4 re-scorable exactly; 4 -> 5 reported as a method change); no simulation code changed; template full 200 x 500 and procedural full 100 x 300 on the branch head PASS strict, NO REGRESSION against `main`'s method 4 reports, needs 4 -> 5 the only method change (`rebaseline_required`), every other oracle identical, method 4 re-scores of both batches equal `main`'s needs results (template needs 154 of 200, +0.166; procedural 72 of 100, +0.091); these are the method 5 baselines; procedural needs drift traced to coastal pairs and the repulsion correction, fiscal-crisis rise not attributable to living caps, restoration +15 not persistable by any accumulator category.)

`fix/procedural-drift` from `main` `7bb2bd4` (PR #52), merged with `db5eff4`
(PR #53) and `13f735a` (PR #54). Details and evidence:
[`docs/integration/procedural-drift.md`](../../integration/procedural-drift.md).

- **Needs drift** (+0.169 -> +0.132 -> +0.111, method 4, paired z -3.46;
  templates flat): real (seed-clustered SE calibrated by half-splits) and
  coastal: coastal pairs +0.240 -> +0.062, other regions +0.128 to +0.143
  in five arms; -0.050 of the -0.059 is within coastal pairs. Reverting
  only PR #51's `spatial.rs` on `main` restores coastal +0.198 (pooled
  +0.149); the mine-soil correction adds about -0.02. Need spread, pair
  counts, drivers, need-driven migration and composition (except mortality)
  unchanged; not a needs defect. Template coasts do not respond. The
  coastal micro-mechanism is open.
- **Oracle flaw fixed, method 5**: 52% of informative pairs had a death in
  the 20-turn window, and the higher-need (older) agent's death decided the
  pair. Synthetic null with differential mortality: method 4 PASS 52%,
  method 5 5.5%. Method 5 censors each pair at its first death. Re-scored:
  procedural `main` +0.111 -> +0.091 (lb +0.066, 72 of 100 seeds, PASS),
  `2f654a8` +0.169 -> +0.145, template `d44cf4f` +0.209 -> +0.170 (PASS);
  15 terms-zeroed sets PASS 15 -> 8 (subset), terms-on 15 -> 14. No
  threshold changed.
- **Fiscal crises**: no great-person upkeep or stipend exists. Old caps on
  `main` (paired, 100 worlds): 1.518 against 1.437 per civ-century (z
  +0.99), fewer crises where more great persons live; ungated intelligence
  1.432. Unrelated arms span 1.43-1.59; the PR #48 rise is inside that
  spread. Not a defect.
- **Restorations**: hybrid write-back recomputes stability from agents each
  tick, so the `keep` +15 lasts until the next tick (31.6 -> 18.4); as
  guard-shock it is one tick's shock (counter-restorations 42% -> 39%,
  worse persistence). Not a category defect; not changed. Options
  (grace period, agent-side loyalty, smoothed gate) documented.
- **Full gates** (branch head `10c67a8` = `main` `13f735a` + method 5,
  fresh release extension, against `main`'s method 4 reports): template
  200 x 500 PASS, NO REGRESSION, needs +0.196 (lb +0.177), 170 -> +0.166
  (+0.144), 154 of 200, binding +0.176 -> +0.191; procedural 100 x 300
  PASS, NO REGRESSION, +0.111 (+0.088), 84 -> +0.091 (+0.066), 72 of 100,
  binding +0.117 -> +0.134. Needs 4 -> 5 the only method change; every
  other oracle JSON-equal to `main`'s, regression deltas 0.0; method 4
  re-scores of both batches equal `main`'s needs results. These are the
  method 5 baselines.
- **Tests**: focused validation suites 262 passed; oracle lane PASS 84.0 s
  at `ee9da60`; native not-slow 6,579 passed, 3 skipped at `c7cec53`.
- **Open**: coastal micro-mechanism; procedural method 5 margin (72 of 100
  against 60); cohort-oracle windows; age unmatched; spiritual pairing;
  fiscal mediators; restoration design.

## Exact checkpoint continuation (2026-10-27, `feat/checkpoint-continuation`)

> **Last updated:** 2026-10-27 (`feat/checkpoint-continuation` from `main` `db5eff4`: an exact resume envelope (`chronicler.run_checkpoint`, `--checkpoint-every N`, `--checkpoint PATH`, `--resume`, `--resume-allow-mismatch`) holding the whole Python run graph and each native simulator's own Rust state blob (`persist.rs`: every field, compile-checked, layout-fingerprinted); versioned, digests per section, refuses another source, extension, interpreter, package set or thread setting unless overridden (then labelled); state files resume as before, labelled legacy; resume identity 17 cases (every mode, template and procedural, switches on and off, 22k and 52k agents), 585 resume points, 13,219 files, 0 differences; gaps closed: the PR #51 tech-focus deltas (wave-3 test back at turn 62), every private attribute, the excluded agent events, bridge, tracker and native state, the economy sidecar summary read from disk, the shadow log; without checkpoints byte-identical to `main` (9-case matrix 399 files, with `--scholarship` 399, shadow and demographics-only 132) and turn CPU 1.00-1.01x; a checkpoint 2.5 MB / 0.17 s write at 22k, 5.4 MB / 0.42 s at 52k. Open: narration state, per-turn debug sidecars before the resume turn, size grows with run length.)

`feat/checkpoint-continuation` from `main` `db5eff4` (PR #53). Details and
evidence: [`docs/integration/checkpoint-continuation.md`](../../integration/checkpoint-continuation.md).

- **Inventory** (section 2 there): every piece of state that affects later
  turns, Python and native, and whether a state-file resume saved, rebuilt
  or lost it in off, demographics-only, shadow and hybrid. Lost today: the
  whole native pool and registry, trips, ledgers and queues, the bridge,
  tracker and agent events, the run's history, a dozen private world
  attributes (focus deltas, tax carry, belief and clergy baselines,
  persecuted regions, settlement fields). Measured at turn 30 of 60: 6 of 9
  files differ in off mode, all 9 / 11 in demographics-only / shadow, 32 of
  44 in hybrid with sidecars.
- **Envelope**: magic, JSON header (format 1, turn, seed, run origin and
  length, switches, run configuration, lineage, source digest, extension
  SHA-256 and state layouts, interpreter, packages, thread settings,
  SHA-256 per section) and zlib sections: one pickle of the run (shared
  references kept, natives as references, agent events as positional
  fields, sidecar rows as columns; a restricted loader) and the Rust blob
  of each simulator (magic, version, kind, FNV schema fingerprint; every
  struct listed by `persist_struct!`, which fails to compile on a new
  field). No random generator state exists between ticks (streams derive
  from the master seed and turn).
- **Gaps fixed**: focus deltas and the rest by the envelope; the economy
  sidecar summary built from this run's snapshots instead of the
  directory's files (shown: without it, resumes at 105 and 150 differ);
  the shadow log kept and rewritten; the war-roster marker re-bound (a
  precaution: no difference observed without it). Wave-3: the three-system
  resume test saves again at its original turn 62 from a checkpoint, a new
  test keeps the raw-file divergence there visible, the four-system test
  drops the raw-save condition.
- **Identity**: `scripts/checkpoint_identity.py`, every turn of 40-60-turn
  runs and a spread (1-3, Fibonacci, 34-46, 99-110, the last turn) of
  150-300-turn runs; 17 cases, 585 points, 0 differences; checkpointing
  itself changes nothing (579 files). Subset again on the last code commit
  (20 points).
- **Cost** (`scripts/checkpoint_cost.py`): 22k 2.51 MB, write 0.17 s, read
  0.18 s; 52k 5.40 MB, 0.42 s, 0.45 s (Rust state 13 ms of it); 22k with
  sidecars at turn 29 5.98 MB, 0.61 s. About 1.5 turns of CPU each.
- **Tests**: cargo 1,051 passed, 2 ignored (debug info off); native not-slow 6,598 passed, 3 skipped;
  oracle lane PASS 101.5 s (new `checkpoint` chunk).
- **Open**: narration (LLM) state is not carried; a resumed run does not
  rewrite the per-turn validation debug files of earlier turns; checkpoints
  grow with the history and, in agent modes, every agent event; Windows and
  macOS not run.

## Native turn speed, second pass (2026-10-27, `perf/rust-turn-2`)

> **Last updated:** 2026-10-27 (`perf/rust-turn-2` from `main` `8142c48`, merged without rebase with `7bb2bd4` (PR #52): performance only, every output byte identical to `main` `7bb2bd4` (9-case matrix 399 files, 3-seed hybrid batch, procedural 32 x 10) and before the merge to `8142c48`; process CPU per turn 1.37x at 22k agents, 1.67x at 52k, 1.96x at 105k (five interleaved runs; 1.26x / 1.68x / 1.94x in three more against `7bb2bd4`), small worlds unchanged. Open: decisions, household consolidation, the rest of knowledge propagation, flat Python; AVX2-only, non-x86 and pre-1.89 builds not timed.)

`perf/rust-turn-2` from `main` `8142c48` (PR #51), merged without rebase
with `7bb2bd4` (PR #52). Performance only. Details:
[`docs/performance/turn-speed-2026-10b.md`](../../performance/turn-speed-2026-10b.md).

- **Profile** (perf `cpu-clock`, no PMU; native phase timers; 1 rayon
  thread): exact drift 57% of the 52k turn (75% of the native tick),
  marriage 7%, knowledge 5.5%; the per-pair ChaCha streams and the
  zero-distance `sincosf` visible on their own.
- **Changes** (4 commits): the discarded Morton sort at 100k+ agents only
  with `TickOptions::profile_spatial_sort` (`set_spatial_sort_profiling`);
  drift repulsion inside the lane loop (the negated density direction,
  bit for bit), a 720-entry fallback table, Z-order lane groups, 1,024-agent
  items and run-time kernel dispatch (AVX-512 16 lanes, AVX2, baseline; all
  the same exact code; the AVX-512 kernel built on Rust 1.89+ through
  `build.rs`, `rust-version` stays 1.85); one ChaCha8 block per
  transmission roll; the marriage scan visits only partners within the
  radius (an exact squared-distance threshold).
- **Result** (process CPU per turn, medians of five interleaved runs
  against `8142c48`, load 1.6-5.3): 22k 146.6 -> 106.7 ms (1.37x), 52k
  498.9 -> 298.1 ms (1.67x), 105k 1,614.6 -> 822.1 ms (1.96x), procedural
  48 x 10 and gate world 1.00x. Drift 295 -> 134 ms on dumped 52k inputs
  (AVX2 157, baseline 215); marriage 31.6 -> 20.4 ms, propagation 20.0 ->
  10.9 ms. After the merge, three rounds against `7bb2bd4`: 1.26x, 1.68x,
  1.94x, 1.00x.
- **Identity**: against `7bb2bd4` (native `c8ef41f5...b6ff`) the 9-case
  matrix 399 files 0 differences, the 3-seed hybrid batch 334 of 335 files
  identical (the batch manifest differs in run identity only), procedural
  32 x 10 117 files 0 differences; the same against `8142c48` before the
  merge (395 / 332 / 116). Every drift kernel equals the per-agent
  reference on dumped real inputs. No full gate run.
- **Tests** cargo 1,044 passed, 2 ignored (debug info off); release
  equivalence subset 627 passed (all three kernels on this CPU); not-slow
  6,571 / 3 skipped; oracle lane PASS 81.8 s.
- **Not kept**: a group bounding-box far filter (scalar slower, AVX-512
  compress -5% of drift), a dense branch-free marriage classification (not
  vectorised by LLVM, slower), 32 AVX-512 lanes (same as 16), id -> slot
  table reuse across phases (review item 2: 0.09-0.10 ms per build, at
  most 0.15% of the turn; not implemented), small-world changes (review
  item 5: flat profile, no clear win).
- **Open**: drift is divider-bound (one square root and two divisions per
  agent-neighbour pair); decisions 5.5% and household consolidation 3% of
  the native tick at 52k; Python around the tick about 30% and flat.

## Production ledger (2026-10-27, `feat/production-ledger`)

> **Last updated:** 2026-10-27 (`feat/production-ledger` from `main` `8142c48`: every production path audited (farming, fisheries, forests, mines, salt, pastoral, foraging, crafts, off mode); a per-region, per-slot, per-turn ledger of realized output, stocks, draws, regrowth, the earlier rule's charge and degradation, written with the validation sidecar and checked by `CHRONICLER_CHECK_RESOURCES=1`; four behavioural corrections where the economy reports output (overextraction streak on output, the mines' soil charge on the ore taken, the fishery charged for the landed catch, the overextraction penalty in the yields with scenario slots initialized), each with a restore key, all four off byte-identical to `main`; template full 200 x 500 and procedural full 100 x 300 PASS strict, NO REGRESSION against `main`; procedural subset 42-61 failed needs by one seed (traced to the mine-soil correction), 62-81 PASS; golden fixtures unchanged. Open: overextraction unreachable at its calibration, the fishery allowance still sized by a labour proxy, timber takes no forest cover, procedural needs signal lower (pooled -0.021).)

`feat/production-ledger` from `main` `8142c48` (PR #51). Details and
evidence: [`docs/integration/production-ledger.md`](../../integration/production-ledger.md).

- **Audit.** Output, depletion, recovery and the charge basis of every
  path (section 1 there). On `main` mineral depletion (PR #51) and crafts
  followed realized output; the overextraction streak read population / 5,
  an active mine took 0.03 soil a turn worked or idle, the fishery stock was
  charged the whole catch allowance whether landed or not, and the
  overextraction penalty never reached the yields.
- **Ledger** (`chronicler.production_ledger`): `validation_resource_ledger.arrow`
  beside the validation files (0.4% of a batch; not in the bundle, not a
  validator input); reads only (same bundle with and without it). The
  native economy reports `slot_output` and `forage_output`; the ecology
  batch what the tick drew, what the proxy would have drawn, the takes and
  the mines' soil. `scripts/production_ledger_report.py` summarizes batches.
- **Corrections** (agent modes with an economy tick; proxies kept bit for
  bit otherwise): overextraction take = output / base yield (dormant: peak
  pressure 0.58 of sustainable, no penalty in any run); the penalty
  `effective / base` in the yields (dormant; scenario slots now start
  undegraded, spurious `ecological_recovery` rolls gone); the unlanded part
  of last turn's fish allowance (10.6-11.7% of it) returns to the stock;
  the mines' soil charge scales with ore over a target crew's (9-10% of the
  flat rule in the full gates, the only correction that moves trajectories).
  Keys `ecology.overextraction_realized`, `ecology.mine_soil_realized`,
  `ecology.fishery_charges_landed_catch`, `ecology.yield_penalty_reaches_goods`.
- **Gates** (needs method 4, cohort method 2; against `main`'s `c0f354d`
  reports, same source): template full PASS strict, NO REGRESSION (needs
  170 of 200, pooled +0.202 -> +0.196, binding +0.182 -> +0.175; migration
  0.0635, rebellion 0.0329; 0 extinct; mineral slots exhausted 42 -> 36,
  final population +2.2%); procedural full PASS strict, NO REGRESSION (needs
  84 of 100, pooled +0.132 -> +0.111, binding +0.136 -> +0.117). Subsets:
  template PASS, NO REGRESSION; procedural 42-61 needs FAIL (11 of 12 seeds,
  lower bound +0.033), 62-81 PASS; with the mine-soil key at 0 both
  procedural subsets reproduce `main`'s reports exactly.
- **Analytics** (matched `main` batches of the gates' first seeds against
  the branch's): fishery collapses 7 -> 0 (template 40 x 500, procedural
  20 x 300), final fish stocks +0.02-0.04, mine collapses up (329 -> 440,
  15 -> 24), exhausted mineral slots 11 -> 8; in the full gates the mines'
  soil charge is 9-10% of the flat rule and 10.6-11.7% of each fish
  allowance went unlanded.
- **Tests** cargo 1,038 / 2 ignored; not-slow 6,570 / 3 skipped; slow 12 /
  3; no-Rust 6,323 / 251; oracle lane PASS 80.3 s (`production-ledger`
  chunk). Golden fixtures unchanged, no `ORACLE_CHAIN` link.
- **Open** overextraction dormant at its calibration; the fishery allowance
  sized by a labour proxy (a cap); timber takes no cover; soil and pasture
  degradation are population and herd pressure; the procedural needs drop's
  mechanism (mine soil) not traced; shadow mode not run.

> **Last updated:** 2026-10-27 (`fix/population-entities` from `main` `18a05be`, merged without rebase with `22c021b`, `dae4ba5`, `2f654a8` and `1cf3e74`: eight review findings, all reproduced on `main` and corrected, behavioural corrections; template full 200 x 500 and procedural full 100 x 300 PASS strict, NO REGRESSION against `main` `2f654a8`, whose own full gates (its first under needs method 4 and cohort method 2) PASS strict; procedural needs signal lower on the branch (pooled +0.169 -> +0.132), template higher (+0.174 -> +0.202). Open: the procedural needs drop is half attributed (repulsion ablation), permanent religious identity, leader of a seceded state after its founder's death, raw-save tech-focus deltas.)

`fix/population-entities` from `main` `18a05be` (PR #46), merged without
rebase with `22c021b` (PR #47), `dae4ba5` (PR #48), `2f654a8` (PR #49) and
`1cf3e74` (PR #50).
Details, tables and evidence:
[`population-entities.md`](../../integration/population-entities.md).

- **Arrivals keep residents** (`utils.add_region_pop`): the increment is
  capped, not the population (100 people on room for 48 plus one arrival
  left 48); returns the people accepted. Migrants and refugees a full
  region cannot take die on the way.
- **Famine refugees conserved**: the toll is split exactly among foreign
  neighbours, remainders in region order (1 among 3 made 3 people; 5 among
  3 lost 2). Only `--agents off` and shadow have a Python drain.
- **Founders die after ascending**: deaths outside the civ rosters resolve
  through `gp_by_agent_id` (`alive`, `death_turn`, the death event, dynasty
  extinction); ascension stays the fate.
- **Faith slots** stay with tolerations in force or remembered for
  restoration and with living movements (a slot was reused while a
  toleration in force named it).
- **Initial occupations** from a conserved budget (5 people spawned 6
  agents, 6 spawned 7; no other population to 100,000 changes).
- **Coincident repulsion** in slot space on both sides (ids 1 and 2 in slots
  0 and 1 drifted the same way), reference and lane paths together.
- **Mineral depletion** by the goods each slot produced in the agent
  economy, consumed by the next ecology tick (no miners, no ore: reserves
  1.0 -> 0.9136 in eight turns); off mode keeps the proxy bit for bit.
- **Conservation tests** and an opt-in ledger
  (`CHRONICLER_CHECK_POPULATION=1`, `--agents off`): every turn's total
  equals its recorded births, deaths and migration; migration creates no
  one.
- **Golden oracles** rolled forward (`ORACLE_CHAIN` link `population`:
  single from turn 16, standard 9, wide 0); the snapshot-pruning run and
  two wave-3 resume tests re-pinned (a raw save drops capped tech-focus
  deltas, pre-existing on `main`).
- **Aggregate effect** (`--agents off`, 20 template and 10 procedural
  worlds x 300 turns): the clamp removed 9,551 and 14,769 residents; mean
  population +4.2% in both; overflow migration 27% and 18% more often, three
  times the migrants, most of whom die for want of room.
- **Gates** (code `c0f354d`, extension `83b76b41...5b87`; `main` `2f654a8`
  with `735558c9...a489`; fresh roots, manifests verified, needs method 4,
  cohort method 2). Template full: `main` PASS strict, branch PASS strict,
  NO REGRESSION; needs +0.174 (+0.155) 165/200 -> +0.202 (+0.183) 174/200,
  artifacts 1.77 -> 1.88, rebellion 0.0364 -> 0.0340, exhausted mineral
  slots 161 -> 42, mine collapses 2,732 -> 1,485. Procedural full: `main`
  PASS strict, branch PASS strict, NO REGRESSION; needs +0.169 (+0.149)
  89/100 -> +0.132 (+0.111) 84/100, binding +0.168 -> +0.136, artifacts
  2.41 -> 2.36; agent-backed ascended persons recorded dead 0 of 8 dead ->
  11 of 11. With `main`'s repulsion the procedural branch gives needs
  +0.151 / binding +0.160 (about half the pooled drop and most of the
  binding drop, each about one standard error). Subsets (20 x 200, both
  worlds) NO REGRESSION.
- **Tests** cargo 1,028 / 2 ignored; not-slow 6,545 / 3 skipped; slow 12 /
  3; no-Rust 6,306 / 243; oracle lane PASS 97.4 s (`population` chunk).

## Viewer performance (2026-10-27, `perf/viewer`)

> **Last updated:** 2026-10-27 (`perf/viewer` from `main` `2f654a8`: viewer only, no Python change; heavy panels in lazy chunks (entry 791,168 -> 307,379 bytes, gzip 233,605 -> 97,058), large uploads decoded in a worker (load blocking time 512 -> 198 ms guard, 984 -> 109 ms procedural 32-region), a fast path for version-6 object patches (history decode 2.3-2.4x), scrub indexes per array (script per scrubbed turn -22% to -69%); rendered DOM identical to `main` on 4 bundles; frames still rendering-bound; no PR opened here.)

`perf/viewer` from `main` `2f654a8` (PR #49). Details and evidence:
[`docs/performance/viewer-2026-10.md`](../../performance/viewer-2026-10.md).
Measured with the committed `viewer/scripts/perf-viewer.mjs` (headless
Chromium 153 through Playwright), 5 interleaved runs per build on a
loaded 4-core machine, medians with the runs' range.

- **Code split.** Systems tabs (with Recharts), languages, region
  history, Batch Lab, batch compare and intervention panels are dynamic
  imports (`components/phase75/lazyPanels.ts`, `lib/preloadable.ts`):
  fetched when idle after the first paint and when a load starts; a
  loaded chunk renders with no fallback; a polite `aria-busy` status
  until then; a failed chunk shows a readable message. Their stylesheets
  stay in the entry stylesheet in the old cascade order (loading them
  with the chunks moved the systems panel; the DOM check caught it). FCP
  656 -> 588 ms, shell's first frame 225 -> 152 ms; no chunk-size warning.
- **Worker decode** (`lib/bundleDecode.ts`, `lib/bundleFile.ts`,
  `hooks/useBundle.ts`): files of 1 MiB or more are read, parsed, checked,
  expanded and hashed in a worker and come back in 33-35 parts (longest
  receive 49 ms); main-thread fallback without a worker; the same
  `BundleDecodeError` / `INVALID_HISTORY_DELTA` messages. Longest task
  347 -> 217 ms (guard 6.9 MB), 824 -> 103 ms (proc32 24.6 MB); upload to
  first overview 732 -> 743 ms and 1,170 -> 1,307 ms (the copy back).
- **Codec fast path** (`lib/bundleCodec.ts`): the common object patch on a
  shallow copy, everything else and every malformed patch through the
  unchanged reference; 2,022 valid and 533 malformed random histories
  decode or fail identically.
- **Scrub indexes** (`lib/bundleIndex.ts`): Event Log, systems event
  lists, pinned event and its provenance, terrain, raids, mass migrations,
  techniques by turn; keyed by the `history` / `events_timeline` array, so
  uploads and live turns (new arrays) re-index. Timeline marks and strip
  segments memoized. Script per step 52.8 -> 16.1 ms (guard, 100
  consecutive) and 111.0 -> 61.8 ms (proc32); random jumps 84.5 -> 62.5
  and 123.4 -> 95.8 ms. Frames ~135-200 ms in both builds: layout, text
  shaping and paint of the same DOM changes dominate in this environment.
- **Equivalence.** `viewer/scripts/viewer-equivalence.mjs`: 95 + 95 + 92 +
  94 shell DOM captures (sampled turns x systems tabs, map layers, Event
  Log, pinned event, regions, surfaces, region history) on both generated
  bundles and two fixtures, 0 differences. Unit checks: each index lookup
  against the replaced filter at every turn (fixtures, synthetic and
  generated bundles), streamed live turns against a fresh shell, the
  worker handler against the main-thread decode.
- **Tests.** Viewer `npm ci`, `npm test -- --maxWorkers=2` 421 passed in
  52 files (`main` 382 in 46), `npm run lint`, `npm run build` pass. No-Rust
  venv: `tests/test_live.py`, `tests/test_live_integration.py`,
  `tests/test_historical_parity.py`, `tests/test_historical_parity_processes.py`
  88 passed.
- **Open.** Batch Lab `bundle_loaded` and reconnect `init` still parse on
  the main thread (needs a transport change); upload latency +12% on the
  24.6 MB bundle; forced-layout increase and smaller heap unexplained;
  Chromium only, no Firefox/Safari or device QA.

## Consistency follow-ups (2026-10-26, `fix/consistency-followups`)

> **Last updated:** 2026-10-26 (`fix/consistency-followups` from `main` `22c021b`, brought to `dae4ba5` before any baseline: narration, viewer, validation tooling, batch runner and tests; simulation output byte-identical; all five items reproduced on `dae4ba5` and fixed; cohort oracle method 2 counts outcomes after the snapshot turn, every retained set and the live subset keep their verdict; no full gate run.)

`fix/consistency-followups` from `main` `22c021b` (PR #47), fast-forwarded
to `dae4ba5` (PR #48) before the identity baseline. Details and evidence:
[`docs/integration/consistency-followups.md`](../../integration/consistency-followups.md).

- **Narrator accounts as of the moment.** `AccountIndex.as_of(AsOf)`:
  a copy lost after the point still stands, later archive losses left out,
  divergence as it stood. `HistoricalRecord(accounts=)` gives each view
  `view.accounts`; the prompt, the mechanical chronicle and both fallbacks
  read the moment's view. A 500-turn hybrid bundle: 41 of 50 prompts change,
  only in the IN-WORLD ACCOUNTS block; loss lines dated after the moment
  95 -> 0; mechanical entries 38 of 50 change, future loss notes 9 -> 0.
- **Viewer at the scrubbed turn.** Fixed: the snapshot before the first
  one (no later snapshot stands in), named-event markers, technique
  options, region terrain (dated transitions), a later pinned event,
  "Led to" consequences, in-world accounts, the chronicle feed (a moment
  once its last turn passed), Cities and Movements record notes and
  default focus, the Languages section (languages, status, endonym,
  changes, inventory, etymology at the turn). Checked unchanged: the other
  systems tabs, map layers, Learning, trade links, event log, whole-run
  timelines, run-level metadata, region history window. Not fixed: map node
  size uses the final carrying capacity (not recorded per turn). Entry
  chunk 788,040 -> 791,168 bytes.
- **Cohort oracle method 2.** Its graph and needs sidecars are written
  after turn t's agent tick (moves, autonomy, the turn's memories that form
  the communities); method 1 counted t .. t+19. Method 2 counts t+1 ..
  t+20 (eligible when t + 20 < N); `method_version=1` re-scores method 1
  exactly; the comparator flags 1 against 2 for re-baselining. The 48 needs
  sidecar sets hold no relationship or memory sidecars (not scorable).
  Retained: `perf` subset 42-61 x 200 PASS 20/20, median 1.025 (equals its
  report) -> PASS 20/20, 1.095; 9 single runs PASS -> PASS. Live template
  subset 42-61 x 200 (extension `735558c9...a489`): gate PASS; cohort
  method 1 PASS 20/20, median 1.347 -> method 2 PASS 20/20, 1.285; needs
  method 4 +0.175 (+0.097), 14 seeds. No threshold changed.
- **`--parallel N` is N workers** (`batch.parallel_workers`): 1 is one
  worker; bare `--parallel` and Batch Lab's `true` stay `cpu_count - 1`.
- **pytest-xdist.** Nine subTests pass plain values (repr, path name,
  patched attribute); the eleven subTest suites pass under `-n 2`.
- **Identity** against `dae4ba5`: `turn_speed_identity.py` off cases 33
  files and hybrid cases 220 files (extension `735558c9...a489`, built
  fresh), 0 differences; a 4-seed batch with `--parallel 1` (3 workers on
  `dae4ba5`, 1 now) and sequential: only `batch_manifest.json` differs.
- **Tests** (no-Rust Python 3.13.17): focused suites pass; oracle lane PASS
  in 104.6 s (2,537 passed, 38 skipped); `pytest -m "not slow" -n 2` 6,265
  passed, 232 skipped, 0 failed; viewer 382 tests (46 files), lint, build.
- **Open.** No full gate with cohort method 2; no LLM narration; no
  browser QA; map node size; a language revived after an earlier
  extinction shows living before its latest one; the curator's contested
  bonus still reads final losses (selection only).

## Procedural open items (2026-10-26, `fix/procedural-open-items`)

`fix/procedural-open-items` from `feat/procedural-gates` `1c98d0a`, merged
without rebase with `main` `c8f7eb4` (PR #43), `fc01d6e` (PR #44),
`b8f0243` (PR #45) and `18a05be` (PR #46). One
commit per item, each measured against the one before on template subsets
42-61 and 62-81 and the procedural subset 42-61. Details:
[`procedural-gates.md`](../../integration/procedural-gates.md#open-items-corrected-2026-10-fixprocedural-open-items).

- **Named characters** (`027fb55`). The native registry counted the dead
  against 50 per world and 10 per civ and checked a batch against the
  registry before it, so it filled by turn 50 (often in one rebellion's
  batch) and agent-born great persons stopped. Caps now count the living,
  regular promotions hold one living named character per 50 of a civ's
  agents (1-10; 50 in all), the caps hold within a batch, and an
  agent-born promotion yields an artifact with chance 0.15 (every one would
  push artifacts to 3.1 and 4.5 per civ-century). Subsets: agent-born great
  persons after turn 50 1.8 -> 19.7 (template) and 1.6 -> 63.5
  (procedural) per world, active at the end 0.1 -> 1.9 and 6.2;
  `get_promotions` +0.01 ms a turn.
- **Calls to arms** (`46ed76a`). Alliance, overlord and federation calls
  bind only partners within reach (a border with either side, or two land
  steps of the attacker); out of reach the treaty stands. Joins three or
  more steps from the attacker 17% -> 3.5% of procedural joins; template
  subsets identical.
- **Intelligence** (`e728c4a`). Merchant and cultural faction and merchant
  great-person bonuses need contact (a direct source or a contact-ledger
  flow). Wars on civs with no direct contact 49% -> 32% of procedural
  declarations. Golden oracles rolled forward (`ORACLE_CHAIN` link
  `open_items`): standard from turn 9, wide from turn 0.
- **Restorations** (`f3d4218`, documented, not changed). Procedural realms
  are larger (succession crises need 3+ regions) and less stable (drains
  14.0 against 7.0 a civ-turn, the black market's per-region repeat the
  largest), and in hybrid a restoration's +15 stability does not hold, so
  deposed rulers counter-restore (8 of 20). No per-pair check scales with
  civ count. The black-market loop correction raised fiscal crises on every
  subset and did not lower restorations; not shipped.
- **Gini** (`f463b2e`). `compute_gini` sums with `math.fsum` (exactly
  rounded): independent of BLAS threads and CPU; 5.6 ms against 1.3 ms at
  50,000 agents. Agents-off byte-identical; in the subsets only the stored
  Gini values change (last bit).
- **Gates** (code head `f463b2e`, extension `7becf518...99b43`, fresh
  directories, strict). Template full 200 x 500 PASS, NO REGRESSION against
  the merged head: needs 171 of 200 (174), artifacts 1.77 (1.69),
  rebellion 0.0364 (0.0330), migration 0.0636; agent-born great persons
  61.9 per world, 54.5 after turn 50, 1.9 active at the end. Procedural
  full 100 x 300 PASS, NO REGRESSION: needs 91 of 100 (83), artifacts 2.41
  (2.00), rebellion 0.0389 (0.0352), fiscal crises 1.59 (1.40); agent-born
  116 per world, 94.8 after turn 50, 5.0 active. The merged heads with
  PR #45 and PR #46 give identical output (50 files).
- **Open.** Epidemic deaths per head, spiritual need, embargoes never lapse,
  hybrid counter-restorations, black-market leakage per border region,
  fiscal stress from wars in reach.
- **Tests** (code head `f463b2e`, extension `7becf518...99b43`). `cargo test`
  1,012 / 2 ignored; not-slow 6,332 / 3 skipped; slow 12 / 3; no-Rust
  6,099 / 237; oracle lane PASS in 97.6 s (2,330 / 36). Merged head
  `4f6d0d7` (extension `735558c9...8a489`): `cargo test` 1,020 / 2;
  not-slow 6,420 / 3; oracle lane PASS in 90.8 s (2,407 / 38).

---

## Validation integrity (2026-10-26, `fix/validation-integrity`)

> **Last updated:** 2026-10-26 (`fix/validation-integrity` from `main` `fc01d6e`, merged with `b8f0243` and `18a05be`: validation tooling only, simulation output byte-identical; needs oracle method 4 counts outcomes after the snapshot turn; batch directories refuse reuse and carry a checked manifest; the comparator refuses different cohorts unless exploratory; seed 0, lockfile, CI from the lock, viewer CI; full gate with method 4 not run.)

`fix/validation-integrity` from `main` `fc01d6e` (PR #44), merged without
rebase with `b8f0243` (PR #45) and `18a05be` (PR #46). An external review's
four findings, each reproduced on `fc01d6e` first. Details and evidence:
[`docs/integration/validation-integrity.md`](../../integration/validation-integrity.md).

- **Needs oracle method 4.** The turn-t sidecar snapshot is written after
  turn t's agent actions (a migrant already in its new region, a rebel's
  autonomy +0.10), and methods 2 and 3 counted turns t .. t+19: two seeds
  whose only actions fall on the snapshot turn passed the full profile.
  Method 4 counts t+1 .. t+20 (eligible when t + 20 < N); same matching,
  criteria and profiles; same-turn rebels stay prior rebels.
  `method_version=3` re-scores method 3 exactly; the comparator flags 3
  against 4 for re-baselining. No threshold changed.
- **Method 3 -> 4 on the 48 retained sidecar sets.** Full gate sidecars
  (200 x 500, needs-followups head `d44cf4f`): pooled +0.222 (+0.204), 176
  seeds -> +0.209 (+0.190), 175; binding +0.192 (+0.168) -> +0.185
  (+0.160); PASS -> PASS. Subsets: 3 subset-profile verdicts change (two
  terms-zeroed sets FAIL -> PASS, the unshipped hunger mid range PASS ->
  FAIL) and 3 full-rule verdicts (two older terms-on sets PASS -> FAIL at
  bounds -0.006 and -0.005, one terms-zeroed set FAIL -> PASS at +0.021).
- **Batch directories.** A batch refuses a non-empty destination (claimed
  by an exclusively created manifest) and writes `batch_manifest.json`:
  seeds, turns, requested simulation configuration, Git revision and
  package digest, native extension SHA-256, interpreter, platform and thread
  environment, SHA-256 of every validation input. Validation refuses
  unlisted bundles, missing seeds, short horizons, changed inputs and
  incomplete batches; `--legacy-batch` validates an old directory
  unchecked. The gate runner checks its destination first and writes a
  manifest for determinism pairs.
- **Comparator.** Refuses reports of different seeds, turns, worlds,
  simulation configuration or profile unless `--exploratory` (labelled
  EXPLORATORY); old reports give seeds and turns through their per-seed
  rows. NO REGRESSION is stated to mean no newly failing required gate.
  Results by category (execution, determinism, balance, mechanism);
  conservation, performance and rendering are named as unmeasured.
- **Small fixes.** `--seed 0`; `uv.lock` regenerated (numpy, scipy,
  pyarrow, arro3-core were missing), CI checks it and installs with `uv sync
  --frozen`; a viewer job (npm ci, tests, lint, build).
- **Gates (method 4, merged `9e563e3`, extension `5a9619cd...0262c` fresh
  from the merged tree; identical at `39d7e35` and `c1ce58a`).** Template subset 42-61 PASS (+0.191 (+0.101), 14
  seeds; binding +0.253 (+0.134)); procedural subset 42-61 PASS (+0.177
  (+0.132), 18; binding +0.206 (+0.117)); each NO REGRESSION against the
  last method 3 report of the same simulation, every other oracle
  identical, needs re-baselining flagged; method 3 re-scored on each batch
  equals that report. Full template gate with method 4 not run (the
  full-gate slot was taken by other gates for three hours, then the shared
  disk reached 100%).
- **Identity.** `turn_speed_identity.py` (4 cases, 320 files) and a
  42-44 x 200 hybrid batch (331 files): 0 differences against `fc01d6e`,
  `b8f0243` and `18a05be` (each merge); `batch_manifest.json` is the only
  new file.
- **Tests** (at `9e563e3`). Focused 512 passed; oracle lane PASS in 100.6 s
  (2,500 passed, 38 skipped; new `validation-tooling` chunk); not-slow
  `-n 2` 6,452 passed, 3 skipped, 9 pytest-xdist serialization failures
  that fail the same way on `fc01d6e` and pass in one process; viewer 363
  tests, lint and build; no `cargo test` (no Rust change on this branch).
- **Open.** The cohort oracle has the same window convention (not
  changed). Method 4 weakens the binding component's subset-scale
  separation a little (it decides only in the full profile). The manifest's
  Git revision does not detect uncommitted changes (the package digest
  does). Not run: the full gates with method 4, `-m slow`, the new CI
  workflows on GitHub.

---

## Seats of learning (2026-10-26, `feat/scholarship`)

`feat/scholarship` from `main` `fc01d6e` (PR #44), merged without rebase with
`b8f0243` (PR #45). Details, tables and evidence:
[`docs/integration/scholarship.md`](../../integration/scholarship.md).

- **System** (`--scholarship`, default off; `WorldState.scholarship`, omitted
  while off). Academies are founded by rulers at their capitals, temple
  schools by temples of the realm's faith, libraries from city purses
  (`--cities`). Each has a level, upkeep (`keep` treasury, prestige or
  purse) and scholars: scholar-occupation agents, great-person scientists
  teaching, refugees. Research gains x(1 + 0.15 x levels); adoption and
  keeping improve near a seat; archives keep more copies. Sack, famine,
  persecution of the seat's faith and loss of patronage strike it. On a fall
  the scholars flee to the nearest seat, a rival's first, with up to 3
  techniques (channel `scholars`) and their archive. Rust adds a fifth
  healthy-world driver, `learning`: gated, appended last, no new draw,
  `seat_pull`/`seat_flight` rebuilt each batch. Seat chroniclers write the
  seats' record. The viewer gets a Learning tab; narration gets seat lines
  in the standing state, from the dated snapshot; the transport contract
  gains `scholarship`.
- **Gates** (switch on, `03a406a`). Template full 200 x 500: PASS strict,
  NO REGRESSION against main (migration 0.0653 / 0.0635, rebellion
  0.0342 / 0.0330, needs 181 / 174 seeds, latest satisfaction 0.626 both,
  0 extinct). Procedural full 100 x 300: PASS strict, NO REGRESSION (needs
  83 / 83, migration 0.0751 / 0.0746, rebellion 0.0333 / 0.0352, artifacts
  2.07 / 2.00). Subsets 42-61, 62-81 and procedural 42-61: PASS, NO
  REGRESSION against the switched-off arms, whose reports equal main's.
  Every gate ran in a fresh output root, and its analysed seeds equal the
  requested ones.
- **Effect** (paired probe, 200 turns). Courts' and temples' accounts lost
  fell from 0.202 to 0.151 (template, 40 worlds) and from 0.209 to 0.148
  (procedural, 20); over 500 turns (template, 20 worlds) it fell from 0.264
  to 0.186. Where a seat kept copies, expected war-loss survival is
  89.6% against 76.8% without them (template) and 90.3% against 78.0%
  (procedural). Technique counts stay within noise. Per run, 6.5
  techniques were carried and 0.27 adopted through `scholars`.
- **Identity**: switch off (default and `--no-scholarship`), 9-case matrix,
  395 files, 0 differences against `fc01d6e` and `b8f0243`. Save/load
  resume identity holds with the switch on and everything on.
- **Tests** at `ec274cb`: cargo 1,017 passed, 2 ignored; pytest not-slow
  6,403 / 3; slow 12 / 3; no-Rust 6,168 / 239; oracle lane PASS in 98.0 s
  (`learning` chunk); viewer 363 passed, lint and build pass. The native
  build `5a9619cd...0262c` was rebuilt clean and is identical.
- **Cost**: turn CPU within noise (+1% and +6% at 15.5k and 35.5k agents with
  seats standing); guard bundle 8.33 MB on, 8.64 MB off.
- **Open**: the default stays off at the review bar although both full gates
  pass (a flip follows `defaults-wave8.md`); civ-level technique effects are
  below noise; the narrator's account block (historiography) still names
  losses dated after the moment, for every chronicler.

## Historical parity (2026-10-26, `fix/historical-parity`)

`fix/historical-parity` from `main` `fc01d6e` (PR #44). Details:
[`docs/integration/historical-parity.md`](../../integration/historical-parity.md).

- **Convention.** `historical_context.py`: `AsOf(turn, phase)` (snapshot
  `S` = state after turn `S - 1`; `after(T)` knows records `<= T`, snapshot
  `T + 1`; `before(T)` knows `<= T - 1`, snapshot `T`; never a later
  snapshot) and an immutable `HistoricalRecord.view`: characters born by
  then with status, deeds, memories, bonds, hostage state and dynasty
  counts as of then; final observations (needs, arc phase, memory strength,
  bond sentiment, bridge Gini/displacement/trade dependency, artifact
  holders) only at or after `observed_through`.
- **Narration** (CLI inline, `--narrate`, live range) reads the view after
  each moment's last turn; settlements and Gini from that snapshot;
  artifacts described by their making; future only in the labelled AFTER
  and LATER CONSEQUENCES sections. Live range narration and `--narrate`
  share `narration_inputs.from_bundle` (the world now reaches live range
  narration). Real 500-turn hybrid bundle: 40 future-dated deed, memory or
  relationship lines and 5 premature deaths in 14 character moments -> 0.
- **Curator gaps** run from `before(start)` to `after(end)` (a last-turn
  change counts; 17 of 49 gaps change on that bundle); civs sorted (bytes
  equal under `PYTHONHASHSEED` 1, 2, 3).
- **Viewer.** Civs without a history row at the snapshot are left out of
  rankings, chips, summaries and default focus; their inspector says
  "Unavailable". One transport contract (`transport_contract.json`, read by
  `transport.py` and `lib/transport.ts`); static, Batch Lab, streaming
  (`guilds` and every later system) and reconnect carry every system of
  one fixture; `completed` carries historiography and languages.
- **Live server**: handshake needs an allowed origin (Vite 5173/4173 on
  loopback, `--live-origin`) and the session token printed in the viewer
  link (`?ws=...&token=...`); else HTTP 403.
- **Codecs**: malformed `history_delta` patches raise `BundleDecodeError`
  (Python, TypeScript); the viewer shows "Invalid bundle history: ..." and
  ends loading in `finally`.
- **Identity**: simulate-only template 42/7/1234 (200 turns) and procedural
  11 (80 turns), 36 files byte-identical (bundles minus `generated_at`);
  mechanical narrated runs 42/7: all but narration identical, prompts
  differ (artifact lines, 3 era registers).
- **Tests** (no-Rust Python 3.13.17): oracle lane PASS in 126.2 s
  (narration chunk 139 passed, with `test_historical_parity.py`); 25
  narration, history, live (socket suites included), codec, bundle and main
  files 654 passed, 4 skipped; viewer 352 passed (44 files), lint and build;
  entry chunk 777,454 -> 780,900 bytes. No cargo, native or 200-seed gate
  (no simulation change).
- **Open**: no hybrid run with live bridge values; undated lifecycle
  changes (exile return) inferred from deeds; curator scoring still uses
  final characters; viewer panels beyond civ views not audited.

## Turn speed (2026-10-26, `perf/turn-speed`)

`perf/turn-speed` from `main` `b3ad9a4` (PR #42), merged without rebase with
`c8f7eb4` (PR #43). Performance only; every output byte identical. Details:
[`docs/performance/turn-speed-2026-10.md`](../../performance/turn-speed-2026-10.md).

- **Profile** (process CPU, 1 rayon thread; hardware counters unavailable
  in this VM): at 22k and 52k agents exact spatial drift was 53% and 55%
  of the instrumented turn (75% and 84% of the native tick); at 52k,
  OpenBLAS threads spinning after `compute_gini`'s threaded dot product
  cost another 30% of the turn once drift was fixed. The gate and
  procedural worlds were flat Python: checkpoint serialization,
  governance, politics marshalling, cyclic GC, sidecars, region batches.
- **Changes** (11 commits): drift in lanes of 8 agents per cell; dormant
  fields omitted with `exclude_if` (pydantic floor 2.12) instead of wrap
  serializers; `OPENBLAS_THREAD_TIMEOUT=16` set before NumPy loads; politics
  op batches through `pylist`, schema read once; knowledge propagation
  without per-packet HashMaps; `IdSlots` id -> slot table in five native
  phases; fishery counts by `bincount`; `columnar.schema_names`; memory
  streams reuse entry JSON; C-level `exclude_if` predicates.
- **Result** (process CPU per turn, uninstrumented, two paired runs against
  `b3ad9a4`): 52k agents 1,717 -> 651 ms (2.64x), 22k 437 -> 206 ms
  (2.12x), procedural 48 x 10 129.9 -> 117.0 ms (1.11x; whole run 1.16x),
  gate world 43.5 -> 37.1 ms (1.17x; whole run 1.19x).
- **Identity**: 9-case matrix (off, hybrid, procedural, 22k, 52k; 395 files)
  byte-identical after every commit and again against `c8f7eb4` after the
  merge; `scale_bench --hash` pool and event digests equal at 20k and
  50k; subset gate 42-61 on the `c8f7eb4` base and on the head: 2,204
  files, run files byte-identical, the three reports that name their
  output directory identical after path normalisation, both PASS. Full
  gate not run.
- **Tests** cargo test 1,009 passed, 2 ignored (at `abab14d`; Rust
  unchanged since); pytest `-m "not slow"` 6,315 passed, 3 skipped;
  `-m slow` 12 / 3 (fresh native build `a6d0de13...6d31`, compiled module
  checked); no-Rust 6,082 / 237; oracle lane PASS in 103.6 s with a new
  `turn-speed` chunk.
- **Found**: `np.dot` in `compute_gini` gives different bits with different
  OpenBLAS thread counts above 10,000 values, so hybrid runs with civs over
  10k agents depend on the machine's core count (not changed);
  `--parallel 1` runs `cpu_count - 1` workers; `uv.lock` was already stale.
- **Open**: drift still 71% of the native tick at 52k (now bound by the
  divisions and the per-lane repulsion lists); per-pair ChaCha setup in
  knowledge propagation; marriage; checkpoint event serialization; GC.

## Procedural gates (2026-10-26, `feat/procedural-gates`)

`feat/procedural-gates` from `main` `11238d5`, merged without rebase with
`aa0f655` (PR #40, guilds), `2dd47d4` (PR #41, narration) and `b3ad9a4`
(PR #42, movement founders). Details, tables and evidence:
[`docs/integration/procedural-gates.md`](../../integration/procedural-gates.md).

- **Profile.** `scripts/m53b_run_validation.py --worldgen procedural`: every
  seed a 32-region, 10-civ heightmap/Voronoi world (`--regions`/`--civs`
  override); subset 20 x 200, full 100 x 300. A procedural seed costs 3.2
  template seeds of CPU, 2.6 of disk, 3-4 of validation memory; 200 x 500
  would need 10-16 GB to validate. The full profile ran in 39-45 minutes
  on three workers (2.5 GB validation peak, 2.8 GB batch once `state.json`
  and memory streams are pruned). The template profile is unchanged.
- **Oracles.** The artifact creation band divided by a fixed 4 civs; it is
  per starting civ now (template reports byte-identical). Reports of
  non-template batches name their worlds; the comparator refuses to mix
  worlds. The other oracles normalise already.
- **Found on `main` `aa0f655`.** Procedural full gate FAIL on artifacts only (5.38
  per starting civ per 100 turns, artworks over half). Aggregate merchant
  great persons needed 3 live trade partners: every other civ in a
  four-civ world, ordinary among ten (hub civ-turns 74-84% against 2-8%),
  so 100-163 merchants per 300-turn world against 3-7.
- **Fix.** A merchant hub trades with every other living civ, and with at
  least three (`contact_ledger.merchant_hub_partners`); unchanged up to four
  living civs. Procedural full gate on the merged head PASS
  strict (artifacts 2.00, needs 83 of 100, migration 0.0746, rebellion
  0.0352, 0 extinct), NO REGRESSION against the fix on `aa0f655`, which
  went FAIL -> PASS there, and against `b3ad9a4` without the fix (FAIL,
  artifacts 5.32), whose artifact failure it resolves; procedural subsets
  on `b3ad9a4` artifacts 6.04 -> 2.69, NO REGRESSION; template full gate on the merged head PASS
  strict, NO REGRESSION against `b3ad9a4` (8 of 200 worlds differ;
  migration 0.0635, rebellion 0.0330, needs 174 of 200, 0 extinct); the
  snapshot-pruning test world re-pinned.
- **Open.** Calls to arms draw allies three to five regions away into wars
  (about half of procedural war declarations follow a call to arms or a
  federation's defence; with the war-chest borrowing, fiscal crises 3.7
  and defaults 3 times the template rate per civ); accuracy bonuses reach
  civs never met; pretender restorations about 12 times the template rate
  per civ; the native registry closes promotions at 50 named characters
  (both worlds, by turn 50); epidemic deaths per head 1.7 times; spiritual
  need below threshold in 26% of agent samples (templates 14%).
- **Tests** not-slow 6,294 passed, 3 skipped; slow 12 / 3 (with the new
  procedural smoke run); no-Rust 6,061 / 237; oracle lane PASS in 103.1 s
  (the gate profile tests in the core chunk); extension
  `c26d6cd2...bbb99`; no `cargo test` (no Rust change).

## Movements and narration polish (2026-10-26, `fix/movements-narration-polish`)

`fix/movements-narration-polish` from `main` `2dd47d4` (PR #41). The first
commit changes the simulation; the rest observe it. Details:
[`agent-movements.md`](../../integration/agent-movements.md#founders-at-founding-no-empty-movements),
[`narration-coverage.md`](../../integration/narration-coverage.md#follow-ups-news-guild-chronicles-spread),
[`guilds.md`](../../integration/guilds.md), [`historiography.md`](../../integration/historiography.md).

- **Movements founded with no members** (`022deb2`). The viewer read the
  record correctly. A movement was founded in Phase 10, after the turn's
  agent tick, and its founders (15% of the region's adults, at least 3, not
  the aggrieved the founding counts) joined on the next tick, so every
  movement stood empty in the snapshot after its founding turn; members who
  lapsed, died or left left it standing empty until the 5-turn fade. On
  `main`: 427 of 7,395 living snapshots in subsets 42-61 and 62-81 (all
  359 founding snapshots, 68 later in 40 stretches, at most 4), 121 of
  2,100 in the three narration runs. Fix: `movements.rs` `seed_founding` /
  `AgentSimulator.found_movement` enrol the founders at founding (the same
  selection, no draw); a founding nobody can join is not made; a movement
  with no member left ends at once. After: none (0 of 82,037 in the full
  gate). Older saves keep the next-tick seeding.
- **Gates**: subsets 42-61 and 62-81 PASS, NO REGRESSION against `main`;
  full gate 200 x 500 PASS strict, NO REGRESSION against the guilds report
  (needs 0.196 -> 0.191 lower bound, 173 seeds; binding 0.178 -> 0.170;
  migration 0.0644 -> 0.0634; rebellion 0.0368 -> 0.0329; latest
  satisfaction 0.627 -> 0.626; 0 extinct; smallest world 63 -> 23).
  Rebellion is lower in all three gates; one part at a time on 42-61 shows
  it follows the founders' timing, not the end of empty movements (which
  alone leaves every figure equal to `main`'s).
- **Movement news** (`a3e83b5`): the native census names the news most
  informed aggrieved hold; a founding where a quarter of them hold news of
  a like movement's won demand elsewhere cites it as a cause ("stirred by
  news of the demand won in R in turn T"; +2 in the prompt's line
  selection). About one linked founding per run; no event added.
- **Guild chronicles** (`e8cee7d`): formations, privileges, guild charters
  granted and repealed and guild risings told from importance 3 (glory,
  decree, disgrace): 18 / 88 / 10 new accounts in the three runs, none
  changed.
- **Curator spread** (`dad4bb3`, `e144ae6`): an untold stretch longer than
  two even spacings gets its best window for the weakest moment that can go
  (at least 75% of its score; importance-9 events stay). Longest untold
  stretch 30 -> 18 / 18 -> 12 / 1 -> 1 turns, largest gap 36 -> 24 / 29 ->
  23 / 11; turning points in the moments 103 -> 95 / 332 -> 329 / 136.
  Prompts bounded: mean 2,647 -> 2,638 / 4,097 -> 4,080 / 2,737 -> 2,739
  tokens, maxima unchanged.
- **Identity** (base `022deb2` + its extension, head `e144ae6` + its
  extension): `narration_identity.py compare-observers` 0 differences over
  six runs (three narrated, template 42 off, template 7 and procedural 11
  hybrid with validation sidecars); `state.json` byte-identical except one
  news cause in three runs; snapshots, validation sidecars and agent events
  byte-identical; golden fixtures unchanged; narration deterministic under
  `PYTHONHASHSEED` 0, 1, 4242 and on rerun.
- **Tests** (Linux, Python 3.13, `-n 2`, the head's extension
  `c26d6cd2...bbb99` built fresh, compiled classes verified): cargo 1,007
  passed, 2 ignored (two new); not-slow 6,284 passed, 3 skipped; slow 11 /
  3; no-Rust 6,043 / 230; oracle lane PASS in 104.1 s (2,288 passed, 36
  skipped). Viewer unchanged (not run): it already read `members` as
  recorded.
- **Open**: news of a founding or rising elsewhere is not cited; levies and
  dissolved guilds are not chronicled; a busy 10-civ moment still mixes
  stories; no LLM was called.

## Narration coverage (2026-10-26, `feat/narration-coverage`)

`feat/narration-coverage` from `main` `11238d5` (PR #39), merged without
rebase with `main` `aa0f655` (PR #40, guilds). Narration and viewer only;
every simulation output byte-identical. Details:
[`docs/integration/narration-coverage.md`](../../integration/narration-coverage.md).

- **Audit.** 252 event types (static scan plus computed and native
  emitters; 200 seen in three hybrid runs). Before: 14 types reached the
  prompt with an empty line (hazard rolls, native politics triggers), 3
  with a misleading description (`move_capital` to the same region,
  "scholars fled", `Mass Migration` "flee" for a persecuted share); every
  event of a six-turn window was listed (procedural prompts averaged 25k
  tokens, max 38k); the chain bonus saturated, so a supervolcano lost to
  quarantines; standing state (reforms, charters, famine severity,
  movement creed and leader, guilds) never reached the narrator.
- **Prompts.** `narration_context.py`: event lines with labels and
  rewordings; at most 12 lines (+4 for turning points of unshown kinds),
  repeats folded, routine counted; STANDING STATE from the snapshot after
  the moment; LATER CONSEQUENCES from recorded causes; agent context limited
  to the moment's characters (6) and three memories each. Prompt mean
  22.0k -> 10.7k, 101.5k -> 16.2k, 23.6k -> 10.6k characters; every turning
  point inside a selected moment listed.
- **Curator.** Chain bonus x0.4; routine and bookkeeping kinds score their
  importance; turning points +1.5 per step from 8; kinds seen 3-5 times +1,
  over 12 times -log2(n/12) (cap 3); cluster = best + 0.5 second + 0.25
  third; diversity on a moment's main actors and kind, exempting only
  landmarks (importance 7+), never a single moment; named events matching no
  event join the moment covering their turn.
- **Viewer** (Chromium on real bundles): Food tab, food layer and region
  detail read crises at the snapshot's completed turn (655 of 861 new
  reports were shown a turn early beside unrelated food); unobserved regions
  sort last; wares to two decimals; creed legend; martyred leaders marked;
  the movement record note marks future ends; header names template or
  procedural worlds.
- **Identity.** Simulate-only 9 / 110 / 91 files and narrated runs 9 / 15 /
  9 files (everything but the narration) byte-identical against `11238d5`
  and `aa0f655`. `curator.event_label` stays as it was: historiography
  writes its saved accounts with it during the run.
- **Tests** not-slow 6,274 passed, 3 skipped; slow 11 / 3; no-Rust 6,034 / 229; oracle lane PASS in 101.7 s (2,279 passed, 35 skipped; new `narration` chunk); viewer 303 passed, lint and build; extension `5ede10a9...8b07d6`. No cargo or 200-seed gate (no Rust or simulation change).
- **Open**: no temporal-spread rule in the curator; movement news is not
  recorded per founding; historiography does not chronicle guild events;
  prose quality with an LLM untested (no API was called).

## Guilds, burghers and movement news (2026-10-26, `feat/guilds`)

`feat/guilds` from `main` `2ef3097` (PR #38), merged without rebase with
`11238d5` (PR #39). On by default for new worlds since its full gate
(`--no-guilds` opts out; saved worlds keep their setting). Details, tables
and evidence: [`docs/integration/guilds.md`](../../integration/guilds.md);
news-driven spread also in
[`agent-movements.md`](../../integration/agent-movements.md).

- **Guilds** (`guilds.py`, `guilds_state.py`): a city that makes wares forms
  a craft guild, one whose merchants and craftworkers (the town's share of
  its farmers' labour; there is no artisan occupation) reach 4 a merchant
  guild. Charters grant privileges: market rights a monopoly of the city's
  wares (the wares' commerce term x1.5), self-government a say in dues
  (x0.8). The guild takes 5% of the city's commerce (10% with the monopoly)
  and helps pay for walls.
- **Guild movements**: a levy (a poor or warring lord raising the city's
  dues), a revoked charter, a sack, an occupation or a repealed guild
  charter may raise a movement of a new `guild` creed; members are the
  city's civilian residents through the existing `movement_id`; its reform
  is a lasting guild charter (dues x0.75, no levy) under Merchant Courts,
  repealed and restored like the others; a rising stirs the city.
- **Burghers**: `FactionType.BURGHER` (appended) in realms with chartered or
  free cities or guilds: the patricians' voice; trade 1.8, embargo 0.6, war
  0.5 within the faction caps; charter grants read merchant + burgher
  influence; +0.3 x influence to crushing commons and liberty; an elected
  succession candidate; the governance kernel keeps the four classic
  factions; native dominant code 4.
- **Movement news**: foundings, risings, reforms and crackdowns become
  packets (type 4) in the region and, at half intensity, its neighbours;
  news never displaces another packet (the others are slot for slot as
  without news). A like movement's news from elsewhere raises joining (up
  to x2; a crackdown down to x0.5) and founding (up to x2). Over 40 paired
  200-turn worlds: significant movements +16% (+0.23, SE 0.12), risings
  +34% (+0.12, SE 0.05), foundings +4% (within noise); a movement's own
  reach unchanged.
- **Gates**: subsets 42-61 and 62-81 PASS, NO REGRESSION, on against off
  (`f0aa299`). Full gates 200 x 500 with `--guilds`, PASS strict, NO
  REGRESSION: `f0aa299` against trade-crafts (needs lower bound 0.177 ->
  0.201, migration 0.0619, rebellion 0.0379); the merged head against
  needs-followups (all pairs 0.204 -> 0.196, binding 0.168 -> 0.178,
  migration 0.0642 -> 0.0644, rebellion 0.0360 -> 0.0368, latest
  satisfaction 0.633 -> 0.627, 0 extinct). Per 500-turn world (merged): 7.0
  guilds, 0.50 guild movements, 0.11 guild charters, burghers in 2.2 realms.
- **Identity**: `--no-guilds` against `main` `11238d5`: 88 files, 0
  differences (and against `2ef3097` before the merge); defaults equal
  `--guilds` (25 files); an old save resumes off (24 files).
- **Tests** (merged head): cargo 1,005 / 2 ignored; not-slow 6,241 / 3;
  slow 11 / 3; no-Rust 6,009 / 235; oracle lane PASS (2,181 passed); viewer
  297 tests, lint and build. Bundle guard 7.894 / 8.613 MB (+570 bytes).
  Rust tick and whole-turn CPU at about 23,700 and 54,000 agents within the
  shared machine's spread of the base.
- **Open**: guild movements are small on template worlds (a guild charter in one
  world of nine per 500 turns); news does not ride with cargo or ships
  except over bonds; members do not cross borders; no leagues of guilds or
  free cities; procedural distributions not measured.

---

## Needs follow-ups (2026-10-26, `fix/needs-followups`)

`fix/needs-followups` from `main` `f5425dc` (PR #37), merged without rebase
with PR #38 (`main` `2ef3097`). Corrections in every agent mode, no switch;
`--agents off` byte-identical to `main` (template 42 and procedural 7, 30
files), golden fixtures unchanged. Details:
[`docs/integration/needs-followups.md`](../../integration/needs-followups.md).

- **Oracle method 3.** Method 2 plus a binding component: pairs of the same
  cell and traits whose lower agent is below the need's threshold and whose
  partner is at or above it, need gap above 0.05; their pooled net
  concordance needs a seed-clustered 95% lower bound above zero. Required
  only in the full profile (`validation_gate.NEEDS_BINDING_REQUIRED_PROFILES`);
  in the subset profile reported (`needs_binding` informational row) but not
  deciding, since its bound sits within one or two standard errors of zero
  there. The m53b runner passes `--profile` to `chronicler.validate`; the
  gate applies each profile's rule to any method 3 result; the comparator
  flags 2 against 3 as a method change and never counts a subset's
  informational binding failure. `method_version` 3; `require_binding=False`
  scores method 2. Subset verdicts with the terms on: PASS 6 of 6 (main and
  head). Full rules on the subsets: terms on 5 of 6 (head 82-101 bound
  -0.028), zeroed FAIL 6 of 6, 59 of 60 shuffles FAIL. The rule (gap 0.05)
  was chosen from four on three earlier code versions; the merged sets were
  held out.
- **Newborn needs** from the birth parent (safety, material, social,
  spiritual, autonomy; purpose 0.5), no random draw: the gap between ages
  0-4 and 20-39 falls from -0.07 / -0.09 / +0.04 / -0.02 to under 0.01
  (safety, material, spiritual, autonomy). Spiritual now binds 23.9% (8.1%):
  the 0.5 reset kept everyone under 20 above its threshold; spiritual-need
  migrations 0.7-1.0% -> 1.9-3.4% of migrations; conversion does not read
  it.
  Matched pairs halve (needs no longer carry age).
- **Autonomy after a move**: the displacement turns still bar a move and
  cost satisfaction, but no longer block autonomy restoration; good
  conditions 5.3% -> 1.4% below, bad 39% -> 28%. No migration weight
  changed.
- **Hunger mid range** (famine deaths 1.50, births 0.60): needs FAIL on
  42-61 (binding bound -0.026); shipped values unchanged.
- **Gates.** Full 200 x 500 against the trade-crafts report: PASS strict, NO
  REGRESSION (needs method 2 -> 3, re-baselining flagged); all pairs +0.222
  (+0.204), 176 of 200 seeds (190); binding +0.192 (+0.168), 5,060
  informative; migration 0.0615 -> 0.0642, rebellion 0.0388 -> 0.0360,
  latest satisfaction 0.627 -> 0.633, 0 extinct, lowest population 78 -> 56.
  Subsets 42-61 and 62-81 PASS, NO REGRESSION.
- **Tests** (extension `f8e1017e...c2f410`): cargo 996 passed, 2 ignored;
  not-slow 6,210 passed, 3 skipped; slow 11 / 3; no-Rust 5,980 / 233;
  oracle lane PASS in 92.0 s (2,153 passed, 33 skipped). Rust tick CPU per agent +8% at ~23k and ~55k alive (shared machine); bundle guard 7.89 / 8.61 MB.
- **Open**: the binding component's subset power (informational there, so
  a subset gate no longer catches zeroed terms; a terms-zeroed full gate
  would likely pass it: residual about +0.07, full-scale error 0.014);
  material's term barely shows in the binding pairs; few autonomy and safety
  pairs; spiritual's dynamics uncalibrated; purpose keeps its age gradient;
  `--parallel 1` runs `cpu_count() - 1` workers.

---

## Bulk trade, mines and forests, crafts (2026-10-26, `feat/bulk-trade-crafts`)

`feat/bulk-trade-crafts` from `main` `7fa364a` (PR #35), merged without
rebase with `b5d41af` (PR #36) and `f5425dc` (PR #37); head `21c0e7e`.
Three commits, on by default, each with a switch that restores the old
behaviour exactly (identity on three worlds each, and all three off against
`main` `f5425dc`). Per-part numbers below were measured before the merges. Details, tables and evidence:
[`docs/integration/bulk-trade-crafts.md`](../../integration/bulk-trade-crafts.md).

- **A, bulk trade** (`41a461c`): a trip carries up to its narrowest leg's
  capacity (2 / 5 / 10 loads by land / river / sea), loads added while the
  next earns the one-load threshold with committed cargo counted; the market
  where the cargo earns most. Food to famine regions +19% / +27% (template /
  procedural), city import share 1.04 -> 1.31% / 1.36 -> 1.68%, famine
  episodes 1.5% / 3% shorter, herding 0.78 -> 0.69 / 0.65 -> 0.56, non-food quantity
  -30-36%. Most loads stay under one unit; the ship's capacity binds on 1% of
  crossings. `economy.{land,river,sea}_cargo_cap: 1`, `cargo_fill: 0`
  restore one load.
- **C, mines and forests** (`8ac3f08`): labour split by headcount, food
  first; food labour on the farm curve, each non-food slot on its own
  (deposit x reserves, woodland x forest cover), same form and reference
  density. Ore per worker 1.74 sparse -> 0.43 crowded (was flat at 1.1);
  raw output +20-26%, food +5-9%, famine region-turns -1.3 to -2.3 pp.
  `economy.raw_reference_density: 0` restores the farm curve on all labour.
- **B, crafts** (`f58076e`): `crafts` (slot 8, category `craft`): city crafts
  turn timber and ore into wares up to the existing `craft_raw_demand`;
  0.01 a head a turn wanted everywhere; sufficiency restores the material
  need (0.006); merchants carry wares (not advertised in packets); city
  commerce counts its wares (+1.5-2% on average). Wares 161 / 897 a run,
  sufficiency 0.92 in city regions against 0.27 elsewhere; raw deliveries to
  city regions x3-3.5; merchant income +53-62%. Optional schema columns; old
  states, cities and bundles load; viewer Wares column.
- **Gates** (head `21c0e7e` against `main` `f5425dc`): subsets 42-61 and
  62-81 PASS, NO REGRESSION (needs lower bound 0.081, 0.090); full gate
  200 x 500 against the movements-on report: PASS strict, NO REGRESSION;
  needs 190 seeds, lower bound 0.177 (188, 0.192); migration 0.0615;
  rebellion 0.0388; latest satisfaction 0.627; 0 extinct. Before the merges
  B failed the needs subset 42-61 (lower bound -0.053; still -0.043 without
  the wares' material term; 82-101 and 102-121 PASS) and passed its full
  gate against the farmland report (171 seeds, lower bound 0.157); after the
  needs-calibration merge 42-61 failed the seed fraction (11 of 12) and the
  full gate passed (182 seeds, lower bound 0.194).
- **Tests** (head): cargo 995 / 2 ignored; not-slow 6,196 / 3; slow 11 / 3;
  no-Rust 5,966 / 233; oracle lane PASS (2,147 passed); viewer 292 tests,
  lint and build. Bundle guard 7.89 / 8.61 MB (as `main`); Rust tick CPU per
  agent at or below `main`'s at about 23k and 52k. Golden fixtures unchanged.
- **Open**: thin markets limit loads (10 everywhere: city imports 2.6%,
  long famines halved; not gated); wares counted by volume in commerce; the
  wares' material weight (0.006) not recalibrated after food's rose to
  0.115; no tools effect, artisan occupation or guilds.

---

## Movements slice 2 and movements on by default (2026-10-26, `feat/movements-2`)

`feat/movements-2` from `main` `ea08126`, merged with `main` after PR #35
(bundle version 6) and PR #36 (needs calibration), without rebase. Details,
measurements and tables:
[`docs/integration/agent-movements.md`](../../integration/agent-movements.md).

- **Lasting reforms.** A granted demand enacts a reform that stays in force:
  poor relief (realm; Commons Management with governance), home rule (the
  stronghold; Written Law; the region's city gains a charter level),
  toleration of the members' faith or the reform of the ruler's church
  (abolishes a Holy Inquisition). Agents it covers read their creed need
  with a 0.3 credit for grievance and recruitment (`movements.rs`
  `REFORM_NEED_CREDIT`, `set_movement_reforms`). Repeal: the institution
  collapses or is forced out, a new ruler (harsh 0.25, else 0.03, once per
  reign), the opposing faction above 0.40 (0.03 a turn), unpaid upkeep, an
  Inquisition again; lapse with the realm or region. A repeal raises a
  restoration movement (cooldown waived, twice the founding chance) whose
  grant restores the reform.
- **Leaders.** A movement that has demanded or risen, with 8+ members and no
  living leader, raises its boldest member in the stronghold: a native
  promotion (`queue_movement_leaders`, trigger 5, caps over living named
  characters), installed on the next turn; a secession crowns a living
  leader.
- **Viewer.** Movements tab (`MovementsPanel`, `lib/movements.ts`); optional
  snapshot `leader`, `restores`, `reforms`; fixture from template seed 48.
- **Calibration after needs calibration.** With slice 1's thresholds the
  corrected needs more than doubled foundings (11.9 -> 26.9 per 500-turn
  template world, significant 1.6 -> 5.2, 0.47 living movements per
  civ-turn against 0.23). Material 0.55 -> 0.45 and autonomy 0.60 -> 0.50: 20.5 founded,
  3.0 significant (1-5), no commons or liberty founding in a region without
  famine, conquest, persecution or a minority faith; repeal gentler (median
  reform life 61 turns).
- **Gates.** Subsets 42-61 and 62-81 PASS / NO REGRESSION, on against off.
  Full 200 x 500 with `--agent-movements` on `36c5617`'s tree: PASS strict, NO
  REGRESSION against the needs-calibration full gate (migration 0.0626 ->
  0.0629, rebellion 0.0385 -> 0.0409, needs 190 -> 188 of 200, lower bound
  0.195 -> 0.192, 0 extinct; 21.6 movements, 3.4 significant, 5.7 reforms,
  3.3 leaders per world; 8 movement secessions).
- **Default on** in a separate commit; `--no-agent-movements` opts out;
  saved worlds keep their setting; `benchmark_headless.run` pins it off.
- **Identity.** `--no-agent-movements` against the base (`e1b6a13`): 88
  files and the 42-61 subset gate (2,201 run files), 0 differences; the
  defaults equal `--agent-movements` (25 files); an old save resumes off.
- **Verification** (final head, fresh native build): `cargo test` 982
  passed, 2 ignored; `pytest -m "not slow"` 6,178 passed, 3 skipped;
  `-m slow` 11 passed, 3 skipped; no-Rust 5,953 passed, 228 skipped; oracle
  lane PASS (2,134 passed, largest chunk 32.4 s of 110 s); viewer 291 tests,
  lint and build. Tick time within the shared machine's spread at ~23,000
  and ~51,600 agents; bundle guard world 7.894 MB native and 8.612 MB
  no-Rust (+785 bytes; guard 10.5 MB).
- **Open.** Information packets as a spread channel; guilds and a city
  faction; agendas of a leader's own; a movements map layer; procedural-world
  distributions; liberty secessions stay rare (8 in 200 full-gate worlds).

## Needs calibration (2026-10-25, `fix/needs-calibration`)

`fix/needs-calibration` from `main` `48b72be`, merged with PRs #32, #33
and #34 (`main` `ea08126`) without rebase. A correction in every agent
mode, no switch; `--agents off` byte-identical to `main` (template 42 and
procedural 7, 30 files), golden fixtures unchanged. Details:
[`docs/integration/needs-calibration.md`](../../integration/needs-calibration.md).

- **Finding.** Safety, material, social and autonomy were below their
  thresholds in at most 0.05% of agent-turns (15 probe worlds, 200 turns),
  in bad conditions as in good: bad-condition fixed points sat above the
  thresholds (famine material 0.43, war-zone safety 0.47), restoration of
  0.01-0.04 a turn met spells mostly under five turns, every agent spawned
  at 0.5 (needs read as age), social counted bonds wherever the other
  person lived, and persecution blocked restoration region-wide while
  rebellion's +0.10 left the persecuted with the highest autonomy.
- **Dynamics.** Decay and restoration raised together (5-15-turn
  response; good fixed points 0.62-0.75 as before). Safety: war-zone
  pressure 0.05, conquest -0.15 and raid -0.20 shocks. Material: hunger
  band pressure (dearth 0.039, famine 0.018), wealth buys food in a
  shortage. Social: restored by positive bonds with living people in the
  region. Autonomy: own-faith persecution, martial law, remembered
  conquest by another civ, a 0.20 cap on the turn of a conquest. Social
  and autonomy thresholds 0.25 -> 0.35. New region-batch columns
  `harsh_rule` and `raided_this_turn` (read and cleared each batch).
- **Binding** (probe, base -> head): safety in contested regions at war
  0.07% -> 32%, conquered or raided 25%, at peace 0.5%; material in famine
  0.07% -> 44% (poorest third 72%, richest 10%), fed 0.8%; social without
  a co-resident bond 0.11% -> 26%, two or more 2.3%; autonomy persecuted
  37%, freshly conquered 40%, martial law 35%, self-ruled 2.6%; good
  conditions 5.7% (the five-turn displacement block after each move).
- **Social sign** reversed: a deficit pushes migration (driver
  `social_need`, code 18), the stay bonus is gone; at base the isolated
  already migrated 10.6% a turn against 5.6% for the bonded; the oracle's
  social pairing -0.20 -> +0.19 at 500 turns. Material's switch push
  skips farmers (it emptied the fields in famine).
- **Sensitivity.** Terms zeroed: the needs oracle still passes all three
  subsets (+0.123 / +0.184 / +0.155; terms on +0.228 / +0.155 / +0.234;
  one of three failed before the farmland merge). Not met: the needs now
  track conditions that drive the same behaviour by other routes, and in
  72% of pairs the lower agent is above its threshold. Pairs whose lower
  agent binds: on +0.27, off +0.08.
- **Gates.** Full 200 x 500 against the farmland report: PASS strict, NO
  REGRESSION; needs 182 -> 190 of 200 (lower bound 0.178 -> 0.195;
  autonomy pairing +0.12 -> +0.62), migration 0.0610 -> 0.0626, rebellion
  0.0308 -> 0.0385, latest satisfaction 0.630 -> 0.622, 0 extinct.
  Subsets 42-61, 62-81, 82-101 PASS / NO REGRESSION.
- **Tests** (extension `0cb2948c...7cdb8d`): cargo 979 passed, 2 ignored;
  not-slow 6,146 passed, 3 skipped; slow 11 / 3; no-Rust 5,921 / 228;
  oracle lane PASS in 76.0 s (2,102 passed, 28 skipped; largest chunk
  28.3 s of 110 s). Bundle guard unchanged (21.55 MB native, 22.67 MB
  no-Rust). Rust tick CPU per agent +6% at ~23k, +10% at ~50k. The
  maritime piracy test moved to seed 8.
- **Open**: an oracle that reads the terms (pairs below the threshold,
  matching within condition, or a terms-off control arm); newborns still
  start at 0.5; autonomy's displacement block; spiritual and purpose
  unchanged.

---

## Bundle version 6 (2026-10-25, `perf/bundle-headroom`)

`perf/bundle-headroom` from `main` `ea08126` (PR #34). A format change of
`chronicle_bundle.json` only; no simulation or Rust change. Details, tables
and evidence: [`docs/performance/bundle-v6.md`](../../performance/bundle-v6.md).

- **Breakdown** (size guard, version 5): `history` 70-73% of the file,
  `world_state` 13-14% (2.72 / 2.37 MiB of it a second copy of
  `events_timeline` and `named_events`), `events_timeline` 10-11%. In the
  history, `civ_stats` 5.6 MiB (`governance` 2.4), `diplomacy` 1.9,
  `techniques` 1.2, `proxy_wars` 1.0, `finance` 0.9, `perception_errors` 0.8;
  most of each snapshot repeats the previous one.
- **Format** (`src/chronicler/bundle_codec.py`): `history_delta` holds the
  first snapshot and one patch per later snapshot (changed keys only,
  `~d` removed keys, `~o` key order, `~l`/`~t`/`~n` list items, `~r` literal);
  `world_state.events_timeline` and `named_events` are `null` when they repeat
  the top-level fields. Plain JSON; decoding restores the version-5 text byte
  for byte (number types, key order, signed zero). No float rounding.
- **Savings**: world_state copies -2.72 / -2.37 MiB, deltas -11.33 / -11.28
  MiB; size guard 22.67 -> 8.61 MiB no-Rust, 21.55 -> 7.89 MiB native
  (-62%, -63%); hybrid seed 42, 8 x 4, 300 turns, every switch on 7.51 -> 3.05 MiB;
  procedural 48 x 10 hybrid, 300 turns, every switch on 33.23 -> 14.72 MiB.
  Guard 24 -> 10.5 MB.
- **Readers**: `restore_bundle` decodes first (validation, analytics,
  narration, oracle scripts); live mode decodes before validating;
  `bundle_codec.load_bundle` for scripts and tests; the artifact oracle
  projects version 6 as version 5 (frozen hashes unchanged); the viewer
  decodes in `classifyParsedBundlePayload`. `scripts/bundle_v6.py` converts,
  decodes, compares and breaks bundles down. Old bundles load unchanged.
- **Identity**: guard world (both lanes), hybrid and procedural runs: every
  other file byte-identical to `ea08126` (`diplomacy_identity.py compare`),
  bundles equal once decoded (`bundle_v6.py compare`). Viewer: the v6 and v5
  guard and procedural bundles render the same DOM and screenshots on four
  surfaces and the system panels at three turns, no console errors.
- **Tests**: not-slow 6,163 passed, 3 skipped (+22, `tests/test_bundle_codec.py`);
  slow 11 / 3; no-Rust 5,940 / 226; oracle lane PASS in 76.6 s (2,124 passed,
  28 skipped); viewer 280 tests, lint and build pass. Native extension
  `21344bb6...02ef` (unchanged). No Rust change; cargo not run.
- **Open**: the event timeline is now the second field (28% of the guard
  file, 39% of the procedural one; repeated keys and defaults); a columnar
  layout would be the next saving.

## Farmland and regional climate (2026-10-25, `feat/farmland-climate`)

`feat/farmland-climate` from `feat/hunger-mortality` `d720fce`,
fast-forwarded to `main` `617a87e` (PR #32) and `82c131b` (PR #33).
Corrections, on by default; `economy.farm_reference_density: 0` and
`climate.trend_share: 1.0` restore the old behaviour (with the old hunger
constants the head is byte-identical to `main` on three worlds, 35 files).
Details, measurements and tables:
[`docs/integration/farmland-climate.md`](../../integration/farmland-climate.md).

- **Finding.** Each farmer grew the slot's yield however many farmed, so
  famine deaths never relieved a famine; famine regions were thinner than
  fed ones (farmer-weighted density 0.29 against 0.43). Climate made three
  quarters of template famine region-turns: drought and cooling drain water
  to the floor in every region at once (two thirds of regions in famine for
  25 turns of each 75-turn cycle; 15.6% of turns with three quarters of a
  world in famine, episodes up to 25 turns).
- **Diminishing returns.** Farm labour is effective labour
  `E = L (L_ref + L_h) / (L + L_h)`, `L_ref = 0.33 x arable capacity`
  (potential capacity x techniques irrigation +0.10, ox plough +0.10, heavy
  plough +0.15, irrigation works +0.10), `L_h = L_ref` (elasticity 0.5).
  Calibrated so today's fed regions produce what they did (0.98-1.01).
  Optional economy columns `farm_labor_ref` / `farm_labor_half`; the kernel
  reports `farm_productivity`, which the region batch carries to farmer
  income. Agents off: the famine check scales the food yield by the curve
  (farm labour 0.54 x population).
- **Regional climate.** Crop factor `1 - 0.5 (1 - m) - h`; global drought and
  cooling water losses halved. Clusters of up to three neighbours
  (`climate_clusters`), harvest years good or bad (persistence 0.4, bad
  22.5% of years, depth 0.2-0.6, water `h x 0.0667` a turn), all from
  namespaced `stable_hash_int`; mean crop factor and water budget derived
  equal to the global schedule's. `get_climate_phase` unchanged; the
  companions are pure; native ecology reads a `harvest_shock` column and
  `set_climate_config`.
- **Effect** (template 42-51 / procedural 7-11, 200 turns, against `main`):
  famine episodes 11.5 -> 8.1 / 6.8 -> 5.3 turns (p90 28 -> 21 / 16 -> 9),
  20+-turn episodes 30% -> 11% / 7.4% -> 2.2%, climate famines 14.9 -> 10.5
  turns, world-wide famines of 10+ turns 13 -> 3 in 10 worlds; output per
  farmer 1.46 at density 0.1-0.2 and 0.84 at 0.5-0.6 times constant
  returns; final population 160 -> 189 / 749 -> 880; agents off: famine
  reports 130 -> 108, lowest population 29 -> 84.
- **Hunger magnitudes.** Mid range (deaths D 0.10 / F 1.50, births 0.15 /
  0.60): famine deaths 2.24 x fed, but needs 42-61 FAIL (10 of 20), 50 of 80.
  Shipped (0.10 / 1.00, 0.15 / 0.45): famine deaths 1.96 -> 2.04 x fed,
  births 1.00 -> 0.87; required subsets pass; lowest population over 500
  turns of the seven low seeds 56 -> 85.
- **Gates.** Subsets 42-61, 62-81, 82-101, 102-121 PASS / NO REGRESSION
  against `main` (needs 61 of 80 both, pooled 0.152 -> 0.171; migration
  +0.006-0.008). Full 200 x 500 against the hunger head: PASS strict, NO
  REGRESSION; needs 186 (method 1) -> 182 of 200 (method 2, lower bound
  0.178; `rebaseline_required`), migration 0.0554 -> 0.0610, rebellion
  0.0301 -> 0.0308, latest satisfaction 0.622 -> 0.630, 0 extinct, one
  silent collapse; final population median 165 -> 179; famine reports
  120 -> 91 per run, dearth 194 -> 238, epidemic reports 135 -> 172.
- **Golden oracles** rolled forward (`corrected_farmland_2026_10*`,
  `ORACLE_CHAIN` link `farmland`): FC-FARM-RETURNS single 5 / standard 0 /
  wide 9, FC-REGIONAL-CLIMATE 0 / 0 / 26, FC-HUNGER-MAGNITUDES none.
- **Tests** (`84bfb44`, extension `21344bb6...02ef`): cargo 969 passed, 2
  ignored; not-slow 6,141 passed, 3 skipped; slow 11 / 3; no-Rust 5,918 /
  226; oracle lane PASS in 83.0 s (2,102 passed, 28 skipped; largest chunk
  27.6 s of 110 s). Bundle guard 16.44 -> 21.55 MB native, 22.21 -> 22.67
  MB no-Rust (more polities alive per snapshot, not more founded). Rust
  tick CPU per agent within spread at ~22k, +10% median at ~51k (diverged
  worlds, more migration).
- **Open**: one harvest-year clock (12 turns) against yearly demography;
  population +18% at 200 turns; ore and timber saturate on the same curve;
  clusters are fixed and latitude does not scale shocks; dearth turns rise
  (17% -> 22% of agent-turns); the mid-range hunger terms wait on the needs
  oracle's seed criterion.

## Needs oracle power (2026-10-25, `fix/needs-oracle-power`)

`fix/needs-oracle-power` from `main` `48b72be` (PR #31). Oracle, comparator
and tests only; simulation, Rust and sidecars unchanged. Details:
[`docs/integration/needs-oracle-power.md`](../../integration/needs-oracle-power.md).

- **Why pairs were scarce:** template worlds hold about 185 agents per
  snapshot in about 55 (civ, region, occupation) cells, and a need spreads
  0.03-0.10 (SD) within a cell. The 0.2 gap plus three traits within 0.1
  left 45-63 informative pairs per subset even over all snapshots. Best-of
  selection then judged each seed on one of 95 candidates (1-4 pairs).
- **Method 2** (`method_version` 2): every eligible snapshot and pairing
  pooled; gap 0.1 (cells, traits and the prior-rebel exclusion unchanged);
  a pair is concordant when the lower-need agent has more of the event.
  PASS: the one-sided 95% seed-clustered lower bound of the pooled net
  concordance above 0, and at least 60% of seeds with C > D. Method 1 is
  kept as `run_needs_oracle_best_of`.
- **Subsets** (method 1 seeds of 12 -> method 2 net, lower bound, seeds):
  main 42-61 16 -> +0.18, +0.10, 15; 62-81 16 -> +0.20, +0.10, 15; 82-101
  16 -> +0.33, +0.24, 18; routing `--no-cities` 62-81 FAIL 8 -> PASS +0.18,
  +0.10, 13; `--agent-movements` 42-61 12 -> PASS +0.14, +0.05, 17. Every
  other oracle result identical.
- **Sensitivity:** needs shuffled within cells: method 2 FAIL 15 of 15,
  method 1 PASS 10 of 15. Rust need-driven terms zeroed: method 2 FAIL 1 of
  3 subsets, method 1 FAIL 1 of 3; pooled net +0.24 -> +0.14, purpose +0.26
  -> -0.09. Only purpose (15% of agents) and spiritual (7%, unpaired) drop
  below their thresholds; safety, material, social and autonomy 0-0.09%.
- **500-turn probe** (142-161, not the full gate): +0.166, bound +0.121, 17
  of 20 seeds (method 1: 19).
- **Compatibility:** the comparator reads `method_version` (absent = 1). A
  needs status change across methods is not counted as a new or resolved
  failure: `rebaseline_required` plus an "Oracle method changes" section.
  With `origin/main`'s comparator, method 1 PASS against method 2 FAIL was a
  new required failure.
- **Identity:** seeds 42-44 x 200, hybrid with sidecars, `origin/main`
  source against the branch: 330 files, 0 differences.
- **Cost:** needs scoring 4.0-5.0 s -> 0.4-1.0 s per subset batch, 12.2 ->
  1.5 s per 20 x 500.
- **Tests (Linux, Python 3.13.17, extension fresh from `48b72be`):**
  not-slow 6,097 passed, 3 skipped (17 new); slow 11 passed, 3 skipped;
  no-Rust 5,878 passed, 222 skipped; oracle lane PASS in 72.1 s (2,062
  passed, 24 skipped). Rust unchanged.
- **Open:** about 60% of the pooled association survives zeroing the need
  terms, so it is not specific to them. Social is paired with more
  migration, against the Rust term (-0.09 on subsets, -0.40 at 500 turns).
  Spiritual has no pairing. Matching cannot see wealth, age or urban
  status. The full gate with method 2 has not been run.

---

## Hunger by severity (2026-10-25, `feat/hunger-mortality`)

`feat/hunger-mortality` from `main` `3355289`, merged with `main` `ec229b5`
(PR #30, city markets) and `48b72be` (PR #31, agent movements) without
rebase. A correction, on by default, no switch. Details, sources and tables:
[`docs/integration/hunger-mortality.md`](../../integration/hunger-mortality.md).

- **Finding.** In agent modes hunger killed no one and did not lower births:
  famine death rates were 1.5 times the fed rate only through soil, water
  and disease; famine births matched or beat fed births (fed regions sit in
  the crowding brake); dearth and famine reports had the same effects; the
  epidemic boost followed the report's cooldown, not hunger.
- **Design.** Dearth `min(1, (1 - s) / 0.4)`, famine
  `(0.6 - s) / 0.6 x min(1, run / 3)` (run below 0.6; Rust reads the new
  optional region column `food_severe_turns`). Deaths
  `x (1 + v (0.05 dearth + 0.50 famine))`, `v` 1 under 5 and at 60+, 0.5
  otherwise, adults x1.25 poorest to x0.75 richest by civ wealth percentile.
  Births `x (1 - 0.10 dearth)(1 - 0.30 famine)`, no new draw; the rebound
  comes from the crowding brake. Agent-mode epidemics read measured hunger
  (`Region.food_shortfall`, saved): susceptibility `+0.15 dearth + 0.35
  famine`, fatality `x (1 + 0.10 dearth + 0.40 famine)`; `--agents off`
  keeps the flat cooldown terms. A dearth report drains 1 stability (famine
  3) and weighs a third of a famine in the cooldown readers
  (`Region.dearth_cooldown`). `--agents off` and shadow: the famine toll
  scales with hunger (the old 5 x mult at a total famine), no second term.
- **Magnitudes** at the low end of the historical ranges. The mid-range
  design (deaths F 1.50, births F 0.60) failed the needs subset 62-81 (9 of
  12) and took a world to 30 people; on `ec229b5` an intermediate one took
  seed 111 to 24: climate phases keep whole worlds in famine for 20-25
  turns and farm labour has constant returns, so deaths never end a famine.
- **Effect** (template 42-51 x 200 against `ec229b5`): famine death rate
  1.54 -> 1.96 times fed (under 5: 2.28, 60+: 1.80); the term is 22% of
  famine deaths and 2% of dearth deaths; famine births 1.39 -> 1.00 times
  fed (27% withheld, dearth 5%); births after a famine 1.41 -> 1.59 times
  fed; epidemic susceptibility in famine 1.21 -> 1.37, fed 1.07 -> 1.05.
  Procedural 7-11 x 300: deaths 1.49 -> 1.77, births 1.01 -> 0.84.
- **Gates.** Full 200 x 500 (merged head `223e23a`) against the city-markets
  report: PASS strict, NO REGRESSION; migration 0.0580 -> 0.0554, rebellion
  0.0308 -> 0.0301, needs 189 -> 186, latest satisfaction 0.618 -> 0.622,
  0 extinct, one silent collapse (limit 20); final population median
  177 -> 165. Subsets 42-61 and 62-81 PASS / NO REGRESSION (needs 16 -> 15
  both). On `3355289` (cities off) the full gate and both subsets PASS / NO
  REGRESSION as well. `ca859b7` (aggregate growth term removed) and the
  movements merge leave hybrid runs byte-identical.
- **Golden oracles** rolled forward (`corrected_hunger_2026_10*`,
  `ORACLE_CHAIN` link `hunger`): the scaled aggregate toll changes
  `standard` from turn 0 and `wide` from turn 9; `single` unchanged.
- **Tests** (`be99dbe`, extension `5d58881c...bf21da`): cargo 963 passed, 2
  ignored; not-slow 6,099 passed, 3 skipped; slow 11 passed, 3 skipped;
  no-Rust 5,879 passed, 223
  skipped; oracle lane PASS in 76.0 s (2,068 passed, 25 skipped; largest
  chunk 27.0 s of 110 s). Bundle guard 16.44 MB native, 22.21 MB no-Rust. Tick
  time within run-to-run spread at ~22k and ~52k alive.
- **Open**: magnitudes stay low until famines can end themselves
  (diminishing returns on land) or climate famines shorten; no marriage,
  flight term or household wealth for children; the dearth weight is a
  judgment; report effects still wait for the cooldown; the aggregate model
  has no dearth tier; migration 0.0054 above the strict floor.

## Agent movements (2026-10-25, `feat/agent-movements`)

`feat/agent-movements` from `origin/feat/city-markets` `b4ce043`,
fast-forwarded to `main` `ec229b5` (PR #30, same tree). Default off behind
`WorldState.agent_movements` (`--agent-movements`). Details, parameters and
a movement's history: [`docs/integration/agent-movements.md`](../../integration/agent-movements.md).

- **Slice.** Movements live in the population: a per-agent `movement_id`
  (Rust pool and snapshot column, appended last; the contract accepts the
  earlier 23-field captures). Three creeds from the needs: commons
  (material), liberty (autonomy), sect (spiritual). Founded (Python, from an
  end-of-tick native census) where 20% of a region's adults are aggrieved
  and a carrier exists (a great person, a city, the boldest aggrieved); an
  adopted M16b idea of the creed's values is carried. Recruitment through
  bonds, co-residence and settlements, gated by grievance, boldness and
  loyalty; spread with migrants, bonds and travelling merchants. Strength
  presses the creed's ally faction; at 10% the movement demands; the ruler
  grants (relief: need and satisfaction recovery), refuses or cracks down
  (persecution memory, martyrs through queued deaths, martyrdom boost for
  sects). Risings (rebel utility in the stronghold, a failed outcome for
  legitimacy) end in secession (liberty, ruler under 30 stability, through
  `politics.transfer_regions_to_new_civ`, now shared with the cities' free
  city), concession or a crushing; sects break away through
  `religion.fire_schism`. Fading, winning, breaking, dissolving.
- **Finding.** The religion detector fills the 16-faith registry in the
  first dozen turns of every gate world; most of those faiths later have no
  believer. A movement schism takes the place of such a faith (same id and
  position); the detector keeps its cap.
- **Identity** (switch off, `scripts/agent_movements_identity.py`, base
  `ec229b5` with its own extension): 88 files, 0 differences (template
  42/7/1234 off 300 and hybrid 200, procedural 48x10 seed 7 off 200 and
  hybrid 120); 73 / 0 with `--no-agent-movements`; switch on with agents
  off 27 / 0 inert; subset gate 42-61 base against the switch-off branch:
  20 x 110 run files and the four reports identical.
- **Gates** (subset, `--parallel 1`, switch on against the base): 42-61,
  62-81, 82-101 PASS / NO REGRESSION. Migration 0.0619 -> 0.0608, 0.0548 ->
  0.0546, 0.0619 -> 0.0603; rebellion 0.0376 -> 0.0350, 0.0153 -> 0.0162,
  0.0353 -> 0.0319; satisfaction latest +0.009, +0.012, +0.006; needs 16 ->
  12, 13, 14 (12 required; a probe without the need restoration on reforms
  gives 14 on 42-61); schisms 12.0 -> 12.25, 12.2, 12.1 per world; no
  movement secession in 60 worlds; 0 extinct. About 7 movements founded per
  200-turn world; per 20 worlds 73-94 demands, 36-42 reforms, 13-17
  crackdowns, 5-13 risings, 2-5 movement schisms.
- **Tick time**: within the run-to-run spread at ~22,800 and ~54,500 alive
  (Rust tick 104-117 ms and 434-469 ms wall in every arm, with 1 and 2
  movements of 108 and 671 members in the timed turns).
- **Bundle guard**: 18.78 MB off (unchanged), 18.90 MB with the switch on
  (field 0.13 MB); hybrid 20.06 / 19.10 MB.
- **Tests**: at `c93e87e` with a fresh extension (`cde64b3e...b5cf6a`): `cargo test`
  959 passed, 2 ignored (main 945); not-slow 6,080 passed, 3 skipped (main
  6,046); slow 11 / 3; no-Rust 5,861 / 222; oracle lane PASS in 75.5 s
  (2,050 passed, 24 skipped; largest chunk 26.4 s of 110 s). Full gate
  not run.
- **Open**: the needs oracle's 2-4 seed drop and the rarity of liberty
  secessions at the full gate (not run); information packets as a spread
  channel; lasting reforms through governance institutions; guild
  movements and a city faction; movement leaders as great persons; a
  viewer tab.

## City markets and cities on by default (2026-10-25, `feat/city-markets`)

`feat/city-markets` from `main` `cee5013` (PR #28, cities default off),
merged with `main` `3355289` (PR #29) without rebase. Details and tables:
[`docs/integration/city-markets.md`](../../integration/city-markets.md).

- **Routing correction** (`0d4df97`, every run): the economy reports demand
  and post-trade supply per category (region batch `market_demand_*` /
  `market_supply_*`); non-food cargo travels by its price gap (activity
  proxy retired); trade packets advertise markets (`market_signal`), not
  export margins; merchants plan sequentially against a per-tick tally of
  committed cargo (herding). Template 42-51 x 200 against `cee5013`: food
  deliveries to short regions 62.5% -> 80.3% (eaten short next turn 31% ->
  61%), to empty 3.3% -> 1.5%; famine events 140 -> 131; deliveries-per-market
  Gini 0.79 -> 0.73; herding 0.91 -> 0.80; merchant income +10%;
  satisfaction 0.589 -> 0.599; migration 0.0591 -> 0.0562. No golden
  fixture moved (agent modes only); mutual-aid adversarial scenario
  reactivates a turn later.
- **Cities as markets** (`bada9a5`, `--cities`): city farmers give part of
  their labour to the town (0.8 / 0.7 / 0.6 by rank; economy column
  `farm_labor_factor`), crafts want raw materials (`craft_raw_demand`), a
  besieged or occupied city is cut off from the merchant graph, imports add
  to commerce. City regions' sufficiency 1.22 -> 1.16; more of their grain
  from same-realm neighbours (39% -> 45%); hinterland farmer income +11%
  (others +8%). Imports stay about 2% of a city's food (one-unit merchants,
  thin surplus). A tested premium variant was dropped (cities stopped
  exporting).
- **Viewer** (`b2f8353`): Cities tab (ranks over time, the turn's table, a
  city's purse, unrest and recorded moments).
- **Gates** (merged tree): full 200 x 500 with cities on: PASS strict, 0
  extinct, NO REGRESSION against main `3355289` and Wave 8 (migration
  0.0580, rebellion 0.0308, needs 189 of 200, final population median 177
  against 199.5). Subsets, routing against main / cities on against off:
  42-61 PASS / NO REGRESSION both; 62-81 routing FAILS needs (8 of 12; also
  before the merge), cities on PASS / NO REGRESSION. Pre-merge 82-101
  routing PASS.
- **Flip** (`e979fd9`): cities on by default for new worlds;
  `--no-cities` opts out; saved worlds keep their setting; benchmark pin.
  `7f54112` gives the cities' agent reads a row-path fallback.
- **Identity**: switch off equals `3355289` + routing (hybrid) and
  `3355289` (agents off): 172 files, 0 differences; pre-merge 145 / 0.
- **Tests** (`e979fd9`, extension `46f4fa81…c52b9b`): cargo 945 passed, 2
  ignored; not-slow 6,046 passed, 3 skipped; slow 11 passed, 3 skipped;
  no-Rust 5,831 passed, 218 skipped; oracle lane PASS in 67.6 s (2,021
  passed, 20 skipped); viewer 276 tests, lint, build. Guard world 18.78 MB
  native (cities field 0.12 MB), 19.92 MB no-Rust. Tick time: equal to
  main at ~22k alive; at ~54k about 20% more Rust CPU in the measured turns
  from the diverged world (first turns, same population, equal or
  cheaper).
- **Open**: needs oracle noise at subset scale (62-81); migration margin
  (routing -0.0015 on subsets); city imports capped by merchant capacity;
  no craft good; city map layer; city proxy for `--agents off`; ~20% more
  Rust CPU per turn at ~54k from the diverged world (unprofiled by phase).

## Navigation, famine labels, migration drivers (2026-10-25, `fix/navigation-famine-labels`)

`fix/navigation-famine-labels` from `feat/defaults-wave8` (`7f055d6`; on
`main` as `a95e4d7`, same tree), no rebase. Details and tables:
[`docs/integration/navigation-famine-labels.md`](../../integration/navigation-famine-labels.md).

- **Navigation** (`47bd9d9`, behavior change): `techniques.technique_level`
  (read-only) counts a civ's known techniques of a domain;
  `maritime.navigation_level` reads navigation (sailing, celestial
  navigation, compass, ocean navigation; 0-4) for range, quality, the ship
  cap and storms. Subsets 42-61 and 62-81 against Wave 8: PASS, NO
  REGRESSION; 2 and 4 of 20 histories change; migration 0.0599 -> 0.0597
  and 0.0549 -> 0.0550, latest satisfaction 0.615 -> 0.616 and 0.620 ->
  0.618, rebellion unchanged; storm losses down a third.
- **Famine** (`3ffa444`, labels only): the agent-mode check reports any
  shortfall; on template worlds 44% of controlled region-turns sat in a
  viewer famine span and 41% of reports were at 0.6 sufficiency or more. A
  report is now famine when sufficiency stayed below 0.6 for 3 turns, else
  dearth (`Region.food_severe_turns`); one provenance episode per region;
  every consumer reads both (`FOOD_CRISIS_EVENT_TYPES`). Famine spans 44% ->
  16% (template) and 47% -> 13% (procedural) of region-turns. Agents-off
  runs byte-identical; hybrid agent events identical. No mechanic changed:
  the famine-memory threshold stays (migration margin).
- **Drivers** (`9930dbc`, Rust, labels only): `AgentEvent.migration_driver`
  (followers carry the lead's) and the `migration_driver` column;
  `mass_migration` and `notable_migration` carry `driver`, the text reads it
  (settle, work, kin, hunger, persecution, war, hardship, prospects). Files
  without the column read as no driver. Agents-off byte-identical; hybrid
  agent events identical in every existing column.
- **Full gate** (200 x 500, `9930dbc`) against Wave 8: PASS strict, NO
  REGRESSION; migration 0.0576 -> 0.0576, satisfaction 0.607 / 0.619 ->
  0.607 / 0.620, rebellion 0.0317 -> 0.0314, needs 194 -> 196, 0 extinct; 55
  of 200 histories change, all with a sea; naval battles 1.16 -> 0.90 and
  storm losses 2.42 -> 2.02 per run, sea cargo +3%; 40% of food-crisis
  reports famine; 21% of mass migrations settling or seeking work.
- **Bundle guard**: 20.35 -> 18.66 MB native, 19.72 -> 19.80 MB no-Rust,
  under 24 (navigation changes the guard world's history).
- **Tests** (`9930dbc`, fresh native build): `cargo test` 928 passed, 2
  ignored; not-slow 6,000 passed, 3 skipped; slow 11 passed, 3 skipped;
  no-Rust 5,792 passed, 211 skipped; oracle lane PASS (77.3 s, largest
  chunk 27.2 s of 110 s); viewer 267 tests, lint and build. Golden
  fixtures unchanged.
- **Merged with `main`** (`cee5013`: PR #27 and PR #28 cities, default off),
  no rebase: `urban` joins the driver names; cities record famine, not
  dearth, as a misfortune. Merged head: `cargo test` 934 passed, 2 ignored;
  not-slow 6,036 passed, 3 skipped; slow 11 passed, 3 skipped; no-Rust
  5,825 passed, 214 skipped; oracle lane PASS (83.8 s, largest chunk
  30.3 s); viewer 267 tests, lint, build; bundle guard bytes unchanged.
  The full gate ran on `9930dbc` (cities off, so it stands).
- **Open**: hunger kills no one in agent modes; the cooldown effects do not
  scale with severity; a famine is declared up to five turns late; the
  famine-memory threshold needs the migration probe before any change;
  the viewer-only migration field has no drivers.

---

## Cities as actors (2026-10-25, `feat/cities`)

`feat/cities` from `integrate/wave-7` (`bcf14d8`), merged with
`origin/main` `a95e4d7` (PR #27, Wave 8 defaults) without rebase. Default
off behind `WorldState.cities` (`--cities`). Details, parameters and
example histories: `docs/integration/cities.md`.

- **Slice.** A city is an M56a settlement grown to town size, keyed by its
  `settlement_id`: ranks town / city / great city from M56a's estimate
  (smoothed), decline, falls (abandoned when M56a dissolves the settlement,
  deserted when nearly empty), refounding that names its predecessor.
  Commerce from residents by occupation, trade routes and food, at the
  reference scale; dues by charter to the lord, paid next Phase 2 as `keep`
  (finance counts them); a civic purse for charters and walls, plundered in
  sacks. Patricians raise the lord's merchant faction; charter petitions
  (granted by trait, treasury, weakness, merchant influence; refusals leave
  grievance); unrest from misery, hunger, dues, occupation and grievance;
  urban revolts end in suppression, concession or, against a lord under 30
  stability, a free city (a new civ built as secession builds one). Sacks
  on occupation or conquest; walls through the infrastructure pipeline;
  epidemics hotter by urban share; chartered cities deepen domestic credit.
  City events name the settlement, so narration gets its in-world name.
- **Rust.** A fourth healthy-world driver, urban pull, with its own gate
  (rural non-soldier adults; a neighbouring region of the realm whose
  `city_pull` exceeds home's by 0.25, fed, with room; farmers only below
  0.80): pull 0.5 x ramp, net of roots, reach rule. `city_pull` is an
  optional region-batch column (absent = 0). Budget term `urban`. No
  existing weight changed; no new draw.
- **Identity** (`scripts/cities_identity.py`, base `a95e4d7` exported with
  its extension): template seeds 42/7/1234 (off 300, hybrid 200),
  procedural 48x10 seed 7 (off 200, hybrid 120): 88 files, 0 differences,
  default and `--no-cities` (also against `bcf14d8` before the merge);
  `--cities` with `--agents off`: 42 files identical apart from the layer's
  own field. Subset gate 42-61 base against switch-off: 2,200 run files and
  4 report files (batch path normalized) identical.
- **Gates** (switch on against off, 20 x 200 hybrid, `--parallel 1`,
  merged head): both PASS / NO REGRESSION. 42-61 / 62-81: migration 0.0599
  -> 0.0622 / 0.0549 -> 0.0558; rebellion 0.0350 -> 0.0341 / 0.0130 ->
  0.0138; satisfaction within 0.004; needs 13 -> 16 / 14 -> 16 seeds;
  epidemic deaths +9.2% / +17.3%; no extinct world; arcs pass. Per world:
  4.5 cities founded, 0.85 fallen, 4.0 charters, 0.58 revolts, 0.075 free
  cities. Before the merge (Wave 7 defaults) also PASS / NO REGRESSION;
  rebellion +0.0052 / +0.0018 there, so its sign is divergence.
- **Urban pull**: 1.9% of migration units (4.3% with household followers);
  gate open for 1.8% of evaluated agent-turns.
- **Tick time** (~23.5k and ~54k agents, cities live, pre-merge): process
  CPU unchanged within noise. Hybrid guard world 500 turns: 16.40 -> 17.50
  MB, the field 0.32 MB; the agents-off guard is unchanged.
- **Tests** (merged head `d3d53a4`, fresh native build `96cad2b5...`):
  - `cargo test --locked`: 933 passed, 2 ignored (+6: the urban gate, the
    bit identity without `city_pull`, the budget term, `tests/test_urban_pull.rs`).
  - `pytest -m "not slow" -n 2`: 6,002 passed, 3 skipped (34 in
    `tests/test_cities.py`, 1 resume test in `tests/test_wave3_combined.py`).
  - `pytest -m slow -n 2`: 11 passed, 3 skipped.
  - No-Rust lane (slow included): 5,792 passed, 213 skipped.
  - Oracle lane (`tests/test_cities.py` in `systems-1`): PASS in 82.9 s,
    slowest chunk 30.2 s of 110 s.
  - Full 200-seed gate: not run.
- **Open:** the full 200-seed gate with the switch on; no viewer panel
  (`history[n].cities` is in the bundle); hybrid lords sit near 30
  stability, so concessions and free cities come easily; cities need
  agents (a world without settlements founds none with `--agents off`).
  Next slices: city markets in the goods economy and merchant routing, a
  guild faction, leagues and protectors for free cities, places for
  scholars and archives, siege targeting by wealth.

---

## Wave 8 defaults: agendas, maritime, nomads (2026-10-25, `feat/defaults-wave8`)

`feat/defaults-wave8` from `integrate/wave-7` (`bcf14d8`; on `main` as
`2a49040`, same tree), no rebase. Details and tables:
[`docs/integration/defaults-wave8.md`](../../integration/defaults-wave8.md).
No oracle, threshold or system parameter changed.

- **Subset gates** (all three on against all three off, `bcf14d8`): 42-61
  and 62-81 PASS, NO REGRESSION, 0 extinct. Rebellion 0.0343 -> 0.0350 and
  0.0189 -> 0.0130; migration 0.0600 -> 0.0599 and 0.0571 -> 0.0549;
  latest satisfaction 0.623 -> 0.615 and 0.609 -> 0.620; needs 13 -> 13
  and 15 -> 14. The off batches equal the Wave 7 subset reports.
- **Full gate** (200 x 500, the flipped defaults, no switch) against the
  Wave 7 full report: PASS strict, NO REGRESSION. Migration 0.0570 ->
  0.0576, satisfaction 0.608 / 0.619 -> 0.607 / 0.619, rebellion 0.0307 ->
  0.0317, needs 185 -> 194, cohort and community 200, artifacts 1.29 ->
  1.49, founders all surviving 0.115 -> 0.110, 0 extinct.
- **Flips**, one commit each (`884f28d` maritime, `29e2dce` agendas,
  `b21c215` nomads): `DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, CLI help,
  live comments, a default-and-resume test each; `benchmark_headless.run`
  pins the three off (without the pins 9 golden tests fail). Agendas lean on
  governance, finance and techniques, all on by default; none is required.
- **Identity**: flags off against `bcf14d8` 69 files, 0 differences; new
  defaults against `bcf14d8` with the three flags 25 files, 0; an old save
  resumed by both 24 files, 0, and stays off.
- **Bundle guard** (takes the defaults): 17.66 -> 20.35 MB native, 18.28 ->
  19.72 MB no-Rust, under 24. Golden fixtures unchanged.
- **Tests** (`ba5ceef`, fresh native build): not-slow 5,967 passed, 3
  skipped; slow 11 passed, 3 skipped; no-Rust 5,760 passed, 210 skipped;
  oracle lane PASS (79.7 s, largest chunk 29.4 s of 110 s). The pruning
  test world pins the three off (its history needs a civ to die).
- **Open**: rebellion floor on low-rebellion seed sets; migration margin
  0.0076; maritime `navigation_level` still 0.

---

## Healthy-world migration (2026-10-25, `feat/healthy-migration`)

`feat/healthy-migration` from `fix/leftover-persecution` (`f3eccec`),
merged with `integrate/wave-6` (`547ebbc`, no rebase). Rust only; a
behavior correction in every agent mode. Details, the calibration and the
HARD constant justification: `docs/integration/healthy-migration.md`.

- **Budget, exact** (`efc2b06`, behavior-neutral): the decision records each
  migration's positive terms; `get_migration_driver_stats`, with household
  followers by the lead's largest term and decisions by age band. Merged
  base, seeds 142-161 x 500, from turn 100: followers 41.9% of migration
  units, famine memory 31.3%, persecution memory 11.0%, opportunity 9.7%.
- **Drivers** (calibrated in `8d675be`): frontier settlement (farmers; home
  >= 0.80 of capacity, neighbour >= 0.25 emptier with land that feeds a
  farmer, food potential >= 0.5; pull 0.6), wage gap (adult farmer and
  merchant peers' mean wealth >= 1.25x with five peers and room below 0.80;
  pull 0.55), chain migration (bonds to settled emigrants from here
  outweigh bonds at home; 0.30 per bond unit, cap 0.45). All internal; a
  gate opens at 0.75 of the pull; a pull counts only toward a region home
  would not beat by the 0.18 hysteresis. Roots: 0 to 35, +0.006 a year,
  +0.02 married, +0.02 per unit of home bond strength; under-20s take no
  voluntary moves. Hysteresis 0.18, the 5-turn lock and the persecution
  terms unchanged; no new random draws.
- **Corrections found in calibration**: wage targets capped at the frontier
  gate's 0.80 (the wage gap refilled regions frontier settlement left);
  children out of the peer mean (births made growing regions look poorly
  paid); five peers (three let one agent set the mean); the reach rule.
- **Probe** (142-161 x 500): gate migration 0.0497 -> 0.0569, regression
  oracle calibrated floor -> strict; traced 0.0486 -> 0.0562 (paired
  +0.0067 +- 0.0025); healthy drivers 5.9% of units, 15.2% with followers;
  voluntary-led decisions 44% aged 20-34 (all decisions 20%); satisfaction
  0.609 / 0.615, rebellion 0.0403 (base 0.0402). Sloshing checks within
  about one standard error of the base.
- **Gates**: subsets 42-61 and 62-81 PASS, NO REGRESSION (migration 0.0600
  and 0.0571). Full gate 200 x 500 PASS, NO REGRESSION against the
  food-logistics full gate (`eda0ec0`): migration 0.0514 -> 0.0570,
  satisfaction 0.608 / 0.619, rebellion 0.0307 (the persecution fix),
  needs 185 of 200, cohort and community 200. Golden fixtures unchanged.
- **Tick time** (22k and 53k agents): process CPU unchanged or lower.
- **Tests** (`8d675be`, fresh native build): `cargo test` 927 passed, 2
  ignored; not-slow 5,923 passed, 3 skipped; slow 11 passed, 3 skipped;
  no-Rust 5,718 passed, 208 skipped; oracle lane PASS (66.1 s, slowest
  chunk 18.5 s of 110 s). Agents-off identity against the merged base 16
  files, 0 differences.
- **Not reached**: the 0.06-0.08 aim; gates open for about 5% of
  evaluated agent-turns. The occupational dead-band patch (about -0.006)
  is not applied.
- **Open**: `mass_migration` is narrated as flight whatever moved it;
  labelling it needs a driver on migration events (own review).

---

## Viewer: systems tabs and map layers (2026-10-25, `feat/viewer-systems`)

`feat/viewer-systems` from `origin/main` (`6e6fae6`), no rebase. An audit
of every system against the bundle and the viewer (table in
[`docs/integration/viewer-systems.md`](../../integration/viewer-systems.md)),
then the gaps a reader of a run meets first:

- **Tabs** in the systems panel for Wars (campaign layer), Food (famine
  spans, hunger over time, hungry regions, relief), Nomads, Agendas,
  Governance and Contact, next to the first five.
- **Map layers**, one at a time with a legend: Food, Epidemics, Wars,
  Migration, Techniques, Sea. The atlas fits the pins' bounds; the region
  inspector gains food and war blocks.
- **Two viewer-only snapshot fields**, written only in agent modes:
  `food` (per-region sufficiency mutual aid observed, relief convoys) and
  `migration` (the turn's agent moves by region pair). No simulation change.
- **Identity** (`scripts/viewer_systems_identity.py`, base `6e6fae6`): the
  bundle-size guard world, agents off, 500 turns: 10 files, 0 differences
  (`compare`). Five hybrid runs (guard world 300 turns; procedural 48x10
  and template 10x5, all on, 200 turns; template and procedural defaults,
  150 turns): every file identical once the two fields are removed
  (`compare-additive`, 62 files, 0 differences).
- **Bundle size:** the guard bundle is unchanged (18,519,396 bytes, 17.66 MB
  native; the no-Rust guard cannot change, not re-measured). Hybrid runs
  grow 0.27-0.37% (guard world 300 turns +33.8 KB).
- **Tests** (Linux, Python 3.13, fresh native build):
  - `pytest -m "not slow" -n 2`: 5,946 passed, 3 skipped (+7 in
    `tests/test_viewer_snapshot_fields.py`).
  - `pytest -m slow -n 2`: 11 passed, 3 skipped.
  - No-Rust lane (slow included): 5,743 passed, 206 skipped.
  - Oracle lane (the new file in `systems-2`): 1,948 passed, 12 skipped,
    guard PASS, 77.0 s (largest chunk 26.0 s).
  - Viewer: 262 tests (+33), lint, build (existing large-chunk warning).
  - Browser: headless Chromium on the production build with the audit
    bundles, every new tab and layer, no console errors.
- **Open:**
  - Per-turn region population, fish stocks, merchant food deliveries and
    per-region herds are not in the snapshot.
  - Elevation, moisture and real adjacency are not drawn.
  - Hashed faction colours can collide.
  - The full 200-seed gate was not run (the simulation is unchanged).

## In-world languages and names (2026-10-25, `feat/languages`)

`feat/languages` from `origin/main` (`baabafb`, Wave 6), no rebase. It adds
an observational layer modelled on the historiography. Each founding
culture group gets a proto-language (sound inventory, syllable templates,
phonotactics, a 78-morpheme naming lexicon); founding civs that share a
style are sister languages of a reconstructed proto. Languages undergo a
regular sound change every 25-55 turns (lenition, umlaut, apocope,
syncope, cluster simplification, mergers, ...), recorded per word.
Daughters branch on secession (detected from regions' previous rulers)
and after a century of separation (exclaves; conquered provinces that keep
their language). Changes spread between related languages in contact.
Contact-ledger flows bring loanwords by channel (trade, migrants,
soldiers, pilgrims) and exonyms (borrowed self-names or descriptive
names). Civs, regions, settlements, faiths, rulers and great persons get
names in the languages that know them; a conqueror takes over the local
name, and a people that shifts language keeps its old name adapted
(substrate). Canonical names stay the identifiers: nothing is renamed.
Narration gains an IN-WORLD NAMES prompt block, an "In their own tongues"
mechanical gloss, and historiography accounts told in their chroniclers'
own names; the viewer a Languages inspector (glossary, family tree,
etymology). `--languages` is **on for new worlds** (`--no-languages`
opts out); state lives in a `state.languages.json` sidecar. No Rust
change. Evidence: `docs/integration/languages.md`.

- **Identity** (`scripts/languages_identity.py`, base `baabafb` exported):
  - Template seeds 42/7/1234 (off 300, hybrid 200) and procedural 48x10
    seed 7 (off 200, hybrid 120), `--no-languages`: 80 files, 0 differences.
  - Default (on): the same 80 files identical apart from narration
    (8 `chronicle.md`, bundles identical apart from `languages` and the
    entries' prose; historiography sidecar and field identical), plus 8
    sidecars.
  - Subset gates (20 x 200 hybrid, `--parallel 1`) base / off / on: all
    PASS, 2,184 files identical, validation reports and gate decisions
    identical (batch path normalized).
  - Frozen exact-trajectory oracles hold with the layer on; a CLI resume
    (150 + 150 turns) equals the straight run.
- **Default on, justified as narration-only:** about 4% run time on the
  500-turn guard world, +1.4% bundle on the subset, 135 KB sidecar per
  200-turn run. The frozen benchmark workloads pin it off.
- **Tests:**
  - `pytest -m "not slow" -n 2` (fresh native build): 5,939 passed, 3
    skipped (34 in `tests/test_languages.py`).
  - `pytest -m slow -n 2`: 11 passed, 3 skipped.
  - No-Rust lane (slow included): 5,737 passed, 205 skipped.
  - Oracle lane (`tests/test_languages.py` in `systems-2`): 1,942 passed,
    11 skipped, 2 deselected, guard PASS, 79.5 s.
  - Viewer: 229 tests (+10), lint, build.
  - Bundle guard unchanged at 24 MB: 17.66 MB native, 18.28 MB no-Rust
    (field 0.20 / 0.21 MB).
- **Open:**
  - Separation dialects are mostly exclaves of template civs whose founding
    regions are not adjacent (about one per 200-turn run).
  - Substrate names at conquest are rare: conquerors usually know the land
    by loan already.
  - Persons' names are adapted, not translated; no morphology beyond
    compounding; rivers and seas are not named.
  - The per-turn local narrator prompt does not use the names.
  - Live-mode resume (from a client-sent state dict) starts without
    languages.
  - The full 200-seed gate was not run (the simulation is unchanged).

## Food logistics (2026-10-24, `fix/food-logistics`)

Branch `fix/food-logistics` from `integrate/wave-5` (`b7d9ced`), starting from
the food-balance open items. Details, numbers and every changed expectation:
[`docs/integration/food-logistics-2026-10.md`](../../integration/food-logistics-2026-10.md).

- **Corrections** (one commit each):
  - merchants route food by the destination's food price (1 / sufficiency)
    instead of the destination's own export margin, and never to empty
    regions (`787ba4e`; native): food deliveries to short regions 30% -> 70%,
    to empty regions 24% -> 2% (template);
  - the goods economy gets M34's subsistence floor where no food slot yields
    (`afe3b3d`; Rust kernel and Python oracle): region-turns below 0.2
    sufficiency 25% -> 13%.
- **Recalibration** (own commit, `98ba9a2`): locust swarms 0.15 -> 0.02 per
  eligible turn (the M35b placeholder gave a swarm in 62% of eligible
  region-years). Golden oracles rolled forward to
  `corrected_food_logistics_2026_10*` (`402230e`; standard and wide from turn
  3); food-balance and dead-civ-pruning fixtures frozen.
- **Effect** (template, base -> head): fed region-turns 44.6% -> 49.6%, winter
  shortfall 67% -> 61%, famines 147 -> 137 per run (below 0.25 sufficiency
  43% -> 32% of them), final population 164 -> 184 (smallest 90 -> 138);
  procedural 64-region worlds never fall below 625 (492).
- **Gates:** full 200 x 500 on `98ba9a2` PASS strict, 0 extinct,
  `validation_compare` NO REGRESSION against the techniques-on full report;
  migration 0.0514 (base 0.0512, floor 0.05), latest satisfaction 0.611.
  Repeated on the merge with `integrate/wave-6` (`eda0ec0`): same result and
  numbers; needs 190 seeds under wave-6's autonomy pairing. Subsets 42-61,
  62-81 and 82-101 PASS (the base fails needs on 62-81).
- **Tests:** before the merge not-slow 5,859 passed (base 5,844), no-Rust
  5,651 / 197 skipped (base 5,637 / 196); `cargo test --release` 903 passed,
  2 ignored. On `eda0ec0`: not-slow 5,905 passed, no-Rust 5,696 / 198
  skipped, slow 11 passed; offline oracle lane PASS in 74 s (chunks 19-21 s
  of 110 s; `test_food_logistics.py` added to `systems-1`); the
  historiography frozen-oracle test reads the food-logistics fixtures. The
  500-turn bundle is 17.47MB native / 18.07MB no-Rust (20.73 / 23.61 on the
  wave-6 tip; 24MB guard unchanged).
- **Verified, not changed:** storage caps (rarely bind) and decay;
  drought/cooling (M34 design); the occupational dead band is real (M53 moved
  the exit threshold, not the entry one) and its fix feeds worlds best of all,
  but it lowers migration by about 0.006 per agent-turn, below the strict
  floor; left open with the measured patch.
- **Open:** the migration floor versus better-fed worlds; trade packets still
  carry export margins (food price read live at known markets); non-food
  routing keeps the activity proxy; the famine definition (any shortfall).

## Needs oracle: autonomy without prior rebels (2026-10-24, `fix/needs-oracle-confound`)

`fix/needs-oracle-confound` from `integrate/wave-6` (`439f0c5`), merged
with `main` (PR #19's guard fix) without rebase. Oracle and test-runner
changes only; the simulation and Rust are unchanged. Details:
`docs/integration/needs-oracle-autonomy.md`.

- **Confound:** a rebellion adds 0.10 to the rebel's autonomy
  (`tick.rs` apply step), so high autonomy marks past rebels, who rebel
  again. One rebellion still reads +0.035 after 20-29 turns, a burst
  +0.07 to +0.11 after 20-34; without restoration it does not decay.
- **Fix:** the autonomy -> rebellion pairing leaves out agents with a
  rebellion on or before the snapshot turn. Other pairings, the window
  and the thresholds are unchanged; `exclude_prior_rebels=False`
  reproduces the old result.
- **Subset gates (before / after, same batches):** needs seeds 17/15,
  11/9, 18/15, 18/15 on 42-61, 62-81, 82-101, 102-121; gates PASS except
  62-81 (FAIL before and after); comparator NO REGRESSION on all four;
  every other oracle identical. Pooled autonomy low/high over the 80
  worlds: 1.00 (0.91-1.09) before, 1.29 (0.82-2.15) after.
- **Finding:** among agents without prior rebellions, 2 of 629 autonomy
  pairs have the low agent under 0.25, the only range where autonomy adds
  rebel pressure. The pairing rarely tests the mechanism.
- **500-turn probe (142-161, not the full gate):** needs 20/20 before
  and after, median d 1.03 -> 2.00; pooled autonomy 1.02 -> 1.04.
- **Offline lane:** four chunks, each its own guarded pytest process with
  the 110-second limit; stops at the first failing chunk. Same selection
  and totals (1,895 passed, 10 skipped, 2 deselected); 75.8 s wall, the
  largest chunk 21.8 s; every guard PASS.
- **Tests (Linux, Python 3.13):** `pytest -m "not slow" -n 2` 5,890
  passed, 3 skipped (three new); `-m slow` 11 passed, 3 skipped; no-Rust
  5,690 passed, 203 skipped. Rust unchanged.
- **Open:** the per-seed needs test has little power for autonomy (a
  calibration for the needs owners); 62-81 still fails subset needs; the
  200 x 500 full gate has not been run with this oracle.

---

## Left-over persecution (2026-10-24, `fix/leftover-persecution`)

`fix/leftover-persecution` from `integrate/wave-6` (`439f0c5`). Two
corrections, each its own commit, plus one test whose world depends on the
second. Python and Rust change. Details:
`docs/integration/persecution-fix-2026-10.md`.

- **Root causes:**
  - `2860af0`: `compute_persecution` wrote intensity only for militant-held
    regions and never reset the others. Half of all persecuted region-turns
    (159 per run) and 41% of hybrid agent rebellions were under left-over
    intensity: a faith had left militancy, or a region had changed hands or
    lost its ruler. The builder now clears every region and writes the
    militant-held ones.
  - Reset, not decay: M38b sets the intensity per turn from the current
    minority. The aftermath is `martyrdom_boost` (10 turns) and the agents'
    persecution memories (25-turn half-life).
  - `44526a1`: the builder counts minorities against the ruler's faith, but
    the Rust tick persecuted everyone outside the region's majority. In 57%
    of live persecuted region-turns the ruler's faith is a local minority.
    Per run, that persecuted 658 agent-turns of the ruler's own faith and
    spared 1,257 of the other-faith majority.
  - The fix records `Region.persecuting_faith` (omitted while None) and
    sends a `persecuting_faith` region column. One Rust predicate covers the
    satisfaction penalty, the rebel/migrate boosts and the memories, and
    martyrdom uses the same rule. Batches without the column fall back to
    the majority.
  - `569040d`: the maritime raid test moves from seed 7 to seed 12. Seed 7's
    sea trade vanishes in the corrected history.
- **Result** (hybrid, 60 worlds, 200 turns, agendas off, per run; base /
  reset / branch):
  - Rebellions 1,355 / 1,078 / 1,168 (branch −187 ± 84 against the base).
  - Share in persecuted regions 82% / 54% / 55%.
  - Persecuted region-turns, live + left-over: 159 + 159 / 157 + 0.05 /
    157 + 0.03.
  - Migrations 1,825 / 1,821 / 1,898; conversions 660 / 576 / 616.
  - Schisms 12 / 12 / 12 (the faith registry fills by turn 9 everywhere).
  - Polities alive 2.97 / 2.97 / 2.92.
- **Agendas** on − off: base +176 ± 68 (20/14), reset −24 ± 80 (17/17),
  branch −15 ± 86 (13/21). The worst branch seed is 73 (688 -> 2,640).
  Agendas are rebellion-neutral; chance tails remain.
- **Gates (subset, branch vs base):**
  - 42-61 PASS, NO REGRESSION; regression strict PASS.
  - 62-81 PASS, NO REGRESSION; resolves needs (12; the base has 11).
  - Migration per agent-turn 0.0580 / 0.0474 (base 0.0577 / 0.0474).
  - Rebellion per agent-turn 0.0352 / 0.0186 (base 0.0428 / 0.0222; the
    62-81 value is under the 0.02 floor, informational in the subset).
  - 0 extinct.
- **Identity:** agents-off base vs branch (each with its own native build),
  seeds 42/7 x 150 turns, 16 files, 0 differences. Golden fixtures are
  off-mode captures and do not change. 60 base hybrid states load.
- **Tests** (pre-merge; `569040d` for the first two, `44526a1` for the rest):
  - `cargo test` 897 passed, 2 ignored.
  - `pytest -m "not slow" -n 2`: 5,902 passed, 3 skipped. On `44526a1` the
    maritime test above failed; `569040d` fixes it.
  - `-m slow`: 11 passed, 3 skipped.
  - No-Rust lane: 5,701 passed, 204 skipped.
  - Oracle lane (PR #19's guard fix local only): 1,892 passed, 10 skipped,
    2 deselected, guard PASS, pytest 72.6 s of 110 s.
- **500-turn probe** (not the full gate; 20 seeds 142-161 x 500, subset
  profile):
  - Migration per agent-turn: base 0.0501, reset 0.0474, branch 0.0468, on
    the calibrated floor.
  - Rebellion per agent-turn: 0.0577 / 0.0293 / 0.0315.
  - Left-over intensity covered 933 of 1,152 persecuted region-turns per run
    and 44% of migrations.
- **Migration budget** (same probe, from turn 100; base / branch):
  - Famine memory 47% / 55%; live persecution 14% / 5%; persecution
    memory 18% / 15%.
  - All opportunity (pull) terms together about 3%; needs about 1%.
  - Healthy worlds have almost no migration driver, so the floor was held
    up by pathologies.
- **Open:**
  - The coordinator decided that healthy-world migration drivers come next,
    on top of this branch. One full gate (with the `integrate/wave-6`
    merge and any fixture roll-forward) covers both. Not run here; this
    branch is not merged with wave-6.
  - Schism saturation.

## Great-person agendas: the rebellion tail (2026-10-24, `fix/agenda-preaching`, default off)

`fix/agenda-preaching` from `integrate/wave-5` (`b1b3f2d`), merged with
`b7d9ced` (techniques on by default; the identity and gate base) and then
with `integrate/wave-6` (`59e6898`, historiography). Both merges are without
rebase. Only `src/chronicler/gp_agendas.py` changes; no Rust. Details:
`docs/integration/great-person-agendas.md`, section "The rebellion tail".

- **Mechanism:**
  - 82% of hybrid agent rebellions with the switch off happen in persecuted
    regions.
  - `compute_persecution` writes intensity only for militant rulers and
    never resets other regions, so intensity is left over after a civ's
    majority faith leaves a militant faith. That covers 41% of rebellions.
  - The agent tick applies the intensity to anyone outside the region's
    majority belief.
  - Preaching fed this in three ways. It led converts into persecuted
    regions (28-37 rebels of the preached faith per episode there, 12-14
    elsewhere). Two thirds of it went into realms of another faith, which
    tipped those realms in and out of militancy (seed 70: 53 militancy
    changes, 0 with the switch off). And it took over a conversion slot's
    leftover rate (+33% pressure).
  - Seed 60's tail is a general's turn-3 conquest followed by 170 turns of
    left-over intensity. No preaching is involved.
- **Fix:**
  - Prophets preach only where the ruler holds their faith and the
    persecution intensity is 0. This applies to the vow's targets and is
    rechecked at every deed.
  - An empty conversion slot gets exactly the prophet's 0.02.
  - Scientists vow only inventions their civ has a site for, which is the
    `_invent` site rule. With techniques on, 37% of invention vows are now
    fulfilled (17% before; 4.4 per run).
- **Result (60 worlds, 42-101):**
  - Rebellions per run: off 1,355; on before 1,508 (+153 ± 67, up/down
    23/11); on fixed 1,531 (+176 ± 68, up/down 20/14).
  - The diagnostic resets left-over intensity (outside this branch, since it
    changes default outputs). Under it, fixed agendas move rebellions
    −24 ± 80 (up/down 17/17). Before the fix, more worlds still rose than
    fell (+88 ± 95, 22/12; `b1b3f2d`: +224 ± 119, 23/11).
  - With the agendas' own path removed, the excess is entirely left-over
    intensity, which any change of history triggers.
  - Removing any single lever (campaigns, weights, shrines, faction shifts,
    coups, crown credit) leaves +90 to +228. No lever carries a tail on its
    own.
- **Identity:** the switch off is byte-identical to `b7d9ced`. Direct runs
  give 30 files with 0 differences (default and `--no-gp-agendas`). The
  42-61 subset batch has 2,164 files; the reports differ only in the batch
  path.
- **Gates (subset, switch on vs `b7d9ced`):**
  - 42-61 PASS, 62-81 PASS (the base FAILs needs at 11), 82-101 PASS.
  - Comparator NO REGRESSION on all three; 0 extinct.
  - `civ_survival` FAIL on 62-81 (9 of 20 worlds keep all four civs; base
    4): informational here, a risk for the full gate.
- **Tests:**
  - `pytest -m "not slow" -n 2`: 5,848 passed, 3 skipped (four new tests;
    `b7d9ced` collects 5,847 of the branch's 5,851). After the wave-6
    merge: 5,887 passed, 3 skipped.
  - Offline oracle lane (PR #19 guard fix applied locally only): 1,854
    passed, 9 skipped, 2 deselected. After the merge: 1,892 / 10 / 2, guard
    PASS, pytest 68.7 s of its 110 s limit. The four new tests take about
    0.3 s.
  - No-Rust environment: 5,649 passed, 202 skipped. The only agenda skip is
    the hybrid determinism test.
- **Open:**
  - Fix left-over persecution intensity in `religion.py`, as its own change
    with a full gate (it cuts off-mode hybrid rebellions by 20%). Without it,
    agendas raise rebellions by about 11-13% through chance tails.
  - `civ_survival` with agendas on.
  - The 200 x 500 full gate has not been run; the default stays off.

## In-world historiography (2026-10-24, `feat/historiography`)

`feat/historiography` from `integrate/wave-5` (`b1b3f2d`), merged forward to
`b7d9ced` (no rebase). It adds an observational layer: court chroniclers
per civ and temple scribes per faith with a standing temple. They record
each completed turn's events with biases read from simulation state (ruler
legitimacy and power struggles, clergy influence and faith, grievances,
victory or defeat). The biases are omissions, inflated or minimized
casualties, claimed stalemates, blame shifted to an enemy's real deed from
the provenance graph, praise or condemnation of rulers, and divine favour,
trials and wrath. Accounts go into archives that sacks, conquest, collapse,
absorption, fire, earthquakes, floods, plague and desecration destroy;
literacy techniques add copies. Chroniclers cite only what survives.
Contested accounts are exported for the narrator (prompt block, mechanical
"In their own words" passage, curator bonus), for `--narrate` and for the
viewer's event inspector. `--historiography` is **on for new worlds**
(`--no-historiography` opts out). State lives in a
`state.historiography.json` sidecar, so `state.json` keeps its bytes. No
Rust change. Evidence: `docs/integration/historiography.md`.

- **Identity** (`scripts/historiography_identity.py`, base `b7d9ced` exported):
  - Template seeds 42/7/1234 (off 300, hybrid 200) and procedural 48x10
    seed 7, flag off: 72 files, 0 differences.
  - Flag on: the same 72 files identical apart from narration (4+4
    `chronicle.md`, bundles identical apart from `historiography`,
    `chronicle_entries`, `gap_summaries`), plus 8 sidecars.
  - Subset gates (20 x 200 hybrid) base / off / on: all PASS, 2,164 files
    identical, validation reports and gate decisions identical (batch path
    normalized).
  - The frozen exact-trajectory oracles hold with the layer on: turn hashes,
    RNG trace, artifacts minus the field and sidecar.
- **Default on, justified as narration-only:** simulation, gates and saved
  state are byte-identical. Cost about 4% run time on the 500-turn guard
  world (three alternating runs each), +2.6% bundle on the subset, 243 KB
  sidecar per 200-turn run. The frozen benchmark workloads pin it off.
- **Tests:**
  - `pytest -m "not slow" -n 2`: 5,883 passed, 3 skipped (base 5,844; +39).
  - No-Rust lane: 5,683 passed, 203 skipped (slow included).
  - Oracle lane (PR #19's guard fix local, now including
    `tests/test_historiography.py`): 1,888 passed, 10 skipped, 2 deselected, guard PASS.
  - Viewer: 219 tests, lint, build.
  - Bundle guard unchanged at 24 MB: 20.73 MB native, 23.61 MB no-Rust (field 0.65 / 0.77 MB).
- **Open:**
  - Bias and survival calibrations are illustrative.
  - Temple desecration dominates archive losses (68 accounts per subset
    run).
  - The curator bonus matters only when clusters exceed the narration
    budget.
  - No inter-archive copying or captured archives.
  - Live-mode resume (from a client-sent state dict) starts without
    chronicles.
  - The full 200-seed gate was not run (the simulation is unchanged).

## Dead civs leave the history snapshots, bundle version 5 (2026-10-24, `perf/prune-dead-civ-snapshots`)

`perf/prune-dead-civ-snapshots` from `integrate/wave-5` (`7fbe8c0`). This is a
bundle format change, not a simulation change. A snapshot now records a civ
only if it holds a region, an exile modifier can restore it, or it was live in
the previous snapshot (its final row). The first snapshot records every civ.
Other civs' `civ_stats` rows, `capitals` entries and pairs (`relationships`,
`per_pair_accuracy`, `perception_errors`) are left out of the bundle and of the
live turn stream. `world_state` and the in-memory history are untouched.
Dead civs' treasuries keep growing (`phase_production` pays every record). The
new top-level `pruned_civ_stats` stores those drifts as runs, and
`snapshot_pruning.restore_bundle` rebuilds the version-4 `civ_stats` exactly.
Validation, analytics, re-narration and the report scripts restore; the viewer
reads gaps through `viewer/src/lib/civRows.ts`. Details:
`docs/performance/dead-civ-pruning.md`.

- **Sizes:**
  - size-guard world: 37.45 MiB -> 20.29 MiB; the guard is now < 21 MB;
  - 500-turn hybrid, seed 42: 12.51 -> 10.96 MiB;
  - procedural 48x10, seed 7, 500 turns hybrid: 44.79 -> 43.41 MiB (11
    polities; its pairs were already living-only);
  - subset batch: -6.2%.
- **Identity:**
  - Subset gate (42-61, hybrid): the branch report is identical to the base
    apart from the batch path, comparator NO REGRESSION. So is the base batch
    converted to version 5 and re-validated.
  - 2,141 non-bundle files are byte-identical, including every `state.json`.
    Every bundle equals the conversion of its base bundle, apart from
    `generated_at`.
  - Without the restore, the era and arc metrics change (dead civs' series),
    so the oracles must restore.
  - The size-guard world's `state.json` and chronicle are identical to the
    base.
- **Fixtures:** `corrected_artifacts_dead_civ_pruning_2026_10.json` rolls the
  artifact oracle forward (only `chronicle_bundle.json`, +22 bytes in each of
  the three workloads; none prunes a civ). The pre-pruning projection still
  matches the frozen food-balance artifacts. The viewer systems fixture was
  regenerated from the same run.
- **Tests:**
  - `pytest -m "not slow" -n 2`: 5,791 passed, 3 skipped (base 5,759).
  - Viewer: 210 tests (base 199), lint and build pass.
  - Headless Chromium on the version-5 size-guard bundle: the inspector keeps
    a dead civ's final row past its death, chart lines end at the last row, no
    console errors.
  - `-m slow`: 11 passed, 3 skipped.
  - No-Rust environment: 5,593 passed, 201 skipped (base 5,561 / 201).
  - Offline oracle lane (PR #19 guard fix applied locally only): 1,803
    passed, 8 skipped, 2 deselected, guard PASS.
- **Open:**
  - The 200 x 500 gate was not run.
  - In-memory snapshots still compute dead civs' pair tables (CPU only).
  - Dead civs' income drift inflates era-oracle inflection counts (left as
    is).

## Great-person agendas (2026-10-24, `feat/great-person-agendas`, default off)

`feat/great-person-agendas` from `integrate/wave-4` (`1a6cacb`), merged with
`705fe2e` (no rebase), which is the identity and gate base. Great persons
declare agendas settled by the M66b ruler-ambition kernel (ten kinds
appended to `AmbitionType`; `src/chronicler/gp_agendas.py`,
`gp_agendas_state.py`). Generals campaign for a region (WAR bias, renown,
agitation in peacetime) or seize the throne from a weak ruler through the
existing `general` succession path, citing the grievance or ambition;
merchants open or protect a trade route, found a trading house or, with
finance, lend to the crown; prophets spread the faith (preaching adds to
the conversion signal) or found a pilgrimage shrine; scientists vow the
next era or, with techniques, steer an invention. Loyalty, conspiracy,
partnership, opposition and feud bonds change coup odds, faction influence
and who backs whom in a succession crisis. Biases ride the capped
governance bucket. Switch `--gp-agendas` (world field, gate forwarding,
dormant field omitted). Details: `docs/integration/great-person-agendas.md`.

- **Identity:** switch off (default and `--no-gp-agendas`) is
  byte-identical to `705fe2e`: 30 files over seeds 42 and 7, agents off
  and hybrid, and the 2,164-file subset gate batch (reports differ only in
  the batch path). No Rust changes.
- **Tests:** `pytest -m "not slow" -n 2` 5,759 passed, 3 skipped (base
  5,707); offline oracle lane (PR #19 guard fix applied locally only)
  1,771 passed, 8 skipped, 2 deselected, guard PASS; no-Rust environment
  5,561 passed, 201 skipped (base 5,510 / 200).
- **Subset gate, switch on** (seeds 42-61 and 62-81, hybrid, new defaults):
  PASS, comparator NO REGRESSION, 0 extinct; artifacts PARTIAL on 62-81
  (loss rate below band, informational). The base's `civ_survival`
  regression FAIL (5 of 20 seeds keep all four civs) is PASS on the branch
  (4 of 20).
- **Effects (hybrid 42-61, per run, off / on):** conversions 734 / 959,
  artifacts 16.1 / 20.7, wars 2.95 / 2.95, all coups 7.05 / 7.25, state
  defaults 1.30 / 0.80. Agent rebellions 1,504 / 1,871, carried by a few
  worlds (median seed ratio 0.91); preaching is the largest single lever.
- **Cut:** artists (no such role), persecution and toleration (no reset
  owner for the persecution signal), Rust, viewer panels, ruler legitimacy
  from agenda outcomes.
- **Open:** the full 200 x 500 gate (required before any default flip);
  the agent-rebellion tail; scientists rarely succeed inside their window.
## Pastoral and nomadic peoples (2026-10-24, `feat/nomads`, default off)

Branch `feat/nomads` from `integrate/wave-4` (`c5f4df4`, PR #21), default
off behind `--nomads` (`WorldState.nomads`). No Rust change. See
[`docs/integration/nomads.md`](../../integration/nomads.md).

- **Built.** Subsistence modes per civ (sedentary, agro-pastoral, nomadic)
  seeded from the pastoral suitability of a civ's land (steppe, desert and
  tundra favour herding), and for later polities at their first tick; herds
  per region with logistic growth on pasture, drought die-off, dzud winters
  and transhumance between seasonal pastures; herd food through one hook
  (`ecology.compute_resource_yields` -> `nomads.food_yields`, identity while
  off); raids on settled neighbours fought with the campaign layer's power
  terms (plunder, deaths, stability, colder dispositions, a border grievance
  with diplomacy on); tribute pacts that spare the payer, lapse or are
  repudiated; hordes kept as federations (a khan unites weaker pastoral
  neighbours or takes command of his federation), riding to war through the
  campaign WAR path with conquest aims and breaking apart when the founding
  khan dies; sedentarization after a generation on farmland, with asabiya
  won on the steppe and lost on farmland; EXPAND into desert and tundra for
  herders; loose hold of empty pasture. Every nomad event cites its causes;
  wars between a raided pair cite the raid, secession and collapse a broken
  horde.
- **Cut.** Pastoral goods in the goods economy (no clean slot among the
  eight fixed goods), mounted mobility for campaign armies, nomad-on-nomad
  raiding, re-nomadization of settled peoples, off-mode herd food with the
  native ecology runtime (one food hook), viewer panels.
- **Evidence.** Switch off is byte-identical to `c5f4df4`: 99 files
  (template seeds 42/7/1234 off 300 / hybrid 200, procedural 48x10 seeds 7
  and 13 off 200 / hybrid 120), 0 differences with the default and with
  `--no-nomads` on the final head; the switch-off subset batch matches the
  base batch file for file (2,160 run files and the normalized reports);
  with the switch on, the 8 gate seeds that never have a herder are
  outcome-identical to the base. Native `pytest -m "not slow" -n 2` 5,758
  passed, 3 skipped (base 5,707 / 3); no-Rust lane 5,560 passed, 201
  skipped; bounded Python oracle lane (PR #19's guard fix applied locally
  only) 1,768 passed, 8 skipped, guard PASS. Subset gate with `--nomads`
  against `c5f4df4`: PASS, NO REGRESSION, 0 extinct worlds; artifacts PASS
  -> PARTIAL (loss rate 1.5% against a 2% floor, one diverged seed);
  regression keeps the base's own civ_survival FAIL. No Rust change, so no
  `cargo test`.
- **Numbers.** Procedural 48x10 worlds with steppe (3 seeds x off/hybrid,
  300 turns): per run 1.8 nomadic and 3.2 pastoral polities at once, 26
  raids through and 4 driven off, 5 tributes, 2.7 hordes (16 over the six
  runs, 11 broken by the khan's death), 4 regions taken by herders, 1.2
  sedentarizations, 10 dzuds; polities alive 15.2 on against 13.0 off; no
  world extinct.
- **Not run / open.** The full 200-seed gate with `--nomads`. In a
  supplementary seed set (62-81) the needs oracle fails with the switch on
  (11 seeds against 12 required; base at exactly 12); in another (82-101)
  arcs move PASS -> FAIL on the dominance ceiling (41.2% against 40%). Both
  are recorded in the integration doc. They concern runs with the switch on
  only (switch-off output is byte-identical), and both block any default
  change until the full gate is run.
## Techniques on by default (2026-10-24, `feat/techniques-default`)

`feat/techniques-default` from `integrate/wave-4` (`c5f4df4`) re-gates
techniques on the Wave 3 defaults (epidemiology, finance and diplomacy on)
and turns them on for new worlds (`594aedb`); `--no-techniques` opts out and
saved worlds keep their setting. No oracle, threshold or technique parameter
changes. Evidence: `docs/integration/techniques-default.md`.

- **Subset gates** (seeds 42-61, 62-81, 82-101, 102-121, with and without
  `--techniques`): every set passes with no comparator regression except
  62-81, where the required needs oracle reads 11 of 20 with techniques (12
  required) and 12 without. Over the 80 seeds both arms qualify 64; 7 seeds
  are lost and 7 gained (McNemar p = 1). Pooled over every snapshot,
  techniques do not weaken the autonomy-rebellion or material-migration
  links. Seeds 62-81 have half the other sets' agent rebellion rate in both
  arms. 0 of 160 worlds extinct.
- **Needs-oracle finding (open, not changed):** a rebellion raises the
  rebel's autonomy by 0.10 (since `aff1b18`), so in 41% of autonomy pairs
  only the high-autonomy agent had just rebelled; the pooled autonomy link
  reads 0.88 (backwards) on the 200-turn defaults and the oracle passes by
  best-of selection over snapshots and pairings.
- **Full gate** (200 x 500, hybrid, `--techniques` on the defaults): PASS
  strict, 0 extinct worlds, `validation_compare` NO REGRESSION against the
  all-on full report, which a `--no-techniques` full gate at `594aedb`
  reproduces exactly. Needs 188 of 200 (191 off), migration 0.0512 against
  the 0.05 floor (0.0524 off), all founders surviving 0.110 (0.155 off).
- **Eras of living civs, Bronze or later** (full gate, off / on): 8% / 78%
  at turn 100, 11% / 82% at 200, 11% / 84% at 500 (Medieval 2 / 19 civs).
  Tech advances 5.4 / 7.1 per run, regressions 4.9 / 1.5.
- **Tests:** `pytest -m "not slow" -n 2` 5,707 passed, 3 skipped; no-Rust
  5,510 passed, 200 skipped after the 500-turn bundle-size limit moved from
  35 to 40 MiB (`ae832c6`: 33.70 off, 36.56 on on the Python oracle path;
  `integrate/wave-4`'s `1078367` raised it the same way for the Wave 3
  defaults and is merged); offline oracle lane (PR
  #19's guard fix applied locally only) 1,721 passed, 7 skipped, guard PASS.
  The frozen benchmark workloads pin techniques off; golden fixtures
  unchanged (without the pin 3 golden tests move).
- **Open:** migration is the tightest margin; the needs oracle's autonomy
  pairing needs its own calibration; trade actions rise about eightfold and
  expansions fall by three fifths with moving eras; one living civ in six is
  still tribal at turn 500.

## Living-world oracles and the Wave 3 defaults (2026-10-24, `feat/wave3-defaults`, merged into `integrate/wave-4`)

Two oracles tuned on worlds that died are recalibrated, one commit each, with
no base result moving from PASS to FAIL:

- **Era (`303e0fa`):** a silent collapse is now a fall of 30% or more in a
  civ's smoothed population with neither its own inflection nor a recorded
  crisis naming it nearby. It used to be one collapse per civ, covered by any
  civ's inflection anywhere in a window that can span a century.
- **Late-run satisfaction (`a595a38`):** read over the last 60 turns, not the
  final sample, which always lands in autumn of a drought.

The founder-survival band and every other threshold were checked and left
alone. The full profile (200 x 500) passes strict with 0 extinct worlds and no
comparator regression both with all three systems off and with
`--epidemiology --finance --diplomacy`. All three now default on for new
worlds, one commit each. The frozen benchmark workloads pin them off.
Migration (0.0524 against the 0.05 floor all on) is the margin to watch.
Evidence: `docs/integration/wave3-defaults.md`.

## Viewer panels for the default-off systems (2026-10-24, `feat/viewer-systems`)

`feat/viewer-systems` from `integrate/wave-4` (`1a6cacb`). The production
viewer (`AppShell`) shows epidemics, finance, diplomacy, techniques and the
maritime layer when a bundle records them: a tabbed "Simulation systems"
panel below the map workspace (tabs only for recorded systems), event lists
that pin an event in the existing provenance inspector, per-region epidemic
and technique state in the region inspector, and live-mode pass-through.
Details: `docs/integration/viewer-systems.md`.

- **Python:** two additive, flag-on-only snapshot fields,
  `diplomacy.pairs` (trust and grievance of every living pair) and
  `techniques.regions` (practice per region); bundle version stays 4.
  Flags off is byte-identical to `1a6cacb` (4 runs, 37 files); with all five
  systems on, outputs are identical apart from the two fields (2 runs, 22
  files; `scripts/viewer_systems_identity.py`). `pytest -m "not slow" -n 2`
  5,699 passed, 3 skipped.
- **Viewer:** 197 tests (base 166), lint clean, build passes. A systems-off
  bundle renders pixel-identically to the base build (9 of 9 headless
  captures); every panel was captured from real all-on bundles with no
  console errors.
- **Cut:** map layers (the map has no sea geometry), a contact-ledger panel,
  a per-lender loan book, phone layout. **Open:** hashed faction colours can
  collide; the shell map's 0-1 coordinate assumption (pre-existing) puts
  generated worlds' region nodes off the canvas.

## Techniques (2026-10-24, `feat/techniques`, default off)

`feat/techniques`, from `integrate/wave-3` (`20eeead`, merged with
`92b6122` for the food-balance corrections), replaces the monolithic tech
era with 30 techniques that civs invent and that spread between regions
along the contact ledger (`chronicler/techniques.py`,
`chronicler/techniques_state.py`, `WorldState.techniques`, CLI
`--techniques`, saved on the world). Per-region practice grows, diffuses
by merchants, migrants, soldiers and pilgrims, and decays when the
connected people who share a craft fall short of its tier's need; a civ's
era is derived from its practised technique mix (quorum, hysteresis, a
three-tick grace, the capital keeping an era), so the M18 random
regression is off with the switch and dark ages come from plague, famine,
collapse and isolation. Effects go through battle strength, build costs,
trade range, one crop/fish yield hook, epidemic fatality and quarantine,
and credit capacity. Inventions, adoptions ("X learned Y from Z's
merchants"), losses, advances and regressions cite their causes. Details:
`docs/integration/techniques.md`.

- **Switch off is byte-identical** to `92b6122` (and to `20eeead` before
  the merge): direct runs 30 files, 0 differences, default and
  `--no-techniques`; the whole subset gate batch (2,164 files) matches
  apart from the reports' batch path; the frozen performance oracles are
  unchanged.
- **Tests:** `pytest -m "not slow" -n 2` 5,649 passed, 3 skipped (base
  `92b6122` 5,610; +39); no-Rust lane 5,454 passed, 198 skipped; bounded
  Python oracle lane (PR #19's guard fix applied locally only) 1,669
  passed, 5 skipped, 2 deselected, guard PASS.
- **Subset gate with `--techniques`** against `92b6122`: seeds 42-61 and
  82-101 PASS with NO REGRESSION; seeds 62-81 **FAIL** on the required
  needs oracle (11 of 20 seeds, 12 required; base 14), comparator
  REGRESSION. Over all 60 seeds base and techniques-on both count 46
  qualifying needs seeds. Era oracle 20 of 20 inflection seeds in every
  set, 1 silent collapse in two sets (base 0; limit 2). 0 of 60 worlds
  extinct.
- **Not run:** the 200-seed x 500-turn full gate. Default stays off.
- **Open:** scientists double with moving eras (treatise artifacts rise,
  inside the band on this base, above it on one pre-merge set); TRADE
  actions rise about sevenfold once civs reach Bronze; Rust technique
  packets and viewer panels are cut.

## Epidemiology (2026-10-24, `feat/epidemiology`, default off)

`feat/epidemiology`, based on `integrate/wave-2` at `db26681`, replaces the
hazard-rolled plague and the M18 black-swan pandemic with one regional SEIRS
model (`chronicler/epidemiology.py`, `WorldState.epidemics`, CLI
`--epidemiology`, saved on the world). Five pathogens (plague, pox, marsh
fever, bloody flux, the black-swan great pestilence) spread along the contact
ledger's region flows from reservoir homelands; never-exposed populations
suffer virgin-soil epidemics; deaths use the plague death path and reach the
hybrid agent pool through the catastrophe transient; famine and crowding raise
susceptibility; states quarantine; labour scarcity eases the governance MMP.
Epidemics are chronic provenance episodes whose onsets cite the contact
arrival. Details and evidence: `docs/integration/epidemiology.md`.

- **Switch off is byte-identical to `db26681`:** 8 direct runs (off and
  hybrid, seeds 42/7) and the full 20-seed subset gate batch (2,161 files)
  match; the frozen performance oracles are unchanged.
- **Tests:** `pytest -m "not slow" -n 2` base 5,497 passed / 3 skipped,
  branch 5,522 / 3 (25 new); slow 4 passed. The guarded offline lane fails
  28 `test_checkpoint_replay` cases identically on base and branch on Linux
  (`platform.processor()` subprocess blocked by the guard).
- **Subset gate with `--epidemiology`:** PASS, `validation_compare` NO
  REGRESSION; 0 extinct; all-initial-civ survival 0.25 as on base (the
  informational regression FAIL is the known 0.20 calibration). Disease
  deaths 159 per run against the base's 72 applied (plus 21 nominal M18
  deaths that never reached agents in hybrid); final population 352 against
  393. A 40-seed x 500-turn harness run loses no world and converges (431
  against 435).
- **Default stays off** until the food-balance work lands (famine feeds
  susceptibility and fatality) and the 200-seed x 500-turn full gate passes
  with the switch on; the full gate was not run.
- **Finding:** the M18 pandemic's population loss was never staged for the
  agent pool, so in hybrid runs it was erased by the write-back. Unchanged
  with the switch off.

## Money, credit and public finance (2026-10-24)

Branch `feat/money-credit` on `integrate/wave-2` (`db26681`, PR #18), default
off behind `--finance` (saved on the world). Details, numbers and stories:
[`docs/integration/money-credit.md`](../../integration/money-credit.md).

- **Built.** `chronicler/finance.py`: a Phase 3b fiscal tick (revenue partly
  indexed to prices, army and administration upkeep at current prices, a court
  that absorbs idle surpluses above a reserve target, debt service on credit
  lines, borrowing from the merchant creditor class and from wealthy foreign
  civs in contact, debasement, arrears and default with stability, legitimacy,
  merchant-influence, grievance, exclusion and premium consequences) and an
  end-of-turn monetary update (regional specie, precious-metal minting, sacks
  of occupied regions, price-specie flow, a sticky per-civ price index).
  Fiscal stress replaces the governing-cost/treasury proxy as the PSI
  `state_debt` input; a finance contributor bucket (clamped to 1.25x) carries
  creditor leverage and grievance into action weights; loans, defaults,
  debasements and lapsed debts cite their causes, and fiscal strain and
  inflation are chronic episodes. `transfer`/`extend_loan` are the API for
  diplomacy. Rust is unchanged.
- **Evidence (Linux, Python 3.13, fresh native build).** Flag-off outputs are
  byte-identical to `db26681` (hybrid 200 and off 300 turns, seeds 42/7/1234,
  45 files, default and explicit `--no-finance`). Not-slow suite 5,520 passed,
  3 skipped; guarded oracle lane 1,596 passed (PR #19's guard line applied
  locally only); subset gates with `--finance` PASS / NO REGRESSION on seeds
  42-61 (vs base) and 62-81 (vs flag off), 0 extinct worlds. Treasury at turn
  200 falls from about 9.1K to 1.0K per civ (30K to 1.2K at turn 500).
- **Open before a default flip.** The era oracle (required only in the full
  profile) reads 5 of 20 seeds as "silent collapse" in seeds 62-81 with finance
  on: base treasuries supply about three quarters of all inflections and cover
  slow population declines; finance makes treasuries homeostatic. Decide the
  oracle treatment, then re-gate after the food-balance work lands. The
  200-seed full gate has not been run with finance on.
## Food balance (2026-10-24)

Branch `fix/food-balance` on `integrate/wave-2` (`db26681`); details, numbers
and every changed expectation are in
[`docs/integration/food-balance-2026-10.md`](../../integration/food-balance-2026-10.md).
Nine root-cause corrections, one commit each: aggregate migration no longer
runs on agent-owned populations; soil degrades against potential capacity;
temperate water recovery is climatic; mines need ORE/PRECIOUS; travelling
merchants count in their origin's occupational balance and return home after
delivering; the fertility brake tapers from 0.75x to 1.0x capacity; the goods
economy reads goods per farmer instead of the raw M34 harvest index (PR #11
unit regression); outbreak contagion is spread over a civ's contacts. One
separate recalibration restores the food-shortage satisfaction weight to
0.15, undoing cuts made to meet the satisfaction floor on starving worlds.
Golden oracles rolled forward to `corrected_food_balance_2026_10*`
(extinction fixtures frozen). No famine, demand or validation threshold
changed.

- Hybrid template worlds: fed region-turns 4% → 42%, famine per 500-turn run
  752 → 341, mutual-aid convoys 0 → 12 per 200 turns, population held at
  0.66x capacity (was 1.0-1.35x on degrading land).
- Procedural 64-region / 16-civ hybrid worlds no longer collapse (seeds 7-10:
  822 → 64 by turn 150 before; 817 → 893 after, 988 at turn 300).
- Gates on the branch head: full 200 × 500 PASS (strict; 0 of 200 extinct,
  latest satisfaction 0.643 against the 0.65 ceiling), subset PASS (the
  `db26681` subset fails `civ_survival`). pytest, no-Rust pytest, slow tests
  and `cargo test --release` pass.
- Open: winter shortage and merchant routing that ignores need, locust
  frequency (M35b rate), drought/cooling compounding of crop and water
  modifiers, the occupational switching dead band (farmers below target),
  no goods-economy subsistence for foodless regions, fishing effort that
  ignores catch per fisher, the secession threshold left pending this sweep,
  the other floor-chasing satisfaction tunings (M47c-M57), and the
  `civ_survival` band (0.15-0.165 on the branch; 0.25 against 0.20 in the
  base subset), and smaller worlds (full-profile final population median 182,
  minimum 33; none extinct). The plague change touches `events.py`, which the
  epidemiology work also owns.

## Diplomacy (2026-10-24, `feat/diplomacy`)

Branch `feat/diplomacy` from `integrate/wave-2` at `db26681`, default off
behind `--diplomacy` (`WorldState.diplomacy`). See
[`docs/integration/diplomacy.md`](../../integration/diplomacy.md).

- **Built.** Directed pair memory on `Relationship.memory` (trust, goodwill,
  six grievance stocks with half-lives) that caps dispositions and enters
  every utility; `peace`, `non_aggression`, `alliance`, `trade_pact` and
  installment `tribute` treaties with terms, expiry, renewal by fresh mutual
  acceptance, breach and consequences, accepted only by the target's
  utility; peace treaties emitted by `conclude_peace` and `close_external`;
  a pre-clamped diplomacy bucket in the action weights, a WAR treaty guard
  and revanche, calls to arms and alliance aid convoys; the
  `client -> vassal -> union -> annexation` ladder on `VassalRelation`,
  replacing the tributary step in `prepare_twilight_absorption` (absorber
  stability above 20 instead of 40), with loosening when the overlord
  weakens and the existing Rust rebellion still ending any stage. The
  absorption body is shared as `politics.absorb_civ`. No Rust change.
- **Cut.** Marriage alliances (no cross-civ ruler marriage exists), grievance
  export from agent memory (Rust memories record the victim's own civ, not
  the perpetrator), embargo lifting (it pushed artifacts and arcs to FAIL on
  the subset), ruler-ambition predicates and viewer panels. Sparing the last
  region of a conquered state is built as `SPARE_LAST_REGION` but off: it
  doubles wars and keeps all founders in half the worlds.
- **Evidence (final head).** Switch off is byte-identical to `db26681`:
  direct runs (off 150 and hybrid 120 turns, seeds 42 and 7, default and
  `--no-diplomacy`) 30 files, 0 differences; the switch-off subset gate
  batch (one commit earlier, the last change being switch-on only) all 2,159
  run files identical. Native `pytest -m "not slow" -n 2` 5,536 passed,
  3 skipped; no-Rust lane 5,344 passed, 193 skipped; bounded Python oracle
  lane (PR #19's guard fix applied locally only) 1,634 passed, 4 skipped,
  2 deselected, guard PASS. Subset gate with `--diplomacy` against base: PASS, NO
  REGRESSION, 0 extinct worlds, artifacts PARTIAL to PASS; informational
  regression `civ_survival` 0.30 (base 0.25) and strict latest satisfaction
  0.445 (base 0.454).
- **Not run.** The full 200-seed gate with `--diplomacy`; it is required
  before any default change, watching `civ_survival` and the strict
  latest-satisfaction floor.

## Maritime layer (2026-10-24, `feat/maritime`, default off)

Branch `feat/maritime` from `integrate/wave-3` (`20eeead`, merged with
`92b6122` for the food-balance corrections), default off behind
`--maritime` (`WorldState.maritime`). See
[`docs/integration/maritime.md`](../../integration/maritime.md).

- **Built.** Fleets per civ commissioned at coastal ports by a naval
  programme (treasury, and timber from free physical stocks in hybrid runs),
  with upkeep, storms and naval battles feeding the campaign war score;
  per-zone control (uncontested, contested, controlled) on Geography 2.0's
  sea zones, or on one derived zone per connected coast-clique group on
  template worlds; blockades that close an enemy's sea lanes to trade
  routes, goods-economy pairs, the native merchant graph and the ledger's
  route proxy, and cut its sea supply; armies cross lanes only with an
  escort or command, wait and request one otherwise, and land through the
  ordinary campaign battle code at reduced power; pirate pressure in
  uncommanded zones that skims the off-mode proxy and, through the native
  `Raid` loss reason (activated), seizes merchant cargo; colonization of
  coasts a civ cannot walk to through EXPAND, gated on a fleet in the zone.
  Naval battles and blockades enter diplomatic memory; every maritime event
  cites its causes.
- **Cut.** Ship classes, troop transports and bombardment (escort capacity
  stands in), privateering orders, fleets crossing between unconnected water
  bodies, navigation techniques (a neutral `navigation_level` seam for the
  technique registry), naval battles in `war_state.battles`, viewer panels.
- **Evidence (final head).** Switch off is byte-identical to `92b6122`: 72
  files (template seeds 42/7/1234 off 300 / hybrid 200, procedural 48x10 off
  200 / hybrid 120), 0 differences with the default and with `--no-maritime`;
  the switch-off subset batch matches the base batch file for file (2,160 run
  files); with the switch on, the 13 sealess gate seeds are outcome-identical
  to the base. Native `pytest -m "not slow" -n 2` 5,657 passed, 3 skipped
  (base `92b6122` 5,610 / 3); no-Rust lane 5,461 passed, 199 skipped; bounded
  Python oracle lane (PR #19's guard fix applied locally only) 1,677 passed, 6
  skipped, guard PASS; `cargo test --release` 894 passed. Subset gate with
  `--maritime` against `92b6122`: PASS, NO REGRESSION, 0 extinct worlds,
  regression PASS (strict) on both sides.
- **Numbers.** Procedural 48x10 worlds (3 seeds x off/hybrid, 200 turns):
  per run 24 fleets, 23 naval battles, 12 blockades, 4 overseas campaigns,
  0.7 colonies, 6.6 cargo units lost to pirates, 827 cargo units carried by
  sea; fewer trading civ pairs in every run. Only 7 of 20 default template
  worlds have a sea at all.
- **Not run.** The full 200-seed gate with `--maritime`; required before any
  default change. Piracy and colonization are small in current worlds
  (illustrative calibration).

## Recovery checkpoint (2026-10-11)

Checkpoint 011 (`b820217a9ea34ead33e2114e38d44f4297b0a70c`) was restored in an
isolated Windows checkout. It contains public `main` (`edf7299`) and 108 further
commits, so no rebase was needed. The continuation branch is
`continuation/recovered-20261011`; older dirty Windows source and the competing
desktop foundation architecture remain preserved separately. See
[`docs/CONTINUATION.md`](../../CONTINUATION.md) for exact locations and standing,
and [`docs/DEVELOPMENT.md`](../../DEVELOPMENT.md) for portable setup and the guarded
Python runner. Fresh checks passed 1,570 guarded Python tests (3 skipped,
2 deselected) and 162 viewer tests, lint and build. A Unix text-fixture comparison
now accounts for Windows newlines without changing production writes or goldens.
POSIX session persistence, native/GPU, full suites and milestone qualification
remain separate gates; no merge, flag activation or deployment is claimed.

## Current Focus (2026-10-07)

- **Historical module import aliases are preserved.** Follow-up commit `e54f3a1c634e45bf88678c91797ec618713c7db1`, merged at `d557bcdcce65c63476b440f842607471e3d3e4cf`, restores `world_gen._pick_regnal_name`, `memory.field`, and `models.field` as the exact original callables. The earlier cosmetic removal remains in checkpoint010 history; its bounded consumer search could not establish absence of external callers and had no measured speed benefit. A new direct-import/identity/call regression fails on checkpoint010 and passes with the restoration. The isolated guarded gate passed 118 tests, with one subprocess test excluded. All 94 module-import inventory leads are now retained, including 64 explicit politics compatibility exports; no speed claim is made for restoring the aliases.
- **Broader Windows persistence checks use an explicit Python-oracle guard.** Checkpoint010 passed 133 additional CLI, fork, sequential-batch, bundle, and checkpoint-replay tests, with one cross-process replay case excluded. Native imports are blocked before collection, main runtime factories return `None`, network activity and nested processes are blocked, and only credential-free runtime paths are inherited. Local hostname metadata remains available for checkpoint identity. The earlier 881-test packet had an installed-native import/factory path and cannot establish zero incidental native execution; its sealed evidence remains unchanged with this qualification. The fixed snapshot/RNG goldens and separate accepted-baseline aggregate comparisons retain their narrower Python-oracle meaning. Final integrated-tree results are recorded in the task evidence packet.
- **Legacy resource compatibility remains live, with two redundant initialization calls removed.** World generation and scenario finalization already call `assign_resources()`, which leaves every ordinary region's legacy resource list nonempty; the following numeric assignment does not clear it. Their final bridge calls therefore only skipped each region. The cleanup removes those calls and unused local import aliases, while preserving the bridge, serialized fields, numeric scenario override path, and resource discovery. It passed 141 existing behavioral tests and 18 exact paired initialization comparisons covering three seeds, three world sizes, numeric and string overrides, empty lists, and unknown terrain. Model/private-cache state, RNG traces and global state, save/load bytes, and fixed-time bundles matched. This is a source cleanup with no speed claim; side-effectful custom regions or external callback replacements fall outside the proof.
- **The deferred eligibility scan was declined before implementation.** Moving the expansion threshold lookup ahead of the unclaimed-region scan changes behavior when a supported custom tuning mapping mutates region control in `.get()`. The original-order `any()` alternative remains unimplemented: the complete getter occupied under 0.7% of the recorded profiles, and a generator could regress fully claimed cases. Neither variant entered integration.
- **Action weights initialize in one enum pass.** The complete dictionary keeps all 11 action keys in declaration order, with the same eligible base and ineligible zero values; the getter and later modifiers stay unchanged. The candidate passed 128 action/determinism checks, including an explicit getter/order/zero regression. Complete-method loops matched 15,360 ordered weight outputs and world/cache/event/RNG state; all 16 paired trials were faster, with four shape medians of 1.057x, 1.050x, 1.028x, and 1.014x. Both opposite-order whole-workload packets preserved exact artifacts, turn hashes, and RNG. Their timing signs varied, so no overall wall-speed gain is established. The profile's 1.295% own-time share is context for the limited opportunity, not an unprofiled bound.
- **The local-import sweep preserves intentional dependencies and annotations.** An AST scan of 90 tracked Python source files found six candidates. The federation lookup's annotation-only `Federation` import now lives in `TYPE_CHECKING`; its separate live constructor import remains. `detect_schisms()` no longer imports unused `FactionType`, while the actual clergy use in `fire_schism()` remains. The isolated change passed 135 existing politics, schism, and turn-artifact tests. Narrator/PyArrow dependency probes and live startup were retained. No speed claim is made for this source cleanup.
- **A direct trade-route deduplication experiment remains held.** The one-condition candidate passed 29 tests, 19,392 paired returned-route outputs, and exact full-workload artifact/turn/RNG comparisons. Its duplicate-heavy helper loop measured 2.55x faster, but hostile pairs were about 5.5% slower and wide workloads measured 0.974x / 0.937x in opposite run orders. Independent review recommended holding it at `held/trade-route-dedup-regression`. A broader evaluated-pair set was left unimplemented because it adds per-call allocation without a representative measured benefit.
- **Ordinary tuning dictionaries avoid repeated abstract-mapping checks.** Both tuning readers retain live per-call lookup, defaults, and subclass/custom-mapping dispatch. Nineteen focused tests passed; complete pure-Python ecology ticks matched 1,600 paired state/event/RNG frames. Four ordinary-dictionary shapes measured 1.17-1.20x faster, while the dict-subclass fallback measured about 1.8% slower. Opposite-order full simulation packets preserved exact artifacts, turn hashes, and RNG, but standard workload wall-time ratios were 0.917x and 0.992x; these packets do not establish an overall speedup. The improvement is scoped to the measured Windows ecology component; no overrides are cached or hoisted across calls.
- **Repeated saves avoid redundant directory creation attempts.** `MemoryStream.save()` and `WorldState.save()` probe the parent once and retain the original recursive `mkdir` path when it is missing, is not a directory, or the probe raises `OSError`. Every serialization and file write is unchanged. Thirteen focused persistence checks passed, including nested creation, exact Windows bytes after changed-content overwrites, parent-as-file preservation, and the Python 3.13-style probe-error fallback. Same-input complete-save comparisons checked 562 paired outputs and improved all 16 alternating-order timing pairs; median ratios were 1.12-1.33x across the measured memory/world payloads. Both opposite-order complete simulation packets preserved artifacts, per-turn hashes, and RNG traces. Their wide-workload timings changed from 0.921x to 1.105x, so no reliable overall speedup is claimed. Measurements are Windows-only; concurrent directory replacement and unusual filesystem error timing remain outside the equivalence scope.
- **Continuing refinement removes unused work and one obsolete private factory.** Economy processing now calculates projected war treasury only when an accumulator and active wars will consume it; queued-change and war processing order remain unchanged. Eight focused tests and eight exact same-input phase comparisons passed. Peaceful accumulator cases measured 1.36x at 8 civilizations and 2.04x at 32 civilizations; these are phase-helper measurements. Delta report traversal replaces three temporary key lists with an ordered iterator, preserving left-first equal-key representatives. Its 43-test and six-case parity gates passed, with 10-28% lower traced peak allocation and near-flat timing; no speedup is claimed for that change.
- **The dead-code sweep distinguished registration from obsolete code.** `_resolve_fund_instability` remains live through `@register_action` and was retained. `_make_transient_ecology_runtime` had no remaining internal caller, export, or reflective reference after the Python fallback replaced its only caller in `a1104c5`; it was removed in a reversible commit. The public ecology dispatcher and persistent runtime factory stay unchanged. Eight focused ecology checks passed, including an explicit blocked-native-import soil-recovery regression. Direct external imports of the removed private name are outside the in-repository compatibility proof.
- **Intelligence adjacency now reuses a lookup only as far as each request needs.** `shares_adjacent_region()` incrementally consumes the live region list and retains the first region with each name, preserving directed/missing edges, duplicate-name selection, edits made between calls, and the public `compute_accuracy()` call seam. The candidate passed 123 focused tests, including all three existing exact snapshot/RNG golden workloads. Identical-input helper benchmarks improved all eight measured shapes; ordered civilization-pair queries measured 1.36x at 8 regions / 3 civilizations and 6.30x at 256 regions / 16 civilizations. Larger full-scan cases used 10.4 KiB rather than 1.1 KiB peak traced temporary allocation, released at return. These are component measurements for stable valid model inputs, not whole-simulation or concurrent-mutation guarantees.
- **Two additional measured candidates remain held.** A cohort demographic-control index passed 79 tests but ran at 0.50-0.61x baseline speed across all four measured shapes. Pre-cap median reuse passed 48 tests but ran at 0.93x / 0.83x for 12 / 4,000 weights because its compatibility guard cost more than the saved sort. Their complete branches remain at `held/cohort-control-index-regression` and `held/analytics-precap-median-regression`; neither is included in production integration.
- **The continuing population-sync refinement removes repeated region scans.** `sync_all_populations()` groups known owners' population values once in region order, then retains built-in `sum()` and civilization-order floor/update behavior. The public single-civ helper stays unchanged. Utility, climate, and ecology coverage passed 102 tests before integration. Same-input helper measurements were 1.94x at 8 regions / 3 civilizations and 14.24x at 256 regions / 24 civilizations; the larger case used 5.4 KiB rather than 0.6 KiB peak traced temporary allocation. Single-civ probes showed no observed regression. These are component results for the measured shapes, not an overall simulation speed claim. Arbitrary missing/raising attributes on malformed mock regions are outside this equivalence scope.
- **The CLI duplicate was reviewed and retained.** `validate.main` and `validation_io.main` have matching bodies but preserve distinct module-local callback/monkeypatch and `python -m` entrypoint behavior. Consolidating them would introduce more adapter indirection than the small body warrants; no public compatibility entrypoint was removed.
- **Scoped cleanup is integrated on `cleanup/chronicler-20261007`.** The source was restored from the verified complete history at accepted production `2bfd655a65c433cb41e1118b86fa6bc1978a37c4`. `graph_distance()` now performs distance-only BFS without path-list copies; the cohort oracle shares one filtered event window between its read-only migration and rebellion calculations. Graph semantics, public validation re-exports, turn selection, snapshot reconstruction, and legacy fallback rules are preserved.
- **Focused Windows checks passed before integration.** Adjacency coverage passed 18 tests; validation and import-compatibility coverage passed 74 tests. Identical-input helper benchmarks measured 1.20x / 1.18x for distance queries over 8 / 32 regions and 1.93x for the event-filtering component over 50,000 events and eight windows. These are component measurements, not whole-simulation or native speed claims. Final integration checks and independent review are recorded in the task's evidence packet.
- **A broader snapshot cache remains held.** It passed 81 tests and measured 1.91x faster snapshot preparation/consumption, but peak traced Python allocation increased from 714,032 to 1,040,736 bytes on the same input. Its complete branch history is preserved at `held/cohort-snapshot-cache-memory`; the production cleanup does not include it.
- **Source and proof boundaries remain explicit.** Economic qualification commits `16005be3` and `19f649a8` are preserved as separate test-only checkpoints. The admitted spatial producer corpus and unbuilt/unrun CPU consumer remain outside production integration. The Rust subtree stays `2fc4b97c629ad9148f9e40a631e0ea86f0eedbd9`; no Rust/native build, dedicated native/GPU qualification, 200-seed milestone gate, deployment, or automatic job was run here. Earlier incidental installed-native execution is unproven as qualified above. The older Windows checkout, all 16 dirty files, and four ignored source files remain untouched, with additional task-local recovery copies. The frozen checkpoint010 bundle has a separately verified portable package for Linux migration; source-side packaging does not establish delivery or Linux validation.
- **Further deletion needs stronger evidence.** Public compatibility helpers and validation re-exports remain intentionally available. A read-only AST sweep found no statements directly following unconditional exits and only the reviewed CLI-body duplicate among nontrivial exact function bodies; this is a candidate scan, not exhaustive dead-code proof. No tracked module was removed as unused.

## Previous Focus (2026-04-05)

- **2026-04-05 Rust warning cleanup follow-up is complete in the working tree.**
  The post-push warning sweep removed dead FFI imports/helpers, dropped an unused `RecomputeContext.turn` field, cleaned unused test locals/imports, and marked the intentionally reserved agent-stream/protocol constants as explicitly retained so the Rust build stops emitting warning noise without changing runtime behavior.
- **Rust validation for the warning cleanup follow-up is green.**
  `cargo test --manifest-path chronicler-agents/Cargo.toml --no-run` now finishes cleanly without warning output, and `cargo nextest run --manifest-path chronicler-agents/Cargo.toml` PASS (`817 passed, 2 skipped`) after prepending `<HOME>\AppData\Local\Python\pythoncore-3.14-64` to `PATH` for the local Windows Python DLL bootstrap quirk.

- **2026-04-05 shadow population routing and live narration offload are complete in the working tree.**
  Shadow mode was still dropping aggregate population growth/loss/repopulation and random-event migration bonuses because those paths routed `population` through `guard` whenever `agent_mode != "off"`, even though shadow has no population write-back and `shadow.arrow` logs aggregate stats from the live Python world. The production and random-migration paths now treat only `hybrid` / `demographics-only` as agent-owned demographics; shadow falls back to direct Python mutation so the aggregate baseline stays truthful while the Rust side still runs in parallel. `live.py` now snapshots `_init_data` and sends `narrate_range` through `asyncio.to_thread(...)`, which keeps the WebSocket loop responsive while long narration runs.
- **Focused validation for the shadow/live follow-up is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_simulation.py::TestPhaseProduction::test_agents_off_population_growth_updates_regions_when_accumulator_present tests/test_simulation.py::TestPhaseProduction::test_shadow_population_growth_updates_regions_when_accumulator_present tests/test_simulation.py::TestPhaseProduction::test_demographics_only_population_growth_stays_agent_owned tests/test_simulation.py::TestEventEffectPopulationRouting::test_shadow_random_migration_updates_population_directly tests/test_simulation.py::TestApplyInjectedEvent::test_plague_reduces_pop_and_stability tests/test_agent_bridge.py::TestSharedModeFixtures::test_hybrid_catastrophe_deaths_survive_write_back tests/test_main.py::TestAgentsWiring::test_shadow_run_writes_arrow_artifact tests/test_live_integration.py::test_rejects_non_object_and_bad_narrate_range tests/test_live_integration.py::test_narrate_range_passes_great_persons_and_agent_name_map tests/test_live_integration.py::test_narrate_range_offloads_work_and_keeps_queue_drain_alive` PASS (`10 passed`). Rust-side regression/compile coverage also PASS via `cargo test --manifest-path chronicler-agents/Cargo.toml --quiet test_catastrophe_deaths_apply_before_tick` with `<HOME>\AppData\Local\Python\pythoncore-3.14-64` prepended to `PATH`.

- **2026-04-05 hybrid plague casualty bridge fix is complete in the working tree.**
  Phase 1 plague losses now keep the direct Python-side region/civ population mutation for pre-tick Phase 2-9 consumers, but they also stage a cleared-per-turn `catastrophe_deaths_this_turn` region transient through `build_region_batch()` so Rust applies the same deaths before the agent tick/write-back. This closes the specific hybrid bug where plague population loss changed Python `region.population` briefly, then disappeared when `_write_back()` rebuilt population from the live agent pool. The transient is builder-cleared on read and the Rust tick now consumes it through the normal death/inheritance/memory path.
- **Focused validation for the hybrid plague bridge fix is green.**
  Rebuilt the extension with `cd chronicler-agents && ..\\.venv\\Scripts\\python.exe -m maturin develop --release`, then verified `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py::TestSharedModeFixtures::test_hybrid_catastrophe_deaths_survive_write_back tests/test_agent_bridge.py::TestM48TransientMemorySignals::test_catastrophe_deaths_clear_after_read tests/test_agent_bridge.py::TestM48TransientMemorySignals::test_batch_has_correct_arrow_types tests/test_simulation.py::TestApplyInjectedEvent::test_plague_reduces_pop_and_stability tests/test_acc_hardening.py::TestInjectedEventAccRouting::test_plague_injection_routes_stability_through_acc tests/test_m36_regression.py::TestEconomyRegression::test_stability_same_order_of_magnitude_hybrid` PASS (`6 passed`). Rust-side regression coverage also PASS via `cargo test --manifest-path chronicler-agents/Cargo.toml --quiet test_catastrophe_deaths_apply_before_tick` after prepending `<HOME>\AppData\Local\Python\pythoncore-3.14-64` to `PATH` for the local DLL bootstrap quirk.

- **2026-04-05 architecture refactor pre-spec handoff pass is complete in the working tree.**
  Reviewed the live coordinator, bridge, model, and viewer-contract seams against the current repo state and recorded the move-forward recommendation set in `docs/superpowers/plans/2026-04-05-architecture-refactor-pre-spec-handoff.md`. The handoff locks six actionable non-rewrite follow-ups that are worth carrying into full specs: typed `TurnArtifacts` / `TurnContext`, a behavior-preserving `run_turn()` coordinator split, `agent_bridge.py` responsibility splitting, a single authoritative bridge-contract module plus ratchet tests, gradual runtime-only dataclass peel-out from the Pydantic hot path, and continued Phase 7.5 thin-client / query-oriented viewer direction.
- **Phase 8/9 compatibility strengthens the first four items.**
  The handoff explicitly ties the recommendation to the live Phase 8-9 planning constraints: cross-system signals should keep the N -> N+1 lag pattern, bridge payload ownership should be explicit, and pre-M63 complexity should not keep accumulating inside `run_turn()` and `agent_bridge.py`. The adjacent action-weight `modifier-composition` guardrail remains important before `M63`, but it is kept as a separate follow-up rather than folded into this handoff batch.
- **Important scoping gotcha for follow-up specs.**
  Not every private `world._...` field should move into one turn-artifact object. The handoff calls out three separate categories that should stay distinct: turn-local artifacts, cross-turn carry state, and hot-path caches. In particular, `pending_shocks`, `_prev_belief_distribution`, `_prev_priest_counts`, `_treasury_tax_carry`, and `_persecuted_regions` should not be treated as the same kind of state as `_agent_snapshot` or `_economy_result`.
- **Status note for this pass.**
  This was a docs-only architecture handoff pass. No runtime behavior changed, no tests were run, and the next concrete step is to choose which of the six items gets the first full spec.

- **2026-04-04 audit verification rewrite is complete in the working tree.**
  The untracked `docs/superpowers/audits/4-4-26opusaudit.md` draft was rechecked against the live repo after the 2026-04-03 remediation pass and rewritten as a verification memo instead of a raw claim dump. The rewritten audit now explicitly drops stale or overstated items such as the "double-count tithe" claim, keeps only source-backed current findings, and breaks the remaining follow-up into four parallel remediation lanes: hybrid accumulator hardening, ecology and demographics alignment, spatial and Great Person cleanup, and Rust RNG or compatibility cleanup.
- **2026-04-03 cross-cutting audit fix pass is complete on `main`.**
  The five verified follow-up fixes from `docs/superpowers/specs/2026-04-03-audit-fix-pass-design.md` and `docs/superpowers/plans/2026-04-03-audit-fix-pass-plan.md` are now landed and pushed: `B1` holy-war clergy boosts now survive `compute_conversion_signals()` through the Phase 10 faction tick, `B3` asabiya-collapse military/economy losses now honor the M18 severity multiplier, `B6` migration/newborn spatial placement now uses packed region/turn streams plus per-agent seeds with a distinct newborn offset, `W17` grudge-driven WAR weighting is capped through a dedicated helper/tuning key, and `W10` now clears `_dead_agents_this_turn` at turn start so stale martyrdom state cannot leak across a failed agent tick.
- **Validation for the 2026-04-03 audit fix pass is complete.**
  Focused regression coverage for the five fixes passed, the broader Python validation surface reached `2579` passing tests and `4` skipped tests while one unrelated pre-existing failure outside this pass remained in the full shell run, and Rust validation reported `812 passed, 2 skipped`.

- **2026-04-03 full audit remediation is complete in the working tree.**
  Four parallel lanes plus a stitched integration follow-up closed the live plan in `docs/superpowers/plans/2026-04-03-full-audit-remediation-plan.md`: shadow-mode output is wired back through `main.py` / `AgentBridge` without adding any shadow write-back, settlement transients now have the required multi-turn reset coverage, the simulation/economy/politics/action/faction/infrastructure cluster landed its confirmed correctness fixes including the neutral-by-default trade-route behavior and the real post-cap action-weight fix, the bridge/FFI lane hardened civ-signal validation and relationship-slot handling without changing the intended stability/shadow ownership rules, Great Person/analytics/narrative/bundle/model hygiene fixes are in place, and the viewer/live shell regressions from the same audit are closed with green tests/lint/build.
- **Claim hygiene from the 2026-04-03 plan was preserved.**
  `C2` and `C3` stayed rejected as filed, `C4` stayed reframed to "insufficient explicit FFI contract coverage" rather than "zero tests", `M15` was re-audited and not reproducible on the current `curator.py` / `narrative.py` path, and `M11` was already closed on head before this pass so no duplicate source change was forced.
- **The stitched post-lane follow-up is also complete.**
  The final integration pass corrected an over-tight civ-signal contract introduced during hardening: demand shifts now only require finiteness end-to-end, `priest_tithe_share` remains non-negative but is no longer incorrectly capped at `1.0`, and the stale intelligence expectations were refreshed to match `H4`'s verified neutral-by-default trade-route behavior.
- **Validation for the 2026-04-03 full remediation pass is green.**
  Rebuilt the extension with `cd chronicler-agents && ..\\.venv\\Scripts\\python.exe -m maturin develop --release`, then ran `.\.venv\Scripts\python.exe -m pytest -q` PASS (`2541 passed, 4 skipped`), `cargo nextest run --manifest-path chronicler-agents/Cargo.toml` PASS (`809 passed, 2 skipped`) with `<HOME>\AppData\Local\Python\pythoncore-3.14-64` prepended to `PATH` so Windows can resolve `python314.dll`, and viewer validation stayed green via `npm test` PASS (`94 passed`), `npm run lint` PASS, and `npm run build` PASS with only the existing Vite chunk-size warning.

- **2026-04-02 audit cache-hot-path follow-up is complete in the working tree.**
  The remaining high-frequency civ/region lookup stragglers on the Sprint 2/3 performance-hardening surface now reuse cached maps instead of repeated linear scans: `build_region_batch()` / `_get_active_focus()` in `agent_bridge.py`, `process_migration()` in `climate.py`, the pandemic / supervolcano / resource-discovery / tech-accident / drought-intensification paths in `emergence.py`, and the remaining hot federation / proxy / congress / exile civ lookups in `politics.py` now consume `world.civ_map` and `world.region_map` (with safe fallbacks for lightweight test worlds where appropriate). This keeps the behavior from the earlier audit closeout but removes the last practical hot-path rescans that were still sitting on the bridge/environment/politics side of the Sprint 2 cache work.
- **Focused validation for the cache-hot-path follow-up is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_politics.py tests/test_agent_bridge.py tests/test_climate.py tests/test_emergence.py` PASS (`262 passed`).

- **2026-04-02 Sprint 5 test-infrastructure scaffolding is complete in the working tree.**
  `tests/conftest.py` now exposes reusable `demographics_bridge_world`, `shadow_bridge_world`, and `hybrid_bridge_world` fixtures so non-off agent-mode tests stop hand-rolling the same `AgentBridge(..., mode=...)` setup. `tests/test_agents_off_determinism.py` now includes a one-civ aggregate smoke to cover the smallest world shape, `chronicler-agents/tests/test_behavior.rs` now includes a narrow economy -> satisfaction -> behavior -> migration integration check through the public `tick_agents()` path, and `.github/workflows/validation-gate.yml` wires the existing `scripts/m53b_run_validation.py` runner into a nightly/manual GitHub Actions entry point for the 200-seed validation gate.
- **Focused validation for the Sprint 5 scaffolding is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py tests/test_agents_off_determinism.py tests/test_simulation.py tests/test_politics.py tests/test_culture.py tests/test_emergence.py tests/test_resources.py` PASS (`392 passed`). `cargo nextest run --manifest-path chronicler-agents/Cargo.toml --test test_behavior` PASS (`5 passed`).

- **2026-04-02 Sprint 4 docs refresh is complete in the working tree.**
  `CLAUDE.md` and `AGENTS.md` now match the live `run_turn()` phase order instead of the older politics/military/diplomacy-era numbering, Rust FFI file references now point at `chronicler-agents/src/ffi/mod.rs`, and the clearly stale source-tree counts were refreshed from the current tree snapshot (`src/chronicler`: 60 Python files / ~28.6k lines, `chronicler-agents/src`: 29 Rust files / ~24.4k lines, `viewer/src`: 38 TS/JS files / ~7.8k lines). Sprint 4's last architecture cleanup is also now done: shared FFI constants live in `src/chronicler/ffi_constants.py`, so `culture.py` and `economy.py` no longer reach upward into `agent_bridge.py` just to import `VALUE_TO_ID` / `TERRAIN_MAP`. Audit status is now documented more explicitly too: Sprint 1 is complete, Sprint 2 and Sprint 3 are closed in the working tree, and Sprint 4 is fully complete.
- **Docs verification for the Sprint 4 refresh was kept narrow.**
  Verified `CLAUDE.md`, `AGENTS.md`, and `simulation.py` against the live `run_turn()` order, refreshed the counts from direct source-tree file/line measurements rather than stale historical estimates, and confirmed the constant-extraction follow-up with `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py tests/test_culture.py tests/test_economy_bridge.py tests/test_economy.py` PASS (`185 passed`).

- **2026-04-02 audit hardening closeout is complete in the working tree.**
  The remaining runtime guardrails from the audit follow-up are now wired through end-to-end: `AgentSimulator.tick()` releases the GIL with PyO3 0.28's `py.detach(...)` while `AgentPool` exhaustion is surfaced as a `PyRuntimeError` during initial spawn and birth processing instead of panicking the Python host, analytics extractors now tolerate empty bundle/history inputs without `history[-1]` / zero-run crashes, climate/ecology/action-engine tuning-derived divisors are floored away from zero, the active-trade-route helpers now reuse `world.region_map` for adjacency lookups instead of repeated linear region scans, and adjacency helpers can now consume a prebuilt adjacency map so the hottest politics distance loops (`apply_governing_costs()`, `resolve_move_capital()`, secession scoring, and `resolve_fund_instability()`) stop rebuilding the same graph on every BFS call.
- **2026-04-02 audit Sprint 2/3 closeout is complete in the working tree.**
  The remaining route-cache and determinism follow-ups are now closed with invalidation-aware behavior instead of a naive forever-snapshot: successful `EXPAND`, `DIPLOMACY`, `EMBARGO`, attacker-win `WAR`, and congress ceasefire/peace mutations now invalidate the current-turn trade-route cache at the mutation site, while Phase 2 explicitly refreshes routes once after politics/disposition updates so trade knowledge sharing and pandemic spread consume current data instead of stale Phase 2-open snapshots. The last Python determinism traps were also removed: diplomatic congress participant ordering and equal-power ceasefire tie-breaks are now name-stable, the bottom-up value-drift path sums over sorted cultural-value keys, and the supervolcano/pandemic regression coverage now locks down deterministic actor/affected-civ ordering plus explicit route-snapshot reuse.
- **Focused validation for the Sprint 2/3 closeout is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_action_engine.py tests/test_resources.py tests/test_politics.py tests/test_culture.py tests/test_emergence.py tests/test_simulation.py` PASS (`379 passed`).
- **Focused validation for the audit hardening closeout is green.**
  `cargo test --quiet test_try_spawn_returns_err_when_next_id_overflows` PASS in `chronicler-agents/`. Rebuilt the extension with `cd chronicler-agents && ..\\.venv\\Scripts\\python.exe -m maturin develop --release`, then verified `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py::TestPythonRoundTrip::test_tick_before_set_region_state_errors tests/test_agent_bridge.py::TestTickBehavior tests/test_agent_bridge.py::TestPythonDeterminism` PASS (`5 passed`). Python-side hardening regression coverage also PASS via `.\.venv\Scripts\python.exe -m pytest -q tests/test_analytics.py tests/test_climate.py tests/test_ecology.py tests/test_utils_civ_helpers.py tests/test_simulation.py::TestPhaseProduction::test_agents_off_population_growth_updates_regions_when_accumulator_present tests/test_resources.py` (`154 passed`), `.\.venv\Scripts\python.exe -m pytest -q tests/test_action_engine.py::TestWarDamper::test_zero_threshold_override_uses_floor tests/test_action_engine.py::TestWarWeariness::test_zero_divisor_override_uses_floor tests/test_action_engine.py::TestEligibility::test_embargo_routes_target_penalty_as_shock_signal_in_accumulator_mode tests/test_politics.py::test_capital_loss_hybrid_routes_through_accumulator_when_available tests/test_simulation.py::TestPhase10AccumulatorFlush::test_phase10_condition_drains_route_through_accumulator tests/test_severity.py::TestSeverityAtEmbargoSite::test_embargo_stability_drain_uses_severity` (`6 passed`), and `.\.venv\Scripts\python.exe -m pytest -q tests/test_adjacency.py tests/test_action_engine.py tests/test_politics.py` (`131 passed`).

- **2026-04-02 audit follow-on population/cache/perf fixes are complete in the working tree.**
  The off-mode production path now applies population growth/loss/repopulation directly to regions even when an accumulator is present, so later `sync_all_populations()` calls no longer erase aggregate-mode population changes. `WorldState` now exposes cached `civ_map` / `civ_index_map` lookups that refresh after civ-count changes, `utils.civ_index()` / `get_civ()` now consume those caches, and several hot `region_map` / trade-route paths in `politics.py`, `simulation.py`, and `resources.py` now reuse the existing cached `world.region_map` instead of rebuilding name maps or rescanning `world.regions` on each lookup.
- **Focused validation for the audit follow-on population/cache/perf pass is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_accumulator.py::TestShockNormalization tests/test_action_engine.py::TestEligibility::test_embargo_routes_target_penalty_as_shock_signal_in_accumulator_mode tests/test_factions.py::TestTickFactions::test_tithe_routes_through_accumulator_keep_in_agent_mode tests/test_utils_civ_helpers.py tests/test_politics.py::test_capital_loss_hybrid_routes_through_accumulator_when_available tests/test_simulation.py::TestPhase10AccumulatorFlush::test_phase10_condition_drains_route_through_accumulator tests/test_simulation.py::TestPhaseProduction::test_agents_off_population_growth_updates_regions_when_accumulator_present tests/test_severity.py::TestSeverityAtEmbargoSite::test_embargo_stability_drain_uses_severity` PASS (`21 passed`). `.\.venv\Scripts\python.exe -m pytest -q tests/test_resources.py tests/test_audit_batch_d.py -k "trade_routes or get_active_trade_routes or self_trade"` PASS (`2 passed, 39 deselected`).

- **2026-04-02 targeted audit Sprint 1 Python fixes are complete in the working tree.**
  Tightened civ-shock normalization so accumulator shock signals now use stat-aware floors (`stability >= 10`, `economy >= 5`) before clamping, which removes the worst low-stat shock amplification path. EMBARGO target stability loss now routes as a shock `signal` instead of a dropped `guard-action` in hybrid mode, clergy tithe treasury gains now go through the accumulator as `keep` mutations when an `acc` is present, and `utils.civ_index()` now raises a descriptive `ValueError` with the missing civ name plus known civs instead of leaking `StopIteration`. `run_turn()` also now documents and asserts the intended Phase 10 hybrid contract: the main hybrid turn path must use the accumulator watermark, while helper-level `pending_shocks` fallbacks remain only for standalone `acc=None` calls.
- **Focused validation for the targeted audit Sprint 1 Python pass is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_accumulator.py::TestShockNormalization tests/test_action_engine.py::TestEligibility::test_embargo_routes_target_penalty_as_shock_signal_in_accumulator_mode tests/test_factions.py::TestTickFactions::test_tithe_routes_through_accumulator_keep_in_agent_mode tests/test_utils_civ_helpers.py tests/test_politics.py::test_capital_loss_hybrid_routes_through_accumulator_when_available tests/test_simulation.py::TestPhase10AccumulatorFlush::test_phase10_condition_drains_route_through_accumulator tests/test_severity.py::TestSeverityAtEmbargoSite::test_embargo_stability_drain_uses_severity` PASS (`18 passed`).
- **Follow-up note from validation.**
  A broader mixed batch that included full `run_turn()` integration tests was red for a pre-existing ecology-runtime/mock issue in this shell (`tick_ecology()` attempting to unpack a stubbed `EcologySimulator.tick_ecology()` result), so this pass intentionally relied on the narrower behavior-level regression set above rather than treating that unrelated harness problem as a new regression from the Sprint 1 fixes.

- **2026-04-02 live viewer/batch contract hardening is complete in the working tree.**
  `live.py` now validates `batch_load_bundle` payloads before hydrating `_init_data` (rejecting malformed JSON roots and unsupported Bundle v2 manifests instead of forwarding arbitrary objects into the viewer), seeds reconnect state from `metadata.total_turns` instead of the dead `metadata.turns` key, carries live-session narration client config forward so `narrate_range` reuses the active/local bundle-selected models rather than defaulting to bare `create_clients()`, and batch-start config now accepts/passses the viewer-selected run shape (`civs`, `regions`, `scenario`, `sim_model`, `narrative_model`, `narrator`, `agents`, `preset`) instead of hardcoding `4x8` procedural defaults. On the viewer side, live `bundle_loaded` messages now flow through the existing bundle-classification guard before touching app state, and Batch Lab reuses the current setup shell values when launching a batch so runs no longer silently narrow back to the server defaults.
- **Focused validation for the live viewer/batch pass is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_live.py tests/test_live_integration.py tests/test_batch_websocket.py` PASS (`45 passed`). Viewer `npm test` PASS (`86 passed`), `npm run lint` PASS, and `npm run build` PASS, with only the existing Vite chunk-size warning on the main JS bundle.
- **Follow-up note for future viewer work.**
  This pass preserves the currently exposed setup choices and blocks malformed/unsupported bundle handoff, but the UI still does not expose first-class controls for advanced batch-only knobs such as `agents`, `preset`, or non-local narrator selection; those remain CLI/protocol-level capabilities rather than surfaced product controls.

- **2026-04-02 hybrid shock merge hardening is complete in the working tree.**
  `build_signals()` now merges duplicate same-civ `CivShock` entries instead of overwriting earlier shocks when multiple carry-over or same-turn shock records reach the Python/Rust boundary together, and the dormant Rust regression `test_rebel_priority_over_migrate()` is now active in the suite with its missing `#[test]` annotation restored.
- **Focused validation for the hybrid shock hardening is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_wealth.py tests/test_politics_bridge.py tests/test_agent_bridge.py` PASS (`158 passed`). `cargo test --quiet test_rebel_priority_over_migrate` PASS in `chronicler-agents/`.
- **2026-04-02 civ-faith bridge hardening and bundle export cleanup are complete in the working tree.**
  `build_region_batch()` and the `--agents=off` Phase 10 fallback now resolve civ faith from the civilization's persisted majority-faith fields before falling back to positional registry order, so resumed/custom worlds no longer depend on `belief_registry` order matching civ order for `initial_belief` seeding. `assemble_bundle()` also now uses `model_dump(mode="json")` directly instead of round-tripping every model through `model_dump_json()` plus `json.loads(...)`.
- **Focused validation for the civ-faith/bundle cleanup pass is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_agent_bridge.py tests/test_simulation.py tests/test_bundle.py` PASS (`172 passed`).
- **Repo-wide validation refresh (2026-04-02).**
  Full discovered Python validation after the live/viewer, hybrid-shock, civ-faith, and bundle-cleanup fixes now resolves to `2455 passed, 4 skipped` via `.\.venv\Scripts\python.exe -m pytest -q`.

- **2026-04-02 Phase A critical audit fixes are complete in the working tree.**
  Closed the six Tier 1 items from `docs/superpowers/audit/2026-04-02-full-codebase-audit.md`: holy-war WAR weighting now compares `Disposition` enums instead of dead strings, governing-cost stability drain no longer truncates `0.5` to `0`, Phase 10 hybrid shocks now route through the accumulator watermark when an `acc` is present (secession, capital loss, federation exits/remains, proxy detection, congress collapse, ongoing condition drains, and forced-collapse shocks), temple prestige now accepts `acc` and records civ prestige as a `keep` mutation, analytics now derives civ liveness from `regions` with a legacy `alive` fallback, and Rust `culture_tick` now uses the same packed `(region, turn, offset)` RNG-stream scheme as `conversion_tick`.
- **Focused validation for the Phase A pass is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_action_engine.py tests/test_politics.py tests/test_simulation.py tests/test_infrastructure_legacy_migration.py tests/test_analytics.py` PASS (`226 passed`). `cargo test --quiet stream_packing_is_distinct` PASS in `chronicler-agents/`.
- **2026-04-02 Phase B correctness fixes and targeted Phase C hardening are complete in the working tree.**
  Closed the remaining live correctness issues from `docs/superpowers/audit/2026-04-02-full-codebase-audit.md`: stalemate military losses, proxy-detection stability loss, and supervolcano population loss now all honor the M18 severity multiplier; dead civs are excluded from WAR/EMBARGO targeting; accumulator misroutes were corrected for embargo pressure, faction power struggles, and assimilation unrest; `_conquered_this_turn` now survives through the bridge handoff and off-mode runs now clear unused region transients (`schism_convert_*`, `_controller_changed_this_turn`, `_war_won_this_turn`, `_seceded_this_turn`) plus reset `tech_advanced` after Phase 10 use; post-decay prestige now drives treasury parity in both modes; merchant route transport costs now reuse the canonical economy transport calculation; persecution clears regions that no longer have believers; movement adoption is capped at 100%; bridge write-back now clamps stability and same-batch dynasty promotions now see freshly created parents; Great Person cap/orphan retirement now behaves globally instead of civ-locally; and narration prompt assembly now threads the focal civ into agent-context construction so Gini/wealth context is no longer zeroed.
- **Focused validation for the Phase B/Phase C pass is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_action_engine.py tests/test_politics.py tests/test_agent_bridge.py tests/test_economy_m43a.py tests/test_narrative.py tests/test_great_persons.py tests/test_simulation.py tests/test_analytics.py` PASS (`391 passed`). `.\.venv\Scripts\python.exe -m pytest -q tests/test_religion.py` PASS (`22 passed`). Rust-side focused checks PASS: `cargo test --quiet --lib shock_effects_apply_outside_social_penalty_cap`, `cargo test --quiet --lib mark_war_survivors_uses_current_partition`, `cargo test --quiet --lib spawn_panics_when_next_id_overflows`, and `cargo test --quiet stream_packing_is_distinct`.
- **Validation gotcha for future audit passes.**
  `tests/test_religion.py` stubs `chronicler_agents` at module import time, so mixed bridge/religion validation should run in separate pytest processes or it will create false failures unrelated to the code under test.
- **2026-04-02 cleanup closeout landed for the remaining dead/deprecated and spec-drift surfaces.**
  `--llm-actions` is now a deprecated compatibility flag that logs and is ignored, `NarrativeEngine` no longer exposes LLM action-selection helpers, `HistoricalFigure`/`WorldState.historical_figures` were removed with a regression proving legacy payloads still load, and Phase 10 relationship syncing now prefers `apply_relationship_ops()` instead of routing live writes through the deprecated `replace_social_edges()` full-graph shim. The last two audit leftovers are now closed too: world generation now seeds both `civ_majority_faith` and `previous_majority_faith` from each civ's founding belief instead of the model default `0`, and the weight-cap wording/analytics now align with the actual engine behavior (`base_weight * weight_cap`, so `0.5` at the default 2.5x cap).
- **Focused cleanup validation is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_main.py tests/test_narrative.py tests/test_models.py tests/test_relationships.py tests/test_m50a_relationships.py tests/test_agent_bridge.py` PASS (`209 passed`). `.\.venv\Scripts\python.exe -m pytest -q tests/test_action_engine.py tests/test_simulation.py tests/test_politics.py` PASS (`196 passed`).
- **Repo-wide validation snapshot (2026-04-02).**
  Full Python discovery is down to one remaining failure: `.\.venv\Scripts\python.exe -m pytest -q` reported `2447 passed, 4 skipped, 1 failed`, with the sole red at `tests/test_bundle.py::TestBundleSize::test_500_turn_bundle_under_5mb` because the generated 500-turn bundle is currently `40.63 MB` against the test's `< 35 MB` budget. Full Rust `cargo test --quiet` PASS in `chronicler-agents/`. Viewer `npm test` PASS (`83 passed`) and `npm run build` PASS, with only the existing Vite chunk-size warning on the main JS bundle.
- **2026-04-02 bundle-size follow-up is complete in the working tree.**
  `write_bundle()` now emits compact JSON for `chronicle_bundle.json` instead of pretty-printed output, which preserves the legacy bundle contract while removing ~16 MB of whitespace overhead from long runs. Reproducing the bundle-size fixture shape (`seed=1`, `turns=500`, `civs=5`, `regions=10`) now writes a `22.79 MB` bundle instead of the prior ~`39-40 MB`, so `tests/test_bundle.py::TestBundleSize::test_500_turn_bundle_under_5mb` is back under its `< 35 MB` gate without dropping snapshot fields.
- **Focused validation for the bundle-size follow-up is green.**
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_bundle.py` PASS (`35 passed`). Full repo-wide `pytest -q` was not rerun in this follow-up pass.

- **2026-04-02 remaining Rust audit fixes landed in the working tree.**
  Closed the three concrete Rust follow-ups that were still live after the critical pass: `compute_satisfaction_with_culture()` now clamps the cultural/religious/persecution subtotal before allocating the remaining social-penalty budget and documents that civ shock effects stay in base satisfaction; `tick_agents()` now marks war-survival from the post-demographics partition instead of the stale pre-migration partition; and `AgentPool::spawn()` now hard-fails on `u32` id exhaustion instead of silently wrapping into the `PARENT_NONE` sentinel. Focused Rust regression coverage now exercises the shock-cap path, the war-survival partition helper, and the `next_id` overflow guard.

- **2026-04-02 full-codebase report verification/fix pass is in the working tree.**
  Verified the 2026-04-02 cross-codebase analysis against the live tree and closed the concrete correctness/perf items that were still real rather than stale after the FFI/module split. Rust-side fixes now document and validate the civ-shock sign contract at the parse boundary, avoid repeated `find_slot_by_id` scans in relationship FFI ops via a prebuilt `id_to_slot` map, move `compute_aggregates()` onto deterministic `BTreeMap` accumulation, replace the full `compute_region_stats()` pre-pass inside satisfaction with a lighter dedicated occupation/demand pre-pass, harden `cultural_distance()` with an invariant check/saturating subtract, smooth the fertility satisfaction gate, harden conversion RNG stream packing across `(region, turn, stream)` space, and freeze the existing Gumbel utility-slot ordering in comments. Python-side fixes now seed wars with attacker/defender identity instead of `world.turn` alone, initialize `att_idx`/`def_idx` once for the accumulator-backed war paths, refresh snapshot-derived displacement/Gini metrics outside hybrid mode too, narrow the agent-snapshot swallow into logged helper code, and clarify punitive-only `normalize_shock()` / demand-manager semantics. Also verified the old `region_state_schema()` warning was stale after the FFI split (`ffi/schema.rs::ecology_region_schema()` is the live replacement) and refreshed the bridge/tests around snapshot metrics and war seeding.
- **Focused validation for the report pass is green; full Rust sweep still has a local PyO3 test-environment gotcha.**
  Rebuilt the extension with `cd chronicler-agents && ..\\.venv\\Scripts\\python.exe -m maturin develop --release`, then verified `.\\.venv\\Scripts\\python.exe -m pytest -q tests/test_action_engine.py tests/test_agent_bridge.py tests/test_simulation.py tests/test_accumulator.py tests/test_m36_regression.py` (`206 passed, 1 skipped`). Rust-side focused checks PASS: `cargo test --quiet --lib test_parse_civ_signals_rejects_out_of_range_shocks`, `cargo test --quiet --lib test_satisfaction_parallel_matches_sequential`, `cargo test --quiet --lib test_compute_aggregates`, `cargo test --quiet --lib test_fertility_`, `cargo test --quiet --lib test_conversion_stream_packing_is_distinct`, and `cargo test --quiet --lib test_apply_ops_`. `cargo test --quiet` still is not a reliable gate in this shell because some PyO3-backed FFI unit tests can fail on interpreter bootstrap (`encodings` / interpreter initialization) before user-code assertions run.

- **2026-04-02 post-review closeout is complete in the working tree.**
  The Phase 7.5 viewer build regression was repaired (`TerritoryMap` state/effect restoration, stale `useCallback` import removed, duplicate `package.json` test key removed). Audit C-13 is now closed in code instead of bundle-only masking: sequential narration no longer writes LLM-generated `arc_summary` text back onto live `GreatPerson` state, and regression coverage now asserts the live object remains unchanged. Audit H-5 is now aligned end-to-end: long-range capability routes can still exist for route discovery/events, but treasury trade income and goods-route batching now filter to civ pairs with an actual adjacent boundary, with targeted regression coverage proving non-adjacent navigation routes no longer mint treasury. Verified commands: `npm run build`, `pytest -q tests/test_narrative.py tests/test_bundle.py tests/test_audit_batch_d.py tests/test_economy_bridge.py tests/test_resources.py tests/test_phase_functions.py tests/test_simulation.py`, and `pytest -q tests/test_arcs.py tests/test_economy.py tests/test_economy_m43a.py tests/test_economy_parity.py`.

- **`M-AF2` tooling trust closeout is complete in the working tree.**
  Hidden legacy `test/` coverage was migrated into canonical `tests/` files and the hidden root was removed. `chronicler.validate` now rejects unknown oracle requests, fails closed on missing required Arrow dependencies, emits explicit `SKIP` reasons, and returns non-zero on invalid/dependency/runtime-error cases. `main.py` now rejects inert flag combinations, logs LLM fallback warnings, and emits canonical `narrative_*_tokens` metadata while preserving deprecated `api_*` aliases. `viewer/src/__fixtures__/sample_bundle.json` was regenerated and Python-side fixture drift checks now gate the legacy viewer contract.
- **`M-AF2` viewer/live trust hardening is verified.**
  `viewer/package.json` now exposes `npm test`, the current viewer lint surface is clean, and `src/chronicler/live.py` now rejects malformed root messages, validates command payload types, and checks `narrate_range` ordering/bounds with structured error responses. Verified commands: `npm test`, `npm run lint`, and `pytest -q tests/test_live.py tests/test_live_integration.py`.
- **Scoped `M-AF3` validate split is complete.**
  `src/chronicler/validate.py` is now a public CLI façade plus backwards-compatible re-export surface, `src/chronicler/validation_io.py` owns bundle/sidecar loading + dependency preflight, and `src/chronicler/validation_oracles.py` owns oracle algorithms + per-oracle runners. Plan record: `docs/superpowers/plans/2026-04-01-m-af3-validate-structural-split.md`.
- **Focused post-split verification is green.**
  `pytest -q tests/test_validate.py tests/test_analytics.py tests/test_shadow_oracle.py tests/test_main.py tests/test_bundle.py tests/test_agent_bridge_legacy_migration.py tests/test_curator_legacy_migration.py tests/test_narrative_legacy_migration.py tests/test_infrastructure_legacy_migration.py tests/test_live.py tests/test_live_integration.py` PASS.
- **Repo-level note:** full discovered `pytest -q` now resolves to `2308 passed, 4 skipped`.
- **M36 regression harness follow-up is closed.**
  `tests/test_m36_regression.py` was the last red discovered Python test, but the failure was a stale cross-mode assertion rather than a new runtime regression: the test still compared hybrid treasury against `--agents=off` treasury after the post-M54b off-mode economy freeze, and its Rust-extension stub logic was order-dependent. The harness now prefers the real extension when available, mirrors the production off-mode ecology/politics runtime wiring, binds the hybrid bridge to the same world instance being advanced, and compares cross-mode stability instead of treasury.
- **Post-audit trust follow-ups are closed.**
  `chronicler.validate` now errors on nonexistent batch paths instead of reporting `SKIP/no_bundles`, `validation_io` only raises missing-`pyarrow` dependency errors for `needs` / `cohort` when Arrow sidecars are the actual blocker, and `live.py` now validates nested `batch_start` config fields up front so malformed payloads return structured `batch_error` responses instead of crashing the batch thread before its exception handler.
- **M58b closeout is complete and merged on `main` at `023d61d` (`fix(m58b): close trade convergence gate`).**
- **Hybrid oracle observability is now fail-fast:** `reconstruct_economy_result(..., require_oracle_shadow=True)` rejects stale-extension schemas instead of silently zero-filling oracle columns.
- **Merchant planning now respects the oracle planning signal end-to-end:** Python exports `merchant_route_margin`, Rust FFI falls back to realized margin only when the planning column is absent, and merchant routing / market attractors now consume the planning field directly.
- **Staged convergence gate (2026-03-30):**
  smoke PASS at `output/m58b_gate_smoke_routefix` with `15/20` passing seeds (`75.0%`), tail guard PASS, conservation PASS.
  full PASS at `output/m58b_gate_full_routefix` with `154/200` passing seeds (`77.0%`), tail guard PASS, conservation PASS.
- **Validation run on closeout head:** `cargo test --test test_merchant --test test_spatial --quiet`, `cargo test --test test_economy --quiet`, `pytest -q tests/test_agent_bridge.py tests/test_economy_bridge.py tests/test_m58b_gate.py tests/test_merchant_mobility.py`, and `pytest -q tests/test_oracle_gate.py` all PASS.
- **Operational note:** use `.venv\\Scripts\\python.exe` consistently when rebuilding/running hybrid validation (`maturin develop --release` in `chronicler-agents/`), or Python may load a stale `chronicler_agents` extension.
- **Post-gate `M-AF1` follow-up in working tree:** agent-event `belief` now survives the Rust `tick()` event batch, Python `AgentEventRecord`, and `agent_events.arrow` sidecar, which restores martyrdom filtering on real death events instead of only dict-shaped test fixtures.
- **Focused follow-up validation:** rebuilt the extension with `.venv\\Scripts\\python.exe -m maturin develop --release`, then ran `pytest -q tests/test_agent_bridge.py tests/test_religion.py tests/test_bundle.py`, `pytest -q tests/test_persecution.py`, and `cargo test --quiet` in `chronicler-agents/`; all PASS.
- **`M59a` is now merged on `main` at `f4df802` (`fix(m59a): harden admission and diagnostics`).**
- **Merged `M59a` scope:** packet slots now live on `AgentPool`, the knowledge phase runs at `0.95`, merchants emit trade packets on arrival, and bundle metadata now carries `knowledge_stats` with per-type created/transmitted counters plus live age / hop summaries.
- **`M59a` validation on merge head:** after rebuilding the extension with `maturin develop --release`, `cargo test --test test_knowledge --test test_merchant --quiet` PASS and `pytest -q tests/test_m59a_knowledge.py tests/test_agent_bridge.py::TestBridgeResetAndEventFallback::test_reset_clears_gini_and_cached_state tests/test_merchant_mobility.py` PASS.
- **`M59b` is now merged on `main` at `d9baf0a` (`style(m59b): fix indentation in threat penalty block`).**
- **Merged `M59b` scope:** merchants use packet-gated route planning (trade packets gate cross-region destination candidates, with counted oracle bootstrap fallback for empty usable sets). Migration avoids threatened adjacent destinations via threat-packet penalties. Four consumer diagnostics counters on `KnowledgeStats` (`merchant_plans_packet_driven`, `merchant_plans_bootstrap`, `merchant_no_usable_packets`, `migration_choices_changed_by_threat`) plumbed through tick.rs → ffi.rs → Python normalization. Local trade observation broadened to idle/loading merchants with arrival-turn dedup. Anti-omniscience enforced: no oracle fallback when packets exist but are unprofitable.
- **`M59b` validation on merge head:** 762 Rust tests pass (2 skipped), 2242 Python tests pass (4 skipped). `--agents=off` verified to emit no knowledge metadata. Phoebe-equivalent review completed with no blocking findings.
- **Deferred from `M59b` (by design):** loyalty coupling (requires `source_civ` on packets), religious signal consumers (producer-only), packet layout expansion. These belong in future milestones with deliberate provenance semantics.
- **Residual polish:** no dedicated `TRIP_PHASE_LOADING` unit test for local trade observation (idle and transit are covered; loading path is structurally identical to idle in the `is_trade_eligible` branch).
- **Next targets:** M44 (API narration), M45 (Character Arcs), M47 (Tuning Pass) per CLAUDE.md.
- **Phase 7.5 roadmap refresh landed (doc-only planning lock):** `docs/superpowers/roadmaps/chronicler-phase75-viewer-roadmap.md` now records the current implementation recommendation for when viewer work reactivates after `M61b`: Tauri 2 as the canonical client, React 19 retained unless M62b benchmarks prove otherwise, PixiJS for the map surface, and a Rust/Tauri query-oriented data plane instead of browser-side heavy bundle parsing.
- **Phase 7.5 still remains dormant until `M61b` freeze:** the roadmap refresh is guidance only. Remaining follow-up stays the same: accepted large fixture, frozen export surface, named owners for `M62a/M62b/M62c`, and the React-vs-Solid benchmark gate during `M62b` rather than as a pre-activation blocker.
- **Linked Phase 7.5 execution docs tightened:** `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md` and `docs/superpowers/plans/2026-03-24-m62a-preactivation-prep.md` now align with the roadmap's Tauri-first, browser-fallback-limited interpretation of `M62a`, and `docs/superpowers/plans/2026-03-30-m62b-preactivation-prep.md` now captures the intended `M62b` execution model, merge gate, and benchmark-driven React-vs-Solid decision path.
- **Phase 7.5 design synthesis folded into docs (doc-only):** the 2026-03-31 mockup pass is now reflected in the roadmap and prep/spec docs as execution guidance: one reusable shell anchored by Overview, dark cartographic analytics as the primary mode, Character/Trade/Campaign treated as shell variants instead of bespoke layouts, and explicit contract pressure on header/timeline/chronicle/inspector data families.
- **Phase 7.5 entry-flow guidance added (doc-only):** the roadmap now explicitly treats setup/lobby, batch/interestingness ranking, and direct run-to-viewer handoff as part of the intended product front door, rather than assuming Phase 7.5 starts only after a user manually opens an existing bundle.
- **Standalone GPT-5 Phase 7.5 prototype pass added (recording/demo only):** `prototype/gpt5/` now contains a self-contained HTML/CSS/JS viewer prototype with one reusable shell spanning setup, run progress, overview, character detail, trade diagnostics, campaign/validation, and batch-ranking handoff, plus autoplay/manual walkthrough controls for browser capture.
- **Prototype scope note:** this pass is intentionally front-end only and does not integrate with the dormant React viewer runtime, bundle v2 loading, or the planned Tauri/Rust data plane.
- **Prototype follow-up still open:** if this shell direction is accepted, the visual/system decisions need to be ported into the actual `viewer/` milestone track once M61b reactivates Phase 7.5 implementation.
- **Phase 7.5 viewer implementation pass started in the real React app (2026-03-31):** `viewer/src/components/phase75/` now holds a first reusable shell that keeps one app family across `Setup`, `Progress`, `Overview`, `Character`, `Trade`, `Campaign`, and `Batch Lab`, with the map-first center canvas, top metadata header, timeline rail, chronicle/event left rail, validation ribbon, and right inspector wired as shared primitives rather than per-mode layout forks.
- **Phase 7.5 batch/front-door handoff is now partially live in the runtime:** `viewer/src/App.tsx` routes setup/live/batch/viewer surfaces through the shared shell, `src/chronicler/analytics.py` now emits ranked `run_summaries` in batch reports (`report_schema_version=2`), and `src/chronicler/live.py` now supports `batch_load_bundle` so Batch Lab can open a ranked result directly into the viewer shell without a separate page.
- **Focused validation on the implementation pass:** `python -m pytest tests/test_analytics.py tests/test_live_integration.py` PASS (`43 passed`), and `npm run build` PASS in `viewer/`.
- **M-AF2 viewer trust hardening landed:** `viewer/package.json` now exposes `npm test`, the current viewer lint surface is clean, and `src/chronicler/live.py` now rejects malformed root messages, validates command payload types, and checks `narrate_range` ordering/bounds. Focused live-mode pytest coverage is green.
- **Still intentionally unfinished in this pass:** shell polish/motion, lighter archive presentation, chunk-splitting/perf cleanup, and the deeper Tauri/Rust Phase 7.5 data-plane work remain deferred; this is a cohesion/flow implementation pass, not the final production polish pass.
- **Gotcha for follow-up work:** Batch Lab `tech_advancement_count` summaries are intentionally derived from actual advancement event names (`tech_advancement`, legacy `tech_advance`) rather than any `tech*` event, so later summary refinements should preserve that semantic or rename the metric.

---

## 2026-03-29 Audit Follow-up (Dedicated Pass)

- Completed a dedicated hardening/closure pass against `docs/superpowers/audits/2026-03-29-full-codebase-audit.md`.
- Closed remaining concrete bugs:
  - `STAT_FLOOR` divergence removed: `StatAccumulator` now uses `utils.STAT_FLOOR` (single floor source).
  - `agent_bridge.py` silent exception sites replaced with explicit exception logging + safe fallbacks (relationship stats, household stats, snapshot aggregates, sidecar outputs, civ realignment flows).
  - Schism civ-origin monkey patch removed: `fire_schism(..., civ_origin=...)` now receives origin explicitly (no `_civ_id` transient mutation on civ models).
  - Treasury tax truncation bias fixed via deterministic fractional carry (`world._treasury_tax_carry`).
  - `apply_stockpile_cap()` no longer destroys stockpile in zero-pop regions.
  - Faction robustness fixes: zero-sum normalization guard, clergy win detection wiring, 4-faction power-struggle threshold retune, deterministic `FUND_INSTABILITY` target ranking.
  - Event aggregation window mismatch fixed (`AgentBridge._event_window` now `maxlen=20`, matching economic boom horizon).
  - Dead temp list removed in `check_twilight_absorption` (`to_remove` no-op cleanup).
- Regression/tests:
  - Full Python suite PASS: `2209 passed, 4 skipped`.
  - New tests added for fractional tax carry, clergy win detection, zero-sum normalization handling, fund-instability target ranking, and martyrdom input-shape compatibility.

## Merged Milestones

### M-AF1: Runtime Correctness & Safety — merged (`effc67f`)

- 17 runtime correctness bugs fixed from dual-model audit (GPT-5 + Opus 4.6).
- 18 commits on `m-af1-runtime-correctness` branch.
- Python fixes: governing cost truncation (#6), black market region scan (#16), conquest_conversion_active clearing (#14), severity multiplier gaps (#9), resolved-action bookkeeping (#3), TRADE route check (#2), war_start_turns population (#4), federation defense wiring (#5), martyrdom decay (#11), martyrdom filtering (#12), rewilding threshold (#13), guard-shock verification (#1), vassalization wiring (#15), federation/vassalization interaction fix.
- Rust fixes: schism conversion wiring (#10), zero-agent writeback (#7), promotions civ_id (#8), replace_social_edges safety (#17).
- 200-seed regression gate PASS: 0 crashes, directional shifts all expected (pop -15%, mil -5%, econ -3%, culture -4%, stability -0.4%, treasury -4.5%). Dead civs unchanged (608 vs 608).
- Test counts: Python 2270 passed / 1 failed (M36 threshold, pre-existing) / 4 skipped. Rust 769 passed / 0 failed / 2 ignored.
- Behavior shift note: `docs/superpowers/audits/m-af1-behavior-shift-note.md`

### M59b: Perception-Coupled Behavior — merged (`d9baf0a`)

- Packet-gated merchant route planning: when usable nonlocal trade packets exist, only packet-known destinations are candidates. Oracle fallback fires only when the usable set is empty (bootstrap).
- Anti-omniscience: when packets exist but all gated destinations score below `MIN_TRIP_PROFIT`, the merchant does NOT fall back to oracle.
- Consumer scoring uses `pkt_intensity / 255.0` directly — no second decay layer (M59a substrate already decays per turn and attenuates per hop).
- Local trade observation broadened to idle/loading merchants (not just arrivals), with `arrived_this_turn` dedup to prevent dropped-packet diagnostic noise. Transit merchants excluded.
- Threat-aware migration: `MAX_THREAT_PENALTY` (0.20) × packet strength penalizes adjacent migration targets. Strongest-packet-wins (no stacking). Own-region and non-adjacent threats excluded. No urgency effect.
- Four consumer diagnostics counters on `KnowledgeStats`, accumulated across merchant mobility phase (0.9) and behavior decisions, merged in `tick.rs`, exposed via `ffi.rs::get_knowledge_stats()`, normalized in Python `agent_bridge.py`.
- Deferred: loyalty coupling (needs `source_civ`), religious signal consumers, packet layout expansion.
- Test counts: 762 Rust, 2242 Python. 18+ new M59b-specific tests covering routing, bootstrap, anti-omniscience, threat penalties, determinism, slot-order independence, divergence from oracle, local observation seeding, and `--agents=off` negative test.

### M58b: Trade Integration & Macro Convergence — merged (`023d61d`)

- Hybrid runtime now hard-fails on missing oracle observability columns (`oracle_imports_*`, `oracle_margin`, `oracle_food_sufficiency`) instead of silently falling back to zeros.
- Oracle planning margin now crosses the Python/Rust boundary explicitly via `merchant_route_margin`; route selection and market attraction consume that planning signal directly, preventing realized-margin feedback from spawning post-oracle trips.
- Merchant cargo capacity is aligned with the abstract economy budget (`MERCHANT_CARGO_CAP = CARRY_PER_MERCHANT = 1.0`) to remove baked-in realized volume surplus.
- Gate semantics now treat windows with no trade activity on either side as neutral, while still failing one-sided activity and enforcing the original price/volume/food thresholds when comparison data exists.
- Canonical closeout artifacts:
  smoke gate: `output/m58b_gate_smoke_routefix`
  full gate: `output/m58b_gate_full_routefix`

### M36: Cultural Identity — merged, sticky flag fixed

- `_culture_investment_active` sticky flag fixed in `da0cb2d`. Pattern: read into local before return, clear attribute, use local in batch. Dead cleanup code after return deleted.

### M38a: Temples & Clergy Faction — merged

- `a199c40` — tithe truncated to int
- `0bee24e` — temple conquest lifecycle wired into production code

### M38b: Schisms, Pilgrimages & Persecution — merged (`67f1353`)

- All Phoebe review items (B-1 through G-4) resolved in implementation.
- Rust test RegionState initializers updated for M38b fields (`58f868d`, `3ebb62b`).
- Secession modifier and `--agents=off` compatibility verified (`9431276`).

### M39: Family & Lineage — merged

- Dynasty detection, extinction, and split wired into AgentBridge (`a235e68`).
- Dynasty context added to narrative prompt (`9e4b20c`).
- Dynasty integration test added (`20c9835`).
- Design decisions: inherit at birth (drift handles assimilation), parent-child only (no grandparent chain), purely narrative (dynasty_id is hook for future mechanics), Rust owns `parent_id` / Python owns dynasty logic.

### M40: Social Networks — merged

- 18 commits on `feat/m40-social-networks`. 79 tests passing.
- Rust `SocialGraph` with `SocialEdge` types + Arrow FFI (`get_social_edges` / `replace_social_edges`).
- Five formation functions: rivalry, mentorship (rewritten from leader-based to agent-source peers), marriage, exile bond (new), co-religionist (new).
- `dissolve_edges()` with death + belief-divergence rules.
- `form_and_sync_relationships()` coordinator in Phase 10.
- Named character scoring activated in `curate()` (`main.py` + `live.py`).
- Relationship context wired into narration pipeline.
- `character_relationships` removed from `WorldState`, `dissolve_dead_relationships` dead code removed.
- `origin_region` on `GreatPerson`, `relationships` on `AgentContext`.

### M41: Wealth & Class Stratification — merged

- Per-agent `wealth: f32` in Rust SoA pool. Multiplicative decay, MAX_WEALTH clamp.
- Binary `is_extractive()` dispatch for farmer/miner income (replaced by M42 modifier).
- Gini computed Python-side, one-turn lag. Class tension as 4th non-ecological penalty (priority-clamped under 0.40 cap).
- `conquered_this_turn` transient signal for soldier conquest bonus.
- Treasury tax, tithe swap deferred to M42 — now landed.

### M42: Goods Production & Trade — merged

- 5 commits on `m42-goods-production-trade` branch. 42 economy unit tests, 188 Rust tests passing.
- New `economy.py`: 3 categories (Food, Raw Material, Luxury), two-pass pricing (pre-trade for margins, post-trade for signals), log-dampened margin-weighted pro-rata trade allocation.
- Four RegionState FFI signals: `farmer_income_modifier`, `food_sufficiency`, `merchant_margin`, `merchant_trade_income`.
- One CivSignals field: `priest_tithe_share`.
- Rust wealth tick: farmer = `BASE_FARMER_INCOME × modifier × yield`, merchant = `merchant_trade_income`, priest = `PRIEST_INCOME + priest_tithe_share`.
- Satisfaction: `food_sufficiency` penalty outside 0.40 cap, `merchant_margin` replaces `trade_route_count` term.
- M41 deferred integrations landed: treasury tax, tithe base swap, per-priest tithe share.
- `FARMER_INCOME`, `MINER_INCOME`, `MERCHANT_INCOME`, `MERCHANT_BASELINE`, `is_extractive()` removed from Rust.
- `trade_route_count` wired to actual boundary-pair counts (was hardcoded to 0).
- **Deferred:** Analytics price time series extractor (needs bundle format update). 200-seed regression (needs calibration values).

### M43a: Transport, Perishability & Stockpiles — merged

- 17 commits (`14f1eb4`..`4b7adff`). 48 M43a tests + 42 M42 tests = 120 total economy tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-17-m43a-transport-perishability-stockpiles-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-18-m43a-transport-perishability-stockpiles.md`
- `RegionStockpile` model with `dict[str, float]` goods, nested on `Region` (parallels `RegionEcology` pattern).
- Transport cost computation: terrain factors (6 terrains), river discount (0.5×), coastal discount (0.6×), winter modifier (1.5×). Pre-allocation margin reduction in `allocate_trade_flow()`.
- Per-good perishability: transit decay (post-allocation volume attrition), storage decay (per-turn with salt preservation). Salt proportional to salt-to-food ratio, capped at 50%.
- Stockpile sub-sequence in `compute_economy()` (steps 2g-2k): accumulate → food_sufficiency from pre-consumption stockpile → demand drawdown → storage decay → cap.
- `food_sufficiency` source changed from single-turn supply to pre-consumption stockpile (Decision 9). Signal value unchanged ([0.0, 2.0]), backward compatible at equilibrium.
- Conquest stockpile destruction (50% loss) in `_resolve_war_action()`.
- Stockpile initialization in `world_gen.py` (`INITIAL_BUFFER × population`).
- `extract_stockpiles()` analytics extractor.
- Conservation law: `EconomyResult.conservation` tracks production, transit_loss, consumption, storage_loss, cap_overflow. Exact global balance verified in test.
- **No Rust changes.** Entirely Python-side.
- **Key design decisions:** M43 split into M43a (infrastructure) / M43b (behavior) for calibration isolation. Emergent shock propagation via price/stockpile dynamics (no explicit shock state machine — M43b). Category-level pricing unchanged from M42; per-good tracking only for stockpile/decay.
- **Phoebe review passed.** I-1 (per-good decomposition single-slot assumption documented), I-2 (conquest integration gap noted), I-3 (import initialization clarified).

### M43b: Supply Shock Detection, Trade Dependency & Raider Incentive — merged (`f25d68c`)

- 14 commits on `feat/m43b-shock-detection` branch. 36 M43b tests, 252 total relevant tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-17-m43b-shock-detection-trade-dependency-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-18-m43b-shock-detection-trade-dependency.md`
- `EconomyTracker` class with dual EMA (α=0.33) for stockpile and import levels. Instantiated in `main.py`, persists across turns, passed to `run_turn()`.
- `detect_supply_shocks()`: delta trigger (30% drop from trailing avg) + absolute severity gate (`food_sufficiency < 0.8` for food). Non-food uses delta-only severity.
- `classify_upstream_source()`: checks import EMA drop + upstream partner stockpile drop. Returns None for local shocks or embargoes (no fallback attribution).
- 6 new `EconomyResult` fields: `imports_by_region`, `inbound_sources`, `stockpile_levels`, `import_share`, `trade_dependent`, plus `CATEGORY_GOODS` constant.
- `inbound_sources` tracking merged into existing trade flow accumulation loop (~5 lines).
- Trade dependency: `import_share = food_imports / max(food_demand, 0.1)`, threshold 0.6.
- Raider WAR modifier: scaled additive (`RAIDER_WAR_WEIGHT * min(overshoot, RAIDER_CAP)`), placed after holy war bonus, before streak-breaker and 2.5x cap. Stacks with holy war intentionally (Decision 8).
- 7 new `CAUSAL_PATTERNS` entries including `supply_shock → supply_shock` self-link for cascade chains.
- Narration: `economy_result` threaded through `narrate_batch` → `build_agent_context_for_moment()`. Early return relaxed to allow economy-source events. `build_agent_context_block()` renders trade dependency and shock context.
- `ShockContext` BaseModel, `shock_region`/`shock_category` optional fields on `Event` (structured metadata, no string parsing).
- `CivThematicContext.trade_dependency_summary` field added but population deferred — `CivThematicContext` is never constructed in current codebase (dead infrastructure).
- 2-turn transient signal test for `world._economy_result` (NB-2 from Phoebe review).
- **Phoebe implementation review:** B-1 (economy_result threading), NB-1 (CivThematicContext deferral documented), NB-2 (transient test added). All resolved in `2b22be3`.
- **No Rust changes.** Entirely Python-side.
- **Calibration constants:** `SHOCK_DELTA_THRESHOLD=0.30`, `SHOCK_SEVERITY_FLOOR=0.8`, `TRADE_DEPENDENCY_THRESHOLD=0.6`, `RAIDER_THRESHOLD=200.0` [CALIBRATE], `RAIDER_WAR_WEIGHT=0.15`, `RAIDER_CAP=2.0`. All `[CALIBRATE]` for M47.

### M44: API Narration Pipeline — merged (`dce271c`)

- 8 commits on `feat/m44-api-narration` branch. 15 new tests, all passing.
- **Spec:** `docs/superpowers/specs/2026-03-18-m44-api-narration-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-18-m44-api-narration.md`
- `--narrator api|local` CLI argument with validation (5 conflict checks above `_run_narrate()` early return).
- `create_clients()` gains `narrator` parameter — returns `AnthropicClient` when `"api"`.
- `AnthropicClient` token tracking: 3 accumulators (`total_input_tokens`, `total_output_tokens`, `call_count`), console summary, bundle metadata (`narrator_mode`, `api_input_tokens`, `api_output_tokens`).
- `execute_run()` API path: noop per-turn narrator (extends existing `_simulate_only` pattern), reflections gated off entirely (`not _api_mode and should_reflect(...)`), post-loop curator + `narrate_batch()` before `agent_bridge.close()`.
- `gap_summaries` threaded to both `compile_chronicle()` and `assemble_bundle()`.
- First-failure warning in `narrate_batch()` — `logger.warning` on first exception per call, per-call local variable (not instance attr).
- Bug fix: `_run_narrate()` reads `events_timeline` key from bundles (was `events`, which didn't match `assemble_bundle()`'s output key).
- Pre-existing test mock fixed: `test_complete_calls_anthropic_api` now includes `usage` fields (prevents MagicMock `__radd__` corruption of accumulators).
- **Phoebe implementation review passed.** NB-1 (batch token bleed across seeds — low urgency edge case), NB-2 (usage mock — fixed in `a559c2b`).
- **No Rust changes.** Entirely Python-side. No simulation determinism impact.
- **M44 deliverables still pending:** 20-seed quality comparison (post-implementation, controlled pipeline). Manual evaluation task.

### M45: Character Arc Tracking — merged (`6c997f3`)

- 10 commits on M45 implementation. Arc classifier with 8 archetypes, deeds population at 9 mutation points, curator scoring (+1.5 arc, +2.5 completion), arc summaries via API follow-up calls, dead character filter relaxed.
- **Spec:** `docs/superpowers/specs/` (M45 spec)
- **Plan:** `docs/superpowers/plans/` (M45 plan)

### M47: Phase 6 Tuning Pass — Tier A + M47a + M47b-prep merged (`d99b178`)

- 1 commit, 36 files changed, 835 insertions, 225 deletions. 532 Python tests pass, 188 Rust tests pass, 2 pre-existing failures.
- **Spec:** `docs/superpowers/specs/2026-03-19-m47-tuning-pass-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-19-m47-tuning-pass.md`
- **Tier A:** Civ-removal fix — `world.civilizations.remove(civ)` deleted from `check_twilight_absorption()`. Dead civs stay in list (`len(regions)==0` convention). Dead-civ guards at 13 critical loop sites + `_write_back()`.
- **M47a consumer wiring:** 8 multipliers wired (all default 1.0, no behavioral change). Python: K_AGGRESSION_BIAS (action_engine), K_TRADE_FRICTION (economy `friction_multiplier` param), K_RESOURCE_ABUNDANCE (ecology yields), K_SECESSION_LIKELIHOOD (politics prob), K_TECH_DIFFUSION_RATE (tech cost division). Rust FFI: `cultural_drift_multiplier` and `religion_intensity_multiplier` as CivSignals fields, wired in culture_tick.rs/conversion_tick.rs via tick.rs lookup.
- **M47a severity cap:** `get_severity_multiplier(civ, world)` composes base × tuning, capped at 2.0. 11 existing call sites updated to pass `world`. `world` param is optional (defaults to base-only for backward compat).
- **M47a severity fix:** 25 missing severity sites fixed across 9 files (politics 11, simulation 4, action_engine 3, leaders 2, climate/culture/ecology/emergence/succession 1 each). 7 new tests in `tests/test_severity.py`.
- **M47a tatonnement:** 3-pass Walrasian price iteration in `compute_economy()`. Damping=0.2, per-pass clamp [0.5, 2.0], convergence threshold 0.01. All [CALIBRATE] for M47c.
- **M47a Pydantic cleanup:** Removed misleading `ge=/le=` Field constraints from `models.py` (silently ignored with `validate_assignment=False`). Tests expecting validation-time rejection removed.
- **M47b-prep:** Gini on CivSnapshot (populated from `AgentBridge._gini_by_civ` via `enumerate` index). `CivThematicContext` deleted (dead infrastructure). `NarrationContext.civ_context` field removed. `region_map` cached property on WorldState via `PrivateAttr` (inline replacements deferred). 9 analytics extractors added.
- **Multiplier validation:** `load_tuning()` rejects multiplier values ≤ 0.
- **Bit-identical:** `--agents=off` determinism verified at default multipliers.
- **Python-side consumers also wired:** `culture.py` (drift), `religion.py` (conversion rate, schism threshold inverse scaling with 0.10 floor, persecution intensity).

### M48: Agent Memory — merged (`136c93e`)

- 14 commits on `feat/m48-agent-memory` branch (12 implementation + 1 Phoebe fix + 1 test gap fill). 241 Rust tests, 48+ Python tests.
- **Spec:** `docs/superpowers/specs/2026-03-19-m48-agent-memory-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-19-m48-agent-memory.md`
- **Phoebe reviews:** Plan review (5 blocking fixes pre-implementation), implementation review (1 blocking fix: conquest source_civ), final pass (clean).
- **Rust (chronicler-agents):**
  - `memory.rs` (new, 389 lines): MemoryEventType enum (14 types), MemoryIntent, gate bits, decay hot path (integer-only), eviction (min-intensity), half-life conversion, compute_memory_satisfaction_score(), compute_memory_utility_modifiers(), agents_share_memory() (M50 interface), write_all_memories(), clear_memory_gates().
  - `pool.rs`: 7 SoA memory fields (50 bytes/agent). Zero-init in both spawn branches.
  - `agent.rs`: ~45 calibration constants ([CALIBRATE M53]), 2 STREAM_OFFSETS reserved (900, 1300).
  - `tick.rs`: Memory decay first, 11 intent collection sites across all tick phases, parent-to-child reverse index for DEATH_OF_KIN, consolidated write last.
  - `satisfaction.rs`: `memory_score` field on SatisfactionInputs, 5th-priority penalty clamping inside 0.40 cap.
  - `behavior.rs`: Memory utility modifiers wired into evaluate_region_decisions() (7 event types → rebel/migrate/switch/stay).
  - `region.rs`: 3 transient boolean fields (controller_changed_this_turn, war_won_this_turn, seceded_this_turn).
  - `ffi.rs`: 3 signal columns parsed (both init + update branches), get_agent_memories() pymethod.
- **Python:**
  - `models.py`: 4 GreatPerson fields (mule, mule_memory_event_type, utility_overrides, memories).
  - `agent_bridge.py`: 3 transient signal columns in build_region_batch() with clear-before-return, Mule detection in _process_promotions() (7% probability, 9 event mappings), memory sync per tick.
  - `action_engine.py`: get_mule_factor() with 25-turn window + 10-turn fade, Mule weight loop (after peace dividend, before streak-breaker, before 2.5x cap), 0.1x suppression floor.
  - `politics.py`: _seceded_this_turn signal in check_secession().
  - `narrative.py`: MEMORY_DESCRIPTIONS (12 templates), render_memory() with vivid/fading descriptors, Mule context rendering.
- **Key design decisions:** Consolidated write phase (no same-turn feedback), conquest source_civ = conquering civ (not agent's own), memory inside 0.40 cap as 5th priority, multiplicative Mule boost.
- **Phoebe observations (non-blocking):** Promotion intent deferred (Python-side, no Rust write path), Victory memories not civ-filtered (minor — losers in region also get Victory), `default_decay_factor()` recomputes powf/ln per write (cold-path acceptable).

### M49: Needs System — merged (`ae05b92`)

- 8 commits on `feat/m49-needs-system` branch. 268 Rust tests, 6 Python tests, all passing.
- **Spec:** `docs/superpowers/specs/2026-03-20-m49-needs-system-design.md` (658 lines, 13 sections)
- **Plan:** `docs/superpowers/plans/2026-03-20-m49-needs-system.md` (1056 lines, 8 tasks)
- **Brainstorming:** 5 design questions, each individually Phoebe-reviewed + holistic cross-decision review. 3 blocking issues found and resolved in holistic review (utility stacking cap, needs-as-independent-trigger, missing architectural decisions).
- **Rust (chronicler-agents):**
  - `needs.rs` (new): NeedUtilityModifiers struct, decay_needs (linear subtraction), restore_needs (proportional to deficit), clamp_needs, update_needs entry point, compute_need_utility_modifiers (threshold-gated), social_restoration pre-M50 proxy.
  - `pool.rs`: 6 SoA f32 fields (24 bytes/agent). Spawn at STARTING_NEED=0.5 in both branches.
  - `agent.rs`: 37 calibration constants ([CALIBRATE M53]) — 6 decay, 6 threshold, 6 weight, 16 restoration, 3 infrastructure.
  - `tick.rs`: `update_needs()` inserted between wealth_tick and update_satisfaction (step 0.75).
  - `behavior.rs`: `personality_modifier` made `pub`. Need utility modifiers wired after M48 memory modifiers, before NEG_INFINITY gates. Per-channel NEEDS_MODIFIER_CAP=0.30. Autonomy deficit accelerates loyalty drift (multiplier on negative drift only).
  - `ffi.rs`: `get_agent_needs(agent_id)` pymethod returning `Option<(f32,f32,f32,f32,f32,f32)>`.
- **Python:**
  - `models.py`: `GreatPerson.needs: Optional[dict] = None` (None in aggregate mode — no serialization diff).
  - `agent_bridge.py`: Needs sync in hybrid branch after memory sync. 6-tuple → named dict.
  - `narrative.py`: NEED_DESCRIPTIONS (6 templates), render_needs() with LOW/satisfied labels, wired into build_agent_context_for_moment + build_agent_context_block.
- **Key design decisions:** 6 needs (sharp Safety/Autonomy split), hybrid restoration (binary for bools, proportional for f32s), uniform linear decay, per-agent restoration conditions for diversity, threshold-gated utility modifiers `(THRESHOLD - need).max(0) * WEIGHT`, needs can independently trigger rebellion (explicit decision), needs-only cap 0.30 (does not retroactively affect M38b/M48), Autonomy uses civ_affinity (political, not ethnic), memory-needs coupling deferred to M53.
- **M53 calibration flags (10):** persecution triple-stacking, famine double-counting, needs-only rebellion rate (<5%), need activation fraction (peacetime 10-20%, crisis 40-70%), migration sloshing, sawtooth oscillation, duty cycle per need, social proxy adequacy, negative modifier trapping, Autonomy assimilation loop.

### M50a: Relationship Substrate — merged (`a4d68f8`)

- 12 commits on `feat/m50a-relationship-substrate` branch + 2 Phoebe fix commits.
- **Spec:** `docs/superpowers/specs/2026-03-20-m50a-relationship-substrate-design.md`
- **Rust (chronicler-agents):**
  - `relationships.rs` (new): BondType enum (Mentor=0..Grudge=7), SoA helpers (find_relationship, write_rel, swap_remove_rel, find_evictable, upsert_directed, upsert_symmetric), is_protected/is_positive_valence predicates.
  - `pool.rs`: 5 SoA relationship fields (65 bytes/agent). Sentinel init (bond_types = [255; 8]).
  - `tick.rs`: Kin auto-formation at birth (form_kin_bond), sentiment drift at phase 0.8, stale-parent-slot fix (ids check in birth loop).
  - `ffi.rs`: apply_relationship_ops (4 op types via Arrow batch), get_agent_relationships (per-agent FFI), get_social_edges (M40 projection), replace_social_edges (deprecated shim with diff-based translation), kin_bond_failures counter with PyO3 getter.
  - `agent.rs`: 8 drift/kin constants, RELATIONSHIP_STREAM_OFFSET=1100 registered in collision test.
- **Python:**
  - `models.py`: `GreatPerson.agent_bonds: Optional[list] = None`
  - `agent_bridge.py`: apply_relationship_ops wrapper, agent_bonds sync in per-GP loop.
- **Key design decisions:** Single truth source (per-agent SoA, not SocialGraph). M40 `get_social_edges()` is a projection, `replace_social_edges()` is a deprecated diff-based shim. Kin-only Rust-native formation; all other formation via Python ops (transitional — M50b changes this). UpsertSymmetric(Kin) explicitly blocked. `formed_turn` preserved on re-upsert.

### M50b: Relationship Emergence & Cohorts — merged (`50301ea`)

- 12 commits on `feat/m50b-relationship-emergence` branch (8 implementation + 3 review fixes + 1 spec/plan docs). 376 Rust tests, 17/18 Python narrative tests (1 pre-existing failure).
- **Spec:** `docs/superpowers/specs/2026-03-20-m50b-relationship-emergence-cohorts-design.md` (Phoebe-reviewed, 2 passes)
- **Plan:** `docs/superpowers/plans/2026-03-20-m50b-relationship-emergence-cohorts.md`
- **Phoebe implementation review passed.** B-1 (death dissolution counter) and B-2 (char_names scope) fixed. User review found 3 additional issues: `since_turn` key mismatch, dissolved edges dropped in M50b path, directed capacity prefilter — all fixed.
- **Rust (chronicler-agents):**
  - `formation.rs` (new, ~1600 lines): `cultural_similarity()`, `compatibility_score()`, 6 per-type gate functions, `FormationCandidate`/`FormationStats` structs, `formation_scan()` with staggered cadence (hash-based shuffle, pair iteration, early rejection cascade, triadic closure, per-agent/per-region budgeting), `death_cleanup_sweep()`, `belief_divergence_cleanup()`, `mix_hash()`, `has_shared_positive_contact()`, `build_belief_census()`, `evaluate_pair()` (returns Vec for multi-bond-per-pair), `attempt_bond()`.
  - `tick.rs`: Death cleanup at phase 5.1 (post-demographics), formation scan at phase 8 (last operation before return). Return type changed to 3-tuple `(Vec<AgentEvent>, u32, FormationStats)`.
  - `ffi.rs`: `get_relationship_stats()` (19 keys: 5 formation counters + 1 kin delta + 4 distribution metrics + 8 bond_type_counts + 1 death dissolution), `get_all_relationships()` (Arrow RecordBatch bulk export).
  - `agent.rs`: 27 formation constants + `LIFE_EVENT_DISSOLUTION: u8 = 6`.
  - `pool.rs`: `synthesis_budget: Vec<u8>` dormant field (1 byte/agent).
  - `memory.rs`: `agents_share_memory_with_valence()` (signed intensities for Grudge gate).
  - `needs.rs`: Social-need blend `(1-α)*proxy + α*bond_factor` with `SOCIAL_BLEND_ALPHA=0.0` (early return, zero perf cost).
  - `tests/test_m50b_formation.rs`: 14 integration tests (staggered scheduling, friend formation, cap enforcement, determinism, transient signal 2-turn test, death cleanup, belief divergence).
- **Python:**
  - `agent_bridge.py`: `rust_owns_formation = True`, dissolution event collection (event_type=6 → `dissolved_edges_by_turn`).
  - `simulation.py`: `form_and_sync_relationships()` gated off when `rust_owns_formation`.
  - `main.py`: `--relationship-stats` CLI flag (parsed but not wired to consumer).
  - `narrative.py`: `rel_type_names` widened for Kin/Friend/Grudge, M50b bond source swap from `gp.agent_bonds` with sentiment descriptors (deep/strong/mild/fading), unnamed target filtering, dissolved edges consumed in M50b path.
  - `analytics.py`: `extract_relationship_metrics()` extractor.
- **Key design decisions:** Deterministic formation (no RNG consumed, stream offset 1100 reserved for M53 probabilistic). Multi-bond-per-pair (Friend + CoReligionist can form simultaneously). Directed bonds only need source-side capacity. Formation scan uses post-demographics alive_slots. `evaluate_pair()` returns Vec (all eligible types), not Option (first match). Dissolution events carry bond_type in `target_region` field (dead target's agent_id unavailable — O-3 deferred).
- **Phoebe observations (non-blocking):** O-1 (`check_friend` evaluates compatibility before shared memory — negligible cost difference), O-2 (`id_to_slot` rebuilt per-region instead of hoisted — minor perf), O-3 (dissolution events lack dead target's agent_id — known plan issue #2), O-4 (`--relationship-stats` flag not wired to consumer — deferred).

### M55a: Spatial Substrate — implemented on `codex/m54a-rust-ecology`

- 10 commits on `codex/m54a-rust-ecology` branch. 48 Rust tests, 2 Python tests, 513 total Rust tests passing, 32 Python bridge tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-24-m55a-spatial-substrate-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-24-m55a-spatial-substrate.md`
- **Rust (chronicler-agents):**
  - `spatial.rs` (new): SpatialGrid (10x10 uniform hash), RegionAttractors (8-slot attractor model with occupation affinity), drift computation (attractor + density + repulsion forces), two-pass update, migration reset, newborn placement, SpatialDiagnostics.
  - `sort.rs` (new): morton_interleave, radix_sort_u64, sort_by_region, sort_by_morton, sorted_iteration_order with SPATIAL_SORT_AGENT_THRESHOLD activation.
  - `pool.rs`: x, y SoA fields (8 bytes/agent), init in new()/spawn(), serialized in to_record_batch().
  - `region.rs`: is_capital (bool), temple_prestige (f32) fields.
  - `ffi.rs`: Spatial state on AgentSimulator (grids, attractors, diag), spatial init on first set_region_state(), weight update every call, get_spatial_diagnostics() getter, new region columns parsed in both simulators.
  - `tick.rs`: tick_agents extended with spatial_grids + attractors + diag params. Step 4.5 inserted: migration reset (4.5a), grid rebuild (4.5b), two-pass drift (4.5c). Parent position snapshot before death pass, newborn placement after spawn.
  - `agent.rs`: final gated calibration restored `INITIAL_AGE_STREAM_OFFSET` to 1400 and moved `SPATIAL_POSITION/DRIFT` to 2000/2001 so the M53/M54 demographic baseline stayed comparable while spatial jitter kept a dedicated range.
- **Python:**
  - `agent_bridge.py`: is_capital and temple_prestige columns in build_region_batch().
  - `analytics.py`: extract_spatial_diagnostics() extractor.
- **Key design decisions:** Attractor positions static (computed once from seed), weights dynamic (recomputed from RegionState each tick). Two-pass drift (snapshot then compute then write) for determinism. Spatial code no-op when attractors empty (backward compatible). Sort threshold at 100K agents. All constants [CALIBRATE M61b].
- **Deferred:** Market attractor (reserved, inactive until M58a). Disease proximity spreading. Formation behavior change. Bundle schema changes.

### M55b: Spatial Asabiya — implemented on `codex/m54a-rust-ecology`

- 11 implementation commits on `codex/m54a-rust-ecology` plus final crystallization review fixes. 35 targeted M55b tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-24-m55b-spatial-asabiya-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-24-m55b-spatial-asabiya.md`
- **Python:**
  - `models.py`: `RegionAsabiya` sub-model on `Region`, `asabiya_variance` on `Civilization` and `CivSnapshot`.
  - `simulation.py`: `apply_asabiya_dynamics()` rewritten to compute per-region frontier fractions, apply the gradient frontier formula, and aggregate mean/variance back to civ level after politics and before collapse.
  - `politics.py`, `emergence.py`, `leaders.py`, `scenario.py`, `world_gen.py`: scalar `civ.asabiya` mutation sites migrated to region-broadcast D-policy helpers or initialization sync.
  - `main.py`: `CivSnapshot` export includes `asabiya_variance`.
- **Tests:**
  - `tests/test_spatial_asabiya.py` covers frontier math, weighted aggregation, D-policy routing, phase ordering, convergence, determinism, and scalar-write guards.
  - Existing politics, leaders, and culture tests updated for region-backed asabiya writes.
- **Key design decisions:** Spot mutations broadcast to all owned regions, frontier detection is purely geographic (`different controller OR uncontrolled`), military projection and collapse-variance gameplay hooks are deferred, and conquered regions keep their prior regional asabiya instead of instant assimilation.
- **Crystallization fixes (2026-03-24):** restoration no longer writes a redundant direct `restored_civ.asabiya = 0.8` scalar that is immediately recomputed from region state, zero-pop / dead civs now reset `asabiya_variance` to `0.0`, and the scalar-write guard test now checks `politics.py` too.
- **Final gate recovery (2026-03-25):** canonical 200-seed/500-turn validation now passes again after restoring the initial-age RNG stream to 1400, moving spatial RNG to 2000/2001, raising `MEMORY_SATISFACTION_WEIGHT` to `0.05`, and reducing `FOOD_SHORTAGE_WEIGHT` to `0.08`. Final gate artifact: `output/m55b/gated_age1400_mem05_food08_p24/full_gate/batch_1/validate_all.json`.

### M56a: Settlement Detection — implemented on `feat/m56a-settlement-detection`

- 8 commits on `feat/m56a-settlement-detection` branch. 54 settlement tests, all passing. No Rust changes.
- **Spec:** `docs/superpowers/specs/2026-03-25-m56a-settlement-detection-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-26-m56a-settlement-detection.md`
- **Python:**
  - `models.py`: `SettlementStatus` enum (4 values), `Settlement` model (16 fields with sentinel defaults for candidates), `SettlementSummary` model. `Region.settlements`, `WorldState.dissolved_settlements`/`next_settlement_id`/`settlement_naming_counters`/`settlement_candidates`, `TurnSnapshot` settlement summary fields (7 fields).
  - `settlements.py` (new, ~490 lines): Detection grid (10x10 uniform hash), density filtering (`DENSITY_FLOOR=5`, `DENSITY_FRACTION=0.03`), 8-neighbor connected components (BFS, row-major scan), cluster extraction with centroid computation, two-pass matching (distance gate `MAX_MATCH_DISTANCE=0.25`, age/pass-count priority), lifecycle state machine (candidate → active → dissolving → dissolved), `run_settlement_tick()` entry point with interval gate (`SETTLEMENT_DETECTION_INTERVAL=15`), diagnostics output.
  - `simulation.py`: `force_settlement_detection` parameter on `run_turn()`, `run_settlement_tick()` call between economy stash and Phase 10.
  - `main.py`: `force_settlement_detection=(turn_num == num_turns - 1)` on terminal turn, 7 settlement fields on `TurnSnapshot`, `SettlementSummary` import.
  - `analytics.py`: `extract_settlement_diagnostics()` extractor.
- **Tests:** `tests/test_settlements.py` — 54 tests across 11 test classes: model construction, grid/density/components/clusters, matching (active + candidate), lifecycle (9 transitions), entry point (6 paths), analytics, determinism, save/load round-trip, integration.
- **Off-mode behavior:** `--agents=off` → no agent snapshot → `run_settlement_tick` early-returns with diagnostics `reason="mode_off_no_snapshot"`. TurnSnapshot settlement fields default to 0/[]. Off-mode 30-turn smoke test passes.
- **Hybrid mode:** Not smoke-tested due to pre-existing FFI mismatch (`set_economy_config` AttributeError). Settlement code is fully unit-tested independently.
- **Key design decisions:** Detection is purely spatial (no RNG). Component IDs are region-local (no cross-region collisions). Candidates persist for `CANDIDATE_PERSISTENCE=2` passes before promotion. Inertia cap scales with age+population. Dissolved settlements get tombstone (zeroed lifecycle fields, preserved in `dissolved_settlements` list). Naming counters never reuse IDs.
- **Calibration constants ([CALIBRATE M61b]):** `GRID_SIZE=10`, `DENSITY_FLOOR=5`, `DENSITY_FRACTION=0.03`, `SETTLEMENT_DETECTION_INTERVAL=15`, `MAX_MATCH_DISTANCE=0.25`, `CANDIDATE_PERSISTENCE=2`, `BASE_INERTIA_CAP=3`, `AGE_BONUS_INTERVAL=50`, `POP_BONUS_INTERVAL=100`, `MAX_INERTIA_CAP=10`, `DISSOLVE_GRACE=2`.
- **No Rust changes.** Entirely Python-side.
- **Deferred:** M56b mechanical consumers (`is_urban`, per-agent `settlement_id`, urban/rural effects). Richer narrator integration for settlement events. Calibration follow-up (M61b). 200-seed regression sweep (blocked on hybrid smoke).

### M56b: Urban Effects â€” implementation verified + calibrated pre-merge on `feat/m56b-urban-effects`

- **Spec:** `docs/superpowers/specs/2026-03-26-m56b-urban-effects-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-26-m56b-urban-effects.md`
- **Calibration pass (2026-03-26):**
  - Updated M56b urban constants in `chronicler-agents/src/agent.rs`:
    - `URBAN_SAFETY_RESTORATION_MULT = 0.97`
    - `URBAN_SOCIAL_RESTORATION_MULT = 1.04`
    - `URBAN_FOOD_SUFFICIENCY_MULT = 0.96`
    - `URBAN_WEALTH_RESTORATION_MULT = 1.02`
    - `URBAN_MATERIAL_SATISFACTION_BONUS = 0.034`
    - `URBAN_SAFETY_SATISFACTION_PENALTY = 0.008`
    - `URBAN_CULTURE_DRIFT_MULT = 1.08`
    - `URBAN_CONVERSION_MULT = 1.03`
- **Probe gate (50 seeds / 500 turns / hybrid / sidecar / parallel 24):**
  - Artifact: `output/m56b/gates/tuning_probe_hybrid_p24_sidecar_v6_with_tuning/validate_all.json`
  - Regression PASS (`satisfaction_mean=0.4506`, `rebellion_rate=0.079908`, `migration_rate=0.080581`, `occupation_ok=true`)
- **Full gate (200 seeds / 500 turns / hybrid / sidecar / parallel 24):**
  - Artifact: `output/m56b/gates/full_gate_hybrid_p24_sidecar_tuned/validate_all.json`
  - Oracles: `community PASS`, `needs PASS`, `era PASS`, `cohort PASS`, `artifacts PASS`, `arcs PASS`, `regression PASS`, `determinism SKIP` (no duplicate pairs)
  - Regression metrics: `satisfaction_mean=0.4503`, `satisfaction_std=0.1213`, `migration_rate=0.078388`, `rebellion_rate=0.06929`, `gini_in_range_fraction=0.8404`, `occupation_ok=true`
- **Rust verification:** `cargo nextest run --manifest-path chronicler-agents/Cargo.toml --workspace --all-targets -j 24` -> `632 passed, 2 skipped`
- **Off-mode smoke (non-blocking sanity):** `output/m56b/gates/smoke_off_tuned` completed without runtime errors.

### M57a: Marriage Matching & Lineage Schema — implemented on `m57a-marriage-lineage`

- 17 tasks, 16 implementation commits on `m57a-marriage-lineage`, plus 2 follow-up review/docs commits (`4888d48`, `604205e`). 23 Rust marriage tests + 10 Python dual-parent tests. 639 Rust tests, 2188 Python tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-26-m57a-marriage-lineage-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-26-m57a-marriage-lineage-plan.md`
- **Rust:**
  - `agent.rs`: 9 marriage constants (`MARRIAGE_STREAM_OFFSET=1600`, `MARRIAGE_CADENCE=4`, `MARRIAGE_RADIUS=0.25`, `MARRIAGE_MIN_AGE=16`, 5 compatibility weights).
  - `pool.rs`: `parent_ids` split into `parent_id_0` (birth parent) + `parent_id_1` (spouse at birth). New accessors: `parent_id_0()`, `parent_id_1()`, `parent_ids()`, `has_parent()`.
  - `ffi.rs`: `snapshot_schema()` and `promotions_schema()` export both parent columns. `get_promotions()` passes both to `register()`. 9 marriage stats in `get_relationship_stats()`.
  - `named_characters.rs`: `NamedCharacter.parent_id` → `parent_id_0` + `parent_id_1`, `register()` takes both.
  - `relationships.rs`: `is_protected()` includes Marriage. New `get_spouse_id()` helper.
  - `tick.rs`: `BirthInfo` dual-parent. Spouse captured at birth-generation time via `get_spouse_id()`. Dual kin bonds, BirthOfKin for both parents. Reverse index widened. `MemoryIntent` identity validation (`expected_agent_id` field).
  - `formation.rs`: `marriage_scan()` — scored greedy matching with region cadence stagger, eligibility filters (age, existing spouse), rejection gates (distance, incest, cross-civ hostility), compatibility scoring (civ/belief/culture/spatial), deterministic hash tie-breaking, disjoint pair acceptance. 9 diagnostic stats.
  - `memory.rs`: `MemoryIntent.expected_agent_id` + identity check in `write_all_memories()`.
- **Python:**
  - `models.py`: `GreatPerson.parent_id` → `parent_id_0` + `parent_id_1` + `lineage_house`. `parent_ids()` helper.
  - `agent_bridge.py`: `_process_promotions()` reads dual-parent columns.
  - `dynasties.py`: `check_promotion()` — 4-rule dual-parent dynasty resolution. `compute_dynasty_legitimacy()` — either-parent direct-heir check.
  - `factions.py`: Succession candidate dict dual-parent.
  - `simulation.py`: `marriage_formed` event wiring for named characters.
  - `narrative.py`: Lineage house resolution in narrator context ("with lineage ties to the House of X").
  - `relationships.py`: `check_marriage_formation()` deprecated (frozen, Rust-native replacement).
- **Tests:** `test_m57a_marriage.rs` (23 tests: determinism, exclusivity, age/distance/incest gates, scored greedy, cadence, FFI round-trip, remarriage, wartime blocking, stats). `test_dynasties.py` (5 dual-parent resolution tests). `test_m51_regnal.py` (4 either-parent legitimacy tests). `test_relationships.py` (aggregate-mode smoke test).
- **Smoke verified:** 50-turn `--agents hybrid` run completed. `marriage_formed` event appears in bundle output.
- **Gotchas discovered:**
  - Python DLL path issue on Windows: `<HOME>\AppData\Local\Python\pythoncore-3.14-64` must be on PATH for `cargo nextest run` to find python314.dll.
  - Maturin develop on Windows may silently fail to overwrite locked .pyd — use `pip install --force-reinstall` if Python tests see stale FFI.
  - `MARRIAGE_STREAM_OFFSET=1600` is reserved but not consumed in v1 (determinism without RNG noise).
- **Regression status (2026-03-27):** canonical 200-seed/500-turn full gate rerun completed at `output/m57a/full_gate/batch_1` with `--parallel 24`. Oracles: `community PASS`, `needs PASS`, `era PASS`, `cohort PASS`, `artifacts PASS`, `arcs PASS`, `determinism SKIP` (no duplicate seed pairs), `regression FAIL`. Reported regression metrics: `satisfaction_mean=0.424`, `satisfaction_std=0.1393`, `migration_rate=0.093362`, `rebellion_rate=0.070325`, `gini_in_range_fraction=0.963`, `occupation_ok=true`; failure is the current regression gate's `satisfaction_mean >= 0.45` requirement in `validate.py`.
- **Deferred / follow-up:** investigate the M57a regression dip before calling the milestone fully closed. M57b (household economics, inheritance, joint migration, widowhood semantics) can still proceed in parallel at the spec level. Later follow-ons can revisit divorce, political marriage, and marriage-based diplomacy if still desired.

### M57b: Households, Inheritance & Joint Migration — implemented on `m57a-marriage-lineage`

- 10 commits on `m57a-marriage-lineage`. 21 Rust household tests, 4 Python tests. 661 total Rust tests, 2196 Python tests passing.
- **Spec:** `docs/superpowers/specs/2026-03-28-m57b-households-inheritance-joint-migration-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-28-m57b-households-inheritance-joint-migration.md`
- **Rust:**
  - `household.rs` (new): `household_effective_wealth`, `resolve_dependents`, `household_death_transfer`, `consolidate_household_migrations`, `HouseholdStats`, `InheritanceEvent`.
  - `tick.rs`: pre-decision `id_to_slot`, `full_dead_ids` precompute, death-transfer in death-apply loop, birth marital counting, household stats accumulation.
  - `behavior.rs`: `evaluate_region_decisions` gains `id_to_slot` param, `migrate_utility` modulated by household-effective wealth.
  - `ffi.rs`: `get_household_stats()` PyO3 method.
  - `agent.rs`: `CATASTROPHE_FOOD_THRESHOLD` constant.
- **Python:**
  - `agent_bridge.py`: `_household_stats_history`, collection in `_process_tick_results()`, `household_effective_wealth_py` parity helper.
  - `analytics.py`: `extract_household_stats()` extractor.
  - `main.py`: household stats in bundle metadata.
- **Regression status (2026-03-28):** canonical 200-seed/500-turn full gate completed at `output/m57b/full_gate/batch_1` with `--parallel 24`. Oracles: `community PASS`, `needs PASS`, `era PASS`, `cohort PASS`, `artifacts PARTIAL`, `arcs FAIL`, `determinism SKIP` (no duplicate seed pairs), `regression PASS`. Regression metrics: `satisfaction_mean=0.4786`, `satisfaction_std=0.1441`, `migration_rate=0.113802`, `rebellion_rate=0.063411`, `gini_in_range_fraction=0.986`, `occupation_ok=true`.
- **Oracle details:** `arcs FAIL` due `icarus` dominance `0.43662` (> `0.40` cap). `artifacts PARTIAL` because `type_diversity_ok=false` and `loss_destruction_rate_ok=false` (`0.08198` vs required `[0.10, 0.30]`), while creation-rate check still passes (`1.8725` artifacts per civ per 100 turns).
- **Policy check note:** compared against control means pinned in `docs/superpowers/analytics/m57-adjudication-2026-03-27.json` (`satisfaction_mean=0.4171`, `migration_rate=0.098642`, `rebellion_rate=0.069242`, `gini_in_range_fraction=0.9489`), M57b deltas are `+0.0615`, `+0.015160`, `-0.005831`, `+0.0371` respectively; the oracle status vector also differs because `arcs` is now `FAIL`.
- **Tuning follow-up (2026-03-28):**
  - Artifact tuning:
    - `src/chronicler/artifacts.py`: deterministic scientist promotion gate (`GP_SCIENTIST_ARTIFACT_CHANCE=0.60`) to diversify artifact mix.
    - `src/chronicler/artifacts.py`: deterministic portable-artifact conquest loss path (`PORTABLE_CAPTURE_LOSS_CHANCE=0.14`) to raise `LOST/DESTROYED` rate into oracle range.
  - Household migration tuning:
    - `chronicler-agents/src/behavior.rs`: household wealth damping switched from inverse-sqrt only to inverse-power plus a flat household factor:
      - `HOUSEHOLD_MIGRATION_WEALTH_DAMP_EXPONENT=1.20`
      - `HOUSEHOLD_MIGRATION_MARRIED_FACTOR=0.88`
    - This reduced arc dominance pressure while keeping regression means within gate bounds.
  - Windows FFI hygiene:
    - `pip install -e .\\chronicler-agents\\ --force-reinstall` was required repeatedly to avoid stale `.pyd` reuse during tuning probes.
  - Probe confidence run:
    - `output/m57b_tune_probe10_exp120_f88_t500_s80/oracle_subset/batch_1` -> all active subset gates `PASS` (`determinism SKIP`).
- **Final regression status (2026-03-28):** canonical 200-seed/500-turn full gate rerun completed at `output/m57b_tuned_v5/full_gate/batch_1` with `--parallel 24`. Oracles: `community PASS`, `needs PASS`, `era PASS`, `cohort PASS`, `artifacts PASS`, `arcs PASS`, `determinism SKIP` (no duplicate seed pairs), `regression PASS`.
- **Final metrics (m57b_tuned_v5):**
  - Regression: `satisfaction_mean=0.4507`, `satisfaction_std=0.149`, `migration_rate=0.099566`, `rebellion_rate=0.059994`, `gini_in_range_fraction=0.9909`, `occupation_ok=true`.
  - Arcs: `icarus=0.371779` (below `0.40` cap), all required families present.
  - Artifacts: `creation_rate=1.45975` per civ/100 turns, `loss_destruction_rate=0.132214`, `type_diversity_ok=true`.
- **Updated policy check note:** against control means (`0.4171`, `0.098642`, `0.069242`, `0.9489`), final deltas are `+0.0336`, `+0.000924`, `-0.009248`, `+0.0420` (sat/migration/rebellion/gini).

---

## Current Status

### M53: Depth Tuning Pass — concluded, canonical gate passed

- **Merge baseline:** landed on `main` at `aff1b18` after passing on `feat/m53-depth-tuning`
- **Spec:** `docs/superpowers/specs/2026-03-21-m53-depth-tuning-validation-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-21-m53-depth-tuning-validation.md` (23 tasks)
- **Commits — infrastructure (prior session):**
  - `4729484`..`f075c74` — 16 commits: tag normalization, FFI exports, sidecar, analytics, validate scaffold, 6 oracles, baseline sweep, mixed age seeding
- **Commits — demographic fix (prior sessions):**
  - `5135522` — fix(determinism): replace hash()-based seeds with stable SHA256 helper
  - `b6972aa` — feat(m53): demographic debug infrastructure + disease probe
  - `9e36df1` — fix(demographics): disease mortality additive → multiplicative
  - `ebec710` — fix(demographics): B+C+D constants + younger-fertile age mix
  - `f05b857` — docs(m53): session handoff — demographic probes, 7/20 extinction rate
  - `ce3a3e4` — fix(demographics): fertility taper replaces hard cutoff (3-4/20 ext)
  - `84775f8` — fix(satisfaction): cap overcrowding penalty at 0.30 (Pass 0 substrate fix)
- **Commits — Pass 1 tuning (prior session):**
  - `ff63fbb` — tune(m53): Pass 1 — social bond restoration + autonomy rebalance
- **Commits — M53b validation cleanup (2026-03-21 session):**
  - `42a199d` — fix(m53b): Oracle 5 counts LOST + DESTROYED artifacts in loss rate
  - `d77b25c` — fix(m53b): Oracle 6 enforces 40% arc dominance cap
  - `1d00894` — fix(m53b): wire world.agent_events_raw into Oracles 2 and 4
  - `7a3bddd` — docs(m53a): frozen constant snapshot with substrate + pass changes + M49 flags
  - `96680fb` — docs(m53b): narrow Oracle 5 scope, update progress with partial cleanup status
- **Tests:** latest focused verification run is `pytest tests/test_sidecar.py tests/test_validate.py tests/test_artifacts.py tests/test_culture.py tests/test_simulation.py -q` -> `229 passed`.
- **New files:** `scripts/m53_demographics_probe.py` (demographics), `scripts/m53_social_probe.py` (needs/bonds/satisfaction)
- **Key demographic changes (cumulative):**
  - `DemographicDebug` struct in tick.rs — 13 per-tick counters
  - `get_demographic_debug()` + `get_age_histogram()` FFI methods
  - Birth counter bug fix: ffi.rs was counting event_type==3 (occ_switch) not 5 (birth)
  - Disease mortality formula: additive → multiplicative (`base*eco*war*(1+disease*SCALE)`)
  - `DISEASE_MORTALITY_SCALE=10.0` [CALIBRATE M53] — at cap 0.15: 2.5x mortality (was 16x additive)
  - `MORTALITY_ADULT` 0.01→0.005, `MORTALITY_ELDER` 0.05→0.03
  - `FERTILITY_BASE_FARMER` 0.03→0.05, `FERTILITY_BASE_OTHER` 0.015→0.03
  - Age mix: 20/55/20/5% at 0-15/16-30/31-45/46-60 (was 30/50/15/5%)
  - Fertility taper: `FERTILITY_FULL_AGE_MAX=50`, `FERTILITY_TAPER_AGE_MAX=60` (replaces hard cutoff `FERTILITY_AGE_MAX=45`)
  - Overcrowding penalty cap: `OVERCROWDING_PENALTY_CAP=0.30` — uncapped formula zeroed satisfaction at 3-7x capacity, blocking all fertility and making depth systems inert

#### Historical Pass 1 Notes

**Pass 1 results (20 seeds × 200 turns, seeds 10-29):**

| Metric (T50) | Baseline v2 | Post-Pass 1 | Delta |
|---|---|---|---|
| social_below_025 | ~30% est | **3.3%** | bond restoration works |
| social_below_035 | ~71% | **33%** | diagnostic threshold |
| autonomy_below_030 | ~77% | **46%** | improving to 18% by T100 |
| autonomy_mean | 0.15 | **0.31** | viable equilibrium |
| satisfaction_mean | 0.33 | 0.30 | slight dip (within noise) |
| extinctions | 4/20 | 5/20 | stable |
| mem_slots/agent | — | 7.05 (of 8) | healthy |
| mem_intensity | — | 43.3 | moderate |

**Constants changed (provisional lock):**
- `SOCIAL_BLEND_ALPHA`: 0.0 → **0.3** (HARD freeze candidate)
- `SOCIAL_RESTORE_BOND`: 0.010 → **0.030** (bonds must outpace 0.008 decay via proxy)
- `AUTONOMY_DECAY`: 0.015 → **0.010** (was fastest-decaying need; aligns with spiritual)
- `AUTONOMY_RESTORE_NO_PERSC`: 0.010 → **0.020** (foreign-controlled agents get viable eq at 0.50)

**Key findings:**
1. **Alpha alone did nothing.** Both `SOCIAL_RESTORE_BOND` (0.010) and `SOCIAL_RESTORE_POP` (0.010) are the same base rate — blend just interpolates between equal values. Bond rate needed to be 3x to outpace decay through the multiplier chain.
2. **Social need was structurally underpowered vs other needs.** Safety has 3 restoration sources summing to ~0.038. Social had 1 source at ~0.006 effective. Decay (0.008) always won. Other needs (safety, material) were fine because they stack multiple sources.
3. **Autonomy decay was too fast for foreign-controlled agents.** Only `NO_PERSC` (0.010) was available; 0.015 decay made equilibrium negative. Doubling restoration + reducing decay gives foreign-controlled equilibrium at 0.50, own-rule at 0.75.
4. **Memory is healthy.** 7/8 slots filled, intensity ~43 at T50 (decaying normally). No trapping signal. No constant changes needed.

**Historical note:** This block records the pre-pass handoff state that led into the final successful M53 rerun.

**Probe results summary (20 seeds × 200 turns each):**

| Configuration | Seeds | Extinctions | Alive T50 | Alive T100 | B/D T20-40 |
|---------------|-------|-------------|-----------|------------|------------|
| Pre-fix (additive disease) | 10-29 | ~20/20 | 8 | 1 | 0.13 |
| B+C+D+age-mix (hard cutoff 45) | 10-29 | 7/20 | 188 | 27 | 0.17 |
| Hard cutoff 50 | 10-29 | 6/20 | 187 | 36 | 0.18 |
| Taper full=40 end=55 | 10-29 | 10/20 | 179 | 20 | 0.16 |
| Taper full=45 end=60 | 10-29 | 7/20 | 188 | 41 | 0.19 |
| **Taper full=50 end=60** | **10-29** | **4/20** | **192** | **50** | **0.22** |
| **Taper full=50 end=60 (confirm)** | **50-69** | **3/20** | **215** | **61** | **0.31** |
| **+ overcrowding cap 0.30** | **10-29** | **4/20** | **309** | **96** | **0.65** |
| **+ overcrowding cap (confirm)** | **50-69** | **4/20** | **316** | **105** | **0.65** |

**Key findings (cumulative):**
1. **Disease was the primary killer.** Additive formula gave 16%/turn at cap. Multiplicative fix alone gave 10x survival improvement.
2. **Disease and war are population stabilizers.** Reducing either causes overshoot-collapse (more extinctions, not fewer).
3. **Fertility taper resolved the generational handoff gap.** Hard cutoff caused entire cohorts to drop out simultaneously. Taper smooths the transition.
4. **Full-rate window must extend to 50.** Taper starting at 40 or 45 reduced net fertility too much. Full=50 + taper to 60 is the sweet spot.
5. **Overcrowding penalty was zeroing satisfaction.** Uncapped `(pop/cap - 1.0) * 0.3` at 5x capacity gave 1.2 penalty, forcing satisfaction to 0 and blocking all fertility. Cap at 0.30 preserves pressure up to 2x while preventing runaway zeroing. Overcrowding already punished via ecology, disease, and demography.
6. **This is a provisional baseline**, not the final word. M53 tuning may reveal remaining edge cases that require further demographic adjustment.

**M53 tuning tasks complete:** All 6 system passes done, constants frozen, integration pass clean at 20 seeds x 200 turns. Freeze snapshot present at `tuning/m53a_frozen.yaml`.

**Canonical M53b infrastructure complete (2026-03-22):**
1. `python -m chronicler.validate` consumes exported bundles, `agent_events.arrow`, canonical validation sidecars, and `validation_summary.json`.
2. Validation runs write `validation_relationships.arrow`, `validation_memory_signatures.arrow`, `validation_needs.arrow`, `validation_summary.json`, and `validation_community_summary.json`.
3. Dedicated duplicate-seed determinism smoke gates remain PASS on the canonical exported-data path for both `--agents=off` and `--agents=hybrid`.

**Structural fixes carried by the passing rerun:**
- Hybrid passive stability recovery now routes through `keep` in agent mode instead of being guard-dropped.
- Stale wars against dead civilizations are pruned before they keep applying phantom dissatisfaction.
- Hybrid assimilation fallback / controller-pressure parity is restored so foreign-control bleed can resolve.
- Artifact mix and arc-classifier edge cases were corrected without weakening the validator assertions.

**Canonical gate results (`200` seeds x `500` turns, seeds `1-200`):**
- Community: PASS (`200/200`, target `150/200`)
- Needs diversity: PASS (`199/200` expected-sign seeds, `822` matched pairs, median effect `1.0063`)
- Era inflection: PASS (`200/200` inflection seeds, `0` silent collapses)
- Cohort distinctiveness: PASS (`200/200` expected-direction seeds, median effect `1.5021`)
- Artifacts: PASS (creation `1.8723/civ/100t`, diversity OK, loss/destruction `0.2705`)
- Six arcs: PASS (`6/6` families, `199` seeds with `3+` types, no dominance violation)
- Regression summary: PASS (satisfaction `0.4577 +/- 0.1131`, migration `0.06465`, rebellion `0.06281`, Gini-in-range `0.9554`, occupation mix OK)
- Determinism in the full gate report: SKIP (`1-200` batch contains no duplicate-seed pairs)

**M53 Status:** `M53a` remains complete and frozen. Canonical `M53b` now passes on the current branch state, so `M53` is concluded and **does** unlock the scale track.

**Artifacts / reports:**
- Canonical report: `docs/superpowers/analytics/m53b-validation-report.md`
- Passing full gate output: `output/m53/codex_m53_secession_threshold25_full/batch_1`
- Persisted machine report: `output/m53/codex_m53_secession_threshold25_full/batch_1/validate_report.json`
- Determinism outputs: `output/m53/canonical/determinism_off/batch_42` and `output/m53/canonical/determinism_hybrid/batch_42`
- Runner/pipeline implementation notes: `docs/superpowers/plans/2026-03-21-m53b-validation-pipeline.md`

#### Integration Pass Results (Task 21, 20 seeds × 200 turns)

| Metric | T50 | T100 | T200 | Gate |
|--------|-----|------|------|------|
| sat_mean | 0.27 | 0.39 | 0.24 | OK (startup dip) |
| sat_floor_frac | 0.13 (max 0.70) | 0.00 | 0.00 | PASS after T50 |
| social_below_025 | 0.02 | 0.21 | 0.19 | PASS |
| autonomy_below_030 | 0.45 | 0.38 | 0.10 | PASS (improving) |
| safety_below_030 | 0.00 | 0.01 | 0.00 | PASS |
| mem_slots | 7.17 | 6.20 | 2.40 | PASS |
| civs | 4.0 | 3.55 | 3.35 | PASS (2-4 range, 20/20) |
| rebellions/seed | — | — | 85.1 | Active |
| migrations/seed | — | — | 138.5 | Active |

**Freeze applied:** All `[CALIBRATE M53]` → `[FROZEN M53 HARD]` (4 changed constants) or `[FROZEN M53 SOFT]` (all defaults). Tags in agent.rs, action_engine.py, agent_bridge.py, artifacts.py, dynasties.py, narrative.py.

#### Pass 1d-1f Results (20 seeds × 200 turns, seeds 10-29)

**Pass 1d — Mule (M48):**
- `MULE_PROMOTION_PROBABILITY`: 0.07 → **0.12** (GP promotion is bursty, need higher hit rate)
- `MULE_ACTIVE_WINDOW`: 25 → **30** (extend influence beyond initial GP burst)
- MULE_MAPPING weights: **unchanged** (narratively coherent, no calibration needed)
- Result: 50% of seeds have Mules (was 35%), mean 1.9 at T50. All Mules expire by T100 — structural (GP promotion is cohort-based, all hit threshold at same turn ~T36).
- GPs ARE promoting (18 mean at T50, gotcha about 0.0 GP mean outdated post-demographic fixes). Dominated by merchants.

**Pass 1e — Legacy (M51):**
- All constants **unchanged**: LEGACY_HALF_LIFE=100, LEGACY_MIN_INTENSITY=10, LEGACY_MAX_MEMORIES=2
- Legacy memory counts: 37.8 at T50, 46.2 at T100 (peak), 20.9 at T200. 100% seed presence at T100.
- LEGITIMACY_DIRECT_HEIR=0.15, LEGITIMACY_SAME_DYNASTY=0.08: **unchanged but inert**. Only 0.1 successions/seed in 200 turns. Leaders rarely change — legitimacy scoring never activates. Structural issue, not constant issue.

**Pass 1f — Artifacts (M52):**
- All constants **unchanged**: CULTURAL_PRODUCTION_CHANCE=0.15, GP_PRESTIGE_THRESHOLD=50, etc.
- Artifact rate: 2.3 at T50, 4.5 at T100, 8.7 at T200 (total ever created).
- 50% loss/destruction rate (was 10-30% target). Driven by civ extinction — when civs fall, artifacts become LOST. Acceptable — lost artifacts are still narrative content.

**Total constants changed across all Pass 1 (a-f): 6** (out of ~145+). Social(2) + autonomy(2) + Mule(2). Memory, legacy, artifact, and legitimacy systems all well-calibrated at defaults.

#### Other Fixes This Session

- **Determinism fix (`5135522`):** Python hash() seeds replaced with stable SHA256 helper in `utils.py`. Wired through 12 modules. 159 tests pass, cross-process determinism verified.
- **Birth counter bug (`b6972aa`):** ffi.rs `last_tick_births` was filtering event_type==3 (occ_switch) instead of 5 (birth). Prior "13 births total" was counting occupation switches.
- **M52 bug (`6339077`, prior session):** `self.world` → `world` in `_process_promotions()`.
- **Rust test DLL / arro3 issues** (prior session, still documented in gotchas).

### M51: Multi-Generational Memory — merged (`412d238`)

- 15 commits on M51 implementation. Legacy memory transfer, regnal naming, dynasty legitimacy scoring.
- **Spec:** `docs/superpowers/specs/2026-03-20-m51-multi-generational-memory-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-20-m51-multi-generational-memory.md`
- **Rust:**
  - `memory.rs`: `memory_is_legacy` SoA bitmask, `write_single_memory` decay override for legacy transfer, legacy extraction + death-path intent emission.
  - `ffi.rs`: `get_agent_memories` returns 6-tuple with legacy flag.
- **Python:**
  - `models.py`: Leader regnal fields (`regnal_name`, `regnal_number`), `Civilization.regnal_name_counts`, `GreatPerson.base_name`.
  - `leaders.py`: `strip_title()`, `_pick_base_name()`, `_pick_regnal_name()`, `to_roman()`. Wired into all 7 ruler creation sites.
  - `dynasties.py`: Dynasty legitimacy scoring, GP candidate lineage fields (`LEGITIMACY_DIRECT_HEIR=0.15`, `LEGITIMACY_SAME_DYNASTY=0.08`).
  - `narrative.py`: Legacy memory rendering with ancestral prefix, succession legitimacy phrasing.
  - `agent_bridge.py`: Memory sync includes is_legacy from FFI.
- **Key design decisions:** Legacy memories preserve original event_type (not `MemoryEventType::Legacy`). `memory_is_legacy` bitmask tracks status. Legacy memories compete in regular ring buffer. Regnal numbering per-civ. GP `base_name` set at promotion via `strip_title()`. Legitimacy captured BEFORE leader swap.

### M52: Artifacts & Cultural Production — merged (`b4fa883`)

- 18 commits on M52 implementation. Artifact lifecycle, cultural production, narrative integration.
- **Spec/Plan:** M52 spec and plan docs.
- **Python (entirely Python-side, no Rust changes):**
  - `artifacts.py` (new): `tick_artifacts()` core — creation from intents, prestige, naming. Artifact lifecycle (conquest transfers, holder reversion, civ destruction). Prosperity gate, cultural artifact type selection. Relic conversion bonus (non-stacking, owner-gated). `extract_artifacts()` analytics extractor.
  - `models.py`: Artifact data model — types, `Artifact`, `WorldState.artifacts`, intent fields.
  - `agent_bridge.py`: GP promotion + Mule artifact intents (agent and aggregate paths). Temple completion emits relic artifact intent.
  - `narrative.py`: Artifact narrative context — relevance selection + prompt rendering.
  - `simulation.py`: `tick_artifacts()` wired into turn loop. Cultural production intents. Conquest, twilight absorption, civ destruction lifecycle intents.
  - `culture.py`: Ephemeral artifact prestige in `tick_prestige()` trade bonus.
- **Key design decisions:** Intent-based creation (intents emitted from multiple sites, `tick_artifacts()` processes them). Artifact naming with cultural flavor vocabulary. `CULTURAL_PRODUCTION_CHANCE=0.15`, `GP_PRESTIGE_THRESHOLD=50`, `RELIC_CONVERSION_BONUS=0.15`.

### M54c: Rust Politics Migration — closed (control-matched adjudication)

- **Branch:** `codex/m54c-rust-politics-clean` is the clean squash integration branch cut from `main` after M54b merged. The original `codex/m54c-rust-politics` branch is retained only as implementation history.
- **Spec:** `docs/superpowers/specs/2026-03-22-m54c-rust-politics-migration-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-23-m54c-rust-politics-migration.md` (5 tasks)
- **What landed:**
  - **Task 1:** Python politics oracle frozen. Dedicated FFI batch builders (`build_politics_*_batch()`), `reconstruct_politics_ops()`, and ordered `apply_politics_ops()` in `politics.py`. 47 builder/apply/oracle tests in `test_politics_bridge.py`.
  - **Task 2:** Pure Rust politics core in `politics.rs`: 11-step ordered Phase 10 consequence pass, helper functions (`graph_distance`, `effective_capacity`, `get_severity_multiplier`, `stable_hash_int`), typed op emission. 40 Rust scenario/determinism/ordering tests in `test_politics.rs`.
  - **Task 3:** Politics FFI surface in `ffi.rs`: `tick_politics()` entry point, `set_politics_config()`, 12 centralized schema helpers, dedicated `PoliticsSimulator` for `--agents=off`. Arrow batch conversion helpers in `politics.py`.
  - **Task 4:** Production routing in `simulation.py`: Phase 10 politics sub-pass routes through Rust when `politics_runtime` is available (both agent-backed and off-mode). Python oracle fallback for bare unit tests. `main.py` constructs `PoliticsSimulator` for off-mode and threads `politics_runtime` through `execute_run()`/`run_turn()`/`phase_consequences()`.
  - **Task 5:** Parity and determinism safety net. 35 Python parity tests in `test_politics_parity.py` (structural parity, apply-layer parity, forced-outcome parity, transient lifecycle, pending shock semantics, step ordering, 20-seed determinism). 6 new Rust determinism tests in `test_politics.rs` (20-seed determinism, complex topology determinism, event merge order stability, forced outcome determinism).
- **Test results (final):**
  - Rust: 46 politics tests + 74 ecology/economy tests = 120 integration tests passing.
  - Python: 257 tests passing across `test_politics.py`, `test_politics_bridge.py`, `test_politics_parity.py`, `test_agent_bridge.py`, `test_main.py`.
- **Final review fixes (2026-03-23):**
  - `apply_politics_ops()` now keeps a stable mapping for existing federation refs while dissolves shift `world.federations`, so later append/remove ops still target the intended federation in the same ordered apply pass.
  - `_materialize_restored_civ()` now resets war-frequency state on the absorber when restoration strips its last region, matching the preserved Python oracle's extinction semantics for `war_weariness` and `peace_momentum`.
  - Focused verification after those fixes: `cargo nextest run --test test_politics` (`54 passed`) and `python -m pytest tests/test_action_engine.py tests/test_politics_bridge.py tests/test_politics_parity.py -q` (`170 passed`).
  - Additional hybrid A/B parity harness: seeds `1-20`, `200` turns each, Rust Phase 10 politics vs forced-Python oracle, all matched after excluding timeline/raw-event sidecar fields.
- **Post-review closeout (2026-03-24):**
  - Backed out the stray economy civ-row patch from the M54c branch so the comparison line stays politics-only (`src/chronicler/economy.py`, `chronicler-agents/src/ffi.rs`, `tests/test_economy_bridge.py`).
  - Preserved the original embargo target tie-break in `action_engine.py` and locked it with `test_embargo_preserves_relationship_iteration_tiebreak()`, so M54c does not silently change Phase 8 targeting behavior.
  - Added coverage for the remaining politics edge cases: stable existing-federation refs across dissolves, non-truncated region-list round trips, proxy-war target-region matching, hybrid shock coalescing, restored-civ decline bookkeeping, and same-turn twilight viability after restoration.
  - Focused verification after the review pass: `python -m pytest tests/test_economy_bridge.py tests/test_action_engine.py tests/test_politics_bridge.py tests/test_politics_parity.py -q` (`194 passed`) and `cargo nextest run --test test_economy --test test_politics` (`72 passed`).
  - Cut clean squash-integration branch `codex/m54c-rust-politics-clean` at `caf263f`, which matches the reviewed M54c tree exactly while excluding the stray economy-only history detour from the original branch.
- **Scope:** M54c stayed politics-only (no spatial sort). Spatial sort deferred to M55.
- **Canonical 200-seed regression adjudication (2026-03-24):**
  - Fresh clean-branch M54c rerun at `output/m54c/codex_m53_secession_threshold25_full_500turn_purepolitics_cleanbranch/batch_1/validate_report.json` passes `community`, `needs`, `era`, `cohort`, `artifacts`, and `arcs`, with `determinism=SKIP` as expected. `regression=FAIL` on `satisfaction_mean=0.4425` (other regression sub-metrics remain in range).
  - Preserved same-machine M54b controls:
    - `output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine/batch_1/validate_report.json`
    - `output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine_run2/batch_1/validate_report.json`
    - `output/m54b/codex_m53_secession_threshold25_full_500turn_control_recheck_current_machine_run3/batch_1/validate_report.json`
    are identical and all fail only on `satisfaction_mean=0.4460`.
  - Historical accepted M54b baseline remains `output/m54b/codex_m53_secession_threshold25_full_500turn_bootstrapfix/batch_1/validate_report.json` (`regression=PASS`, `satisfaction_mean=0.4533`), indicating the floor shift is baseline/provenance-related rather than M54c-specific.
  - Formal adjudication artifact: `docs/superpowers/analytics/m54-baseline-adjudication-2026-03-24.md` and machine-readable output `docs/superpowers/analytics/m54-baseline-adjudication-2026-03-24.json`.
  - M54 closeout rule: require core oracle pass plus control-relative deltas within tolerance (`|delta_satisfaction|<=0.005`, `|delta_migration|<=0.001`, `|delta_rebellion|<=0.001`, `|delta_gini|<=0.005`).
- **Key decisions:**
  - RNG parity between Python and Rust is structural, not numeric (different RNG engines). Probabilistic decisions are tested via forced-outcome scenarios and structural blocking conditions.
  - Tie-breaking in capital reassignment differs (Python picks first-in-list, Rust picks last). Parity tests use distinct effective_capacity values to avoid ties.
  - Python oracle functions preserved for test/parity reference. Deletion gated on both hybrid-mode and off-mode passing parity.

---

## Ready for Implementation

**Next steps:**
- **M54 status:** M54a, M54b, and M54c are all closed on the clean line (`main` at `7c012d9` in this repo state).
- **M54 regression policy:** Absolute `regression` floor remains informative, but final M54 signoff uses preserved same-machine control matching (`docs/superpowers/analytics/m54-baseline-adjudication-2026-03-24.md` and `.json`) to avoid false negatives from baseline/provenance shift.
- **Operational tool:** `scripts/m54_baseline_adjudication.py` is the source-of-truth comparator for candidate vs controls; keep its output artifact with every post-M54 migration closeout.
- **M55 status:** M55a and M55b are both implemented and gated on the clean merge line. Final canonical artifact: `output/m55b/gate_food007_farmer030_stab280_p24/full_gate/batch_1/validate_all.json`.
- **Gate recovery note:** The branch-level regression drift was not caused by M55b alone. Final recovery that restored the canonical gate on the accepted M54 runtime line combined (1) age stream staying at `1400`, (2) spatial streams moving to `2000/2001`, (3) `MEMORY_SATISFACTION_WEIGHT=0.05`, (4) `FOOD_SHORTAGE_WEIGHT=0.07`, (5) `FOOD_SCARCITY_FARMER_BONUS=0.30`, and (6) the satisfaction stability bonus denominator moving from `300` to `280`.
- **`M59a` status:** merged on the clean line. Canonical design doc: `docs/superpowers/specs/2026-03-30-m59a-information-packets-design.md`. Canonical implementation plan: `docs/superpowers/plans/2026-03-30-m59a-implementation-plan.md`.
- **Next implementation target:** promote `M59b: Perception-Coupled Behavior` from pre-spec handoff to spec/implementation on the clean post-`M59a` baseline (`docs/superpowers/plans/2026-03-30-m59b-pre-spec-handoff.md`).
- **M59b prep (2026-03-30):** Added `docs/superpowers/plans/2026-03-30-m59b-pre-spec-handoff.md` to capture the live post-`M59a` baseline for `M59b`, including the still-perfect-info merchant planner in `merchant.rs`, the still-local-only migration / loyalty logic in `behavior.rs`, the merchant bootstrap problem if route planning becomes packet-gated, and the recommended defaults for scoping merchants, migration, loyalty, and diagnostics.
- **Phase 8 roadmap alignment (2026-03-30):** Reviewed and tightened `docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md` against the live repo contracts. The draft now keeps the global action-weight cap at `2.5x`, routes Phase 8 Rust-politics inputs through the dedicated politics civ batch rather than agent-tick `CivSignals`, keeps legitimacy on a normalized `0.0-1.0` scale, moves the ambition RNG reservation off the existing `1600` marriage slot, and makes M64 commons inputs explicitly one-turn lagged because ecology runs before the current turn's agent tick.
- **Scale baseline:** Preserve `tuning/codex_m53_secession_threshold25.yaml` and `output/m53/codex_m53_secession_threshold25_full/batch_1/validate_report.json` as the reference pass profile.
- **If depth tuning is reopened later:** treat it as post-M53 follow-on work and rerun the canonical gate against this baseline rather than reverting milestone status.
- **ERA_REGISTER A/B experiment:** Dropped (2026-03-21)
- **Phase 7.5 pre-activation prep (2026-03-24):** Added `docs/superpowers/specs/2026-03-24-m62a-bundle-v2-contract-design.md` and `docs/superpowers/plans/2026-03-24-m62a-preactivation-prep.md` to lock the Bundle v2 contract draft, test matrix, and activation checklist. Viewer-side `useBundle` now detects manifest-first Bundle v2 files and emits explicit compatibility guidance until M61b freeze fixtures are available.

---

## Known Gotchas / Deferred Items

- **Transient signal rule (CLAUDE.md):** Clear BEFORE return in builder functions. 2+ turn integration test required for every new transient signal.
- **Phase 7 roadmap restructure (2026-03-23):** Approved split update landed in `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md`. Shared sort infrastructure now belongs to `M54a`, `M54c` is politics-only, `M55-M61` are split into smaller merge gates (`M55a/b`, `M56a/b`, `M57a/b`, `M58a/b`, `M59a/b`, `M60a/b`, `M61a/b`), and viewer work remains in the separate Phase 7.5 roadmap.
- **~~M51 implementation gotchas~~** - All resolved during M51 implementation (`412d238`). Legacy bitmask, regnal naming, phantom counter, legitimacy scoring all landed.
- **M51: Legitimacy activation rate still unmeasured.** M53 passed without a dedicated legitimacy gate, but if most successions produce abstract/external candidates the dynasty scoring remains largely decorative. Measure before any dynasty-focused retune.
- **M51: Legacy + persecution stacking.** Legacy persecution memories still add to the M38b + M48 + M49 pressure stack. M53 passed, but this remains a watchpoint if rebellion tuning is revisited.
- **M34 farmer-as-miner:** Resolved. M41 added `is_extractive()` dispatch; M42 replaced it with market-derived `farmer_income_modifier`.
- **M44 (API narration):** Merged. 20-seed quality comparison still pending (manual evaluation task).
- **~~Viewer extensions (M46)~~ — Dropped 2026-03-17.** Phase 7 redesigns the viewer from scratch (M62). All Phase 3-6 viewer requirements preserved as inventory in Phase 7 roadmap.
- **M44: Sequential batch token accumulation bleeds across seeds.** `--batch N --narrator api` shares one `AnthropicClient` across seeds; seed 2's bundle metadata shows seed 1+2 cumulative tokens. Low urgency — edge case, tokens for operator awareness not billing. Fix: reset accumulators per `execute_run()`, or snapshot deltas. Phoebe NB-1.
- **M44: `_run_narrate()` agent context still limited.** Pre-existing gap — `narrate_batch()` call in `_run_narrate()` doesn't thread `great_persons`, `social_edges`, `gini_by_civ`, `economy_result`. API and local narration both equally affected. Not M44 scope.
- **M54b: off-mode economy runtime is intentionally frozen.** Production `run_turn()` does not synthesize `world._economy_result` in `--agents=off`; `compute_economy(agent_mode=False)` remains an oracle/test surface only. A regression test now locks this expectation in `tests/test_simulation.py::test_agents_off_keeps_economy_result_unset`, and M56a planning should preserve the same no-op off-mode assumption.
- **Spec-ahead strategy:** M44 merged. M45 design complete (spec doc pending).
- **M42 analytics deferred:** Price time series extractor needs bundle format update to persist `EconomyResult` prices into turn snapshots. Land when bundle schema is designed (M43 or M62).
- **M42+M43a 200-seed regression pending:** Calibration values (PER_CAPITA_FOOD, RAW_MATERIAL_PER_SOLDIER, LUXURY_PER_WEALTHY_AGENT, LUXURY_DEMAND_THRESHOLD, MERCHANT_MARGIN_NORMALIZER, TAX_RATE, BASE_FARMER_INCOME, plus M43a transport/decay/stockpile constants) need tuning before regression is meaningful.
- **M43a: `RegionStockpile` is persistent, `RegionGoods` remains transient.** CLAUDE.md note "M43 adds stockpile persistence" is now landed. `food_sufficiency` source changed from single-turn supply to pre-consumption stockpile.
- **M43a: `resource_effective_yields` not `resource_yields`.** `compute_economy()` line 595 was referencing `region.resource_yields[0]` (a property that may not exist on all Region instances). Fixed to `region.resource_effective_yields[0]` during implementation.
- **M43a: Salt preservation denominator excludes salt.** `total_food` in `apply_storage_decay()` uses `FOOD_GOODS if g != "salt"`. Salt doesn't preserve itself.
- **M43a: Per-good import decomposition assumes single resource slot.** Inline comment documents M41 Decision 14 dependency. Multi-slot milestone would need broader decomposition.
- **M43a: Conquest stockpile destruction wiring untested by M43a tests.** Formula is tested; integration point covered by existing war/action tests (which now operate on stockpile-bearing regions).
- **M43a: `--agents=off` stockpile accumulation test not written.** Phoebe recommended. Low priority.
- **Phase 7 roadmap:** `docs/superpowers/roadmaps/chronicler-phase7-roadmap.md` — draft, M47 dependency for sequencing. Phase 8-9 horizon extracted to `chronicler-phase8-9-horizon.md`.
- **Phase 8-9 brainstorm enrichments:** Most brainstorm "new systems" are content for existing milestones, not new milestones. Disease → M55, diaspora → M50, legal systems → M63, education → M63/M64, language → M68, espionage → M71. See enrichment notes on each milestone.
- **~~Tier 1 multiplier consumers not wired~~** — Fixed in M47 (`d99b178`). All 8 consumers wired.
- **~~`--tuning` YAML loading was missing for single runs.~~** Fixed in prior uncommitted main.py, now committed.
- **~~M43b: `CivThematicContext` population deferred.~~** Deleted entirely in M47 (`d99b178`).
- **M43b: `trade_dependent_regions` not scoped to moment civs.** Phoebe O-1. The spec says filter by controller, but `build_agent_context_for_moment` lacks world access. Currently includes all trade-dependent regions. Low impact — narration context is already scoped to agent events.
- **M43b: `_get_adjacent_enemy_regions()` rebuilds region_map per call.** Phoebe O-2. Fine at current civ counts (~10). If civ count grows, cache `region_map` on `ActionEngine`.
- **M42+M43a+M43b+M44+M45+M47 200-seed health check pending.** Six milestones unvalidated. M47b extractors landed, health check run (Task 12) not yet executed. Absolute thresholds, not delta regression.
- **~~CRITICAL: Civ-removal stale-index bug.~~** Fixed in M47 Tier A (`d99b178`). Dead civs stay in list, 13 guards added.
- **~~25 severity multiplier sites missing.~~** Fixed in M47 (`d99b178`). All 25 sites now use `get_severity_multiplier(civ, world)`.
- **K_PEAK_YIELD has no consumer.** Defined in `tuning.py` but never read anywhere. No yield cap exists in `compute_resource_yields()`. K_RESOURCE_ABUNDANCE scales linearly with no upper bound. Downstream `food_sufficiency` clamp at [0, 2.0] is the effective guard.
- **~~`AgentBridge._gini_by_civ` keyed by int, not name.~~** Fixed in M47 (`d99b178`). Snapshot uses `enumerate` index.
- **M45: `gp.deeds` is defined but never populated.** The field exists on GreatPerson (models.py:334), narrative pipeline reads `gp.deeds[-3:]` (narrative.py:173), but nothing ever appends. M45 fixes this with 9 mutation points.
- **M45: `gp.region` not auto-synced from agent snapshot.** Only set at major transitions (creation, conquest, hostage release). Agent migration doesn't update GP region. Affects Wanderer classification — use `notable_migration` event count instead of region field.
- **M45: `build_agent_context_for_moment()` excludes dead characters.** Line 162 filters `if not gp.active`. Death moments (the most important arc events) don't get accumulated arc context in the prompt. M45 relaxes filter to include characters whose names appear in moment event actors.
- **M45: Character events include character name in `actors`.** Verified: `character_death` actors=[name, civ.name], `exile_return` actors=[name], `notable_migration` actors=[name], `conquest_exile` actors=[gp.name, conquered_civ, conqueror_civ]. The `gp.name in e.actors` filter works for character-specific events. Civ-level events (war, trade, rebellion) only have civ names — classifier operates on character events only.
- **Fullscale Phoebe review (2026-03-18):** CLAUDE.md line counts + file table updated, simulation.py docstring aligned, dead `derive_food_sufficiency()` removed, Phase 7 viewer scope estimate corrected.
- **M47: 3 integration test files hang after Pydantic cleanup.** `test_bundle.py::TestBundleSize::test_500_turn_bundle_under_5mb`, `test_m36_regression.py`, `test_main.py` — all run full `execute_run()` integration. Complete in <1s on clean tree, hang indefinitely with M47 changes. The simulation loop benchmarks at 1ms/turn, so tatonnement is not the cause. Suspected root cause: removing `ge=/le=` Field constraints changed default values (e.g., `population: int = 0` was `Field(ge=0, le=1000)`, `stability: int = 50` was `Field(ge=0, le=100)`) — test fixtures may rely on old default behaviors or the Civilization constructor may now accept states that trigger infinite loops in the simulation. Investigation started but not completed. See session handoff for details.
- **M47: `region_map` inline replacements deferred.** The `world.region_map` cached property is added but the ~19 inline `{r.name: r for r in world.regions}` rebuilds are NOT yet replaced. Safe — property works alongside inline rebuilds. Replace opportunistically. `invalidate_region_map()` calls not yet added at region mutation sites.
- **~~M48 spec: `_detect_character_events` referenced but doesn't exist by that name.~~** Resolved — memory sync placed in tick() hybrid branch loop, after events processed.
- **~~M48 spec: Phase 7 roadmap text outdated.~~** Resolved — spec Section 10 documents 5 divergences.
- **M48: Promotion intent not generated.** `MemoryEventType::Promotion` has constants and decay factor but no intent collection in tick.rs. Promotion happens Python-side in `_process_promotions()`. No Rust-to-Python memory write path exists. Wire when character arc system needs it.
- **M48: Victory memories not civ-filtered.** `war_won_this_turn` is a bare boolean on RegionState. ALL soldiers in the region get Victory memories, including losing side. Fix requires `war_winning_civ: u8` field on RegionState + civ filtering in tick.rs intent collection.
- **M48: `default_decay_factor()` recomputes `factor_from_half_life()` per write.** Cold-path (thousands/turn, not millions). Could be lazy-static lookup table if memory write volume increases.
- **M48: `build_agent_context_for_moment()` new params not wired in batch path.** `civ_names`/`world_turn` params default to None/0 for backward compatibility. Memory/Mule context populated when callers pass those params. `_prepare_narration_prompts` does not wire them yet.
- **M49: Persecution triple-stacking.** M38b direct boost (0.30) + M48 memory boost (~0.10) + M49 Autonomy need boost (up to 0.24) all push rebel/migrate. Total can reach ~0.64 additive on rebel. M53 passed, but this remains a future retune watchpoint.
- **Need restoration structural asymmetry (found in M53 Pass 1).** Safety has 3 additive restoration sources summing to ~0.038 effective rate. Social had 1 source at ~0.006. Blend formula interpolates (doesn't stack), so bond_factor needed to be 3x proxy to outpace decay. Key takeaway for future needs: any need with only one restoration source needs rate >> decay, or needs a second source.
- **T10 satisfaction transient.** Satisfaction dips to 0.16 mean at T10 across all seeds (overcrowding + shock + war penalties stack at game start), then recovers to 0.43-0.45 by T20. Not structural — 79% above fertility threshold by T50. May resolve naturally as Pass 1 calibrates penalties. Do not chase this — it's startup dynamics, not a broken formula.
- **Great person promotions are no longer the blocker.** Demographic stabilization restored regular GP promotions during M53. If promotion volume drifts again in future tuning, re-check `PROMOTION_SKILL_THRESHOLD` and `PROMOTION_DURATION_TURNS`.
- **M49: `_NEED_THRESHOLDS` in narrative.py must stay synced with agent.rs constants.** Both files define threshold values (0.3, 0.25, 0.35). No compile-time enforcement. If thresholds change in future tuning, update both.
- **~~M49: Social need pre-M50 proxy.~~** Resolved in M50b + M53. `social_restoration()` blend formula `(1-α)*proxy + α*bond_factor`. Alpha ramped to 0.3, bond rate to 0.030. Social_below_025 = 3.3% at T50.
- **M50b: Dissolution events lack dead target's agent_id.** `AgentEvent.target_region` is repurposed for bond_type; dead agent's ID is not carried. Python stores `(agent_id, 0, bond_type, turn)` with 0 as placeholder. Narration can say "a bond was severed" but not "between X and Y." Fix requires adding `target_agent_id: u32` field to AgentEvent. Deferred — not blocking until M53b needs dissolution trace data.
- **~~M50b: `--relationship-stats` flag parsed but not wired.~~** Wired in M53 (`fcb0700`). `AgentBridge` now calls `get_relationship_stats()` per tick when the flag is set and stores the history in bundle metadata.
- **M50b: `id_to_slot` HashMap rebuilt per-region.** Spec says build pool-wide map once per cadence tick. Implementation rebuilds from `alive_slots` inside the region loop. Correct behavior, minor perf waste (~100K unnecessary hash insertions per tick with 50K agents). Hoist above region loop if formation scan shows in profiles.
- **M50b: `check_friend` evaluates compatibility before shared memory.** Spec cascade puts expensive checks last. At current memory slot counts (5 max), cost difference is negligible. Low priority.
- **M49: Phase 7 roadmap estimates ~24 M49 constants.** Actual count is 37. Update roadmap when next editing it.
- **M49: Material equilibrium sensitive to wealth percentile assumptions.** Spec equilibrium table assumes "median wealth" restoration rate that may be optimistic. Re-verify numerically if wealth restoration is retuned in the future.
- **Demographics: provisional baseline (4/20 extinction, healthy trajectories).** Fertility taper + overcrowding cap. T100 alive mean ~100, B/D ratio ~0.65. Remaining 4/20 extinctions are late (mean T170+). Disease and war are stabilizers — do NOT reduce them.
- **Overcrowding penalty capped (M53 Pass 0).** `OVERCROWDING_PENALTY_CAP=0.30` in satisfaction.rs remains part of the passing M53 baseline. Without it, population growth beyond carrying capacity zeroes satisfaction and makes the depth systems inert.
- **Disease mortality is multiplicative (M53 fix).** Formula changed from `base*eco*war + disease` to `base*eco*war*(1+disease*SCALE)`. This remains part of the passing M53 baseline. The additive formula was the original demographic collapse bug.
- **Disease/war volatility reduction causes overshoot-collapse.** Lowering DISEASE_SEVERITY_CAP (0.15→0.10) or WAR_CASUALTY_MULTIPLIER (2.0→1.5) both increased extinctions from 7/20 to 11/20. These pressure sources prevent population overshoot that leads to harder crashes. Counterintuitive but confirmed across 20-seed probes.
- **Birth counter was wrong prior to `b6972aa`.** ffi.rs `last_tick_births` filtered event_type==3 (occ_switch) not 5 (birth). All prior birth count reports from `last_tick_births` were measuring occupation switches. Fixed.
- **Determinism: Python hash() seeds were non-deterministic.** Fixed in `5135522` with SHA256-based `stable_seed()` in utils.py. All prior M53 cross-process comparisons were invalid. Bundle timestamps remain non-deterministic metadata (acceptable).
- **M52: `self.world` bug in `_process_promotions()`.** Fixed in `6339077`. `emit_gp_artifact_intent` was called with `self.world` but AgentBridge doesn't store world as instance attribute.
- **arro3 vs pyarrow API.** pyo3-arrow 0.17 returns `arro3.core.RecordBatch`, not pyarrow. Use `batch.column(name).to_pylist()` for column access. `to_pydict()` does NOT exist on arro3. Convert to pyarrow via `pa.record_batch(batch)` if needed.
- **Windows Rust test DLL fix.** Python 3.14 DLL (`python314.dll`) lives in `pythoncore-3.14-64/` dir which isn't in PATH. Pre-commit hook must use `export PATH=...` not inline `PATH=... command` — the latter doesn't propagate to cargo's child processes on Windows. Fixed in `.claude/settings.json` hooks.
- **Module deployment.** After `cargo build --release`, copy `target/release/chronicler_agents.dll` to `<python-site-packages>/chronicler_agents/chronicler_agents.cp314-win_amd64.pyd`. Rename-then-copy pattern needed if the file is locked (old → `.old`, then copy new).
