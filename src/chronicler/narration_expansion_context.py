"""Bounded, dated reads of the three optional expansion snapshot receipts.

No simulation imports or world-state fallbacks. Estimates remain estimates,
attendance remains selected local presence and work-time inputs are not deaths,
clinical diagnoses or an attribution of lost production.
"""
from __future__ import annotations

from collections.abc import Mapping
import math


def _number(value):
    return value if (isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value) and value >= 0) else None


def _dated(snapshot, field, at_turn):
    state = getattr(snapshot, field, None)
    if not isinstance(state, Mapping):
        return None
    source = state.get("source_turn")
    return state if (isinstance(source, int) and not isinstance(source, bool)
                     and source == snapshot.turn - 1 and source <= at_turn) else None


def _rows(state, key):
    values = state.get(key)
    return [r for r in values if isinstance(r, Mapping)] if isinstance(values, list) else []


def _focus(row, civs, regions, owner_key):
    return (row.get("region_name") in regions or row.get(owner_key) in civs)


def expansion_state_facts(snapshot, civs, regions, at_turn):
    """At most one line per system, with keys for existing snapshot citations."""
    facts = []
    health = _dated(snapshot, "health_care", at_turn)
    if health is not None and health.get("units") == "worker-turns":
        rows = [r for r in _rows(health, "regions") if r.get("region_name")
                and _focus(r, civs, regions, "civ_name")
                and all(_number(r.get(k)) is not None for k in ("episodes", "impaired_work", "care_work"))]
        rows.sort(key=lambda r: (r.get("region_name") not in regions, -r["impaired_work"], r["region_name"]))
        if rows:
            row = rows[0]
            text = (f"Work impairment in {row['region_name']} after recorded turn {health['source_turn']}: "
                    f"{row['episodes']:.0f} active temporary work-injury episodes; manual work time reduced by "
                    f"{row['impaired_work']:.2f} worker-turns for impairment, with "
                    f"{row['care_work']:.2f} worker-turns allocated to care")
            facts.append(([("work_health", ("region", row["region_name"]))], text))

    gatherings = _dated(snapshot, "ritual_gatherings", at_turn)
    if gatherings is not None:
        rows = [r for r in _rows(gatherings, "outcomes")
                if r.get("turn") == gatherings["source_turn"] and r.get("region_name")
                and r.get("gathering_id") and _focus(r, civs, regions, "host_name")
                and r.get("purpose") == "harvest"
                and r.get("status") in ("held", "cancelled")]
        rows.sort(key=lambda r: (r.get("region_name") not in regions, r.get("status") != "cancelled",
                                 str(r["gathering_id"])))
        for row in rows:
            if row["status"] == "held":
                if (not isinstance(row.get("attendee_ids"), list)
                        or any(_number(row.get(k)) is None for k in ("food", "funds", "bond_ops", "contact_units"))):
                    continue
                text = (f"Local harvest gathering in {row['region_name']}, held by {row.get('host_name') or 'its recorded host'} "
                        f"on turn {row['turn']}: {len(row['attendee_ids'])} selected local adults; "
                        f"{row['food']:.2f} grain consumed and {row['funds']:.0f} treasury units spent; "
                        f"{row['bond_ops']:.0f} friendship attempts and {row['contact_units']:.0f} "
                        "additional contact units from verified arrivals")
            else:
                reasons = {"occupied": "enemy occupation", "shortage": "food shortage",
                           "food": "insufficient uncommitted grain", "funds": "insufficient host funds",
                           "no_host": "no eligible host", "no_attendees": "no eligible local adults",
                           "unmeasured_food": "food availability unmeasured"}
                reason = reasons.get(row.get("reason"))
                text = f"Local harvest gathering in {row['region_name']} cancelled on turn {row['turn']}"
                if reason is not None:
                    text += f" because of {reason}"
                if all(row.get(k) == 0 for k in ("food", "funds", "bond_ops", "contact_units")):
                    text += "; no gathering expense, bond attempt or additional contact"
            facts.append(([("gathering", row["gathering_id"])], text))
            break

    forecasts = _dated(snapshot, "harvest_forecasts", at_turn)
    if forecasts is not None:
        source = forecasts["source_turn"]
        rows = [r for r in _rows(forecasts, "reports") if r.get("id")
                and (r.get("recipient_region_name") in regions or r.get("owner_name") in civs)
                and isinstance(r.get("issued_turn"), int) and r["issued_turn"] <= source
                and isinstance(r.get("expires_turn"), int) and source <= r["expires_turn"]
                and r.get("status") in ("pending", "delivered", "withheld")
                and _number(r.get("probability")) is not None and r["probability"] <= 1
                and isinstance(r.get("target_start"), int) and isinstance(r.get("target_end"), int)]
        rows.sort(key=lambda r: (r.get("recipient_region_name") not in regions,
                                 r.get("status") != "delivered", r["issued_turn"], str(r["id"])))
        for row in rows:
            status = row["status"]
            if status == "delivered":
                delivered = row.get("delivered_turn")
                if not isinstance(delivered, int) or delivered > source:
                    continue
                delivery = f"delivered on turn {delivered}"
            else:
                delivery = "awaiting delivery" if status == "pending" else "withheld from its recipient"
            text = (f"Harvest assessment for {row.get('recipient_region_name') or 'its recorded recipient'} "
                    f"from {row.get('source_region_name') or 'its recorded source'}, issued on turn "
                    f"{row['issued_turn']} and {delivery}: assessors estimate {100 * row['probability']:.0f}% "
                    f"production-shortfall risk for turns {row['target_start']}-{row['target_end']} "
                    "(a reported estimate; the future outcome is not established)")
            keys = [("harvest_report", row["id"])]
            spending = next((p for p in _rows(forecasts, "preparedness")
                             if p.get("forecast_id") == row["id"] and status == "delivered"
                             and all(_number(p.get(k)) is not None
                                     for k in ("bought_during_warning", "paid_during_warning"))), None)
            if spending is not None:
                text += (f"; granary purchases during the warning: {spending['bought_during_warning']:.2f} "
                         f"grain for {spending['paid_during_warning']:.0f} treasury units")
                keys.append(("harvest_preparedness", row["id"]))
            facts.append((keys, text))
            break
    return facts
