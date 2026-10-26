# Guilds and burghers (`--guilds`)

Branch `feat/guilds` from `main` `2ef3097` (PR #38, bulk trade and crafts),
merged without rebase with `main` `11238d5` (PR #39, needs follow-ups).
Code: `src/chronicler/guilds.py` (behaviour), `src/chronicler/guilds_state.py`
(persisted state), the guild creed in `agent_movements.py` and
`chronicler-agents/src/movements.rs`, movement news in
`chronicler-agents/src/knowledge.rs`, `FactionType.BURGHER` in `models.py`
and `factions.py`, hooks in `cities.py`; viewer `CitiesPanel.tsx`,
`FactionDashboard.tsx`, `lib/guilds.ts`; scripts `guilds_report.py`
(histories), `guilds_probe.py` (distributions).

**Status.** On by default for new worlds, in a separate commit (`efd0b3a`)
after the full gate with the switch on passed strict with no regression;
the merged head passed it again against the needs-followups report
([Gates](#gates)). `--no-guilds` opts out and saved worlds keep their
setting. With the switch off every output is byte-identical to `main`
([Identity](#feature-off-identity)).

## Result

| | |
| --- | --- |
| subset gates 42-61, 62-81 (on against off, `f0aa299`) | PASS; NO REGRESSION, both |
| full gate against trade-crafts (`f0aa299`) | PASS strict; NO REGRESSION (needs lower bound 0.177 -> 0.201; migration 0.0615 -> 0.0619; rebellion 0.0388 -> 0.0379) |
| full gate against needs-followups (merged head) | PASS strict; NO REGRESSION (needs 0.204 -> 0.196, binding 0.168 -> 0.178; migration 0.0642 -> 0.0644; rebellion 0.0360 -> 0.0368; 0 extinct) |
| per 500-turn world (merged gate) | 7.0 guilds, 8.1 privileges, 2.7 levies, 0.50 guild movements, 0.11 guild charters; burghers in 2.2 realms, the dominant faction in 0.40 |
| news against no news (40 paired 200-turn worlds) | significant movements +16% (+0.23, SE 0.12), risings +34% (+0.12, SE 0.05), foundings +4% (within noise); a movement's own reach unchanged |
| `--no-guilds` against `main` `11238d5` | 88 files, 0 differences |
| bundle guard world | +570 bytes (7.894 MB native, 8.613 MB no-Rust; guard 10.5 MB) |
| tick time at ~23,700 and ~54,000 agents | within the shared machine's spread of the base |

## Design

### Guilds

A city (`cities.py`) forms one guild, on the first tick it meets either test
(no random draw):

- it made wares last turn (`City.crafts` at least `GUILD_WARES` 0.05): a
  **craft guild** (the Weavers', Smiths', Potters', Masons', Dyers' or
  Coopers' Guild of the city, the craft fixed by a hash of the seed and the
  settlement id);
- its **merchants and craftworkers** reach `GUILD_MASTERS` 4 at the
  reference scale (the cities' `scale`): a **merchant guild**.

There is no artisan occupation. Craftworkers are the town's share of the
city's farmers' labour, the share city markets already take off the land:
`size / scale x (merchant share + farmer share x (1 - URBAN_FARM_LABOR[rank]))`.
A guild dissolves when its city falls, or after 20 turns under one master.

**Membership is not a new per-agent column.** A guild is a city body; its
people are the city's civilian residents (`settlement_id` and occupation,
already in the pool). When a guild rises, its members carry the existing
`movement_id` of its guild movement, so the movement machinery (seeds,
recruitment, lapse, leaders, crackdowns, risings) runs unchanged on them.

### Privileges and money

| privilege | granted with | effect |
| --- | --- | --- |
| monopoly of the city's wares | market rights (or a guild charter) | the wares' term in commerce access x1.5, its cap 0.3 -> 0.45; the guild's take 5% -> 10% of commerce |
| a say in civic dues | self-government or a free city (or a guild charter) | the city's dues share x0.8; a levy half as likely |
| a guild charter (a movement's reform) | its guild movement's grant | both of the above, dues x0.75 more, no levy while in force |

The guild takes its share of the city's commerce from the civic purse into
its own (2% decay a turn). It presses for protection: when walls are due
(`cities._walls`) and the purse is short, the guild pays the rest. A
privilege won or lost is an event (`guild_privilege`,
`guild_privilege_lost`).

### Threats and guild movements

Five things threaten a guild's privileges:

| threat | when |
| --- | --- |
| levy | a lord short of money (treasury under 30) or at war raises the city's dues: chance 0.04 a turn (0.02 with a say), dues share +0.10 for 20 turns, the city's grievance +0.1; none under a guild charter, none in a free city |
| charter | the city's charter level falls (a conqueror's revocation, a home rule repeal) |
| sack | the city is sacked |
| occupation | its region is newly occupied |
| repeal | its guild charter is repealed (not lapsed) |

With movements on and agent rows present, a threatened guild with at least
3 masters, residents' mean satisfaction under 0.65 and no living movement of
its own rises with chance 0.5 (0.8 after a repeal) as a movement of the
**guild creed** (`CREED_NAMES[3]`, appended), at most 4 living in the world.
It takes the guild's name, targets the city's lord, is founded in the city's
region and cites the threat. Guild movements are founded by their guilds,
never from the census, and count apart from the census movements' caps.

In Rust (`movements.rs`, `CREED_GUILD`) the row carries the city's
settlement id (optional table column `settlement`). A guild's people are the
civilian adults living in the city; one is aggrieved while its satisfaction,
read with a guild charter's 0.3 credit, is under 0.65 (`GUILD_SAT`), with
intensity 0.5 + 0.5 x the deficit; it stays committed while it lives there
within 0.10 of the threshold. Seeding, recruitment, lapse and leaders are the
existing ones; a guild's leader is promoted as a merchant (wire role 1, now a
leader role).

In Python the creed has its own parameters: demand at 3% of the realm's
adults (a city's guild is small against a realm), pressure from 2%, rising
at grievance 0.5 with 15% of the stronghold and 5 members; the ally faction
is the burghers where the realm has them, else the merchants; the grant
chance reads merchant plus burgher influence; a grant costs the military
faction 0.02. A rising stirs the city (unrest +0.3, so the cities' urban
revolt, and with it a free city, may follow); it resolves as a concession or
a crushing, never a secession.

The reform is a **guild charter** (`REFORM_NAMES[3]`, appended), a lasting
reform through the movements reform machinery: covering the city's region,
upheld by Merchant Courts when governance has room (`REFORM_INSTITUTIONS`),
opposed by the military faction without one, repealed by a new ruler or the
opposition, lapsed when the city falls or changes lord, and restored by a
restoration movement the guild raises after a repeal.

### The burgher faction

`FactionType.BURGHER` is appended to the enum. A civ's influence map holds it
only while guilds are on and the civ is lord of chartered cities, a free
city or a guild city: weight = sum over its cities of rank x (charter weight
0 / 1 / 2 / 3 for none / market rights / self-government / free city, +1
with a guild). With weight it enters at the faction floor (0.08) and gains
`min(0.015, 0.002 x weight)` a turn; without, it loses 0.01 a turn and
leaves after 20 turns. `normalize_influence` runs over the factions a civ has
(the four classic ones in declaration order without the switch, as before).

How burghers press rulers:

- **Action weights** (dominant faction, `faction_weight ** influence`):
  trade 1.8, develop 1.3, build 1.3, embargo 0.6, war 0.5, within the four
  factions' range; the faction bucket's 1.5 ceiling and the global cap hold.
- **Charters**: they take the patricians' voice and the charters' +0.03 from
  the merchants (`cities._shift_merchants`), and charter grants read
  merchant plus burgher influence.
- **Order**: a ruler's chance to crush a commons or liberty movement +0.3 x
  burgher influence.
- **Succession**: at 0.15 they field an elected candidate; charter and guild
  privilege events count as their wins in power struggles.
- The governance kernel reads the four classic factions (`_FACTIONS`); the
  agent and politics batches code a burgher-dominated realm 4, which the
  native tick and politics treat as no occupation and no intelligence bonus
  (as the Python oracle does).

### Movement news

Movement foundings, risings, reforms and crackdowns become information
packets: `InfoType::MovementNews` (type 4, appended). Python derives, for
every region batch, last turn's strongest movement event per region from the
persisted movement records (`founded_turn`, `rising_turn`, `reform_turn`,
`crackdown_turn` at `turn - 1`): optional columns `movement_news` (creed x 4
+ kind) and `movement_news_intensity` (founding 120, rising 180, reform
220, crackdown 160). Rust reads no news without them. The agents of the
region observe a packet; it passes on friend, kin, family, mentor and
co-religionist bonds (base rate 0.35, the usual 0.85 a hop) and decays 10 a
turn. The provenance byte (`pkt_source_civ`) of a news packet holds its news
code.

News **never displaces** another packet: it takes only an empty slot or the
oldest news slot, and a packet of another type takes a news slot as if it
were empty. So the threat, trade and religious packets of every agent are,
slot for slot, those of a world without news
(`with_or_without_news_the_other_packets_are_slot_for_slot_the_same`), and
the migration and trade consumers of packets read what they read before.

Consumers, bounded:

- **Joining** (Rust): an aggrieved agent holding news of a like movement
  (same creed) from another region joins with probability x(1 + 0.5 x
  strength) for a founding, rising or reform and x(1 - 0.25 x strength) for
  a crackdown (strength = intensity / 255), under the existing 0.5 cap;
  without news the factor is not applied.
- **Founding** (Python): the census counts, per region and creed, the
  aggrieved holding inspiring news of a like movement elsewhere
  (`informed_*` columns); a candidate's founding chance is x(1 + informed /
  aggrieved), at most x2, under the existing cap.

Tuning `guilds.movement_news: 0` turns news off with guilds on (for the
comparison below).

**Provenance** (`fix/movements-narration-polish`): the census also names,
per region and creed, the news most of the informed aggrieved hold
(`news_source_{region,turn,kind,count}_*`: the strongest inspiring packet
of each, counted by source region, turn and kind; read only). When news of
a demand a like movement won in another region (a reform or a concession)
is held by at least a quarter of a founding region's aggrieved
(`agent_movements.NEWS_CAUSE_SHARE`), the founding cites that event as a
cause, so the curator's chains and the prompt tell it ("stirred by news of
the demand won in R in turn T"). No event, draw or state is added; about
one founding in a run of 150-400 turns qualifies
([narration-coverage.md](narration-coverage.md#follow-ups-news-guild-chronicles-spread)).

**In-world chronicles**: the court chroniclers tell guild formations,
privileges won and lost, guild charters granted and repealed and guild
movements' foundings from importance 3, with their usual bias (glory,
decree, disgrace; `historiography.GUILD_GLORY`, `GUILD_DECREE`). A guild
movement now enrols its founders, the city's aggrieved civilian residents,
when it is founded, and is not founded when none of them is free to join
([agent-movements.md](agent-movements.md#founders-at-founding-no-empty-movements)).

### Contracts

- Randomness: `random.Random(stable_hash_int("guilds", namespace, seed,
  turn, settlement id, ...))`, namespaces `levy`, `movement`; the craft name
  from `("guilds", "name", seed, settlement id)`. News propagation uses the
  knowledge phase's per-packet streams; no new Rust stream.
- Identity: region index, civ index, settlement id, guild index (dissolved
  guilds stay), movement and reform indices.
- Bridge signals: the news columns and the movement table's `settlement`
  column are rebuilt from persisted state for every batch; Rust resets the
  region news fields from every batch and reads no news without the columns;
  nothing transient is kept on the world. Multi-tick checks:
  `test_movement_news_is_observed_while_set_and_travels_after` (Rust),
  `test_native_news_is_observed_on_the_tick_after_the_event_and_not_again`
  and `test_news_columns_come_from_last_turns_events_and_reset` (Python).
- Accumulator: no new stat change; the guild's take is moved within the
  city's purse, dues stay `keep` treasury through `pay_dues`, the movement
  outcomes keep their categories. Faction influence is written to the
  faction state.
- Append-only orders: `FactionType.BURGHER`; `CREED_NAMES` "guild",
  `REFORM_NAMES` "guild_charter", the per-creed tuples
  (`RISE_*`, `REFORM_INSTITUTIONS`, `REFORM_OPPONENTS`, names, demands,
  reforms); `cities_state.HISTORY_KINDS` "levy"; `InfoType::MovementNews`;
  `KIND_NAMES`, `HISTORY_KINDS`, `THREAT_NAMES`, `COUNTER_KEYS`,
  `NEWS_KINDS` (= `knowledge.rs` `NEWS_*`).

## Turn placement

| When | What |
| --- | --- |
| Region batch, each tick | news columns from last turn's movement records |
| Agent tick, knowledge phase | news observed and passed on (after the other packets) |
| Agent tick, movement pass | guild rows (the city's people), the news factor on joining |
| Agent tick, end | census with the informed aggrieved |
| Phase 10, cities | the guild's take, monopoly, dues share and wall help; the patricians' voice to the burghers |
| Phase 10, movements | guild movements' demands, grants (guild charters), risings; news-raised foundings |
| Phase 10, after movements | `tick_guilds`: dissolutions, masters, privileges and charters, threats and guild movements, levies, foundings, burghers |

## Switch and persistence

| Surface | Value |
| --- | --- |
| CLI | `--guilds` / `--no-guilds` (`BooleanOptionalAction`) |
| World field | `WorldState.guilds: GuildState \| None` (presence = on), omitted while `None` |
| Default | on (`guilds.DEFAULT_ENABLED_FOR_NEW_WORLDS = True`, in a separate commit after the full gate) for `execute_run`, batch and the live server; resumed, forked and supplied worlds keep their setting; `scripts/benchmark_headless.run` pins it off |
| Gate runner | `scripts/m53b_run_validation.py --guilds` forwards the switch and records it in `run_manifest.json` |
| Bundle | `history[n].guilds`: living guilds (id, name, city, region, kind, masters, purse, monopoly, say, levy, charter, movement), the dissolved count, burgher influence by realm, counters; omitted while off; civ rows' `factions.influence` gain `burgher` where a realm has one |
| Analytics | `generate_report` gains `guilds` for runs that carry it |
| Old saves | load with `guilds` None; a guild-on world keeps its guilds and burgher keys on resume |

## A guild's history

`scripts/guilds_report.py RUN_DIR --guild INDEX` prints a guild's record
and the record of each movement it raised, with the event text the
simulation wrote. Template world, seed 71, 500 hybrid turns, `--guilds`,
every other system at its default (a world of the full gate below);
movement lines shortened:

```
the Merchant Guild of Verdant Plains Settlement 1 (merchant), Verdant Plains; founded turn 15;
peak 24.8 masters; standing: 10.9 masters, purse 11.4, monopoly, say in dues
    15: founded: The masters of Verdant Plains Settlement 1 in Verdant Plains form the Merchant
         Guild of Verdant Plains Settlement 1 to govern its trade
    24: privilege: ... wins the monopoly of its wares
    25: levy: Kethani Empire raises the dues of Verdant Plains Settlement 1 to fill the treasury
    37: walls: Verdant Plains Settlement 1 in Verdant Plains begins walls with the Merchant Guild of
         Verdant Plains Settlement 1's help
    54: privilege: ... wins a say in the city's dues
   185: levy: Kethani Empire raises the dues of Verdant Plains Settlement 1 to fill the treasury
   185: movement: ... takes up its cause against the new dues: its 5 masters want relief from new
         dues and the confirmation of its privileges
   191: charter: Kethani Empire confirms the privileges of the Merchant Guild of Verdant Plains
         Settlement 1; a guild charter fixes its dues under Merchant Courts
   301: levy: Free Verdant Plains raises the dues of Verdant Plains Settlement 1 for the war
   301: movement: ... (301) takes up its cause against the new dues: its 11 masters want ...
   318: charter: Free Verdant Plains confirms the privileges of ...; a guild charter fixes its dues
         under Merchant Courts
   331: repealed: Archon Gillian of Free Verdant Plains repeals the charter of the Merchant Guild of
         Verdant Plains Settlement 1
   331: movement: ... (331) takes up its cause for its repealed charter: its 8 masters want the
         restoration of the charter ...
   336: charter: Free Verdant Plains confirms the privileges ...; the charter ... is restored under
         Merchant Courts
   435: repealed: The clergy faction of Free Verdant Plains forces the repeal of Merchant Courts,
         and with it the charter of the Merchant Guild of Verdant Plains Settlement 1
   435: movement: ... (435) takes up its cause for its repealed charter ...
   440: charter: ... the charter ... is restored under Merchant Courts
   441: repealed: The clergy faction of Free Verdant Plains forces the repeal of Merchant Courts,
         and with it the charter of the Merchant Guild of Verdant Plains Settlement 1
  the Merchant Guild of Verdant Plains Settlement 1 (301) (guild), founded turn 301 against Free
  Verdant Plains, led by Warchief Anchora; peak 9 members, 2 demands, 1 martyrs; ended won turn 330
     302: spread: ... spreads to Sapphire Coast (2 members)
     306: demand: ..., 8 strong (9% of the people of Free Verdant Plains), demands relief from new
          dues and the confirmation of its privileges
     306: crackdown: Free Verdant Plains suppresses ... in Verdant Plains; 1 dies a martyr's death
     313: leader: Warchief Anchora rises to lead ... in Verdant Plains
     318: demand: ..., 7 strong (8% of the people of Free Verdant Plains), demands ...
     318: reform: Free Verdant Plains confirms the privileges of ...
     330: ended: ... disbands, its demand met
```

Formation at the city's founding (turn 15, a merchant guild: the city's
merchants and craftworkers reach 24.8 at their peak). Privileges with the
city's charters: market rights at 24 bring the monopoly, self-government at
54 the say in dues. The guild helps pay for the city's walls (37). Conflict:
a third levy by a short-of-money Kethani Empire at 185 raises its first
movement, which demands at 3% of the realm and wins a guild charter under
Merchant Courts at 191. At 299 a liberty movement, the Sons of Obsidian
Shore, carries Verdant Plains and two other regions out of Kethani Empire
(the Free Verdant Plains); the charter lapses with the old lord at 300.
Kethani Empire goes to war to take the region back, and the new state
levies the city for that war at 301; the guild's second movement is suppressed once (a martyr), raises a leader
from its boldest member (a merchant promotion; the name generator's title
is no rank) and wins a new charter at 318. Outcome: a new ruler repeals it
at 331 and a restoration movement wins it back at 336; at 435 the clergy
faction, opposed to Merchant Courts, forces the institution out and the
charter with it; restored at 440, it falls again the next turn. At turn 500
the guild keeps its monopoly and its say through the city's own charter.

## News and movement spread

Measured as guilds on with news against guilds on with news off (tuning
`guilds.movement_news: 0`; everything else the same), template seeds 42-81,
200 hybrid turns, 40 worlds, differences paired by seed
(`scripts/guilds_probe.py`). The news-on arm is the subset gates' runs.

How far news reaches (template seed 44, 200 turns; the census each turn):

| | news by bonds only (first build) | with the neighbours (shipped) |
| --- | ---: | ---: |
| aggrieved agent-creed samples holding news of a like movement elsewhere | 1.7% | 5.0% |
| founding candidates (region, creed) with any such agent | 8.9% | 19.5% |
| informed share of the aggrieved there | 0.16 | 0.29 |

The first build had news observed in the event's region only; it changed
nothing measurable (42-61: foundings 10.35 against 10.3 a world, 0.45
raised by news). The shipped build adds the neighbours at half intensity
and doubles the bounds of the join factor.

Per world, news on against off (mean of 40 paired worlds; SE of the paired
difference):

| | news on | news off | difference (SE) |
| --- | ---: | ---: | ---: |
| movements founded (census creeds) | 10.65 | 10.22 | +0.42 (0.31) |
| of them with news raising the chance | 1.70 | - | |
| significant (a demand and 10+ members at the peak) | 1.62 | 1.40 | +0.23 (0.12) |
| demands | 6.28 | 5.78 | +0.50 (0.37) |
| reforms (grants) | 2.77 | 2.45 | +0.33 (0.26) |
| risings | 0.47 | 0.35 | +0.12 (0.05) |
| crackdowns | 1.32 | 1.38 | -0.05 (0.15) |
| peak members per movement | 6.80 | 6.75 | +0.04 (0.11) |
| regions reached per movement | 2.32 | 2.36 | -0.04 (0.04) |

News raises a founding's chance in one founding of six. It does not widen a
movement's own reach (members, regions): it acts where a like movement
already rose nearby, so more movements reach significance (+16%, two SE)
and rise (+34%, more than two SE). The rise in foundings, demands and grants
is within one or two SE. Packets per world: 895 news packets observed and
1,820 passed on (200 turns).

## Gates

Every gate is hybrid, `PYTHONHASHSEED=0`, Linux, Python 3.13, with the
branch's native extension built fresh (`maturin develop --release --locked`;
compiled `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator`
verified). The batch runner's `--parallel 1` runs `cpu_count - 1` (3)
workers; the subsets ran so.

**Subset gates** (`--profile subset`, 20 seeds x 200 turns), `--no-guilds`
against `--guilds` at `f0aa299` (extension SHA-256 `d93833d0...ec4bda`),
compared with `validation_compare` (`--baseline-report` the off arm). The off
arms' validation reports equal those of `main`'s tree (trade-crafts'
subset-final reports for 42-61 and 62-81, 0 differences once the batch path
is normalised). In the subset only community, needs and cohort are
required; its regression oracle is informational.

| | 42-61 off | 42-61 on | 62-81 off | 62-81 on |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS | **PASS; NO REGRESSION** | PASS | **PASS; NO REGRESSION** |
| needs: net; lower bound; seeds (12 needed) | 0.163; 0.081; 14 | 0.207; 0.125; 16 | 0.152; 0.090; 17 | 0.165; 0.089; 17 |
| cohort; community; era (seeds) | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 | 20; 20; 20 |
| arcs (three types); artifacts | PASS (16); PARTIAL | PASS (16); PARTIAL | PASS (15); PARTIAL | PASS (14); PARTIAL |
| regression (informational) | FAIL (civ_survival) | FAIL (civ_survival) | FAIL (civ_survival) | FAIL (civ_survival) |
| satisfaction; latest | 0.603; 0.618 | 0.607; 0.626 | 0.614; 0.622 | 0.613; 0.623 |
| migration; rebellion | 0.0657; 0.0418 | 0.0650; 0.0393 | 0.0612; 0.0266 | 0.0603; 0.0219 |
| final population min / median / max; extinct | 102 / 167 / 292; 0 | 115 / 183 / 274; 0 | 116 / 186 / 261; 0 | 127 / 191 / 256; 0 |

The first build (news by bonds only, `d4768bd`) passed both subsets with no
regression as well (needs lower bound 0.115 and 0.071; rebellion 0.0411 and
0.0247).

Guilds per 200-turn world (the 40 switched-on worlds): 4.6 guilds founded,
1.0 dissolved, 5.0 privileges won, 1.3 levies, 1.7 threats, 0.35 guild
movements, 0.13 guild charters, 0.15 walls the guild helped pay; at turn
200, 2.3 realms have burghers (mean influence 0.22) and 0.23 are ruled by
them as the dominant faction.

**Full gates** (`--profile full`, 200 seeds x 500 turns, `--parallel 3`,
`--guilds`), each against the newest full report on `main` at the time:

- before PR #39: `f0aa299` (extension `d93833d0...ec4bda`) against the
  trade-crafts report (`main` `2ef3097`);
- after merging PR #39 (needs follow-ups, needs oracle method 3): the merged
  head `6431c35` (extension `5ede10a9...b8b07d6`) against the
  needs-followups report (the tree `main` `11238d5` carries). The default
  flip rests on this gate.

| | trade-crafts (`2ef3097`) | `--guilds`, `f0aa299` | needs-followups (`11238d5`) | **`--guilds`, merged** |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS | PASS; NO REGRESSION | PASS | **PASS; NO REGRESSION** |
| regression adjudication | strict | strict | strict | **strict** |
| needs, all pairs: net; lower bound; seeds with C > D | 0.191; 0.177; 190 | 0.217; 0.201; 187 | 0.222; 0.204; 176 | 0.214; 0.196; 172 |
| needs, binding pairs (method 3): net; lower bound; informative; seeds positive | - | - | 0.192; 0.168; 5,060; 159 | 0.202; 0.178; 5,094; 157 |
| informative pairs (all) | 19,746 | 19,687 | 9,902 | 10,051 |
| cohort (median effect); community; era (silent collapses) | 1.67; 200; 200 (0) | 1.61; 200; 200 (1) | 1.53; 200; 200 (0) | 1.56; 200; 200 (0) |
| arcs (three types; families); artifacts (creation; loss) | 158; 6; 1.68; 6.0% | 159; 6; 1.65; 6.2% | 159; 6; 1.66; 5.7% | 159; 6; 1.71; 5.8% |
| satisfaction mean; latest (ceiling 0.65) | 0.616; 0.627 | 0.616; 0.630 | 0.618; 0.633 | 0.617; 0.627 |
| migration per agent-turn (strict floor 0.05) | 0.0615 | 0.0619 | 0.0642 | 0.0644 |
| rebellion per agent-turn (0.02-0.08) | 0.0388 | 0.0379 | 0.0360 | 0.0368 |
| final population min / median / max; extinct worlds | 78 / 185 / 329; 0 | 57 / 180 / 320; 0 | 56 / 179 / 308; 0 | 63 / 183 / 304; 0 |
| worlds whose founders all survive | 18.5% | 16.0% | 16.5% | 18.0% |

The comparator reports no regression reason, no new required failure, no
oracle method or status change and no strict-regression downgrade in either
gate. Against needs-followups the needs oracle loses 0.008 of its all-pairs
lower bound and four seeds while its binding component gains 0.010; the
binding component, required in the full profile, passes.

Guilds per 500-turn world (the `f0aa299` full gate, 200 worlds;
`scripts/guilds_probe.py`): 6.9 guilds founded, 3.0 dissolved, 8.2
privileges won, 3.1 levies, 4.3 threats, 0.68 guild movements, 0.19 guild
charters, 0.24 walls helped; at turn 500, 2.1 realms have burghers (mean
influence 0.29), 0.40 are ruled by them as the dominant faction. Movements
founded 21.6 (2.6 with news raising the chance), 3.1 significant; 1,485
news packets observed and 3,123 passed on. The merged gate's worlds
(PR #39's needs found fewer movements): 7.0 guilds, 3.0 dissolved, 8.1 privileges, 2.7 levies, 3.9
threats, 0.50 guild movements, 0.11 guild charters, 0.23 walls; burghers in
2.2 realms at turn 500 (mean influence 0.27), 0.40 burgher-dominated;
movements founded 18.2 (2.5 raised by news), 3.0 significant; 1,236 news
packets observed and 2,722 passed on.

## Feature-off identity

Base: `main` exported with `git archive` and its extension built from that
tree into a separate virtualenv, `PYTHONPATH` on the export: `11238d5` (tree
`305923e`, PR #39; extension SHA-256 `f8e1017e...c2f410`, the one
needs-followups recorded) for the merged head, `2ef3097` (tree `e7dd6be`;
`cf109460...cd90e`, as trade-crafts recorded) before the merge. Branch: the
worktree and its extension. Same interpreter, `PYTHONHASHSEED=0`,
`--simulate-only`, compared with `scripts/agent_movements_identity.py
compare` (every output file; the bundle without `metadata.generated_at`) and
`scripts/guilds_identity.py` (the same, or without the `guilds` field).

| Comparison | Runs | Merged head against `11238d5` | Before the merge (`efd0b3a` against `2ef3097`) |
| --- | --- | --- | --- |
| base (no flags) against the branch `--no-guilds` | template seeds 42 / 7 / 1234, `--agents off` 300 turns and hybrid 200; procedural 48 regions x 10 civs, seed 7, off 200 and hybrid 120 | 88 files, **0 differences** | 88 files, **0 differences** (also with guilds default off at `d4768bd`) |
| the branch with no flags against `--guilds` | template 42 hybrid 200; procedural 48 x 10 seed 7 off 150 | 25 files, **0 differences**: the defaults are the gated configuration | 25 files, 0 differences |
| an old save resumed: base save at turn 30 (agents off, no flags), resumed to turn 60 by the base and by the branch, no flags | template 42; procedural 48 x 10 seed 13 | 24 files, **0 differences**; the resumed worlds carry no `guilds` field | 24 files, 0 differences |
| switch on, agents off: base against the branch `--guilds` | template 42 and 7, 200 turns | - | 18 files, 0 differences once the `guilds` field is removed (no city forms without agents) |
| subset gates 42-61 and 62-81, the branch `--no-guilds` | 20 seeds x 200 hybrid | - | validation reports equal to `main`'s (trade-crafts' subset-final reports), 0 differences once the batch path is normalised |

The two bases' hybrid outputs differ (PR #39 changes the needs), so the
merged comparison is not the pre-merge one repeated. With the switch off no
guild code runs (`test_feature_off_never_runs_guild_code`), the bridge
sends no news column and no `settlement` column, no civ has a burgher key,
and the native admission rule and recruitment factor take their old paths
without news (the frozen exact-trajectory oracles pass unchanged).

## Tick time

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, starting targets
18,800 and 43,700, 20 warm-up and 8 timed turns, two repeats, one child at a
time, release builds; base the `11238d5` export with its extension, the
branch at the merged head with `--no-guilds` and with `--guilds`; shared
4-core machine (a validation and another agent's probe alongside). Per run,
wall / process CPU, in ms:

| alive | | base `11238d5` | branch, `--no-guilds` | branch, `--guilds` |
| ---: | --- | ---: | ---: | ---: |
| ~23,700 | Rust tick | 151, 137 / 297, 280 | 123, 133 / 314, 316 | 126, 124 / 321, 306 |
| | whole turn | 281, 250 / 436, 430 | 217, 227 / 473, 485 | 210, 232 / 435, 416 |
| ~54,100 (53,300 with guilds) | Rust tick | 587, 468 / 1,379, 1,297 | 472, 471 / 1,403, 1,314 | 457, 510 / 1,376, 1,465 |
| | whole turn | 761, 622 / 1,808, 1,791 | 611, 602 / 1,908, 1,822 | 597, 674 / 1,854, 2,014 |

Every arm is within the run-to-run spread: the switch-off branch runs the
base's code path and differs from it by as much as the switched-on arm
does (whole-turn CPU +8-13% at 23,700 in this set, where the switched-on
arm is at or below the base). New work with the switch on: news observed by
the agents of a few regions on the turns after movement events, a scan of
four packet slots per candidate in recruitment and per aggrieved adult in
the census, a loop over the cities' guilds in Phase 10.

## Tests

- `tests/test_guilds.py` (30 tests; offline lane chunk `systems-1`, the two
  native ones skip there): switch, dormancy, old saves, CLI and gate
  forwarding, the feature off never running guild code, new worlds' default
  and resume; craft and merchant guilds, privileges with charters and a
  revocation as a threat, the monopoly, say, levy and take, dues to the lord
  with a say, dissolution; a poor lord's levy and the guild's movement (the
  movement table's `settlement`), no movement from content townsmen or
  without agent rows; a granted demand as a guild charter (its reform row,
  privileges, no levy), its repeal raising a restoration, its lapse when the
  city changes hands; a rising stirring the city; the guild creed's tables;
  burghers joining and leaving, free cities' weight, the patricians' voice
  and charter grants, the weights within the caps, succession, power
  struggles and the kernel, order against commons and liberty; news
  columns from last turn's events and their reset, the founding factor and
  its bound, guild movements apart from the census caps; snapshot, history
  and metrics; off-mode determinism; native: news observed on the tick after
  the event and not again, a hybrid run forming guilds and burghers.
- `tests/test_wave3_combined.py`: save/load resume identity with guilds and
  every other system on (a guild and its movement placed as a save carries
  them; guilds form, take and win privileges; burghers): the movement table
  with the guild's city, the reform table, the news columns compared turn by
  turn, and every byte of the world after 15 more turns.
- `tests/test_factions.py`, `tests/test_governance_runtime.py`: iterate the
  four classic factions (`CLASSIC_FACTIONS`).
- Rust `movements`: the guild creed aggrieves discontented civilians of its
  city only, a guild founding seeds its city, news of a like movement raises
  joining and a crackdown lowers it (news of another creed or from one's own
  region does nothing), the informed census, the optional `settlement`
  column. `knowledge`: news never displaces another packet and yields its
  slot; with or without news the other packets are slot for slot the same
  (400 random admissions and decays); observation by region and by
  neighbours at half intensity, reading by creed. `tests/test_knowledge.rs`:
  news observed while the column is set, carried on after, decayed. `ffi`:
  the merchant leader role.
- Viewer: `lib/__tests__/guilds.test.ts` (3), a Cities panel guild test in
  `SystemsPanel.test.tsx`, a faction bar test in `components.test.tsx`.

## Verification

Merged head (`6431c35` plus this document; Linux, Python 3.13.17, Node 22),
extension built fresh from it (SHA-256 `5ede10a9...b8b07d6`; compiled
`chronicler_agents.chronicler_agents` with real `AgentSimulator`,
`EcologySimulator` and `PoliticsSimulator` verified):

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 1,005 passed, 0 failed, 2 ignored (before the merge 1,004; `main` `2ef3097` 995) |
| `pytest -m "not slow" -n 2` | 6,241 passed, 3 skipped, 526 subtests (before the merge 6,227) |
| `pytest -m slow -n 2` | 11 passed, 3 skipped |
| No-Rust lane (virtualenv without `chronicler_agents`, every test) | 6,009 passed, 235 skipped, 526 subtests |
| `scripts/run_python_oracle_checks.py` | PASS in 95.5 s: 2,181 passed, 35 skipped; largest chunk `systems-2` 36.9 s of 110 s |
| Viewer `npm test` / `npm run lint` / `npm run build` | 39 files, 297 tests / clean / built (the existing large-chunk warning); one run under the full gate's load failed a test that passed in the two reruns after it |
| Golden and exact-trajectory fixtures | unchanged |
| Identity (switch off), resume, subset and full gates, tick time, bundle | above |

Bundle guard world (`tests/test_bundle.py::TestBundleSize`: seed 1, 500
turns, 10 regions, 5 civs, `--agents off`, every default), bytes of
`chronicle_bundle.json`: native 8,277,349 with `--no-guilds` (as `main`)
and 8,277,919 with guilds (7.894 MB, +570 bytes: the empty `guilds` field;
no city forms without agents); no-Rust 9,030,719 and 9,031,287 (8.613 MB).
Guard 10.5 MB.

## Open items

- **Reach of news.** News reaches neighbours and travels on bonds; it does
  not ride with merchants' cargo or cross seas with ships except through
  bonds. Members do not cross borders.
- **Guilds' economics.** The monopoly raises the city's wares term in
  commerce; it does not raise the price of wares or restrict who makes them
  (only cities make wares). There is still no artisan occupation.
- **Leagues.** No league of guilds or of free cities; a guild's movement
  stays in its city's realm.
- **Calibration.** Guild movements are rare on template worlds (a few per
  500 turns); procedural worlds were not measured.
- **News provenance** names only a won demand clearly held by the
  aggrieved; news of a founding or rising elsewhere sparks foundings
  without a record of which.
