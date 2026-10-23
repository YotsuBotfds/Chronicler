"""Campaign-layer parameters.

The logistics core is the reviewed M60a kernel's ``Policy`` record: the same
integer morale/stress/desertion contract, applied per army cohort. Everything
else is an explicit production constant, overridable through
``world.tuning_overrides`` with the ``war.*`` keys below.
"""
from __future__ import annotations

from chronicler.campaign_logistics import Policy

# --- M60a logistics policy (production calibration) -------------------------
POLICY = Policy(
    version="m60-production-v1",
    ration_demand=1,          # rations per soldier per turn
    carried_limit=6,          # turns of food a soldier can carry
    distance_stress=12,       # morale per edge beyond the nearest friendly region
    unreachable_stress=120,   # no friendly supply source reachable at all
    hunger_stress=150,        # full starvation for one turn
    needs_stress=90,          # unpaid upkeep (unmet needs = unpaid fraction)
    information_stress=30,    # fog of war about the enemy
    morale_recovery=30,
    desertion_threshold=300,
    desertion_chance=1200,    # per-soldier desertion chance (1/10000) at low morale
    movement_min_morale=150,
    require_full_rations=False,
)

# --- tuning keys -------------------------------------------------------------
K_MOBILIZATION_BASE = "war.mobilization_base_permille"
K_MOBILIZATION_PER_MILITARY = "war.mobilization_per_military_permille"
K_MAX_MOBILIZATION = "war.max_mobilization_permille"
K_UPKEEP_PER_10 = "war.upkeep_per_10_soldiers"
K_RAISE_COST_PER_10 = "war.raise_cost_per_10_soldiers"
K_BATTLE_CASUALTY_SCALE = "war.battle_casualty_scale"
K_ANNEX_TURNS = "war.annex_occupation_turns"
K_REVOLT_THRESHOLD = "war.revolt_unrest_threshold"

# --- armies ------------------------------------------------------------------
MIN_ARMY = 3
MAX_ARMIES_PER_CIV = 2
MOBILIZATION_BASE_PERMILLE = 60           # of controlled population
MOBILIZATION_PER_MILITARY_PERMILLE = 2.4  # per military point
MAX_MOBILIZATION_PERMILLE = 250
RAISE_COOLDOWN_TURNS = 3
INITIAL_MORALE_BASE = 600
UPKEEP_PER_10_SOLDIERS = 3
RAISE_COST_PER_10_SOLDIERS = 5
REGROUP_MORALE = 250
REGROUP_RECOVERED_MORALE = 550
REGROUP_STRENGTH_FRACTION = 0.3
ARMY_NOUNS = {
    "tribal": "Warband", "bronze": "Host", "iron": "Host", "classical": "Legion",
    "medieval": "Army", "renaissance": "Grand Army", "industrial": "Field Army",
    "information": "Field Army",
}
ORDINALS = ("First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh",
            "Eighth", "Ninth", "Tenth")

# --- logistics extensions (beyond the detached kernel) -----------------------
SUPPLY_RANGE = 3
REFILL_BY_DISTANCE = {0: 3, 1: 2, 2: 1, 3: 1}  # rations per soldier per turn
FORAGE_BY_TERRAIN = {"plains": 2, "forest": 2, "coast": 2, "mountains": 1, "desert": 0, "tundra": 0}
ATTRITION_PERMILLE = {"plains": 3, "coast": 3, "forest": 6, "mountains": 12, "desert": 20, "tundra": 18}
HUNGER_ATTRITION_PERMILLE = 25
DISTANCE_ATTRITION_PERMILLE = 6   # per edge beyond supply range
UNREACHABLE_ATTRITION_PERMILLE = 30
WINTER_ATTRITION_PERMILLE = 10    # mountains/tundra/forest in winter
SIEGE_DISEASE_PERMILLE = 8
MOVE_COST = {"mountains": 2, "forest": 1, "desert": 1, "tundra": 2, "plains": 1, "coast": 1}

# --- battles -----------------------------------------------------------------
ERA_QUALITY_STEP = 0.12
DECISIVE_RATIO = 1.15
GARRISON_PERMILLE = 60          # militia drawn from region population
MIN_GARRISON = 2
RIVER_DEFENSE = 0.10
HOME_GROUND_DEFENSE = 0.10
COMMANDER_BASE = 0.15
BATTLE_MORALE_WIN = 100
BATTLE_MORALE_LOSS = 220
MIL_LOSS_BATTLE_SCALE = 25.0    # military stat lost per fully destroyed mobilization
MIL_LOSS_ATTRITION_SCALE = 10.0
GENERAL_DEATH_CHANCE = 0.10
SIEGE_BASE_TURNS = 2
SIEGE_CIVILIAN_LOSS_PERMILLE = 20

# --- occupation ----------------------------------------------------------------
UNREST_BASE = 35
UNREST_CULTURE = 40
UNREST_PROXY = 30
UNREST_PER_SOLDIER = 8
UNREST_GARRISON_CAP = 160
UNREST_DEPOPULATION = 500
REVOLT_THRESHOLD = 600
ANNEX_TURNS = 15
ANNEX_MAX_UNREST = 450
OCC_TAX_LOSS = 2
OCC_REQUISITION = 1

# --- war score / peace -----------------------------------------------------------
OCC_POINTS = 12
OCC_CAPITAL_POINTS = 20
BATTLE_POINTS_BASE = 6
BATTLE_POINTS_SCALE = 12
SIEGE_POINTS = 5
CAPITULATION_SCORE = 60
NEGOTIATION_SCORE = 20
MIN_WAR_TURNS = 3
WHITE_PEACE_TURNS = 15
TRIBUTE_BASE = 20
BATTLE_WEARINESS = 1.0
LOSS_WEARINESS = 4.0
OCCUPATION_WEARINESS = 0.2
THREAT_RANGE = 3
TRUCE_TURNS = 10                # no new war between treaty parties
