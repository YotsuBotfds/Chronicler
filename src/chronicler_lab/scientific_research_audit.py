"""Read-only finite-agenda identities and bounded recorded-history checks.

This module deliberately imports no producer/runtime models. Retained IDs and
counts are not a replacement for missing trial or evidence receipt bodies.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math

RULE = "finite-retained-v1"
SYSTEM = "scientific_claims"
CAPS = {"topics": 20, "trials": 40, "proposals": 400, "receipts": 800,
        "messages": 1200, "cycles": 10, "seats": 20}
META_KEYS = frozenset(("schema_version", "rule", "enabled", "enabled_turn",
    "current_cycle_id", "next_open_turn", "opening_interval", "funding_window",
    "original_window", "effort_started_turn", "effort_cadence", "paid_use_seasons",
    "origin_cursor", "blocked_reason", "blocked_turn", "capacity", "archive", "cycles"))
CYCLE_KEYS = frozenset(("id", "legacy_adopted", "opening_roster_complete", "opened_turn",
    "origin_seat", "participants", "claims", "trials", "announcement_event_id",
    "closed_turn", "close_reason", "unfunded_originals", "unfunded_replications",
    "slot_reasons", "original_deadline", "funding_deadline", "next_open_not_before",
    "opening_roster_scope"))
ARCHIVE_KEYS = frozenset(("retained_topics", "retained_trials", "retained_proposals",
    "retained_receipts", "raw_records_retained", "trial_details_scope", "historical_export_completeness"))


def _int(value, low=0, high=None):
    # Bound direct-Python inputs as well as JSON inputs; IDs/dates are scalar.
    return type(value) is int and low <= value and value.bit_length() <= 63 and (high is None or value <= high)


def _text(value, *, nonempty=False):
    return isinstance(value, str) and len(value) <= 4096 and (bool(value) or not nonempty)


def _actual(value, source, *, optional=False):
    return (optional and value is None) or (_int(value) and value <= source)


def _ids(values, maximum, high=None):
    return (isinstance(values, list) and len(values) <= maximum
        and all(_int(v, high=high) for v in values) and len(values) == len(set(values)))


def _metadata(science, source):
    """Validate bounded v1 structure/actual dates without exporting unknown data."""
    if not isinstance(science, Mapping) or not _int(source) or type(science.get("source_turn")) is not int or science.get("source_turn") != source:
        raise ValueError("unavailable dated science section")
    raw = science.get("research_agendas")
    if not isinstance(raw, Mapping) or set(raw) != META_KEYS:
        raise ValueError("unsupported or incomplete agenda metadata")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1 or raw["rule"] != RULE:
        raise ValueError("unsupported agenda schema or rule")
    if (type(raw["enabled"]) is not bool or not _actual(raw["enabled_turn"], source)
            or not _int(raw["next_open_turn"]) or not _int(raw["origin_cursor"], -1)
            or not _actual(raw["effort_started_turn"], source, optional=True)
            or not _actual(raw["blocked_turn"], source, optional=True)
            or not _text(raw["blocked_reason"])):
        raise ValueError("invalid or future actual agenda header")
    if any(type(raw[k]) is not int or raw[k] != v for k, v in (
            ("opening_interval", 25), ("funding_window", 24), ("original_window", 12), ("effort_cadence", 6))):
        raise ValueError("unsupported agenda timing contract")
    anchor = raw["effort_started_turn"]
    seasons = [] if anchor is None else sorted({(anchor % 12) // 3, ((anchor + 6) % 12) // 3})
    if not _ids(raw["paid_use_seasons"], 2, 3) or raw["paid_use_seasons"] != seasons:
        raise ValueError("invalid paid-use calendar")
    if bool(raw["blocked_reason"]) != (raw["blocked_turn"] is not None):
        raise ValueError("undated agenda blockage")
    cycles = raw["cycles"]
    if not isinstance(cycles, list) or len(cycles) > 10:
        raise ValueError("invalid bounded cycle table")
    open_ids = []
    for index, row in enumerate(cycles):
        if not isinstance(row, Mapping) or set(row) != CYCLE_KEYS or type(row["id"]) is not int or row["id"] != index:
            raise ValueError("invalid append-only cycle identity")
        if (type(row["legacy_adopted"]) is not bool or type(row["opening_roster_complete"]) is not bool
                or not _actual(row["opened_turn"], source, optional=True)
                or not _actual(row["closed_turn"], source, optional=True)
                or not _int(row["origin_seat"]) or not _ids(row["participants"], 20)
                or not _ids(row["claims"], 2, 19) or len(row["claims"]) != 2
                or not _ids(row["trials"], 4, 39)
                or not _ids(row["unfunded_originals"], 2, 19)
                or not _ids(row["unfunded_replications"], 2, 19)
                or not set(row["unfunded_originals"]).issubset(row["claims"])
                or not set(row["unfunded_replications"]).issubset(row["claims"])
                or not _text(row["announcement_event_id"]) or not _text(row["close_reason"])):
            raise ValueError("invalid or future actual cycle body")
        reasons = row["slot_reasons"]
        allowed_slots = {f"{kind}:{cid}" for kind in ("original", "replication") for cid in row["claims"]}
        if (not isinstance(reasons, Mapping) or len(reasons) > 4
                or any(k not in allowed_slots or not _text(v, nonempty=True) for k, v in reasons.items())):
            raise ValueError("invalid bounded slot reasons")
        opened, closed = row["opened_turn"], row["closed_turn"]
        if closed is not None and (opened is not None and closed < opened):
            raise ValueError("inverted actual cycle dates")
        if row["legacy_adopted"]:
            if (index != 0 or row["opening_roster_complete"] or opened is not None and opened > raw["enabled_turn"]
                    or closed != raw["enabled_turn"] or row["opening_roster_scope"] != "observed_at_legacy_activation"
                    or any(row[k] is not None for k in ("original_deadline", "funding_deadline", "next_open_not_before"))):
                raise ValueError("invalid legacy activation scope")
        else:
            if (not row["opening_roster_complete"] or opened is None or opened < raw["enabled_turn"]
                    or row["origin_seat"] not in row["participants"]
                    or row["opening_roster_scope"] != "frozen_at_actual_opening"
                    or not row["announcement_event_id"]):
                raise ValueError("invalid actual opening roster")
            for key, offset in (("original_deadline", 11), ("funding_deadline", 23), ("next_open_not_before", 25)):
                if type(row[key]) is not int or row[key] != opened + offset:
                    raise ValueError("invalid inclusive funding windows")
            if closed is None:
                if source > opened + 23:
                    raise ValueError("open funding cycle exceeds its deadline")
                open_ids.append(index)
        if (closed is None and row["close_reason"]) or (closed is not None and not row["close_reason"]):
            raise ValueError("invalid cycle closure reason")
    current = raw["current_cycle_id"]
    if current is not None and not _int(current, high=9):
        raise ValueError("invalid current funding cycle")
    if len(open_ids) > 1 or open_ids != ([] if current is None else [current]):
        raise ValueError("current cycle is not the open funding cycle")
    if not raw["enabled"] and current is not None:
        raise ValueError("paused research retains an open funding cycle")
    capacity = raw["capacity"]
    if not isinstance(capacity, Mapping) or set(capacity) != set(CAPS):
        raise ValueError("incomplete bounded capacity table")
    for key, cap in CAPS.items():
        row = capacity[key]
        if (not isinstance(row, Mapping) or set(row) != {"used", "reserved", "limit"}
                or any(not _int(row[k]) for k in row) or row["limit"] != cap):
            raise ValueError("invalid capacity quantities or limits")
    archive = raw["archive"]
    if (not isinstance(archive, Mapping) or set(archive) != ARCHIVE_KEYS
            or any(not _int(archive[k]) for k in ("retained_topics", "retained_trials", "retained_proposals", "retained_receipts"))
            or archive["raw_records_retained"] is not True
            or archive["trial_details_scope"] != "resolved_this_source_turn_only"
            or archive["historical_export_completeness"] != "not_inferred"):
        raise ValueError("unsupported retained archive scope")
    return raw


def _lineage(row):
    return {k: deepcopy(row[k]) for k in ("id", "legacy_adopted", "opening_roster_complete",
        "opened_turn", "origin_seat", "participants", "claims", "announcement_event_id", "opening_roster_scope")}


def research_agenda_identity(science_section, source_turn):
    """Return dated immutable context; unknown presence never becomes legacy.

    This is a mode/lineage reader, not full receipt/capacity qualification. All
    unknown bodies are withheld, including malformed/future actual cycle IDs.
    """
    unknown = {"mode": "unknown", "enabled": None, "enabled_turn": None, "cycle_lineage": None}
    if (not isinstance(science_section, Mapping) or not _int(source_turn)
            or type(science_section.get("source_turn")) is not int or science_section.get("source_turn") != source_turn):
        return unknown
    if "research_agendas" not in science_section:
        return {"mode": "legacy", "enabled": None, "enabled_turn": None, "cycle_lineage": []}
    try:
        raw = _metadata(science_section, source_turn)
    except (ValueError, TypeError, OverflowError):
        return unknown
    return {"mode": RULE, "enabled": raw["enabled"], "enabled_turn": raw["enabled_turn"],
            "cycle_lineage": [_lineage(row) for row in raw["cycles"]]}


class ResearchAgendasAudit:
    """Checks only dated exported tables, sharing the parent reader's budgets."""
    def __init__(self, science):
        self.science, self.a = science, science.a
        self.previous = None
        self.last_source = None
        self.current = None
        self.canonical = {}
        self.resolved = {}

    def _out(self):
        return self.science.out.setdefault("research_agendas", {
            "recorded_turns": 0, "unsupported_turns": 0, "enabled_turns": 0, "paused_turns": 0,
            "rule": None, "schema_version": None, "latest_source_turn": None,
            "latest_capacity": None, "latest_retained_archive_counts": None,
            "cycle_details": [], "paid_allocation_details": [], "paid_topic_attribution_complete": True,
            "trial_details_scope": "resolved_this_source_turn_only",
            "historical_trial_and_receipt_export_completeness": "not_inferred"})

    def finding(self, code, source, detail, rid=None):
        self.science.finding(code, source, detail, rid)

    def check(self, key, good):
        self.science.check("research_agendas." + key, good)

    def unavailable(self, key):
        self.a.check(SYSTEM + ".research_agendas." + key, "unavailable")

    def detail(self, table, row):
        out = self._out()
        if len(out[table]) < self.a.limits.max_details:
            out[table].append(row)
        else:
            self.science.detail_omissions["agenda_" + table] += 1

    def begin(self, state, source):
        """Fail closed before the legacy reader can interpret unknown presence."""
        if self.last_source is None or self.last_source + 1 != source:
            self.previous = None
            self.canonical.clear()
            self.resolved.clear()
        self.last_source = source
        self.current = None
        if "research_agendas" not in state:
            if self.previous is not None:
                self.finding("research_agenda_metadata_disappeared", source,
                    "A retained agenda plan disappeared inside continuous recorded coverage; pausing must retain its metadata.")
                self.previous = None
            return True
        out = self._out()
        try:
            raw = _metadata(state, source)
        except (ValueError, TypeError, OverflowError):
            out["unsupported_turns"] += 1
            out["paid_topic_attribution_complete"] = False
            self.a.truncated.add("unsupported_research_agenda_metadata")
            self.finding("unsupported_research_agenda_metadata", source,
                "Present agenda metadata is unknown, incomplete, malformed or contains unavailable actual dates; its body is withheld and agenda completeness is not inferred.")
            self.unavailable("schema_and_actual_dates")
            self.previous = None
            self.canonical.clear()
            self.resolved.clear()
            return False
        self.current = raw
        out["rule"], out["schema_version"] = RULE, 1
        out["recorded_turns"] += 1
        out["enabled_turns" if raw["enabled"] else "paused_turns"] += 1
        self.check("schema_and_actual_dates", True)
        return True

    def process(self, state, source, tables, complete):
        raw = self.current
        if raw is None:
            return
        cycles, cycle_complete = self.a.rows(raw["cycles"], SYSTEM, source, "research_agenda_cycles")
        # Semantic checks that require a whole retained table are never run on a
        # truncated table. The bounded header reader alone is not qualification.
        if not cycle_complete:
            self._out()["paid_topic_attribution_complete"] = False
            self.previous = None
            self.unavailable("complete_retained_membership")
            return
        out = self._out()
        if not complete:
            out["paid_topic_attribution_complete"] = False
        out["latest_source_turn"] = source
        out["latest_capacity"] = deepcopy(raw["capacity"])
        out["latest_retained_archive_counts"] = deepcopy(raw["archive"])
        previous = self.previous
        if previous is not None:
            prior = previous[1]
            good = (raw["enabled_turn"] == prior["enabled_turn"]
                and (prior["effort_started_turn"] is None or raw["effort_started_turn"] == prior["effort_started_turn"]))
            self.check("activation_identity", good)
            if not good:
                self.finding("changed_research_activation", source,
                    "Immutable activation date or an established paid-effort calendar changed inside continuous coverage.")
            good = len(cycles) >= len(prior["cycles"])
            self.check("append_only_cycles", good)
            if not good:
                self.finding("removed_research_cycle", source, "Retained cycle IDs disappeared inside continuous coverage.")
            for old, new in zip(prior["cycles"], cycles):
                identity_ok = _lineage(old) == _lineage(new)
                self.check("immutable_opening_membership", identity_ok)
                if not identity_ok:
                    self.finding("changed_research_opening", source,
                        "An existing cycle changed its immutable opening roster, canonical membership, origin or announcement.", new["id"])
                trials_ok = new["trials"][:len(old["trials"])] == old["trials"]
                self.check("append_only_trial_membership", trials_ok)
                if not trials_ok:
                    self.finding("changed_research_trial_membership", source,
                        "Existing retained paid trial membership changed or disappeared.", new["id"])
                if old["closed_turn"] is not None:
                    closed_ok = all(new[k] == old[k] for k in ("closed_turn", "close_reason", "unfunded_originals", "unfunded_replications", "slot_reasons", "trials"))
                    self.check("immutable_cycle_closure", closed_ok)
                    if not closed_ok:
                        self.finding("changed_research_closure", source, "A closed retained cycle changed its terminal receipt.", new["id"])
            for new in cycles[len(prior["cycles"]):]:
                if new["legacy_adopted"] or new["opened_turn"] != source or not raw["enabled"]:
                    self.finding("unrecorded_or_paused_research_opening", source,
                        "A newly observed cycle inside continuous coverage needs an enabled actual opening on this source turn.", new["id"])
        trial_owners = {}
        for index, cycle in enumerate(cycles):
            if index and not cycle["legacy_adopted"]:
                old = cycles[index - 1]
                earliest = raw["enabled_turn"] + 25 if old["legacy_adopted"] else old["opened_turn"] + 25
                good = (cycle["opened_turn"] >= earliest and old["closed_turn"] is not None
                    and old["closed_turn"] <= cycle["opened_turn"])
                self.check("opening_interval", good)
                if not good:
                    self.finding("early_research_opening", source, "A retained agenda violates the minimum opening interval or overlaps its predecessor's actual funding history.", cycle["id"])
            if cycle["legacy_adopted"]:
                self.unavailable("legacy_opening_roster_and_windows")
            else:
                self.a.event_ref(cycle["announcement_event_id"], "scientific_research_agenda_opened",
                    cycle["opened_turn"], SYSTEM, source, cycle["id"])
            for tid in cycle["trials"]:
                if tid in trial_owners:
                    self.finding("duplicate_research_trial_membership", source,
                        "A paid trial ID belongs to more than one retained agenda.", tid)
                trial_owners[tid] = cycle
            lineage = _lineage(cycle)
            lineage["announcement_event_id"] = self.a.label(lineage["announcement_event_id"])
            self.detail("cycle_details", {"source_turn": source, **lineage,
                "trial_ids": list(cycle["trials"]), "closed_turn": cycle["closed_turn"],
                "close_reason": self.a.label(cycle["close_reason"]),
                "original_deadline": cycle["original_deadline"], "funding_deadline": cycle["funding_deadline"],
                "next_open_not_before": cycle["next_open_not_before"]})
        earliest = (cycles[-1]["opened_turn"] + 25 if cycles and not cycles[-1]["legacy_adopted"]
            else raw["enabled_turn"] + (25 if cycles else 0))
        cursor = cycles[-1]["origin_seat"] if cycles else -1
        good = raw["next_open_turn"] >= earliest and raw["origin_cursor"] == cursor
        self.check("planned_opening_and_origin", good)
        if not good:
            self.finding("research_opening_plan_mismatch", source, "Earliest next opening or last actual origin disagrees with retained cycles.")
        cap, archive = raw["capacity"], raw["archive"]
        good = all(row["used"] + row["reserved"] <= row["limit"] for row in cap.values())
        self.check("capacity_conservation", good)
        if not good:
            self.finding("research_capacity_overcommitted", source, "Recorded used plus reserved capacity exceeds a fixed retained-state limit.")
        expectations = {"topics": state.get("claims"), "trials": state.get("trials"),
            "receipts": state.get("evidence_receipts"), "messages": state.get("pending_messages"),
            "cycles": len(cycles), "seats": state.get("seats")}
        good = all(type(value) is int and cap[key]["used"] == value for key, value in expectations.items())
        good &= all(cap[key]["reserved"] == 0 for key in ("topics", "cycles", "seats"))
        good &= all(archive["retained_" + field] == cap[key]["used"] for field, key in (
            ("topics", "topics"), ("trials", "trials"), ("proposals", "proposals"), ("receipts", "receipts")))
        self.check("retained_counts", good)
        if not good:
            self.finding("research_retained_count_mismatch", source, "Agenda capacity/archive counts disagree with their dated core counts or fixed zero reservations.")
        memberships_ok = type(state.get("trials")) is int and sorted(trial_owners) == list(range(min(40, state["trials"]))) and state["trials"] <= 40
        self.check("complete_retained_membership", memberships_ok)
        if not memberships_ok:
            self.finding("research_trial_membership_mismatch", source,
                "Retained cycle membership does not cover exactly the funded trial IDs; this does not expose their missing bodies.")
        unpaid = sum(4 - len(c["trials"]) for c in cycles if c["closed_turn"] is None)
        owed_receipts = sum((4 - len(c["trials"])) * (20 if c["legacy_adopted"] else len(c["participants"]))
            for c in cycles if c["closed_turn"] is None)
        good = cap["trials"]["reserved"] == unpaid and cap["receipts"]["reserved"] >= owed_receipts
        owed = cap["proposals"]["reserved"] + cap["receipts"]["reserved"]
        good &= max(0, owed - cap["messages"]["used"]) <= cap["messages"]["reserved"] <= owed
        self.check("reservation_bounds", good)
        if not good:
            self.finding("research_reservation_mismatch", source,
                "Open unpaid trial slots or recorded receipt/message obligations violate the quantities observable in this summary.")
        self.unavailable("full_historical_trial_and_receipt_bodies")
        props = {}
        for row in tables["propositions"]:
            cid, proposed = row.get("id"), row.get("proposed_turn")
            if not _int(cid, high=19) or not _actual(proposed, source):
                continue
            key = _canonical(row)
            if key is None:
                self.finding("invalid_canonical_research_topic", source, "Canonical agenda topics need finite metric/comparator/intervention/horizon and bounded recorded context.", cid)
                continue
            if cid in self.canonical and self.canonical[cid] != key:
                self.finding("changed_canonical_research_topic", source, "A retained canonical topic changed inside continuous finite-mode coverage.", cid)
            self.canonical.setdefault(cid, key)
            protocol_ok = _protocol(row)
            self.check("registered_canonical_protocol", protocol_ok)
            if not protocol_ok:
                self.finding("unsupported_canonical_research_protocol", source, "Canonical topic literals differ from the registered finite-retained-v1 grain-output protocol.", cid)
            props[cid] = row
        if complete:
            topic_count = state.get("claims")
            good = (_int(topic_count, high=20) and sorted(props) == list(range(topic_count))
                and len({_canonical(row) for row in props.values()}) == len(props))
            self.check("append_only_canonical_ids", good)
            if not good:
                self.finding("research_canonical_identity_mismatch", source, "The complete dated topic table must have consecutive unique canonical IDs and no duplicate full protocol/context keys.")
            referenced = {cid for cycle in cycles for cid in cycle["claims"]}
            roster = {seat for cycle in cycles for seat in (*cycle["participants"], cycle["origin_seat"])}
            roster.update(row.get("origin_seat") for row in props.values() if _int(row.get("origin_seat")))
            good = referenced == set(props) and len(roster) <= cap["seats"]["used"]
            self.check("retained_topic_and_roster_bounds", good)
            if not good:
                self.finding("research_retained_topic_or_roster_mismatch", source, "Canonical cycle references or retained institution counts cannot cover the complete dated topic/roster tables.")
            for cycle in cycles:
                available = [props.get(cid) for cid in cycle["claims"]]
                good = all(row is not None for row in available)
                if good:
                    good = ({row["recipe"] for row in available} == {"irrigation", "masonry"}
                        and _context(available[0]) == _context(available[1]))
                self.check("canonical_cycle_membership", good)
                if not good:
                    self.finding("research_cycle_topic_mismatch", source, "A cycle needs the two canonical recipes for one available dated context.", cycle["id"])
        for row in tables["trials_resolved"]:
            tid, cid, funded, resolved = (row.get(k) for k in ("id", "claim", "funded_turn", "resolved_turn"))
            if not _int(tid, high=39) or not _actual(funded, source) or resolved != source or not _int(cid, high=19) or cid not in props:
                continue
            cycle = trial_owners.get(tid)
            if cycle is None:
                self.finding("research_trial_without_agenda", source, "An actual resolution has no retained agenda membership.", tid)
                continue
            parent, seat = row.get("parent"), row.get("seat")
            good = cid in cycle["claims"]
            if not cycle["legacy_adopted"]:
                good &= (seat in cycle["participants"] and cycle["opened_turn"] <= funded <= cycle["funding_deadline"]
                    and (cycle["closed_turn"] is None or funded <= cycle["closed_turn"]))
                if _int(parent, -1) and parent < 0:
                    good &= seat == cycle["origin_seat"] and funded <= cycle["original_deadline"]
                elif _int(parent):
                    good &= parent in cycle["trials"] and parent != tid
                    prior = self.resolved.get(parent)
                    if prior is None:
                        self.unavailable("replication_parent_body")
                    else:
                        good &= prior["claim"] == cid and prior["parent"] < 0 and prior["seat"] != seat and funded >= prior["funded_turn"] + 12
                else:
                    good = False
            else:
                self.unavailable("legacy_trial_windows_and_audience")
            self.check("observed_trial_funding_window", good)
            if not good:
                self.finding("research_trial_window_or_membership", source, "An exported actual trial violates its recorded canonical, roster, parent or funding-window contract.", tid)
            if row.get("status") in ("completed", "cancelled", "failed") and _int(parent, -1) and _int(seat):
                self.resolved[tid] = {"claim": cid, "parent": parent, "seat": seat, "funded_turn": funded}
        if tables["allocations"]:
            anchor = raw["effort_started_turn"]
            good = anchor is not None and source >= anchor and (source - anchor) % raw["effort_cadence"] == 0
            self.check("actual_paid_use_calendar", good)
            if not good:
                self.finding("research_paid_use_calendar_mismatch", source, "Recorded paid use occurs outside its retained paid-effort calendar.")
        for row in tables["allocations"]:
            cid = row.get("claim_id")
            claim = props.get(cid) if _int(cid, high=19) else None
            good = claim is not None and row.get("recipe") == claim["recipe"]
            legacy_unknown = (not good and cid is None and source == raw["enabled_turn"]
                and bool(cycles) and cycles[0]["legacy_adopted"])
            if legacy_unknown:
                self.unavailable("actual_paid_canonical_topic")
            else:
                self.check("actual_paid_canonical_topic", good)
            if not good:
                out["paid_topic_attribution_complete"] = False
                if legacy_unknown:
                    # Activation may occur through the internal API after old
                    # Phase 4 paid work in this same source turn. Its unknown
                    # canonical identity is legitimate, never inferred.
                    self.unavailable("legacy_activation_paid_topic")
                    continue
                self.finding("unknown_paid_research_topic", source,
                    "Agenda-mode paid use lacks its actual Phase 4 canonical claim ID; recipe or final belief cannot supply it.")
                continue
            if not _int(row.get("seat")) or any(not _finite(row.get(k)) for k in ("confidence", "share", "paid")):
                continue
            self.detail("paid_allocation_details", {"source_turn": source, "seat": row.get("seat"),
                "claim_id": cid, "recipe": claim["recipe"], "funded_topic_context": {self.a.label(k): self.a.label(v) if isinstance(v, str) else v for k, v in claim["context"].items()},
                "phase4_confidence": row.get("confidence"), "share": row.get("share"), "paid": row.get("paid")})
        if not raw["enabled"]:
            self.unavailable("paused_funding_vs_retained_knowledge")
            events = self.science.events_by_turn
            if events is None or not self.a.event_complete:
                self.unavailable("paused_no_new_funding")
            else:
                good = not any(e.get("event_type") in ("scientific_trial_funded", "scientific_research_agenda_opened") for e in events.get(source, []))
                self.check("paused_no_new_funding", good)
                if not good:
                    self.finding("funding_while_research_paused", source,
                        "Paused agenda metadata coincides with new funding/opening events; old resolutions, delivery and paid knowledge use remain permitted.")
        self.previous = (source, deepcopy(raw))


def _context(row):
    context = row.get("context")
    if not isinstance(context, Mapping) or len(context) > 16:
        return None
    if any(not isinstance(k, str) or len(k) > 128 or type(v) not in (str, int, float, bool, type(None))
           or isinstance(v, str) and len(v) > 4096 or type(v) is int and not _int(v, -(2**63))
           or type(v) is float and not math.isfinite(v)
           for k, v in context.items()):
        return None
    return tuple(sorted(context.items()))


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _canonical(row):
    context = _context(row)
    if (context is None or row.get("recipe") not in ("irrigation", "masonry")
            or not _text(row.get("metric"), nonempty=True) or not _int(row.get("horizon"), 1)
            or any(not _finite(row.get(k)) for k in ("comparator", "intervention", "threshold"))):
        return None
    return (row["recipe"], context, row["metric"], row["comparator"], row["intervention"], row["horizon"], row["threshold"])


def _protocol(row):
    context = row["context"]
    return (row["metric"] == "grain_output" and row["comparator"] == 0. and row["intervention"] == 1.
        and row["horizon"] == 1 and row["threshold"] == .02
        and set(context) == {"crop", "soil_band", "water_band", "season", "climate_phase", "crew", "protocol"}
        and context.get("crop") == "grain" and context.get("protocol") == "fixed-crew-grain-v1"
        and type(context.get("crew")) is int and context["crew"] == 4
        and all(_int(context.get(k), high=3) for k in ("soil_band", "water_band", "season"))
        and _text(context.get("climate_phase")))
