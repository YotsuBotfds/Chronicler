"""Wiring and phase hooks for the livelihoods/commons sprint (default off).

Independent switches share one persisted container,
``WorldState.livelihoods`` (:mod:`chronicler.livelihoods_state`):

* ``--workshops`` (L1): staffed public workshops in selected cities;
* ``--food-allocation`` (L2): explicit allocation of regional food to people;
* ``--timber-stock`` (L3): a renewable harvestable timber stock;
* ``--grain-convoys`` (L4): multi-leg public grain convoys under risk;
* ``--commons-rules`` (L8): a paid, enforced harvest rule on the timber stock;
* ``--learning-cohorts`` (L5): named learners attending delivered academy teaching;
* ``--workshop-payroll`` (L6a): customers and payroll around the workshops;
* ``--relocation-costs`` (L7): a fare paid for ordinary household moves;
* ``--local-budgets`` (L9): one finite, bargained budget per ruler for relief,
  granary works and workshops.

The recovery-skills phase appends five more (RS0 groundwork: registered with
inert stub modules; their lanes add the mechanisms):

* ``--apprenticeship`` (RS1): named mentors and apprentices at operating
  workshop sites, and a workshop qualification by stable id;
* ``--repair-projects`` (RS2): paid repair projects for workshops and
  granaries;
* ``--veteran-reintegration`` (RS3): veterans captured at real roster
  releases, with priority access to work openings;
* ``--remittances`` (RS4): a diaspora ledger and bounded remittances along
  Marriage/Kin bonds;
* ``--clearing-protection`` (RS5): controller-funded protection of forest
  cover from clearing.

The productive-recovery phase appends:

* ``--operating-wear`` (PL2): funded operating workshop sites wear each turn,
  offset only by qualified upkeep (``--apprenticeship`` implies it).
* ``--timber-supply`` (PL1): named, paid woodcutting expeditions that carry
  timber from a forest of the civ to its repair projects.
* ``--recovery-crews`` (PL3): named granary repair crews paid from the granary's
  existing coins, and a wider workshop repair pool that admits veterans;
* ``--maintenance-obligation`` (PL3): a bounded L9 obligation reserved for RS2's
  planned repair charges before the budget is bargained.
* ``--household-retail`` (PL4, L6b): producer title of new harvest, owned
  food, paid provisioning, income replacement and relief in pilot regions.

The connected-world program appends:

* ``--watershed`` (B1): a conserved water account on the drainage graph of a
  procedural world; mode ``record_only`` changes nothing outside its record.
* ``--wealth-accounting`` (A1): an observation-only ledger of agent wealth per
  region and turn (opening, typed flows from the packages' receipts, closing,
  the labelled native-model residual); appended last so its Phase 2 and Phase 10
  hooks run after every other package's. It changes nothing it observes.

This module owns only CLI forwarding, validation of prerequisites and the
fan-out of phase hooks to each package's module ``chronicler.<switch>``.
State, decisions and accounting belong to those modules. An omitted switch
keeps the saved state; a world that never enabled one has no container, no
snapshot key, no checkpoint flag and no manifest entry, so feature-off runs
keep their exact serialized output.

Package module protocol (each function optional unless noted):

``set_<name>_enabled(world, value, *, args, agent_mode)`` (required),
``<name>_active(world)`` (required), ``snapshot_summary(world)`` (required),
``reserve_first(world, agent_bridge, snapshot)`` (Phase 2, before every
package's ``prepare_phase2``: reservations of work held across turns),
``prepare_phase2(world, region_input, agent_bridge, snapshot, acc)`` returning
the region batch, ``finish_phase2(world, economy_result, agent_bridge, acc)``,
``rollback_phase2(world)``, ``before_agent_tick(world, agent_bridge,
economy_result)``, ``after_agent_tick(world, agent_bridge)``,
``on_pool_reset(world)`` (see :func:`bind_native_pool`), ``rollback_agent_tick(world, agent_bridge)`` (the before hooks or the agent
tick raised: release what is still pending natively, charge nothing),
``phase10_before_reserves(world, acc, economy_result, agent_bridge)`` and
``phase10(world, acc, economy_result, agent_bridge)``; event-returning hooks
return a list. ``before_ecology(world, acc, native=...)`` and ``after_ecology(world,
acc)`` (event-returning) run immediately before the Phase 9 region sync and
after the ecology tick, in every agent mode.
"""
from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState

#: Non-boolean options, with their choices (first: the default when enabled).
LIVELIHOODS_CHOICES: dict[str, tuple[str, ...]] = {
    "workshop_mode": ("operate", "observe", "cost_only"),
    "food_allocation_regime": ("floor_means", "equal", "targeted_relief"),
    "convoy_route_policy": ("adaptive", "cheapest", "safest"),
    "commons_rule_mode": ("enforced", "cost_only"),
    "learning_cohort_mode": ("learn", "no_learning"),
    "workshop_payroll_mode": ("paid", "unpaid_labor", "no_customer"),
    "relocation_mode": ("paid", "assisted", "liquidity_only"),
    "local_budget_mode": ("bargained", "fixed_shares"),
    "apprenticeship_mode": ("train", "no_qualification"),
    "repair_mode": ("repair", "cost_only"),
    "veteran_mode": ("priority", "record_only"),
    "remittance_mode": ("send", "record_only"),
    "clearing_protection_mode": ("enforced", "cost_only"),
    "timber_supply_mode": ("supply", "cost_only"),
    "recovery_crew_mode": ("paid", "unpaid"),
    "maintenance_obligation_mode": ("reserve", "reserve_only"),
    "apprenticeship_rules": ("2", "1"),
    "household_retail_mode": ("retail", "no_relief", "free_exchange", "record_only"),
    "household_retail_boundary": ("market", "paid_work", "all", "schedule"),
    "household_retail_rules": ("2", "1"),
    "watershed_mode": ("record_only",),
}
#: All parser destinations owned here (``batch_manifest.SIMULATION_ARG_KEYS``).
LIVELIHOODS_ARG_KEYS: tuple[str, ...] = (
    "workshops", "workshop_mode", "food_allocation", "food_allocation_regime",
    "timber_stock", "grain_convoys", "convoy_route_policy", "commons_rules", "commons_rule_mode",
    "learning_cohorts", "learning_cohort_mode",
    "workshop_payroll", "workshop_payroll_mode",
    "relocation_costs", "relocation_mode",
    "local_budgets", "local_budget_mode",
    "apprenticeship", "apprenticeship_mode",
    # PL2 review: inserted beside its switch (a choice belongs to the switch
    # declared before it, ``feature_catalog``), not appended.
    "apprenticeship_rules",
    "repair_projects", "repair_mode",
    "veteran_reintegration", "veteran_mode",
    "remittances", "remittance_mode",
    "clearing_protection", "clearing_protection_mode",
    "operating_wear",
    "timber_supply", "timber_supply_mode",
    "recovery_crews", "recovery_crew_mode",
    "maintenance_obligation", "maintenance_obligation_mode",
    "household_retail", "household_retail_mode", "household_retail_boundary",
    "household_retail_rules",
    "watershed", "watershed_mode",
    "wealth_accounting",
)
#: Options that take a file path (A2R), parser destinations owned here too
#: (``batch_manifest.SIMULATION_ARG_KEYS``). Command line only: the feature
#: catalog serves switches and choices, and a browser cannot hand the server
#: a file, so the choices that need one are not served either
#: (``feature_catalog.CLI_ONLY_CHOICES``).
LIVELIHOODS_PATH_KEYS: tuple[str, ...] = ("household_retail_schedule",)
_AGENT_ECONOMY = ("hybrid", "shadow", "demographics-only")

_HELP = {
    "workshops": (
        "Staffed public workshops: up to four selected cities employ named adult "
        "urban farmers' already-diverted time; with --workshop-mode operate the "
        "controller's treasury pays construction and upkeep as a public cost (no "
        "wages) and the crew's work replaces the region's craft ceiling; requires "
        "--agents hybrid and cities (default off)"
    ),
    "workshop_mode": "operate (default): treasury-funded crews replace the craft ceiling; observe: crews and native craft inputs only; cost_only: the ablation that builds and pays but keeps the legacy ceiling",
    "food_allocation": (
        "Allocate each region's available food to its people and derived households "
        "under an explicit rule; individual hunger, needs and mortality read the "
        "person's own allocation; requires --agents hybrid (default off)"
    ),
    "food_allocation_regime": (
        "floor_means (default): an equal subsistence floor, the scarce remainder by "
        "household means; equal: equal per person (reproduces the regional signal); "
        "targeted_relief: equal market food, public granary release to the worst off"
    ),
    "timber_stock": (
        "Renewable harvestable timber stock: realized timber extraction debits it, "
        "regrowth takes turns under forest cover and water, harvest cannot exceed it; "
        "requires an agent-backed economy (default off)"
    ),
    "grain_convoys": (
        "Multi-leg public grain convoys: paid foreign purchases travel leg by leg, "
        "can be delayed, rerouted, turned back, captured or lost; requires "
        "--public-grain-shipments (default off)"
    ),
    "convoy_route_policy": "adaptive (default), cheapest or safest route choice at dispatch",
    "commons_rules": (
        "Commons rules on the timber stock: a region's controller may adopt a harvest "
        "quota with a rest period on a depleted, harvested stand, paying wardens from its "
        "treasury; partial payment leaves part of the stand open access; requires "
        "--timber-stock (default off)"
    ),
    "commons_rule_mode": "enforced (default): the rule lowers the harvest cap; cost_only: the ablation that adopts and pays identically but applies no cap",
    "learning_cohorts": (
        "Named learners at academies: finite cohorts of present adults attend actual "
        "delivered academy teaching, give up part of their ordinary income, and on "
        "completion gain skill in their trade; requires --agents hybrid and "
        "--academy-services (default off)"
    ),
    "learning_cohort_mode": "learn (default): completion raises the learner's trade skill; no_learning: the cost-retaining control (same attendance, cost and supplies, no skill gain)",
    "workshop_payroll": (
        "Workshop payroll (L6a): each operating workshop becomes a debt-free firm with cash and "
        "owned wares; an academy of the region's ruler (--academy-services) buys them with real "
        "treasury money, sales fund wages that replace the crew's ordinary income share, and "
        "unpaid wages cut hours, then crew, then close the firm; requires --workshops in operate "
        "mode (default off)"
    ),
    "workshop_payroll_mode": (
        "paid (default); unpaid_labor: the ablation that sells and replaces the income share "
        "but pays no wage; no_customer: wages are owed but nothing is sold"
    ),
    "relocation_costs": (
        "Costly voluntary relocation (L7): an ordinary household move costs a fare per person "
        "(children included) that the adult movers must hold at the household gate and pay "
        "after the move is applied; requires --agents hybrid and no household-mobility liquid "
        "requirement (default off)"
    ),
    "relocation_mode": (
        "paid (default); assisted: the destination's ruler funds a bounded share of the fare "
        "for households short of it; liquidity_only: the control that requires the fare but "
        "charges nothing"
    ),
    "local_budgets": (
        "Local collective budgets: each ruler commits one finite projected budget "
        "to bargained envelopes for granary relief purchases, granary works and "
        "workshop bills; those services spend only within an accepted envelope; "
        "delivered or broken promises move the city's grievance; requires "
        "--agents hybrid and --grain-reserves (default off)"
    ),
    "local_budget_mode": (
        "bargained (default): constituencies' allocations arbitrated by influence, "
        "with political response; fixed_shares: the control, the same budget split "
        "by fixed declared shares, no bargaining and no response"
    ),
    "apprenticeship": (
        "Apprenticeship and skill continuity (RS1): qualified crew members mentor named "
        "apprentices at operating workshop sites; apprentices give up part of their ordinary "
        "income (a stipend with --workshop-payroll) and on completion earn a workshop "
        "qualification by stable id, kept for life; qualified people perform upkeep against "
        "site wear; requires --workshops in operate mode (--agents hybrid) (default off)"
    ),
    "apprenticeship_mode": (
        "train (default): completion grants the qualification; no_qualification: the "
        "cost-retaining control (same wear, attendance and costs, no new qualifications)"
    ),
    "apprenticeship_rules": (
        "RS1 rules version of a new apprenticeship state: 2 (default): attendance by region, "
        "portable progress, training on the job (PL2); 1: the recovery-skills phase's rules "
        "exactly (presence in the city box, seats before the crew, the consecutive-miss "
        "dropout). A saved state keeps its version; a conflicting value is refused on resume"
    ),
    "repair_projects": (
        "Repair projects (RS2): paid projects rebuild workshop sites and granaries from their "
        "real condition and war damage, with named workers, timber and the controller's coins; "
        "they replace the L1 lump repair; requires --agents hybrid and --workshops or "
        "--grain-storage (default off)"
    ),
    "repair_mode": (
        "repair (default): delivered work restores condition; cost_only: the cost-retaining "
        "control (reserves, pays and uses timber identically, condition unchanged)"
    ),
    "veteran_reintegration": (
        "Veteran reintegration (RS3): soldiers released from real armies are recorded by stable "
        "id and get priority, among otherwise eligible candidates, for workshop crew, "
        "apprenticeship and repair openings; nothing is guaranteed or created; requires "
        "--agents hybrid and one of --workshops, --apprenticeship or --repair-projects "
        "(default off)"
    ),
    "veteran_mode": (
        "priority (default): eligible veterans come first for openings; record_only: the "
        "control that captures and tracks veterans without priority"
    ),
    "remittances": (
        "Remittances (RS4): a diaspora ledger of applied migrations; settled migrants send a "
        "bounded share of their wealth along Marriage/Kin bonds to the region they left, with "
        "a courier fee and exactly-once receipts; requires --agents hybrid (default off)"
    ),
    "remittance_mode": (
        "send (default); record_only: the control that keeps the ledger and sends nothing"
    ),
    "clearing_protection": (
        "Funded clearing protection: a region's controller may protect up to two forested "
        "regions under population-driven clearing, paying wardens from its treasury for each "
        "turn the clearing is active; the paid share of the clearing is suspended at the "
        "ecology's clearing decision (native and Python); works in every agent mode (default off)"
    ),
    "clearing_protection_mode": (
        "enforced (default): the paid protection suspends clearing; cost_only: the control that "
        "adopts and pays identically but leaves the clearing unchanged"
    ),
    "operating_wear": (
        "Workshop operating wear (PL2): each funded operating workshop site loses 0.02 condition a "
        "turn, offset only by the upkeep of qualified crew members (--apprenticeship); a worn site "
        "stops until repaired. --apprenticeship implies it; --workshops --operating-wear is the "
        "reference arm with the same maintenance assumption; requires --workshops in operate mode "
        "(--agents hybrid) (default off)"
    ),
    "timber_supply": (
        "Timber supply (PL1): when RS2 repair projects lack timber, a named, paid crew of adults "
        "from the needing region (veterans first) walks to a forest of its civ or of nobody "
        "within two hops, cuts for a season and carries the timber home to the projects; their "
        "farm labour leaves the home economy, the harvest is debited from the L3 stock, wages "
        "come from the controller's treasury; requires --agents hybrid, --repair-projects and "
        "--timber-stock (default off)"
    ),
    "timber_supply_mode": (
        "supply (default); cost_only: the cost-retaining control (the same expeditions, crews, "
        "travel, wages and home labour removal, no cutting: no timber and no stock debit)"
    ),
    "recovery_crews": (
        "Recovery crews (PL3): granary repair work is done by a named crew of adult farmers "
        "resident in the granary's region, reserved for the turn and paid the granary's existing "
        "coins per work as wages by stable id (no new money); workshop repair crews draw on the "
        "site's whole region and admit eligible veterans of any non-enlisted occupation, their "
        "paid share withheld from ordinary income; requires --agents hybrid and --repair-projects "
        "(default off)"
    ),
    "recovery_crew_mode": (
        "paid (default): the granary coins go to the crew as wages; unpaid: the control with the "
        "same crews, income withheld and the same charge, the coins leaving the economy as before"
    ),
    "maintenance_obligation": (
        "Maintenance obligation (PL3): before the L9 budget is bargained each ruler reserves its "
        "repair projects' planned per-turn charges, capped at a declared share of the budget; "
        "requires --local-budgets and --repair-projects (default off)"
    ),
    "maintenance_obligation_mode": (
        "reserve (default): repairs may spend the reservation beyond their bargained envelope; "
        "reserve_only: the crowding-out control that reserves the same amount but keeps repairs to "
        "their envelope and returns the reservation unspent"
    ),
    "household_retail": (
        "Household food retail (L6b): in pilot regions most of each new harvest belongs to its "
        "farmers by stable id; owners' households eat their own food and sell the rest to "
        "neighbours at the clamped market price, buyers pay from their wealth, farmers' ordinary "
        "farm income is replaced by their sales; commons and granary releases stay free; requires "
        "--agents hybrid and --food-allocation (default off)"
    ),
    "household_retail_mode": (
        "retail (default); no_relief: the whole harvest titled, L2's rule on the commons, no means "
        "test; free_exchange: the same title and rounds at price 0 with farm income kept; "
        "record_only: the control that computes the pilot and the would-be title and changes nothing"
    ),
    "household_retail_boundary": (
        "market (default): each ruler's capital region, sticky; paid_work: regions where paid work has "
        "been done (an open workshop firm, a paid repair or granary crew, or the home of a paid "
        "woodcutting crew), sticky; all: every controlled region (stress)"
    ),
    "household_retail_rules": (
        "Retail rules version of a new retail state: 2 (default): each conquest, siege turn and "
        "occupation start destroys the share of pilot regions' owned food it destroys of their commons, "
        "once per event, recorded with its cause, actor and victim; 1: checkpoints 2-3 exactly (the "
        "conquest share once per turn, siege and occupation leave owned food alone). A saved state "
        "keeps its version; a conflicting value is refused"
    ),
    "household_retail_schedule": (
        "With --household-retail-boundary schedule (command line only): a JSON file of exact pilot "
        "intervals {region index: [[open, close], ..., [open, null]]}, as scripts/retail_schedule.py "
        "writes them from a bundle's recorded intervals; a region is in the pilot on the turns open <= "
        "turn < close while it has a controller and leaves when its interval ends, even with a "
        "controller (a frozen enrollment, e.g. one arm's replayed in another). The first-turn format "
        "{region index: opening turn} (in the pilot from that turn on while it has a controller) is "
        "approximate: it cannot replay a region the source closed. The schedule and its SHA-256 are "
        "saved with the state; a resume keeps it and refuses a different one"
    ),
    "watershed": (
        "Watershed account (B1): a conserved water account on the drainage graph rebuilt from the "
        "world's saved procedural elevation (precipitation, storage, evaporation, irrigation "
        "withdrawal, downstream transfer, outflow to the sea), with closure checked every turn, "
        "floods and droughts recorded with their conditions, and the water index the account would "
        "derive recorded beside the one the simulation uses; requires a procedural world (template "
        "worlds have no elevation); opens with a new world (default off)"
    ),
    "watershed_mode": (
        "record_only (default, the only mode of this slice): the account runs beside the existing "
        "water index and changes nothing outside its own record"
    ),
    "wealth_accounting": (
        "Wealth accounting (A1): an observation-only ledger of agent wealth; each turn and region it "
        "reads the balance at the Phase 2 opening (checked bit for bit against the last closing) and "
        "after every payer, records the typed flows from the packages' receipts (wages, stipends, "
        "purchases, procurement, remittances, fares, domestic credit), the paid-work income each "
        "package withheld and the treasury side, and labels the rest as unitemized native model "
        "flows; changes nothing; requires --agents hybrid (default off)"
    ),
}


def add_livelihoods_arguments(parser: argparse.ArgumentParser, *, forwarding: bool = False) -> None:
    for name in LIVELIHOODS_ARG_KEYS:
        flag = "--" + name.replace("_", "-")
        prefix = f"Forward {flag} to every run. " if forwarding else ""
        if name in LIVELIHOODS_CHOICES:
            parser.add_argument(flag, choices=LIVELIHOODS_CHOICES[name], default=None,
                                help=prefix + _HELP[name])
        else:
            parser.add_argument(flag, action=argparse.BooleanOptionalAction, default=None,
                                help=prefix + _HELP[name])
    for name in LIVELIHOODS_PATH_KEYS:
        flag = "--" + name.replace("_", "-")
        prefix = f"Forward {flag} to every run. " if forwarding else ""
        parser.add_argument(flag, metavar="PATH", default=None, help=prefix + _HELP[name])


def livelihoods_arguments(args: Any) -> list[str]:
    """Forward explicit requests, including explicit disables, to child runs."""
    flags = []
    for name in LIVELIHOODS_ARG_KEYS:
        value = getattr(args, name, None)
        if value is None:
            continue
        flag = name.replace("_", "-")
        if name in LIVELIHOODS_CHOICES:
            if value not in LIVELIHOODS_CHOICES[name]:
                raise ValueError(f"{name} must be one of {LIVELIHOODS_CHOICES[name]}")
            flags.append(f"--{flag}={value}")
        elif isinstance(value, bool):
            flags.append("--" + ("" if value else "no-") + flag)
        else:
            raise ValueError(f"{name} must be a boolean or None")
    for name in LIVELIHOODS_PATH_KEYS:
        value = getattr(args, name, None)
        if value is None:
            continue
        if not isinstance(value, (str, Path)) or not str(value):
            raise ValueError(f"{name} must be a path or None")
        # Absolute, so a child run reads the same file from any directory.
        flags.append(f"--{name.replace('_', '-')}={Path(value).resolve()}")
    return flags


class LivelihoodsRefusal(ValueError):
    """A refused resume of a saved livelihoods switch (RL3): the run cannot
    honour the saved state and names the option that ends it.

    A plain ``ValueError`` to every caller (tests, library callers, the live
    lobby, which reports it and reopens, batch workers, threads and asyncio
    tasks). Only at the command line, where nothing catches it, it is shown
    as one line: constructing one installs :func:`_refusal_excepthook`, so an
    uncaught refusal prints ``Error: <message>`` without a traceback and the
    interpreter exits with status 1, as ``main``'s own refusals do (``main.py``
    is pinned, so the clean refusal lives here). ``code`` holds that line.
    (A5's first version also subclassed ``SystemExit``, which a thread
    swallows and asyncio takes for a shutdown; review A5, finding 4.)"""

    def __init__(self, message: str):
        super().__init__(message)
        self.code = f"Error: {message}"
        _install_refusal_excepthook()


def _refusal_excepthook(previous):
    def hook(kind, value, traceback):
        if isinstance(value, LivelihoodsRefusal):
            print(value.code, file=sys.stderr)          # the interpreter then exits with status 1
            return
        previous(kind, value, traceback)
    hook.livelihoods_refusal = True
    return hook


def _install_refusal_excepthook() -> None:
    """Show an uncaught :class:`LivelihoodsRefusal` as its one-line message
    (every other exception goes to the hook that was installed before);
    idempotent. Installed when a refusal is first constructed, so a process
    that never refuses anything keeps its hook untouched."""
    if not getattr(sys.excepthook, "livelihoods_refusal", False):
        sys.excepthook = _refusal_excepthook(sys.excepthook)


def livelihoods_state(world: Any) -> LivelihoodsState | None:
    state = getattr(world, "livelihoods", None)
    if state is not None and not isinstance(state, LivelihoodsState):
        raise TypeError("world.livelihoods must be LivelihoodsState or None")
    return state


def _module(name: str):
    return import_module("chronicler." + name)


def _on(world: Any, values: dict, name: str) -> bool:
    """Requested on, or omitted with a saved enabled state."""
    saved = getattr(livelihoods_state(world), name, None)
    return values[name] is True or (values[name] is None and saved is not None and bool(saved.enabled))


def _workshops_operate(world: Any, values: dict, args: Any) -> bool:
    """``--workshops`` on in operate mode (explicit or saved), as L6a checks it."""
    saved = getattr(livelihoods_state(world), "workshops", None)
    mode = getattr(args, "workshop_mode", None) or (saved.mode if saved is not None else "operate")
    return _on(world, values, "workshops") and mode == "operate"


def _grain_storage_on(world: Any) -> bool:
    """Grain storage assets enabled (``main`` applies ``--grain-storage`` first)."""
    from chronicler.grain_reserves_state import grain_reserves_on
    return grain_reserves_on(world) and getattr(world.grain_reserves, "storage", None) is not None


def _check_prerequisites(world: Any, values: dict, agent_mode: str, args: Any = None) -> None:
    if values["watershed"] is not None or getattr(livelihoods_state(world), "watershed", None) is not None:
        # Procedural geography; opens with a new world; a resume cannot end it
        # or change its mode (chronicler.watershed.check_request).
        from chronicler.watershed import check_request
        check_request(world, values["watershed"], args)
    if values["workshops"] is True:
        if agent_mode != "hybrid":
            raise ValueError("--workshops requires --agents hybrid")
        if getattr(world, "cities", None) is None:
            raise ValueError("--workshops requires cities")
    if values["food_allocation"] is True and agent_mode != "hybrid":
        raise ValueError("--food-allocation requires --agents hybrid")
    if values["timber_stock"] is True and agent_mode not in _AGENT_ECONOMY:
        raise ValueError("--timber-stock requires an agent-backed economy")
    if values["grain_convoys"] is True:
        reserves = getattr(world, "grain_reserves", None)
        if reserves is None or getattr(reserves, "shipments", None) is None:
            raise ValueError("--grain-convoys requires --public-grain-shipments")
    if values["commons_rules"] is True:
        saved = getattr(livelihoods_state(world), "timber_stock", None)
        if values["timber_stock"] is False or (values["timber_stock"] is None
                                               and not getattr(saved, "enabled", False)):
            raise ValueError("--commons-rules requires --timber-stock")
    if values["learning_cohorts"] is True:
        if agent_mode != "hybrid":
            raise ValueError("--learning-cohorts requires --agents hybrid")
        services = getattr(getattr(world, "scholarship", None), "learning_services", None)
        if services is None or not getattr(services, "enabled", True):
            raise ValueError("--learning-cohorts requires --academy-services")
    if values["workshop_payroll"] is True:
        saved = getattr(livelihoods_state(world), "workshops", None)
        on = values["workshops"] is True or (values["workshops"] is None and saved is not None and saved.enabled)
        mode = getattr(args, "workshop_mode", None) or (saved.mode if saved is not None else "operate")
        if not on or mode != "operate" or agent_mode != "hybrid":
            raise ValueError("--workshop-payroll requires --workshops in operate mode (--agents hybrid)")
    if values["relocation_costs"] is True:
        if agent_mode != "hybrid":
            raise ValueError("--relocation-costs requires --agents hybrid")
        from chronicler.household_mobility_state import liquid_requirement
        if liquid_requirement(world) > 0:
            raise ValueError("--relocation-costs cannot run with a household-mobility liquid requirement")
    if values["local_budgets"] is True:
        from chronicler.grain_reserves_state import grain_reserves_on
        if agent_mode != "hybrid" or not grain_reserves_on(world):
            raise ValueError("--local-budgets requires --agents hybrid and --grain-reserves")
    if values["apprenticeship"] is True:
        if agent_mode != "hybrid" or not _workshops_operate(world, values, args):
            raise ValueError("--apprenticeship requires --workshops in operate mode (--agents hybrid)")
    if values["repair_projects"] is True:
        # Workshops in any mode (only built sites have anything to repair:
        # observe mode builds none) or grain storage.
        if agent_mode != "hybrid" or not (_on(world, values, "workshops") or _grain_storage_on(world)):
            raise ValueError("--repair-projects requires --agents hybrid and --workshops or --grain-storage")
    if values["veteran_reintegration"] is True:
        if agent_mode != "hybrid" or not any(_on(world, values, name) for name in
                                             ("workshops", "apprenticeship", "repair_projects")):
            raise ValueError("--veteran-reintegration requires --agents hybrid and one of --workshops, "
                             "--apprenticeship or --repair-projects")
    if values["remittances"] is True and agent_mode != "hybrid":
        raise ValueError("--remittances requires --agents hybrid")
    if values["recovery_crews"] is True:
        if agent_mode != "hybrid" or not _on(world, values, "repair_projects"):
            raise ValueError("--recovery-crews requires --agents hybrid and --repair-projects")
    if values["maintenance_obligation"] is True:
        if not (_on(world, values, "local_budgets") and _on(world, values, "repair_projects")):
            raise ValueError("--maintenance-obligation requires --local-budgets and --repair-projects")
    # --clearing-protection has no prerequisite (it works in every ecology path).
    if values["operating_wear"] is True:
        if agent_mode != "hybrid" or not _workshops_operate(world, values, args):
            raise ValueError("--operating-wear requires --workshops in operate mode (--agents hybrid)")
    if _on(world, values, "timber_supply"):
        # Also when only saved (review A, 2026-11-06): a resume that turns RS2 or
        # L3 off would otherwise freeze the store and the live cargo unseen;
        # --no-timber-supply releases the store and deposits the cargo, dated.
        if agent_mode != "hybrid" or not _on(world, values, "repair_projects") \
                or not _on(world, values, "timber_stock"):
            saved = values["timber_supply"] is not True
            raise ValueError("--timber-supply requires --agents hybrid, --repair-projects and --timber-stock"
                             + ("; this world has it on: pass --no-timber-supply to end it" if saved else ""))
    if _on(world, values, "wealth_accounting") and agent_mode != "hybrid":
        # Also when only saved: the ledger reads the hybrid agent pool; a resume
        # outside hybrid is refused until the switch is ended (dated).
        saved = values["wealth_accounting"] is not True
        raise ValueError("--wealth-accounting requires --agents hybrid"
                         + ("; this world has it on: pass --no-wealth-accounting to end it" if saved else ""))
    if _on(world, values, "household_retail"):
        # Also when only saved: a resume that turns L2 off (or leaves hybrid)
        # would otherwise keep the claims, the owned food and the pilot regions
        # unseen; --no-household-retail closes every claim to the commons, dated.
        if agent_mode != "hybrid" or not _on(world, values, "food_allocation"):
            saved = values["household_retail"] is not True
            message = ("--household-retail requires --agents hybrid and --food-allocation"
                       + ("; this world has it on: pass --no-household-retail to end it (every claim "
                          "returns to its region's commons, dated)" if saved else ""))
            raise (LivelihoodsRefusal if saved else ValueError)(message)
    rules = getattr(args, "household_retail_rules", None) if args is not None else None
    retail = getattr(livelihoods_state(world), "household_retail", None)
    if rules is not None and retail is not None and str(rules) != retail.rules:
        # A saved state keeps the rules it recorded (refused before any change).
        from chronicler.household_retail import rules_conflict
        raise ValueError(rules_conflict(rules, retail))
    if getattr(args, "household_retail_schedule", None) is not None or (
            getattr(args, "household_retail_boundary", None) == "schedule"):
        # A2R: the schedule boundary's file, validated before any change.
        from chronicler.household_retail import check_schedule_request
        check_schedule_request(world, args, on=_on(world, values, "household_retail"), saved=retail)
    if agent_mode != "hybrid" and values["food_allocation"] is None and _on(world, values, "food_allocation"):
        # RL3: a saved L2 outside hybrid would otherwise run silently inert (no
        # bridge, no hooks) while the world still says it is on.
        raise LivelihoodsRefusal("--food-allocation requires --agents hybrid; this world has it on: resume with "
                                 "--agents hybrid, or pass --no-food-allocation to end it")


def configure_livelihoods(world: Any, args: Any, *, agent_mode: str) -> None:
    """Apply explicit switches after prerequisites (expansion features) are set."""
    values = {name: getattr(args, name, None) for name in LIVELIHOODS_SWITCHES}
    for name, value in values.items():
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean or None")
    for name, choices in LIVELIHOODS_CHOICES.items():
        value = getattr(args, name, None)
        if value is not None and value not in choices:
            raise ValueError(f"{name} must be one of {choices}")
    _check_prerequisites(world, values, agent_mode, args)
    state = livelihoods_state(world)
    for name, value in values.items():
        if value is None:
            continue
        if value is False and (state is None or getattr(state, name) is None):
            continue
        if state is None:
            state = world.livelihoods = LivelihoodsState()
        getattr(_module(name), f"set_{name}_enabled")(world, value, args=args, agent_mode=agent_mode)


def _present(world: Any):
    state = livelihoods_state(world)
    if state is None:
        return
    for name in LIVELIHOODS_SWITCHES:
        if getattr(state, name) is not None:
            yield name, _module(name)


#: Each option of ``LIVELIHOODS_CHOICES``: its switch and the sub-state field holding it.
_CHOICE_FIELDS: dict[str, tuple[str, str]] = {
    "workshop_mode": ("workshops", "mode"),
    "food_allocation_regime": ("food_allocation", "regime"),
    "convoy_route_policy": ("grain_convoys", "route_policy"),
    "commons_rule_mode": ("commons_rules", "mode"),
    "learning_cohort_mode": ("learning_cohorts", "mode"),
    "workshop_payroll_mode": ("workshop_payroll", "mode"),
    "relocation_mode": ("relocation_costs", "mode"),
    "local_budget_mode": ("local_budgets", "mode"),
    "apprenticeship_mode": ("apprenticeship", "mode"),
    "repair_mode": ("repair_projects", "mode"),
    "veteran_mode": ("veteran_reintegration", "mode"),
    "remittance_mode": ("remittances", "mode"),
    "clearing_protection_mode": ("clearing_protection", "mode"),
    "timber_supply_mode": ("timber_supply", "mode"),
    "recovery_crew_mode": ("recovery_crews", "mode"),
    "maintenance_obligation_mode": ("maintenance_obligation", "mode"),
    "apprenticeship_rules": ("apprenticeship", "rules"),
    "household_retail_mode": ("household_retail", "mode"),
    "household_retail_boundary": ("household_retail", "boundary"),
    "household_retail_rules": ("household_retail", "rules"),
    "watershed_mode": ("watershed", "mode"),
}


def livelihoods_resume_conflicts(world: Any, args: Any, recorded: dict) -> list[str]:
    """Explicit options an exact resume of ``world`` cannot honour.

    ``batch_manifest.simulation_config`` omits options that were never
    given, so the generic checkpoint adoption never sees them; the retained
    state is authoritative. Options the checkpoint recorded (``recorded``)
    are left to that adoption, except ``--household-retail-schedule``, which
    is compared by its schedule's digest (see below). Never changes ``world``
    or ``args``."""
    state = livelihoods_state(world)
    conflicts = []
    for name in LIVELIHOODS_SWITCHES:
        given = getattr(args, name, None)
        if given is None or name in recorded:
            continue
        sub = getattr(state, name, None) if state is not None else None
        effective = sub is not None and bool(sub.enabled)
        if given != effective:
            conflicts.append(f"--{name.replace('_', '-')} {given!r} conflicts with the checkpoint "
                             f"(saved: {effective!r})")
    for key, (name, field) in _CHOICE_FIELDS.items():
        given = getattr(args, key, None)
        if given is None or key in recorded:
            continue
        sub = getattr(state, name, None) if state is not None else None
        saved = getattr(sub, field) if sub is not None else None
        if given != saved:
            conflicts.append(f"--{key.replace('_', '-')} {given!r} conflicts with the checkpoint "
                             f"(saved: {saved!r})")
    schedule = getattr(args, "household_retail_schedule", None)
    if schedule is not None:
        # A2R: the retained schedule is authoritative and is identified by its
        # digest, so the same schedule read from another path is no conflict:
        # the recorded path is dropped from the generic comparison (the one
        # change this function makes, to ``recorded``).
        from chronicler.household_retail import schedule_resume_conflict
        sub = getattr(state, "household_retail", None) if state is not None else None
        problem = schedule_resume_conflict(world, schedule, sub)
        if problem is not None:
            conflicts.append(problem)
        else:
            recorded.pop("household_retail_schedule", None)
    # --quarantine-mode shares this resume seam; its rules live on the epidemic
    # state (chronicler.quarantine_rules), not on LivelihoodsState.
    from chronicler.quarantine_rules import quarantine_resume_conflicts
    conflicts.extend(quarantine_resume_conflicts(world, args, recorded))
    return conflicts


def livelihoods_feature_flags(world: Any) -> dict[str, bool]:
    """Checkpoint header flags, only for switches this world ever enabled."""
    return {name: bool(getattr(module, f"{name}_active")(world)) for name, module in _present(world)}


def livelihoods_snapshot_fields(world: Any) -> dict:
    """Copied completed-turn observations of active packages; never final state."""
    parts = {name: module.snapshot_summary(world) for name, module in _present(world)
             if getattr(module, f"{name}_active")(world)}
    if not parts:
        return {}
    return {"livelihoods": {"schema_version": 1, **parts}}


def _hooks(world: Any, hook: str):
    for name, module in _present(world):
        fn = getattr(module, hook, None)
        if fn is not None and getattr(module, f"{name}_active")(world):
            yield fn


def bind_native_pool(world, agent_bridge, *, reset: bool = True) -> None:
    """Bind saved stable ids to the native pool they name.

    Native agent ids are scoped to one pool. A run that rebuilds the pool
    (a legacy state-file resume spawns new people from region populations
    under reused ids) must not hand saved id-bound progress to strangers, as
    the war rosters already re-draft for the same reason. The first hook of
    a turn against a simulator other than the bound one calls each present
    package's optional ``on_pool_reset(world)``, which closes its id-bound
    records with a dated reason (a no-op when it holds none, as in a fresh
    run). An exact checkpoint load restores the same pool and re-binds
    without a reset (``reset=False``).
    """
    state = livelihoods_state(world)
    sim = getattr(agent_bridge, "_sim", None) if agent_bridge is not None else None
    if state is None or sim is None or state._pool_sim == id(sim):
        return
    state._pool_sim = id(sim)
    if not reset:
        return
    for _name, module in _present(world):
        fn = getattr(module, "on_pool_reset", None)
        if fn is not None:
            fn(world)


def paid_work_receipt(world, sim) -> dict[int, tuple[float, float, float]] | None:
    """This turn's native paid-work receipt, shared by every package.

    The native wealth phase records one receipt for the turn's whole paid-work
    install (``install_paid_work`` plus every ``extend_paid_work``), and it
    can be taken from the simulator only once. The first package to ask after
    the agent tick takes it; later callers get the same rows. Returns
    ``{agent_id: (share, ordinary_income, deducted)}``, or None when nothing
    was installed this turn. A receipt of another turn is an error.
    """
    state = livelihoods_state(world)
    if state is None:
        return None
    cached = state._paid_receipt
    if cached is not None and cached[0] == world.turn:
        return cached[1]
    got = sim.take_paid_work_receipt()
    if got is None:
        return None
    if int(got[0]) != int(world.turn):
        raise RuntimeError("paid work receipt belongs to another turn")
    rows = {int(aid): (float(share), float(ordinary), float(deducted))
            for aid, share, ordinary, deducted in got[1]}
    state._paid_receipt = (world.turn, rows)
    return rows


def prepare_phase2(world, region_input, agent_bridge, snapshot, *, acc=None):
    """Before the native economy tick: may replace columns; charges nothing.
    Work held across turns (PL1 expedition crews, away from home) is reserved
    first (``reserve_first``), so every package's planner sees it as held."""
    bind_native_pool(world, agent_bridge)
    for fn in _hooks(world, "reserve_first"):
        fn(world, agent_bridge, snapshot)
    for fn in _hooks(world, "prepare_phase2"):
        region_input = fn(world, region_input, agent_bridge, snapshot, acc)
    return region_input


def finish_phase2(world, economy_result, agent_bridge, *, acc=None) -> list:
    """After a successful native economy tick and storage settlement."""
    events: list = []
    for fn in _hooks(world, "finish_phase2"):
        events.extend(fn(world, economy_result, agent_bridge, acc) or [])
    return events


def rollback_phase2(world) -> None:
    """Release anything a failed Phase 2 left pending; never a native rollback."""
    for name, module in _present(world):
        fn = getattr(module, "rollback_phase2", None)
        if fn is not None:
            fn(world)


def wrap_agent_tick(world, agent_bridge, tick_agents, economy_result):
    """Wrap the native agent tick with the active packages' before/after hooks."""
    before = list(_hooks(world, "before_agent_tick"))
    after = list(_hooks(world, "after_agent_tick"))
    release = list(_hooks(world, "rollback_agent_tick"))
    if (not before and not after) or tick_agents is None:
        return tick_agents

    def _tick(*args, **kwargs):
        bind_native_pool(world, agent_bridge)
        try:
            for fn in before:
                fn(world, agent_bridge, economy_result)
            events = tick_agents(*args, **kwargs)
        except BaseException as exc:
            # A failed kernel is not rolled back: release only reservations and
            # one-tick installs that remain pending (the teaching precedent).
            for fn in reversed(release):
                try:
                    fn(world, agent_bridge)
                except Exception as error:
                    exc.add_note(f"livelihoods release also failed: {error!r}")
            raise
        for fn in after:
            events = list(events or []) + list(fn(world, agent_bridge) or [])
        if after:
            # The hooks may have moved native wealth (wages, fares, stipends,
            # remittances): Phase 10 must not reuse the batch read in the tick.
            discard = getattr(type(agent_bridge), "discard_post_tick_snapshot", None)
            if discard is not None:
                discard(agent_bridge)
        return events

    return _tick


def before_ecology(world, *, acc=None, native: bool | None = None) -> None:
    """Before the Phase 9 region sync and ecology tick: plans; charges nothing.
    ``native``: whether the native ecology (not the Python fallback) runs it."""
    for fn in _hooks(world, "before_ecology"):
        fn(world, acc, native=native)


def after_ecology(world, *, acc=None) -> list:
    """After a successful Phase 9 ecology tick."""
    events: list = []
    for fn in _hooks(world, "after_ecology"):
        events.extend(fn(world, acc) or [])
    return events


def phase10_before_reserves(world, *, acc=None, economy_result=None, agent_bridge=None) -> list:
    bind_native_pool(world, agent_bridge)
    events: list = []
    for fn in _hooks(world, "phase10_before_reserves"):
        events.extend(fn(world, acc, economy_result, agent_bridge) or [])
    return events


def phase10(world, *, acc=None, economy_result=None, agent_bridge=None) -> list:
    events: list = []
    for fn in _hooks(world, "phase10"):
        events.extend(fn(world, acc, economy_result, agent_bridge) or [])
    return events
