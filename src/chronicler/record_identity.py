"""Reviewed person identity paths for opt-in connected-record prose audits.

A numeric match alone establishes no identity. Unknown package/path/key
combinations, public accounts and other entity namespaces do not authorize a
personal causal join. This helper does not certify the truth of a causal claim.
"""
from __future__ import annotations
import re

# package, exact object path, native-person keys, retained identity start date
_PERSON_PATHS = (
    ("recovery_crews", r"receipts/[0-9]+/members/[0-9]+", ("agent_id",), None),
    ("infrastructure_condition", r"receipts/[0-9]+/members/[0-9]+", ("agent_id",), None),
    ("epidemic_care", r"frame/[0-9]+/carers/[0-9]+", ("agent_id",), None),
    ("public_health", r"guards/[0-9]+/members/[0-9]+", ("agent_id",), None),
    ("titled_trade", r"(?:shipments|closed)/[0-9]+", ("holder", "carrier"), "dispatched_turn"),
    ("titled_trade", r"frame/(?:dispatched|sales)/[0-9]+", ("holder",), None),
    ("titled_trade", r"frame/withheld/[0-9]+", ("carrier",), None),
    ("titled_trade", r"lots/[0-9]+", ("holder",), None),
    ("timber_orders", r"(?:orders|closed)/[0-9]+", ("holder",), "dispatched_turn"),
    ("timber_orders", r"frame/(?:events|withheld)/[0-9]+", ("holder",), None),
    ("war_requisition", r"frame/claims/[0-9]+", ("owner",), "turn"),
    ("war_requisition", r"frame/events/[0-9]+", ("owner",), None),
    ("adaptive_livelihoods", r"frame/(?:work|offers|refusals|quick_departures|trade)/[0-9]+", ("id",), None),
    ("war_consequences", r"(?:frame/events|history)/[0-9]+", ("id",), "turn"),
    ("residence_ledger", r"events/[0-9]+", ("id",), None),
)


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def person_namespace(bundle, record, key):
    """Return a reviewed native person epoch, or None when unproven.

    Old title holders and restitution owners stay in the segment in which
    their lifecycle began. A rebuilt pool cannot make a reused integer refer
    to its former person. Dropped reset logs conservatively limit identity
    proof to one source date, rather than presuming continuous identity.
    """
    if not isinstance(key, str) or not isinstance(record.value, dict) or not _integer(record.value.get(key)):
        return None
    relative = record.pointer.split("/livelihoods/", 1)[-1]
    package, _, path = relative.partition("/")
    matched = next((start for pkg, pattern, keys, start in _PERSON_PATHS
                    if package == pkg and key in keys and re.fullmatch(pattern, path)), False)
    if matched is False:
        return None
    identity_turn = record.value.get(matched) if matched else record.source_turn
    if not _integer(identity_turn) or identity_turn > record.source_turn:
        return None
    if record.value.get("kind") == "pool_reset":
        identity_turn -= 1
    boundaries = set()
    uncertain = False
    metadata = bundle.get("metadata") or {}
    resume = metadata.get("resume") if isinstance(metadata, dict) else None
    if isinstance(resume, dict) and resume.get("exact") is False:
        if not _integer(resume.get("turn")):
            return None
        boundaries.add(resume["turn"])
    for snapshot in bundle.get("history") or []:
        if not isinstance(snapshot, dict):
            continue
        lh = snapshot.get("livelihoods")
        r = lh.get("residence_ledger") if isinstance(lh, dict) and lh.get("schema_version") == 1 else None
        if not isinstance(r, dict) or r.get("schema_version") != 1 or r.get("stage") != "X1" or not _integer(snapshot.get("turn")) or r.get("source_turn") != snapshot["turn"] - 1:
            continue
        if not isinstance(r.get("log", []), list):
            return None
        uncertain |= _integer(r.get("log_dropped")) and r["log_dropped"] > 0
        for event in r.get("log") or []:
            if isinstance(event, dict) and event.get("kind") == "pool_reset" and _integer(event.get("turn")) and event["turn"] <= r["source_turn"]:
                boundaries.add(event["turn"])
    epoch = max((turn for turn in boundaries if turn <= identity_turn), default=None)
    return ("person", epoch, identity_turn if uncertain else None)
