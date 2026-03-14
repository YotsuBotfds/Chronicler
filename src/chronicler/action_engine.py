"""Deterministic action selection engine with personality, situational, and streak logic."""

from __future__ import annotations

import random

from chronicler.models import (
    ActionType, Civilization, Disposition, TechEra, WorldState,
)

TRAIT_WEIGHTS: dict[str, dict[ActionType, float]] = {
    "aggressive":   {ActionType.WAR: 2.0, ActionType.EXPAND: 1.3, ActionType.DEVELOP: 0.5, ActionType.TRADE: 0.8, ActionType.DIPLOMACY: 0.3},
    "cautious":     {ActionType.WAR: 0.2, ActionType.EXPAND: 0.5, ActionType.DEVELOP: 2.0, ActionType.TRADE: 1.3, ActionType.DIPLOMACY: 1.5},
    "opportunistic":{ActionType.WAR: 1.0, ActionType.EXPAND: 1.5, ActionType.DEVELOP: 0.8, ActionType.TRADE: 2.0, ActionType.DIPLOMACY: 0.7},
    "zealous":      {ActionType.WAR: 1.5, ActionType.EXPAND: 2.0, ActionType.DEVELOP: 1.3, ActionType.TRADE: 0.5, ActionType.DIPLOMACY: 0.4},
    "ambitious":    {ActionType.WAR: 1.2, ActionType.EXPAND: 1.8, ActionType.DEVELOP: 1.5, ActionType.TRADE: 1.0, ActionType.DIPLOMACY: 0.6},
    "calculating":  {ActionType.WAR: 0.7, ActionType.EXPAND: 0.8, ActionType.DEVELOP: 1.8, ActionType.TRADE: 1.5, ActionType.DIPLOMACY: 1.3},
    "visionary":    {ActionType.WAR: 0.4, ActionType.EXPAND: 1.0, ActionType.DEVELOP: 1.8, ActionType.TRADE: 1.3, ActionType.DIPLOMACY: 1.5},
    "bold":         {ActionType.WAR: 1.8, ActionType.EXPAND: 1.8, ActionType.DEVELOP: 0.6, ActionType.TRADE: 1.0, ActionType.DIPLOMACY: 0.5},
    "shrewd":       {ActionType.WAR: 0.5, ActionType.EXPAND: 0.7, ActionType.DEVELOP: 1.2, ActionType.TRADE: 2.0, ActionType.DIPLOMACY: 1.8},
    "stubborn":     {},
}

SECONDARY_TRAIT_ACTION: dict[str, ActionType] = {
    "warlike": ActionType.WAR, "builder": ActionType.DEVELOP, "merchant": ActionType.TRADE,
    "conqueror": ActionType.EXPAND, "diplomat": ActionType.DIPLOMACY,
}

_ERA_ORDER = list(TechEra)

def _era_at_least(era: TechEra, minimum: TechEra) -> bool:
    return _ERA_ORDER.index(era) >= _ERA_ORDER.index(minimum)


class ActionEngine:
    def __init__(self, world: WorldState):
        self.world = world

    def get_eligible_actions(self, civ: Civilization) -> list[ActionType]:
        eligible = [ActionType.DEVELOP, ActionType.DIPLOMACY]
        unclaimed = [r for r in self.world.regions if r.controller is None]
        if civ.military >= 30 and unclaimed:
            eligible.append(ActionType.EXPAND)
        has_hostile = False
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    has_hostile = True
                    break
        if has_hostile:
            eligible.append(ActionType.WAR)
        if _era_at_least(civ.tech_era, TechEra.BRONZE):
            if civ.name in self.world.relationships:
                for rel in self.world.relationships[civ.name].values():
                    if rel.disposition not in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                        eligible.append(ActionType.TRADE)
                        break
        return eligible

    def compute_weights(self, civ: Civilization) -> dict[ActionType, float]:
        eligible = self.get_eligible_actions(civ)
        base = 0.2
        weights: dict[ActionType, float] = {a: base for a in ActionType}
        for action in ActionType:
            if action not in eligible:
                weights[action] = 0.0
        trait = civ.leader.trait
        if trait == "stubborn":
            history = self.world.action_history.get(civ.name, [])
            last_action = history[-1] if history else None
            for action in ActionType:
                if weights[action] == 0.0:
                    continue
                if last_action and action.value == last_action:
                    weights[action] *= 2.0
                else:
                    weights[action] *= 0.8
        else:
            profile = TRAIT_WEIGHTS.get(trait, {})
            for action in ActionType:
                if weights[action] == 0.0:
                    continue
                weights[action] *= profile.get(action, 1.0)
        self._apply_situational(civ, weights)
        if civ.leader.secondary_trait:
            boosted = SECONDARY_TRAIT_ACTION.get(civ.leader.secondary_trait)
            if boosted and weights[boosted] > 0:
                weights[boosted] *= 1.3
        if civ.leader.rival_civ:
            if civ.name in self.world.relationships:
                rival_rel = self.world.relationships[civ.name].get(civ.leader.rival_civ)
                if rival_rel and rival_rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    weights[ActionType.WAR] *= 1.5
        history = self.world.action_history.get(civ.name, [])
        streak_limit = 5 if civ.leader.trait == "stubborn" else 3
        if len(history) >= streak_limit:
            last_n = history[-streak_limit:]
            if len(set(last_n)) == 1:
                streaked = ActionType(last_n[0])
                weights[streaked] = 0.0
        return weights

    def _apply_situational(self, civ: Civilization, weights: dict[ActionType, float]) -> None:
        if civ.stability <= 20:
            weights[ActionType.DIPLOMACY] *= 3.0
            weights[ActionType.WAR] *= 0.1
        has_hostile = False
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition in (Disposition.HOSTILE, Disposition.SUSPICIOUS):
                    has_hostile = True
                    break
        if civ.military >= 70 and has_hostile:
            weights[ActionType.WAR] *= 2.5
        if civ.treasury >= 200:
            weights[ActionType.EXPAND] *= 2.0
            weights[ActionType.TRADE] *= 1.5
        if civ.treasury <= 30:
            weights[ActionType.DEVELOP] *= 0.3
            weights[ActionType.EXPAND] *= 0.2
        if civ.population >= 80 and len(civ.regions) <= 2:
            weights[ActionType.EXPAND] *= 3.0
        if civ.economy <= 30:
            weights[ActionType.DEVELOP] *= 2.0
            weights[ActionType.TRADE] *= 1.5
        if not has_hostile:
            weights[ActionType.WAR] *= 0.1
        all_allied = True
        if civ.name in self.world.relationships:
            for rel in self.world.relationships[civ.name].values():
                if rel.disposition != Disposition.ALLIED:
                    all_allied = False
                    break
        else:
            all_allied = False
        if all_allied:
            weights[ActionType.DIPLOMACY] *= 0.1

    def select_action(self, civ: Civilization, seed: int) -> ActionType:
        weights = self.compute_weights(civ)
        actions = [a for a, w in weights.items() if w > 0]
        action_weights = [weights[a] for a in actions]
        if not actions:
            return ActionType.DEVELOP
        rng = random.Random(seed + self.world.turn + hash(civ.name))
        return rng.choices(actions, weights=action_weights, k=1)[0]
