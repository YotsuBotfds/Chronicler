# Hunger: deaths, births, disease and unrest by food severity (2026-10)

Branch `feat/hunger-mortality` from `main` at `3355289` (PR #29: navigation,
famine labels, migration drivers), merged with `main` at `ec229b5` (PR #30,
city markets; cities on by default) and at `48b72be` (PR #31, agent
movements, default off) without rebase. A **correction**, on by
default with no switch (section 9). The investigation in
[navigation-famine-labels.md](navigation-famine-labels.md) found that hunger
killed no one in agent modes and that dearth and famine had the same effects.

Commits: `fc22453` native mortality and fertility; `709f330` disease,
unrest, the aggregate toll and the golden oracles; `223e23a` the merge with
city markets; `ca859b7` the aggregate growth term removed (section 6);
`be99dbe` the merge with agent movements (`48b72be`, default off).

Every run is Linux, Python 3.13, `PYTHONHASHSEED=0`, hybrid unless stated,
with a native extension built fresh (`maturin develop --release --locked`)
and its compiled `AgentSimulator`, `EcologySimulator` and `PoliticsSimulator`
verified. Template worlds are the default 8 regions and 4 civs; procedural
ones 64 regions and 16 civs (`--worldgen procedural`). Region-turns are
"fed" at food sufficiency 1 or more, "dearth" at 0.6-1, "severe" below 0.6
for one or two turns and "famine" below 0.6 for three or more (the report
labels' rule). A turn is a month for the seasons and a year for agent ages;
death and birth rates per turn are annual rates.

**Bases.** Tables marked *main* use `ec229b5` (cities on) as the base and
the merged head `223e23a`; tables marked *3355289* use the branch before the
merge (cities off) and its base. Both full gates are in section 7.

## Result

| *main* (cities on), merged head against `ec229b5` | base | head |
| --- | ---: | ---: |
| famine death rate / fed rate, template (procedural) | 1.54 (1.49) | 1.96 (1.77) |
| deaths from the hunger term: dearth / famine region-turns | 0 / 0 | 2% / 22% |
| births in famine / fed, template (procedural) | 1.39 (1.01) | 1.00 (0.84) |
| births withheld by hunger: dearth / famine | 0 / 0 | 5% / 27% |
| births after a famine / fed (five fed turns), template | 1.41 | 1.59 |
| epidemic susceptibility in famine / when fed | 1.21 / 1.07 | 1.37 / 1.05 |
| dearth report: stability drain (famine 3) | 3 | 1 |
| full gate (200 x 500): gate; comparator | PASS | PASS strict; NO REGRESSION |
| migration per agent-turn (strict floor 0.05) | 0.0580 | 0.0554 |
| needs seeds of 200; extinct worlds | 189; 0 | 186; 0 |
| final population median (min) | 177 (70) | 165 (49) |

Deaths and births now respond to hunger, most for young children and the
old; dearth is milder than famine everywhere it acts. The magnitudes are
milder than the first, mid-range design, which pushed long world-wide
famines towards extinction (section 4).

## 1. Where it is decided

| Step | Where | Before this branch |
| --- | --- | --- |
| Food sufficiency | Phase 2, the native goods economy: pre-consumption food over demand, 0-2 (`EconomyResult.food_sufficiency`) | |
| ... to the agents | Phase 9: `sync_regions` builds the region batch with this turn's sufficiency; the agent tick reads it the same turn | satisfaction `(1 - s) x 0.15`; safety and material needs; farmer target; famine memory below 0.6 (migration push); merchant food price |
| ... to the labels | Phase 9, `ecology._check_famine_yield`: `Region.food_severe_turns` (the run below 0.6); a report once the 5-turn cooldown has run out, famine after 3 severe turns, else dearth | |
| Agent mortality | Rust `demographics::mortality_rate`: base by age (under 20 0.0035, 20-59 0.0025, 60+ 0.016) x ecological stress (soil, water, crowding) x war x endemic disease | no food term |
| Agent fertility | Rust `demographics::fertility_rate_with_pressure`: base by occupation x soil and water x age taper x satisfaction gate x crowding brake (0.75-1.0 of capacity) | no food term |
| Aggregate population (`--agents off`, shadow) | `simulation.phase_production`: +5 per region and turn while the civ's economy, stability and capacity allow; a famine report drains 5 x stress multiplier and sends refugees | the same toll for every report |
| Epidemics | Phase 1, `epidemiology.tick_epidemics` (SEIRS per region and pathogen), `_modifiers` | +0.2 susceptibility and x1.25 fatality for five turns after any report |
| Stability, unrest | the report's drain, `-3 x mult` (`signal`); readers of the cooldown: hazard hardship +0.5 (rebellion and migration in off and shadow modes), civ stress +2 per region, technique growth x0.5, nomad raid hunger 0.5 | identical for dearth and famine |

The goods economy has constant returns to farm labour: a region's food per
head does not rise when people die. A famine ends when the season, climate
or trade changes, not because it has thinned the population; only soil
recovery and the crowding terms respond to fewer people (section 4).

## 2. Before

Read-only probes (kept outside the repository) recorded, per region and
turn, the food sufficiency, the severe run, the agent tick's exposure by age
band (survivors plus the dead, in the post-migration region), deaths by age
and by civ wealth tercile, births, epidemic deaths and the epidemic
susceptibility. Rates are per 1,000 agent-turns; births per 1,000 agents
aged 16-60.

*main* `ec229b5`, template seeds 42-51, 200 turns:

| | fed | dearth | severe | famine |
| --- | ---: | ---: | ---: | ---: |
| share of agent-turns | 59.7% | 16.7% | 6.4% | 17.2% |
| deaths | 14.0 | 17.5 | 19.7 | 21.7 |
| deaths aged 0-4 / 5-19 / 20-59 / 60+ | 9.4 / 9.8 / 8.1 / 33.2 | 10.5 / 12.2 / 9.7 / 37.7 | 11.8 / 14.3 / 11.1 / 43.4 | 17.3 / 12.8 / 12.1 / 45.7 |
| deaths, poorest / middle / richest third | 9.8 / 12.8 / 19.7 | 11.9 / 17.5 / 22.4 | 12.3 / 21.6 / 25.6 | 14.6 / 21.8 / 30.3 |
| births per 1,000 aged 16-60 | 26.4 | 26.2 | 37.4 | 36.7 |
| epidemic deaths | 3.2 | 4.5 | 4.9 | 5.6 |
| epidemic susceptibility (mean) | 1.07 | 1.22 | 1.21 | 1.21 |

*main* `ec229b5`, procedural seeds 7-11, 300 turns:

| | fed | dearth | severe | famine |
| --- | ---: | ---: | ---: | ---: |
| share of agent-turns | 63.6% | 18.0% | 7.5% | 11.0% |
| deaths | 16.5 | 22.5 | 23.4 | 24.5 |
| deaths aged 0-4 / 5-19 / 20-59 / 60+ | 12.4 / 12.5 / 11.2 / 36.7 | 16.9 / 16.6 / 16.4 / 45.0 | 17.9 / 17.3 / 17.1 / 44.1 | 20.3 / 18.3 / 17.4 / 49.2 |
| births per 1,000 aged 16-60 | 35.3 | 36.6 | 36.2 | 35.7 |
| epidemic deaths | 5.6 | 9.5 | 10.1 | 10.1 |

The *3355289* base (cities off) reads the same: famine deaths 22.4 and 23.7
against 14.4 and 16.7 fed; famine births 36.0 and 36.4 against 28.3 and
35.5; epidemic deaths 6.2 and 9.5 against 3.5 and 5.7.

What this shows:

* A famine raises the death rate by about half (1.54 times the fed rate on
  template worlds, 1.49 on procedural ones), all of it indirect: famine
  regions have worse soil and water, and disease is boosted after every
  report.
* Births are as high in famine as when fed, or higher (37 against 26 on
  template worlds): fed regions sit in the crowding brake, short ones below
  it.
* The rich die more than the poor because they are old: wealth accumulates
  over a life.
* The epidemic boost follows the report, not the hunger: fed regions inside
  a cooldown carry it (mean susceptibility 1.07), and dearth and famine carry
  the same.

## 3. Design

One measure of hunger drives every rate. For a region with food sufficiency
`s` and severe run `run` (turns below 0.6, this turn included):

| Component | Formula | 0 | 1 |
| --- | --- | --- | --- |
| dearth | `min(1, (1 - s) / 0.4)` | fed | at or below 0.6 |
| famine | `(0.6 - s) / 0.6 x min(1, run / 3)` | at or above 0.6 | no food for three turns or more |

The thresholds are the labels' (`FAMINE_SEVERE_SUFFICIENCY`,
`FAMINE_SEVERE_TURNS`, the agents' famine-memory threshold). The famine
component builds over the season a famine takes to declare, so one lean
month below 0.6 is mostly dearth. Rust computes the components in the
demographic tick (`demographics::hunger_components`) from the batch's new
`food_severe_turns` column, the run up to the previous turn (Phase 9 extends
the run after the batch is built); Python mirrors them
(`ecology.hunger_components`) for epidemics and the Python-owned models.

| Effect | Shipped | Full design (section 4) |
| --- | --- | --- |
| Deaths: `x (1 + v x (D x dearth + F x famine))` | D 0.05, F 0.50 | D 0.10, F 1.50 |
| vulnerability `v` | 1 under 5 and at 60+; 0.5 at 5-59; adults (20+) also x `1 + 0.5 x (0.5 - civ wealth percentile)` (0.75 richest to 1.25 poorest) | same |
| Births: `x (1 - D x dearth) x (1 - F x famine)` | D 0.10, F 0.30 | D 0.15, F 0.60 |
| Epidemic susceptibility (agent modes) | `+ 0.15 x dearth + 0.35 x famine` | same |
| Epidemic fatality (agent modes) | `x (1 + 0.10 x dearth + 0.40 x famine)` | same |
| Report stability drain | famine `-3 x mult`, dearth `-1 x mult` | same |
| Cooldown readers | a dearth's cooldown weighs a third of a famine's | same |

What each piece means:

* **Deaths.** At the edge of the dearth band a young child or an old person
  carries +5% mortality; in a total famine sustained for a season +55%.
  Children's own wealth is not their household's, so only adults carry the
  poverty spread. With the indirect excess the world already had (soil,
  water, crowding, disease), famine death rates come to about twice the fed
  rate (section 5).
* **Births.** A lean season withholds up to 10% of births, a total famine
  37%. The multiplier never reaches zero, so a survivor keeps its birth draw
  and no random stream changes shape.
* **Rebound.** No separate term. After a famine the region is below the
  crowding brake and satisfaction recovers, so births run above the fed rate
  for some turns (section 5): postponed births are made up through the
  existing brake.
* **Disease.** Agent modes read the last measured hunger
  (`Region.food_shortfall`, saved, with `food_severe_turns`) instead of the
  report's cooldown: a fed region whose report is four turns old no longer
  gets the famine boost, and a deep famine gets more than the old flat
  +0.2 / x1.25 (+0.5 / x1.5 at worst). The epidemic onset cites the open
  food crisis when hunger raised susceptibility. The aggregate model keeps
  the flat terms: it has no sufficiency, and its report is a famine.
* **Unrest and stability.** A dearth report drains a third of a famine's
  stability (1 against 3, times the stress multiplier; still `signal`). While
  its cooldown runs a dearth weighs a third of a famine in hazard hardship,
  civ stress, technique growth and nomad raid hunger
  (`ecology.food_crisis_weight`; `Region.dearth_cooldown`, saved, cleared when
  the cooldown ends or the shortage reaches famine severity). Agent unrest
  was already graded: the satisfaction penalty is `(1 - s) x 0.15`.
* **Python-owned population.** `--agents off` and shadow keep their famine
  toll but scale it: the old toll (5 x stress multiplier) is what a total,
  sustained famine takes, and a report takes the share of the agents' added
  mortality its hunger carries (`hunger_toll_share`). The aggregate model
  has no demand, so its hunger is the depth of the food yield below the
  famine threshold (0.12); shadow reads the measured sufficiency. The toll
  stands for a famine's whole population effect in these models (deaths,
  flight, births not born), so their growth rule, a civ-level rule of
  economy, stability and capacity, is left alone: cutting it as well would
  count hunger twice (an earlier version did; section 6).

Historical grounding (rough):

| Measure | Historical | Shipped (*main*, template) |
| --- | --- | --- |
| Deaths in dearth (high-price) years | a few percent to 10-20% above normal (Lee 1981; Galloway 1988) | +2% from the direct term |
| Crude death rate in famine | 2-4 times normal over a famine year or region, more in the worst districts (Ó Gráda 2009; Finland 1868, Ireland 1847, China 1960) | about 2 times the fed rate |
| Who dies | young children and the old most in relative terms; labourers and the poor (Mokyr and Ó Gráda 2002; Dyson 1991; Sen 1981) | the vulnerable ages carry twice the hazard of others, the poorest adults 1.67 times the richest |
| Births | down 5-15% in dearth (Galloway 1988); a quarter to a half in famine (Dyson 1991; Ó Gráda 2009), half at the worst (Stein et al. 1975); a rebound after (Ashton et al. 1984) | -5% in dearth, -27% in famine; +59% above the fed rate in the five fed turns after a famine |
| Disease | most famine deaths came from infection (dysentery, typhus, relapsing fever, cholera, smallpox), spread by weakened bodies, crowding and flight (Mokyr and Ó Gráda 2002); the nutrition link differs by disease (Livi-Bacci 1991) | susceptibility up to +0.5, fatality up to x1.5 |
| Unrest | food riots came with dearth and high prices; deep famine brought flight more than revolt (Walter and Wrightson 1976; Walter and Schofield 1989) | dearth drains a third of a famine's stability; flight is the existing famine memory |

Sources: C. Ó Gráda, *Famine: A Short History* (2009); J. Mokyr and C. Ó
Gráda, "What do people die of during famines", *European Review of Economic
History* 6 (2002); R. Lee, "Short-term variation: vital rates, prices and
weather", in E. A. Wrigley and R. S. Schofield, *The Population History of
England 1541-1871* (1981); P. Galloway, "Basic patterns in annual variations
in fertility, nuptiality, mortality and prices in pre-industrial Europe",
*Population Studies* 42 (1988); T. Dyson, "On the demography of South Asian
famines", *Population Studies* 45 (1991); A. Sen, *Poverty and Famines*
(1981); Z. Stein et al., *Famine and Human Development: the Dutch Hunger
Winter of 1944-1945* (1975); B. Ashton et al., "Famine in China, 1958-61",
*Population and Development Review* 10 (1984); M. Livi-Bacci, *Population
and Nutrition* (1991); J. Walter and K. Wrightson, "Dearth and the social
order in early modern England", *Past and Present* 71 (1976); J. Walter and
R. Schofield (eds.), *Famine, Disease and the Social Order in Early Modern
Society* (1989).

Contracts. No new random draw. The batch column is optional (absent = 0: a
caller without it reads every region as never severe). `Region.food_shortfall`
and `Region.dearth_cooldown` are omitted while None, so worlds that never
hunger and every `--agents off` world keep their region keys; both are saved,
so labels and epidemics resume as an uninterrupted run. The stability drain
keeps its `signal` category; regions and civs are identified by index; no
transient signal is added. `get_demographic_debug` gains
`expected_hunger_deaths` and `hunger_births_withheld` (diagnostics).

## 4. The full design against the milder terms

The design was first built with magnitudes from the middle of the historical
ranges ("full": deaths D 0.10 / F 1.50, births D 0.15 / F 0.60). It broke
two guards, so the shipped terms are milder, as the brief allows: graded
disease, unrest and fertility effects and a milder mortality term.

| Variant (hybrid, 200 turns) | deaths D / F | births D / F | famine deaths vs fed (template) | subset needs 42-61 / 62-81 (12 needed) | needs, 80 seeds 42-121 (48 needed) | lowest world at turn 200, 80 seeds |
| --- | --- | --- | ---: | --- | ---: | ---: |
| *3355289* base | - | - | 1.55 | 13 / 14 | 61 | 86 |
| *3355289* full | 0.10 / 1.50 | 0.15 / 0.60 | 2.57 | 15 / **9** | 52 | **30** |
| *3355289* intermediate | 0.05 / 0.75 | 0.15 / 0.60 | 2.08 | 13 / 12 | 56 | 62 |
| *main* base | - | - | 1.54 | 16 / 16 | 61 | 85 |
| *main* intermediate | 0.05 / 0.75 | 0.15 / 0.60 | | **11 / 11** | 54 | **24** |
| *main* severity effects only (no native term) | 0 / 0 | 0 / 0 | | 16 / **11** | 57 | 87 |
| *main* births F 0.40 | 0.05 / 0.50 | 0.10 / 0.40 | | 13 / **10** | 54 | 86 |
| *main* **shipped** | 0.05 / 0.50 | 0.10 / 0.30 | 1.96 | 15 / 15 | 58 | 64 |

Two findings decided it.

* **Long, world-wide famines.** The climate cycle's drought and cooling
  phases can keep every region of a world below 0.6 for 20-25 turns (seed
  111: 91% of agent-turns in famine for turns 175-199). With constant
  returns to farm labour, deaths do not end such a famine, and per-year
  historical magnitudes applied to every turn of it compound: with the
  intermediate terms seed 111 (*main*) fell from 200 people to 24 by turn
  200 (base: 95 at its lowest), deaths 35 and births 7 per 1,000 in turns
  175-199 against 18 and 19 in the base. Simulated famines are longer and
  more frequent than historical famine years (famine is 15-17% of
  agent-turns on template worlds), so the shipped terms sit at the low end of
  the ranges. Over 500 turns the seven lowest-population seeds of the *main*
  set reach a lowest population of 56 with the shipped terms (base 59; births
  F 0.40: 56).
* **The needs oracle.** It pairs agents identical in civ, region, occupation
  and personality whose need differs, and asks whether the deprived one
  migrates or rebels more in the next 20 turns. Most seeds find one or two
  pairs, so a seed's result turns on a handful of agents, and any change to
  the histories redraws it: the severity effects alone (no native term,
  population unchanged) moved the 62-81 subset from 16 to 11. Over 80 seeds
  every variant passes (52-58 of 80 against 48 needed; base 61); the full
  design passes fewest. Births F 0.30 against 0.40 is within that noise;
  0.30 is taken for the reason above and is the low end of the historical
  range (a quarter of births in famine).

## 5. After

*main*, the merged head against `ec229b5`, the same worlds and probes as
section 2. Template seeds 42-51, 200 turns:

| | fed | dearth | severe | famine |
| --- | ---: | ---: | ---: | ---: |
| share of agent-turns (base) | 62.5% (59.7%) | 16.5% (16.7%) | 6.5% (6.4%) | 14.5% (17.2%) |
| deaths (base) | 13.7 (14.0) | 17.6 (17.5) | 18.4 (19.7) | 26.9 (21.7) |
| deaths aged 0-4 / 5-19 / 20-59 / 60+ | 7.7 / 9.8 / 7.8 / 32.7 | 11.8 / 11.3 / 9.9 / 36.8 | 7.0 / 11.9 / 11.0 / 40.7 | 17.6 / 19.2 / 14.5 / 58.7 |
| deaths, poorest / middle / richest third | 9.4 / 13.1 / 19.0 | 11.8 / 16.1 / 24.0 | 11.2 / 18.5 / 25.6 | 18.1 / 28.9 / 35.8 |
| share of deaths from the hunger term | 0 | 2.0% | 9.5% | 22.1% |
| births per 1,000 aged 16-60 (base) | 27.6 (26.4) | 27.9 (26.2) | 30.7 (37.4) | 27.6 (36.7) |
| share of births withheld by hunger | 0 | 5.0% | 14.2% | 27.0% |
| epidemic deaths (base) | 2.9 (3.2) | 3.8 (4.5) | 3.4 (4.9) | 7.1 (5.6) |
| epidemic susceptibility / fatality multiplier | 1.05 / 1.01 | 1.11 / 1.06 | 1.13 / 1.08 | 1.37 / 1.34 |

Procedural seeds 7-11, 300 turns:

| | fed | dearth | severe | famine |
| --- | ---: | ---: | ---: | ---: |
| share of agent-turns (base) | 65.0% (63.6%) | 17.2% (18.0%) | 7.4% (7.5%) | 10.4% (11.0%) |
| deaths (base) | 15.5 (16.5) | 20.1 (22.5) | 21.1 (23.4) | 27.5 (24.5) |
| deaths aged 0-4 / 5-19 / 20-59 / 60+ | 10.2 / 11.3 / 10.0 / 36.2 | 14.2 / 14.9 / 12.9 / 43.6 | 16.0 / 14.3 / 12.6 / 45.3 | 21.8 / 19.5 / 17.5 / 59.9 |
| share of deaths from the hunger term | 0 | 2.0% | 9.3% | 18.8% |
| births per 1,000 aged 16-60 (base) | 33.8 (35.3) | 34.3 (36.6) | 32.7 (36.2) | 28.2 (35.7) |
| share of births withheld by hunger | 0 | 5.1% | 14.4% | 23.7% |
| epidemic deaths (base) | 4.3 (5.6) | 6.7 (9.5) | 6.3 (10.1) | 10.1 (10.1) |

The shares from the hunger term are reconstructed from each region-turn's
components and the observed deaths and births; the native tick's own
expected values agree (6.1% of all expected deaths and 6.7% of births on
template worlds, 4.0% and 4.8% procedural).

| Per world | template base | template head | procedural base | procedural head |
| --- | ---: | ---: | ---: | ---: |
| famine death rate / fed | 1.54 | 1.96 | 1.49 | 1.77 |
| deaths aged 60+, famine / fed | 1.38 | 1.80 | 1.34 | 1.65 |
| deaths aged 0-4, famine / fed | 1.83 | 2.28 | 1.64 | 2.15 |
| births, famine / fed | 1.39 | 1.00 | 1.01 | 0.84 |
| births in the five fed turns after a famine / fed | 1.41 | 1.59 | 1.17 | 1.15 |
| epidemic deaths, famine / fed | 1.75 | 2.48 | 1.80 | 2.38 |
| epidemic deaths, all region-turns | 3.9 | 3.7 | 7.1 | 5.4 |
| migration per agent-turn | 0.0592 | 0.0590 | 0.0653 | 0.0630 |
| famine-memory share of moves | 44.9% | 42.0% | 42.2% | 42.6% |
| food-crisis reports per run (famine / dearth) | 51.0 / 80.7 | 44.7 / 85.2 | 384.6 / 1,086.4 | 352.0 / 1,115.6 |
| final population: mean (min) | 180.9 (147) | 158.6 (120) | 797 (710) | 759 (577) |

What changed:

* **Deaths.** Famine death rates rise from about 1.5 to about 1.8-2 times
  the fed rate, most for young children (2.3 times on template worlds) and
  the old (1.8). The direct hunger term is 22% of famine deaths and 2% of
  dearth deaths (a few percent). The rich still die more than the poor
  because they are old; within the term the poorest adults carry 1.67 times
  the richest's hazard.
* **Births.** Famine no longer raises births: they fall to the fed rate on
  template worlds (from 1.39 times it) and below it procedurally; the term
  withholds 27% of famine births and 5% in dearth.
* **Rebound.** In the five fed turns after a famine births run 59% above the
  fed rate on template worlds (41% before) and 15% procedurally (17%), from
  the crowding brake and the recovering satisfaction gate.
* **Disease.** The epidemic multipliers now follow hunger: 1.05 when fed
  (1.07 before, from cooldowns), 1.37 in famine (1.21). Famine epidemic
  deaths rise from 1.75-1.8 to 2.4-2.5 times the fed rate; epidemic deaths
  over all region-turns fall (3.9 to 3.7 template, 7.1 to 5.4 procedural),
  since fed and lean regions no longer carry a report's boost.
* **Population.** Lower by about 12% on template worlds and 5% (mean)
  procedurally; no world dies.
* **Migration.** Unchanged on template worlds, -3.5% procedurally; famine
  memory still leads 42% of moves.

## 6. Agents off

The aggregate model already had a famine toll; it is scaled, not doubled.
Its reports fire on yields below 0.12, most (58%) in regions short for ten
turns or more, at a median depth of 0.39 below the threshold, so the median
report now takes 2 people where it took 5, and a near-total failure the old
5. Template worlds (the same on *main* and *3355289*: cities need agents):

| `--agents off` | base | head |
| --- | ---: | ---: |
| seeds 42-51, 200 turns: mean population | 210.3 | 215.7 |
| lowest population after turn 10 | 29 | 33 |
| famine reports per run | 130.0 | 130.6 |
| seeds 42-45, 500 turns: mean population | 200.6 | 205.2 |
| lowest population after turn 10 | 16 | 24 |
| extinct worlds | 0 | 0 |

An earlier version also scaled the aggregate growth of a region under a
famine cooldown by the agents' birth multiplier. It counted hunger twice
and, by chance, pushed the bundle-guard world to 17-18 polities and 24.4-24.9
MB on the no-Rust path, over the 24 MB guard; over six seeds of that world's
configuration the sizes were unchanged on average (20.4 MB base, 20.9 MB).
It was removed (`ca859b7`); hybrid runs never take that path, and three
hybrid worlds (template seed 42 for 120 turns and 43 for 200, procedural seed 7
with 48 regions and 10 civs for 100) are byte-identical with and without it, so the gates in section 7 stand.

Golden oracles (Python off mode, native runtimes disabled) are rolled forward
as `corrected_hunger_2026_10.json` (turn hashes, RNG traces) and
`corrected_artifacts_hunger_2026_10.json` (artifact bytes, both
projections), with the `hunger` link in `ORACLE_CHAIN`;
`corrected_food_logistics_2026_10*` stay frozen. Consecutive captures, first
changed turn per workload:

| Correction | single | standard | wide | Artifact files changed |
| --- | --- | --- | --- | --- |
| HM-DEARTH-WEIGHT | - | - | - | none (dearth exists only in agent modes) |
| HM-EPIDEMIC-HUNGER | - | - | - | none (agent modes; the lane runs without epidemics) |
| HM-NATIVE-DEMOGRAPHY | - | - | - | none (native agents only) |
| HM-AGGREGATE-TOLL | - | 0 | 9 (RNG trace changes) | standard and wide: state, bundle, memories |

The capture script reproduced the food-logistics oracles exactly on
`3355289` before the change, and the rolled oracles hold on the merged head
(city markets pin cities off in the benchmark workloads).

## 7. Gates

Subset gates (20 seeds x 200 turns, hybrid, `chronicler.validation_compare`
against the base's own subset report; in the subset only community, needs and
cohort are required):

| Oracle | *main* 42-61 base | head | *main* 62-81 base | head |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS; - | PASS; NO REGRESSION | PASS; - | PASS; NO REGRESSION |
| needs (seeds; median effect) | 16; 1.17 | 15; 1.00 | 16; 1.00 | 15; 1.00 |
| cohort (seeds; median effect) | 20; 1.16 | 20; 1.17 | 20; 1.27 | 19; 1.02 |
| arcs (three types; families) | 15; 5 | 18; 5 | 15; 5 | 15; 6 |
| artifacts | PARTIAL 2.80, 2.5% | PASS 2.56, 3.9% | PASS 2.85, 2.6% | PASS 2.87, 5.7% |
| regression (status) | PASS (strict) | FAIL (civ_survival) | FAIL (rebellion, civ_survival) | FAIL (rebellion, civ_survival) |
| satisfaction mean; latest | 0.591; 0.603 | 0.598; 0.616 | 0.608; 0.619 | 0.620; 0.627 |
| migration per agent-turn | 0.0619 | 0.0599 | 0.0548 | 0.0526 |
| rebellion per agent-turn | 0.0376 | 0.0330 | 0.0153 | 0.0122 |
| all founders surviving (limit 0.20) | 0.20 | 0.25 | 0.35 | 0.30 |
| final population min / median / max | 115 / 176 / 262 | 64 / 150 / 256 | 125 / 175.5 / 247 | 91 / 154 / 224 |
| extinct | 0 | 0 | 0 | 0 |

The 42-61 regression FAIL is the founders' survival (0.25 against 0.20,
informational in the subset; the full gate reads it, 0.07). *3355289*
subsets (cities off) against their base: 42-61 PASS / NO REGRESSION (needs
13 -> 15, migration 0.0597 -> 0.0581, rebellion 0.0350 -> 0.0331, latest
satisfaction 0.616 -> 0.627); 62-81 PASS / NO REGRESSION (needs 14 -> 13,
migration 0.0550 -> 0.0535, rebellion 0.0130 -> 0.0194, latest satisfaction
0.619 -> 0.626).

Full gates (200 seeds x 500 turns, hybrid, `--parallel 2`, seed directories
deleted once the reports and a per-seed extract were kept):

| Oracle | *main* base (city-markets report) | **head** `223e23a` | *3355289* base (nav-famine report) | *3355289* branch `709f330` |
| --- | --- | --- | --- | --- |
| gate; comparator | PASS; NO REGRESSION | **PASS; NO REGRESSION** | PASS; NO REGRESSION | PASS; NO REGRESSION |
| community (seeds) | 200 | 200 | 200 | 200 |
| needs (seeds; median effect) | 189; 1.41 | 186; 1.41 | 196; 1.41 | 189; 1.41 |
| cohort (seeds; median effect) | 200; 1.63 | 200; 1.62 | 200; 1.63 | 200; 1.65 |
| era (seeds with inflections; silent collapses) | 200; 0 | 200; 1 | 200; 0 | 200; 1 |
| arcs (seeds with three types; families) | 166; 6 | 167; 6 | 168; 6 | 158; 6 |
| artifacts (status; creation; loss) | PASS; 1.43; 6.3% | PASS; 1.32; 7.5% | PASS; 1.49; 4.5% | PASS; 1.43; 4.2% |
| regression (status) | PASS (strict) | PASS (strict) | PASS (strict) | PASS (strict) |
| satisfaction mean; latest (ceiling 0.65) | 0.605; 0.618 | 0.612; 0.622 | 0.607; 0.620 | 0.612; 0.624 |
| migration per agent-turn (strict floor 0.05) | 0.0580 | 0.0554 | 0.0576 | 0.0553 |
| rebellion per agent-turn (0.02-0.08) | 0.0308 | 0.0301 | 0.0314 | 0.0307 |
| all founders surviving (limit 0.20) | 0.12 | 0.07 | 0.11 | 0.12 |
| extinct worlds | 0 | 0 | 0 | 0 |
| final population min / median / max | 70 / 177 / 328 | 49 / 165 / 326 | 60 / 199.5 / 342 | 46 / 173 / 299 |

The head's gate ran on the merged tree before `ca859b7` removed the
aggregate growth term; hybrid runs do not take that path and are
byte-identical with and without it (section 6). 2,693 s on the shared host
(the *3355289* gate 2,461 s). One world of 200 has a silent collapse (a
population fall without a recorded crisis) in each branch gate, against 0;
the limit is 10% of seeds.

| Per run (200 worlds, 500 turns) | *main* base | head |
| --- | ---: | ---: |
| population at turn 500 | 182.4 | 168.4 |
| agent deaths / births | 1,537.7 / 1,521.2 | 1,400.0 / 1,369.5 |
| food-crisis reports (famine / dearth) | 131.6 / 203.4 | 120.2 / 193.9 |
| epidemic reports | 172.7 | 135.3 |
| civ plague outbreaks | 34.0 | 28.8 |
| mass migrations | 181.7 | 154.2 |
| agent migrations | 5,408.1 | 4,758.3 |
| agent rebellions | 2,868.0 | 2,584.4 |
| wars | 19.0 | 20.6 |
| cities founded | 6.3 | 6.0 |
| polities alive at turn 500 | 2.81 | 2.71 |

Population falls 8% over 500 turns. Migration per agent-turn falls 0.0026
(4.5%) to 0.0554, 0.0054 above the strict floor: fewer hungry people means
fewer famine memories (migration weights unchanged). Latest satisfaction
rises 0.004, 0.028 under the ceiling. Epidemic reports fall 22%: fed and
lean regions no longer carry a report's boost.

## 8. Tick time and bundle size

`scripts/agent_scale_benchmark.py`, seed 42, 12 regions, starting targets
18,800 and 43,700, 20 warm-up turns and 8 timed turns, two repeats, one
child at a time, release builds; base `ec229b5`, head the merged tree
(before agent movements), on the shared 4-core host. Medians per run, wall /
process CPU, in ms:

| alive (base; head) | | base | head |
| --- | --- | ---: | ---: |
| 21,643; 23,097 | Rust tick | 87, 87 / 219, 211 | 99, 101 / 255, 248 |
| | whole turn | 144, 146 / 283, 278 | 161, 160 / 353, 379 |
| 52,855; 51,354 | Rust tick | 398, 388 / 1,288, 1,301 | 337, 370 / 1,154, 1,207 |
| | whole turn | 495, 482 / 1,670, 1,654 | 446, 465 / 1,539, 1,583 |

Rust tick CPU per alive agent: 10.0 against 10.9 us at about 22k, 24.5
against 23.0 us at about 52k. The worlds diverge from the first famine, so
the two arms are not the same work; the hunger terms are two component
evaluations per region and one multiplication per agent's death and birth
rates.

Bundle guard world (`tests/test_bundle.py::TestBundleSize`: seed 1, 500
turns, 10 regions, 5 civs, `--agents off`, every default). The scaled
aggregate toll changes its history:

| Guard world | base (`ec229b5`) | head |
| --- | ---: | ---: |
| native | 18.78 MB, 13 polities over the run | 16.44 MB (17,236,056 bytes), 11 polities |
| no-Rust | 19.92 MB, 13 polities | 22.21 MB (23,285,909 bytes), 16 polities |

(MB is 2^20 bytes.) The 24 MB limit stays.

## 9. Why no switch

The brief makes this a correction to the simulation. The evidence does not
argue for a switch: the shipped terms pass the full gate strictly with no
regression against `main` (section 7), every guard holds, and a world in
which hunger cannot kill or lower births is the defect being corrected, not
an alternative worth keeping. `--agents off` keeps its own (graded) model.

## 10. Verification

Final head `be99dbe` (merged with `main` `48b72be`, PR #31 agent movements,
default off), extension built fresh (SHA-256 `5d58881c…bf21da`), shared
4-core host (`-n 2`). With movements off, hybrid template seed 42 (120
turns), procedural seed 7 (48 regions, 10 civs, 100 turns) and agents-off
seed 42 (150 turns) are byte-identical to `ca859b7`, so the gates above
stand for it.

| Check | Result |
| --- | --- |
| `cargo test --locked` (debug info off) | 963 passed, 2 ignored (`main` `e979fd9`: 945; +4 here, +14 movements) |
| `pytest -m "not slow" -n 2` | 6,099 passed, 3 skipped, 526 subtests |
| `pytest -m slow -n 2` | 11 passed, 3 skipped (`TestBundleSize` 16.44 MB) |
| No-Rust lane (virtualenv without `chronicler_agents`, every test) | 5,879 passed, 223 skipped, 526 subtests |
| `scripts/run_python_oracle_checks.py` | PASS in 76.0 s: 2,068 passed, 25 skipped; largest chunk `systems-2` 27.0 s of 110 s |
| Golden fixtures | rolled forward (section 6); `ORACLE_CHAIN` link `hunger` |
| Viewer | not touched |

New tests: `tests/test_hunger_mortality.py` (17, one native: the tick's
hunger terms appear while a region starves and reset when fed), in the
oracle lane's `systems-2` chunk; Rust `demographics` (components,
vulnerability, multipliers) and `tick` (a starving region's expected deaths
and births).

Changed expectations, each because a dearth or the aggregate toll now acts
by severity:

* `tests/test_food_crisis_labels.py`: a first-turn dearth drains 1
  stability (was 3) and marks its cooldown; a shadow dearth at 0.9 takes no
  toll (was 5), a total shadow famine the full 5.
* `tests/test_ecology_harvest_timing.py`: the agent-mode report tests expect
  the dearth drain (79, was 77) and a shadow toll from the measured hunger;
  the refugee test's toll follows the report's hunger (off: yield depth;
  shadow: no food on a first turn).
* `tests/test_ecology.py::TestFamineSeverityScaling` and
  `tests/test_emergence.py` (famine amplified by stress): a near-total yield
  failure (0.0012; 0.0 falls back to subsistence); losses 4 and 7 (were 5
  and 7) and 73 (unchanged).
* `tests/test_snapshot_pruning.py`: the real run is 60 turns; the
  Thornwall Confederacy is pruned from turn 55 (was 44).
* `tests/test_bundle.py`: the guard world's sizes in the comment.
* `tests/test_performance_equivalence.py`, `test_governance_dormancy.py`,
  `test_historiography.py`, `test_languages.py`: read the hunger oracles;
  a scoped-difference test for the hunger artifacts.

## 11. Open items

* **Magnitudes at the low end.** Famine death rates reach about twice the
  fed rate (history: two to four times). The mid-range design is held back
  by the simulation, not the history: climate phases keep whole worlds in
  famine for 20-25 turns, and the goods economy's constant returns to farm
  labour mean deaths never relieve a famine. Diminishing returns to labour
  on land, or shorter climate famines, would let the terms rise.
* **Clocks.** A turn is a month for seasons and a year for ages, so a
  three-turn famine is a season of shortage and three years of demography.
  The famine ramp follows the label (three turns); the rates are annual.
* **Marriage.** Postponed marriages are not modelled; births carry the whole
  fertility response.
* **Flight.** No new flight term; the existing famine memory (below 0.6)
  still drives migration. Migration per agent-turn on the full gate fell
  0.0580 -> 0.0554 (strict floor 0.05).
* **Children's poverty.** A child's hazard does not read its household's
  wealth (only adults carry the poverty spread).
* **Dearth weight.** A third of a famine's report effects is a judgment;
  no measure here calibrates it.
* **Report lag.** The rates read live hunger, but report effects still wait
  for the five-turn cooldown; a dearth cooldown upgrades to famine weight
  when the shortage reaches famine severity.
* **Aggregate model.** Its hunger is the yield depth at the report; it has
  no dearth tier (no demand) and no duration.
* **The needs oracle at subset scale** turns on one or two agent pairs per
  seed: any change to histories redraws it (section 4). The full gate reads
  186 of 200 (base 189).
