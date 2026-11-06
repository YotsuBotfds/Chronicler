#!/usr/bin/env python3
"""Find natural success and failure examples of the productive-recovery checkpoint-1 packages.

    python scripts/productive_recovery_examples.py BUNDLE [BUNDLE ...]

Scans each run's dated livelihoods records (``history[i]["livelihoods"][<package>]``;
never the final world state) and prints, per package, the first natural instance of
each example kind with its snapshot turn and the stable ids involved, or "none
found". The packages are PL1 timber supply, PL2 (RS1 rules version 2 and
``--operating-wear``), PL3 recovery crews and the maintenance obligation, and RS2's
``no_people`` correction. A snapshot is dated by its ``turn``; every record in it
observes the completed turn before (``source_turn``).

A bundle carries no CLI flags, so the reproducing command is the one that wrote it
(docs/superpowers/progress/productive-recovery-examples.md lists them). Constructed
examples are the unit and native tests named in that document, not this script.

The record keys read here are the packages' own model fields and declared reasons
(``*_state.py``); :func:`check_fields` checks them against this checkout's source,
as ``productive_recovery_screens.check_extractor`` checks the counters it reads.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Workshop condition below which a site stops operating until repaired, when the
#: record does not state it (``workshops.OPERATE_CONDITION``).
OPERATE_CONDITION = 0.5
#: Tolerance for comparing recorded conditions.
EPS = 1e-9

# --- Record access ---------------------------------------------------------------


def _liv(snap: dict, name: str):
    rec = (snap.get("livelihoods") or {}).get(name)
    return rec if isinstance(rec, dict) else None


def _records(hist, name):
    for snap in hist:
        rec = _liv(snap, name)
        if rec is not None:
            yield snap.get("turn"), rec


def _rows(rec, key) -> list:
    return (rec or {}).get(key) or []


def _first(hist, name, key, pred):
    for turn, rec in _records(hist, name):
        for row in _rows(rec, key):
            if pred(row, rec):
                return turn, row
    return None


def _has(hist, name) -> bool:
    return any(True for _ in _records(hist, name))


def _pick(row: dict, *keys) -> dict:
    return {k: row.get(k) for k in keys}


# --- PL1 timber supply --------------------------------------------------------------

#: The refusals that mean "no forest to cut" (``timber_supply_state.REFUSALS``).
FOREST_REFUSALS = ("no_forest", "too_far", "forest_depleted")
_EXPEDITION = ("eid", "civ", "home", "forest", "hops", "launched_turn", "ended_turn", "launched_crew", "crew")


def _timber_supply(hist):
    delivered: dict[int, tuple[int, dict]] = {}   # eid -> (snapshot, expedition), first seen delivered
    by_region: dict[int, list[tuple[int, dict]]] = {}
    pending: dict[int, tuple[int, dict]] = {}     # home -> a delivery not yet held by RS2 or released
    held: dict[int, list[tuple[int, float]]] = {}  # region -> (source turn, store timber RS2 held)
    used = completed = None
    seen_projects: set[int] = set()
    for snap in hist:
        turn = snap.get("turn")
        ts, rp = _liv(snap, "timber_supply"), _liv(snap, "repair_projects")
        if ts is None:
            continue
        for e in _rows(ts, "closed"):
            if e.get("status") == "delivered" and (e.get("delivered") or 0) > 0 and e["eid"] not in delivered:
                delivered[e["eid"]] = (turn, e)
                by_region.setdefault(e["home"], []).append((turn, e))
                pending.setdefault(e["home"], (turn, e))
        store = ts.get("store") or {}
        for row in _rows(ts, "stores"):
            if (row.get("held") or 0) > 0:
                held.setdefault(row["region"], []).append((ts.get("source_turn"), row["held"]))
            hit = pending.get(row["region"])
            if used is None and hit is not None and hit[0] < turn and (row.get("held") or 0) > 0:
                e = hit[1]
                used = (turn, {**_pick(e, *_EXPEDITION, "cut", "delivered"), "delivered_snapshot": hit[0],
                               "store_held": row["held"],
                               "rs2_projects": [_pick(r, "pid", "kind", "asset", "timber_used", "credited")
                                                for r in _rows(rp, "receipts")
                                                if r.get("region") == row["region"] and (r.get("timber_used") or 0) > 0]})
        for region in list(pending):
            # A store emptied without a hold: the delivery was released to the stockpile.
            if pending[region][0] < turn and str(region) not in store:
                del pending[region]
        for p in _rows(rp, "closed"):
            if completed is not None or p["pid"] in seen_projects:
                continue
            seen_projects.add(p["pid"])
            if p.get("kind") != "granary" or p.get("status") != "completed":
                continue
            before = [(t, e) for t, e in by_region.get(p["region"], [])
                      if p["opened_turn"] <= e["ended_turn"] < p["closed_turn"]]
            if before:
                t0, e = before[0]
                completed = (turn, {**_pick(p, "pid", "asset", "region", "cause", "opened_turn", "closed_turn",
                                            "opened_condition", "scope", "delivered", "timber_used"),
                                    "deliveries": [_pick(x, "eid", "ended_turn", "delivered") for _t, x in before],
                                    "store_held_while_open": sum(a for s, a in held.get(p["region"], [])
                                                                 if p["opened_turn"] <= s <= p["closed_turn"])})
    out = {
        "success: an expedition delivers timber that RS2 then holds from the store": used,
        "success: a granary project completes after a delivery to its region": completed,
    }
    for reason in FOREST_REFUSALS:
        out[f"failure: a need refused for want of forest ({reason})"] = _first(
            hist, "timber_supply", "needs", lambda n, _r, reason=reason: n.get("status") == "refused"
            and n.get("reason") == reason)

    lost = None
    for turn, rec in _records(hist, "timber_supply"):
        for e in _rows(rec, "closed"):
            if e.get("status") == "abandoned" and e.get("end_reason") == "crew_lost" and (e.get("abandoned") or 0) > 0:
                deposits = [d for d in _rows(rec, "deposits") if len(d) == 4 and d[1] == e["eid"]]
                lost = (turn, {**_pick(e, *_EXPEDITION, "stage", "cut", "abandoned", "drops"),
                               "deposits": deposits})
                break
        if lost is not None:
            break
    out["failure: a crew lost and its cargo abandoned to the forest commons"] = lost

    recall = _first(hist, "timber_supply", "receipts", lambda r, _r: bool(r.get("recalled")))
    if recall is not None:
        turn, r = recall
        ended = next(((t, e) for t, rec in _records(hist, "timber_supply") if t >= turn
                      for e in _rows(rec, "closed") if e["eid"] == r["eid"]), None)
        recall = (turn, {**_pick(r, "eid", "civ", "home", "forest", "stage", "crew", "cut_end", "unpaid",
                                 "cargo_after", "wages_due_milli"),
                         "ended": None if ended is None else {"snapshot": ended[0],
                                                              **_pick(ended[1], "status", "delivered",
                                                                      "unpaid_turns", "recalled_turn")}})
    out["failure: a crew recalled for want of coins"] = recall
    return out


# --- PL2 RS1 rules version 2 -------------------------------------------------------------

_ARCHIVE = ("agent_id", "first_site", "site", "region", "started_turn", "ended_turn", "ended_reason", "attended",
            "transfers", "on_crew", "attached", "absent", "interruptions", "mentors", "granted")


def _apprenticeship(hist):
    def v2(rec):
        return rec.get("rules_version") == 2

    def archived(reason, extra=lambda a: True):
        return _first(hist, "apprenticeship", "archive", lambda a, r: v2(r) and a.get("ended_reason") == reason
                      and extra(a))

    graduate = _first(hist, "apprenticeship", "receipts", lambda s, r: v2(r) and s.get("operating")
                      and s.get("graduates_on_crew") and (s.get("offset_by_graduates") or 0) > 0)
    no_mentor = None
    for turn, rec in _records(hist, "apprenticeship"):
        if not v2(rec):
            continue
        for s in _rows(rec, "receipts"):
            seats = [x for x in _rows(s, "seats") if x.get("outcome") == "missed" and x.get("reason") == "no_mentor"]
            if seats and not s.get("qualified_on_crew"):
                no_mentor = (turn, {**_pick(s, "site", "region", "operating", "crew", "qualified_on_crew",
                                            "qualified_in_region"),
                                    "missed": [_pick(x, "agent_id", "reason") for x in seats]})
                break
        if no_mentor is not None:
            break
    site_region: dict[int, int] = {}       # workshop site -> region, from the dated records
    for _turn, rec in _records(hist, "apprenticeship"):
        for row in [*_rows(rec, "sites"), *_rows(rec, "receipts")]:
            site_region.setdefault(row["site"], row["region"])

    def pick(hit):
        if hit is None:
            return None
        return hit[0], {**_pick(hit[1], *_ARCHIVE), "first_region": site_region.get(hit[1].get("first_site"))}

    ungranted = pick(archived("completed", lambda a: a.get("granted") is False))
    if ungranted is None and all(rec.get("mode") == "train" for _t, rec in _records(hist, "apprenticeship")):
        ungranted = "not applicable (train mode grants every completion)"
    if not any(v2(rec) for _t, rec in _records(hist, "apprenticeship")):
        note = "not applicable (the run's RS1 records are rules version 1)"
        graduate = no_mentor = ungranted = note
        pick = (lambda _hit: note)
    return {
        "success: a graduate on an operating crew gives upkeep offset": graduate if not isinstance(graduate, tuple)
        else (graduate[0], _pick(graduate[1], "site", "region", "crew", "graduates_on_crew", "qualified_on_crew",
                               "offset_by_graduates", "offset_by_via", "upkeep_offset", "wear",
                               "condition_before", "condition_after")),
        "success: an apprentice who transferred regions completed":
            pick(archived("completed", lambda a: (a.get("transfers") or 0) > 0)),
        "failure: an apprenticeship ends long_absence": pick(archived("long_absence")),
        "failure: an apprenticeship ends stalled": pick(archived("stalled")),
        "failure: an apprentice misses teaching with no mentor aboard (no_mentor)": no_mentor,
        "control: a completion that grants no qualification (no_qualification)": ungranted,
    }


# --- PL2 operating wear ----------------------------------------------------------------------


def _operating_wear(hist):
    floor = OPERATE_CONDITION
    window: dict[int, list[dict]] = {}    # site -> wear receipts since its last repair
    worn: dict[int, list[dict]] = {}      # site -> every wear receipt, for RS2 projects
    done: dict[int, list[int]] = {}       # workshop site -> turns its RS2 projects completed
    lump = rebuilt = None
    rs2 = False
    seen: set[int] = set()

    def decline(rows):
        return {"worn_turns": len(rows), "first_turn": rows[0]["turn"], "last_turn": rows[-1]["turn"],
                "condition_before": rows[0]["condition_before"], "condition_after": rows[-1]["condition_after"],
                "wear": round(sum(r["wear"] for r in rows), 6),
                "upkeep_offset": round(sum(r.get("upkeep_offset") or 0 for r in rows), 6)}

    def by_operation(rows, below):
        """From full condition (built or repaired), operating turns with no qualified
        member and no upkeep offset, nothing else wearing the site between them, and
        the last one leaving it below ``below``."""
        return (bool(rows) and rows[0]["condition_before"] >= 1.0 - EPS and rows[-1]["condition_after"] < below
                and all(not (r.get("upkeep_offset") or 0) and not r.get("qualified_on_crew") for r in rows)
                and all(abs(a["condition_after"] - b["condition_before"]) < EPS for a, b in zip(rows, rows[1:])))

    for snap in hist:
        turn = snap.get("turn")
        ow, ws, rp = _liv(snap, "operating_wear"), _liv(snap, "workshops"), _liv(snap, "repair_projects")
        if ow is None:
            continue
        rs2 = rs2 or rp is not None
        floor = ((ws or {}).get("parameters") or {}).get("operate_condition", floor)
        for r in _rows(ws, "receipts"):
            if not (r.get("paid") or {}).get("repair"):
                continue
            rows = window.pop(r["site"], [])
            if lump is None and by_operation(rows, floor):
                lump = (turn, {"site": r["site"], "region": r["region"], "payer": r.get("payer"),
                               "repair_paid": r["paid"]["repair"], "condition_after_repair": r.get("condition_after"),
                               **decline(rows)})
        for p in _rows(rp, "closed"):
            if rebuilt is not None or p["pid"] in seen:
                continue
            seen.add(p["pid"])
            if p.get("kind") != "workshop" or p.get("status") != "completed":
                continue
            last = max((t for t in done.get(p["asset"], []) if t < p["opened_turn"]), default=None)
            done.setdefault(p["asset"], []).append(p["closed_turn"])
            if p.get("cause") != "wear":
                continue
            rows = [w for w in worn.get(p["asset"], [])
                    if w["turn"] <= p["opened_turn"] and (last is None or w["turn"] > last)]
            if by_operation(rows, p["opened_condition"] + EPS):
                rebuilt = (turn, {**_pick(p, "pid", "asset", "region", "opened_turn", "opened_condition", "closed_turn",
                                          "delivered", "timber_used", "last_crew"), **decline(rows)})
        for w in _rows(ow, "receipts"):
            window.setdefault(w["site"], []).append(w)
            worn.setdefault(w["site"], []).append(w)
    if lump is None and rs2:
        lump = "none found (RS2 owns workshop repair in this run, so no L1 lump repair is billed)"
    if rebuilt is None and not rs2:
        rebuilt = "not applicable (no repair_projects record)"
    return {
        "failure: a site worn below the operating floor for want of qualified upkeep, then an L1 lump repair": lump,
        "failure: a site worn to an RS2 project for want of qualified upkeep, then rebuilt by it": rebuilt,
    }


# --- PL3 recovery crews, the maintenance obligation and RS2's no_people correction -------------


def _recovery_crews(hist):
    paid = _first(hist, "recovery_crews", "receipts", lambda r, _r: r.get("kind") == "granary"
                  and (r.get("wages_milli") or 0) > 0 and r.get("members"))
    veteran = _first(hist, "recovery_crews", "receipts", lambda r, _r: any(m.get("veteran") for m in _rows(r, "members")))
    short = None
    for snap in hist:
        rc = _liv(snap, "recovery_crews")
        for r in _rows(rc, "receipts"):
            if r.get("kind") == "granary" and r.get("short"):
                rs2 = [x for x in _rows(_liv(snap, "repair_projects"), "receipts") if x.get("pid") == r["pid"]]
                short = (snap.get("turn"), {**_pick(r, "pid", "region", "payer", "eligible", "planned", "capacity",
                                                    "requested", "delivered"),
                                            "members": [m["agent_id"] for m in _rows(r, "members")],
                                            "rs2": [_pick(x, "status", "reasons") for x in rs2]})
                break
        if short is not None:
            break

    def members(hit, keys):
        if hit is None:
            return None
        turn, r = hit
        return turn, {**_pick(r, "pid", "kind", "region", "payer", "delivered", "wages_milli", "sunk_milli"),
                      "members": [_pick(m, *keys) for m in _rows(r, "members")]}

    return {
        "success: wages paid to a named granary crew": members(paid, ("agent_id", "origin", "worked", "wage_milli")),
        "success: a veteran placed on a repair crew": members(veteran, ("agent_id", "origin", "veteran")),
        "failure: a granary crew short of farmers (short / no_labor)": short,
    }


def _maintenance_obligation(hist):
    return {
        "success: an obligation reservation used":
            _first(hist, "maintenance_obligation", "uses", lambda u, _r: (u.get("used") or 0) > 0),
        "failure: a reservation returned unspent":
            _first(hist, "maintenance_obligation", "uses", lambda u, _r: (u.get("returned") or 0) > 0),
    }


def _no_people(hist):
    suspended: dict[int, int] = {}   # pid -> first dated suspension
    resumed = None
    for turn, rec in _records(hist, "repair_projects"):
        for p in [*_rows(rec, "projects"), *_rows(rec, "closed")]:
            for t, event, *_rest in p.get("history") or []:
                if event == "suspended_no_people":
                    suspended.setdefault(p["pid"], t)
                elif event == "resumed" and resumed is None and p["pid"] in suspended and t > suspended[p["pid"]]:
                    resumed = (turn, {**_pick(p, "pid", "kind", "asset", "region", "opened_turn", "status"),
                                      "suspended_turn": suspended[p["pid"]], "resumed_turn": t})
        if resumed is not None:
            break
    return {
        "failure: a granary project suspended no_people and later resumed": resumed,
        "failure: a worn granary with no project for want of people (unmet no_people)":
            _first(hist, "repair_projects", "unmet", lambda u, _r: u.get("reason") == "no_people"),
    }


#: Group -> (the packages whose records it needs, finder).
FINDERS = {
    "PL1 timber_supply": (("timber_supply",), _timber_supply),
    "PL2 apprenticeship (rules version 2)": (("apprenticeship",), _apprenticeship),
    "PL2 operating_wear": (("operating_wear",), _operating_wear),
    "PL3 recovery_crews": (("recovery_crews",), _recovery_crews),
    "PL3 maintenance_obligation": (("maintenance_obligation",), _maintenance_obligation),
    "RS2 no_people correction (repair_projects)": (("repair_projects",), _no_people),
}

#: Record fields and declared values this script reads: (module, model) -> fields.
FIELDS_READ = {
    ("timber_supply_state", "Expedition"): {*_EXPEDITION, "status", "stage", "cut", "delivered", "abandoned", "drops",
                                            "end_reason", "unpaid_turns", "recalled_turn"},
    ("timber_supply_state", "ExpeditionReceipt"): {"eid", "civ", "home", "forest", "stage", "crew", "cut_end",
                                                   "unpaid", "recalled", "cargo_after", "wages_due_milli"},
    ("timber_supply_state", "StoreRow"): {"region", "held"},
    ("timber_supply_state", "NeedRow"): {"status", "reason"},
    ("repair_projects_state", "RepairProject"): {"pid", "kind", "asset", "region", "cause", "opened_turn",
                                                 "closed_turn", "opened_condition", "scope", "delivered",
                                                 "timber_used", "status", "history", "last_crew"},
    ("repair_projects_state", "RepairReceipt"): {"pid", "kind", "asset", "region", "status", "reasons",
                                                 "timber_used", "credited"},
    ("repair_projects_state", "UnmetNeed"): {"reason"},
    ("apprenticeship_state", "Apprenticeship"): set(_ARCHIVE),
    ("apprenticeship_state", "SiteReceipt"): {"site", "region", "operating", "crew", "qualified_on_crew",
                                              "qualified_in_region", "graduates_on_crew", "offset_by_graduates",
                                              "offset_by_via", "upkeep_offset", "wear", "condition_before",
                                              "condition_after", "seats"},
    ("apprenticeship_state", "Seat"): {"agent_id", "aboard", "reason", "outcome"},
    ("operating_wear_state", "WearReceipt"): {"turn", "site", "wear", "upkeep_offset", "condition_after",
                                              "qualified_on_crew"},
    ("workshops_state", "WorkshopReceipt"): {"site", "region", "payer", "paid", "condition_after"},
    ("recovery_crews_state", "CrewReceipt"): {"pid", "kind", "region", "payer", "eligible", "planned", "capacity",
                                              "requested", "delivered", "short", "members", "wages_milli",
                                              "sunk_milli"},
    ("recovery_crews_state", "CrewMember"): {"agent_id", "origin", "worked", "wage_milli", "veteran"},
    ("maintenance_obligation_state", "ReservationUse"): {"used", "returned"},
}
#: Declared values this script matches: (module, tuple name) -> values.
VALUES_READ = {
    ("timber_supply_state", "REFUSALS"): set(FOREST_REFUSALS),
    ("timber_supply_state", "STATUSES"): {"delivered", "abandoned"},
    ("timber_supply_state", "END_REASONS"): {"crew_lost"},
    ("repair_projects_state", "PROJECT_STATUSES"): {"completed"},
    ("repair_projects_state", "CAUSES"): {"wear"},
    ("repair_projects_state", "REASONS"): {"no_people"},
    ("repair_projects_state", "UNMET_REASONS"): {"no_people"},
    ("apprenticeship_state", "END_REASONS"): {"completed", "long_absence", "stalled"},
    ("apprenticeship_state", "MISS_REASONS"): {"no_mentor"},
}
#: Dated RS2 project history events (``repair_projects._note``) this script matches.
HISTORY_EVENTS = ("suspended_no_people", "resumed")


def check_fields() -> None:
    """Every record field and declared value this script reads exists in this
    checkout's source (its models, reason tuples and RS2's dated notes), and the
    fallback operating floor is the workshops' own. Raises SystemExit naming each problem."""
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))
    from importlib import import_module
    problems = []
    for (module, model), fields in FIELDS_READ.items():
        declared = set(getattr(import_module(f"chronicler.{module}"), model).model_fields)
        problems += [f"{model}.{f} is not a field" for f in sorted(fields - declared)]
    for (module, name), values in VALUES_READ.items():
        declared = set(getattr(import_module(f"chronicler.{module}"), name))
        problems += [f"{module}.{name} does not declare {v!r}" for v in sorted(values - declared)]
    source = (REPO / "src" / "chronicler" / "repair_projects.py").read_text(encoding="utf-8")
    problems += [f"repair_projects.py notes no {e!r} event" for e in HISTORY_EVENTS if f'"{e}"' not in source]
    if import_module("chronicler.workshops").OPERATE_CONDITION != OPERATE_CONDITION:
        problems.append("OPERATE_CONDITION differs from workshops.OPERATE_CONDITION")
    if problems:
        raise SystemExit("productive-recovery examples do not match the source: " + "; ".join(problems))


def find(bundle: dict) -> dict:
    """{group: {kind: (snapshot turn, row) | None | note}} for the groups whose
    packages the run recorded (a group whose records are absent is left out)."""
    hist = bundle.get("history") or []
    out = {}
    for group, (needs, finder) in FINDERS.items():
        if all(_has(hist, name) for name in needs):
            out[group] = finder(hist)
    return out


def rules_version(bundle: dict):
    """The apprenticeship rules version the run's records state (None: no RS1 record)."""
    for _turn, rec in _records(bundle.get("history") or [], "apprenticeship"):
        return rec.get("rules_version", rec.get("schema_version"))
    return None


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    sys.path.insert(0, str(REPO / "src"))
    from chronicler.bundle_codec import load_bundle
    for path in argv:
        b = load_bundle(Path(path))
        seed = (b.get("metadata") or {}).get("seed")
        hist = b.get("history") or []
        modes = {}
        for name in ("apprenticeship", "timber_supply", "recovery_crews", "maintenance_obligation", "repair_projects"):
            first = next(_records(hist, name), None)
            if first is not None:
                modes[name] = first[1].get("mode")
        print(f"== {path} (seed {seed}, {len(hist)} snapshots; natural; modes {json.dumps(modes, sort_keys=True)}; "
              f"RS1 rules {rules_version(b)})")
        found = find(b)
        for group in FINDERS:
            if group not in found:
                print(f"  {group}: not recorded in this run")
                continue
            print(f"  {group}")
            for kind, hit in found[group].items():
                if hit is None:
                    print(f"    {kind}: none found")
                elif isinstance(hit, str):
                    print(f"    {kind}: {hit}")
                else:
                    turn, row = hit
                    print(f"    {kind}: snapshot {turn}: {json.dumps(row, sort_keys=True)[:600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
