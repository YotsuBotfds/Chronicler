"""M16a: Culture as property -- value drift, assimilation, prestige."""

from __future__ import annotations

from chronicler.models import Disposition, WorldState

VALUE_OPPOSITIONS: dict[str, str] = {
    "Freedom": "Order",
    "Order": "Freedom",
    "Liberty": "Order",
    "Tradition": "Knowledge",
    "Knowledge": "Tradition",
    "Honor": "Cunning",
    "Cunning": "Honor",
    "Piety": "Cunning",
    "Self-reliance": "Trade",
    "Trade": "Self-reliance",
}

_DISPOSITION_ORDER = list(Disposition)


def _upgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[min(idx + 1, len(_DISPOSITION_ORDER) - 1)]


def _downgrade_disposition(current: Disposition) -> Disposition:
    idx = _DISPOSITION_ORDER.index(current)
    return _DISPOSITION_ORDER[max(idx - 1, 0)]


def apply_value_drift(world: WorldState) -> None:
    """Accumulate disposition drift from shared/opposing values."""
    civs = world.civilizations
    for i, civ_a in enumerate(civs):
        for civ_b in civs[i + 1:]:
            shared = sum(1 for v in civ_a.values if v in civ_b.values)
            opposing = sum(
                1 for va in civ_a.values for vb in civ_b.values
                if VALUE_OPPOSITIONS.get(va) == vb
            )
            net_drift = (shared * 2) - (opposing * 2)
            if net_drift == 0:
                continue

            for a_name, b_name in [(civ_a.name, civ_b.name), (civ_b.name, civ_a.name)]:
                rel = world.relationships.get(a_name, {}).get(b_name)
                if rel is None:
                    continue
                rel.disposition_drift += net_drift
                if rel.disposition_drift >= 10:
                    rel.disposition = _upgrade_disposition(rel.disposition)
                    rel.disposition_drift = 0
                elif rel.disposition_drift <= -10:
                    rel.disposition = _downgrade_disposition(rel.disposition)
                    rel.disposition_drift = 0
