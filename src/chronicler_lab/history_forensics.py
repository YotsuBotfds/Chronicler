"""Read-only event ancestry and surviving historical accounts from a bundle.

Recorded ``Event.causes`` are dependencies emitted by the simulation, not
proof that removing a cause would prevent its effect. This reader never
infers causal edges from chronology, prose, account citations or type pairs.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from chronicler.bundle_codec import decode_bundle
from chronicler.historical_context import AsOf, Phase
from chronicler.historiography import ACCOUNT_COLUMNS, AccountIndex


INTERPRETATION = (
    "The event timeline is the simulation's record; accounts are its chroniclers' claims. "
    "An ancestry edge is a recorded dependency, not a proven counterfactual: this report "
    "does not establish that removing a cause would prevent its effect. Missing edges "
    "mean no dependency was recorded here, not that the event had no cause."
)


class ForensicsError(ValueError):
    """An input cannot identify a dated event unambiguously."""


@dataclass(frozen=True)
class Limits:
    """Bounds on the returned graph (nodes includes the selected event).

    Indexing is linear in the input timeline/accounts. Traversal and report
    size are bounded independently of the size or branching of that graph.
    """

    max_nodes: int = 200
    max_edges: int = 1000
    max_depth: int = 20
    max_accounts: int = 20  # per event

    def __post_init__(self) -> None:
        for key, low, high in (("max_nodes", 1, 10000), ("max_edges", 1, 50000),
                               ("max_depth", 0, 256), ("max_accounts", 1, 1000)):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ForensicsError(f"{key} must be an integer in {low}..{high}")


def _turn(value: Any) -> int | None:
    return value if type(value) is int else None


def _check_historiography(hist: dict) -> None:
    """Fail clearly on malformed optional tables before indexing them."""
    for key, identity in (("chroniclers", "id"), ("archives", "owner"), ("contested", "event_id")):
        rows = hist.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(r, Mapping) or not isinstance(r.get(identity), str)
                                             for r in rows):
            raise ForensicsError(f"historiography.{key} must be a list of objects with {identity}")
    for row in hist.get("chroniclers", []):
        if not isinstance(row.get("name"), str):
            raise ForensicsError("historiography chroniclers must have names")
    plain = hist.get("plain", {})
    if not isinstance(plain, Mapping) or any(
        not isinstance(cid, str) or not isinstance(ids, list)
        or any(not isinstance(eid, str) or not eid for eid in ids) for cid, ids in plain.items()
    ):
        raise ForensicsError("historiography.plain must map chronicler ids to lists of event ids")
    for archive in hist.get("archives", []):
        losses = archive.get("losses", [])
        if not isinstance(losses, list) or any(
            not isinstance(loss, Mapping) or _turn(loss.get("turn")) is None for loss in losses
        ):
            raise ForensicsError("historiography archive losses must be dated objects")
    columns = hist.get("account_columns") or list(ACCOUNT_COLUMNS)
    if (not isinstance(columns, (list, tuple)) or any(not isinstance(c, str) for c in columns)
            or len(set(columns)) != len(columns) or not {"event_id", "chronicler"}.issubset(columns)):
        raise ForensicsError("historiography.account_columns must include unique event_id and chronicler columns")
    rows = hist.get("accounts", [])
    if not isinstance(rows, list):
        raise ForensicsError("historiography.accounts must be a list of compact rows")
    for raw in rows:
        if not isinstance(raw, (list, tuple)):
            raise ForensicsError("historiography.accounts must contain compact rows")
        row = dict(zip(columns, raw))
        if any(not isinstance(row.get(key), str) for key in ("event_id", "chronicler")):
            raise ForensicsError("each account must name its event_id and chronicler")
        for key in ("turn", "lost_turn"):
            if row.get(key) is not None and _turn(row[key]) is None:
                raise ForensicsError(f"account {key} must be an integer or null")
        if row.get("text") is not None and not isinstance(row["text"], str):
            raise ForensicsError("historiography account text must be a string or null")
        cited = row.get("cited") or []
        if not isinstance(cited, list) or any(not isinstance(eid, str) for eid in cited):
            raise ForensicsError("historiography account citations must be event ids")
        transforms = row.get("transforms") or []
        if not isinstance(transforms, list) or any(
            not isinstance(t, (list, tuple)) or len(t) != 2 or not isinstance(t[0], str) for t in transforms
        ):
            raise ForensicsError("account transforms must be [kind, detail] pairs")


class HistoryForensics:
    """Index an existing bundle once, then inspect events by stable event id.

    Accepts decoded or v6 encoded bundle dictionaries. No input is changed,
    no WorldState is required, and old bundles need not have historiography.
    Events without stable ids are counted, never assigned invented ids.
    """

    def __init__(self, bundle: Mapping[str, Any]) -> None:
        if not isinstance(bundle, Mapping):
            raise ForensicsError("the bundle must be a JSON object")
        decoded = decode_bundle(bundle)
        world = decoded.get("world_state") or {}
        events = decoded.get("events_timeline", decoded.get("events"))
        if events is None and isinstance(world, Mapping):
            events = world.get("events_timeline", [])
        if not isinstance(events, list) or any(not isinstance(e, Mapping) for e in events):
            raise ForensicsError("the event timeline must be a list of event objects")
        self.events = events
        self.indices: dict[str, list[int]] = {}
        self.missing_ids = 0
        for i, ev in enumerate(events):
            eid = ev.get("event_id")
            if isinstance(eid, str) and eid:
                self.indices.setdefault(eid, []).append(i)
            else:
                self.missing_ids += 1
        metadata = decoded.get("metadata") or {}
        self.seed = metadata.get("seed") if isinstance(metadata, Mapping) else None
        self.declared_completed = (_turn(world.get("turn")) if isinstance(world, Mapping) else None)
        if self.declared_completed is not None:
            self.declared_completed -= 1
        if self.declared_completed is None and isinstance(metadata, Mapping):
            total = _turn(metadata.get("total_turns"))
            self.declared_completed = total - 1 if total is not None else None
        hist = decoded.get("historiography")
        if hist is not None and not isinstance(hist, dict):
            raise ForensicsError("historiography must be an object when present")
        self.has_accounts = isinstance(hist, dict)
        if self.has_accounts:
            _check_historiography(hist)
        self.account_index = AccountIndex(hist) if self.has_accounts else None
        # Plain accounts are compact references: the bundle did not retain
        # their original wording, stance or citations. Do not invent a quote.
        self.plain: dict[str, list[str]] = {}
        if self.has_accounts:
            for chronicler, ids in sorted((hist.get("plain") or {}).items()):
                for eid in ids:
                    self.plain.setdefault(eid, []).append(chronicler)
        dated = [_turn(e.get("turn")) for e in events]
        if self.account_index is not None:
            for rows in self.account_index.by_event.values():
                for row in rows:
                    dated.extend((_turn(row.get("turn")), _turn(row.get("lost_turn"))))
        self.last_recorded = max((t for t in dated if t is not None), default=-1)

    def _matches(self, event_id: str, as_of: AsOf | None = None) -> list[int]:
        matches = self.indices.get(event_id, [])
        if as_of is None:
            return matches
        # An undated candidate cannot safely be assigned to the future. Dated
        # future copies, however, must not change an earlier event's identity.
        return [i for i in matches
                if (turn := _turn(self.events[i].get("turn"))) is None or as_of.knows(turn)]

    def _unique(self, event_id: str, as_of: AsOf | None = None) -> int:
        matches = self._matches(event_id, as_of)
        if not matches:
            if as_of is not None and self.indices.get(event_id):
                raise ForensicsError(
                    f"event_id {event_id!r} is not known after completed turn {as_of.completed}")
            hint = (f" {self.missing_ids} timeline records have no stable event_id; "
                    "legacy records cannot be selected by invented ids.") if self.missing_ids else ""
            raise ForensicsError(f"event_id {event_id!r} was not found.{hint}")
        if len(matches) != 1:
            raise ForensicsError(f"event_id {event_id!r} is ambiguous ({len(matches)} records)")
        return matches[0]

    def _key(self, event_id: str, as_of: AsOf | None = None) -> tuple:
        matches = self._matches(event_id, as_of)
        if len(matches) != 1:
            return (float("inf"), float("inf"), event_id)
        i = matches[0]
        t = _turn(self.events[i].get("turn"))
        return (t if t is not None else float("inf"), i, event_id)

    def _accounts(self, eid: str, view: AccountIndex | None,
                  limit: int, *, as_of: AsOf) -> tuple[list[dict], int]:
        rows = list(view.accounts_for(eid)) if view is not None else []
        event = self.events[self._unique(eid, as_of)]
        for chronicler in self.plain.get(eid, []):
            rows.append({"account_id": f"{chronicler}/{eid}", "chronicler": chronicler,
                         "turn": event["turn"], "_plain": True})
        counts = Counter(r["account_id"] for r in rows)
        rows.sort(key=lambda r: (r["chronicler"], _turn(r.get("turn")) or 0, r["account_id"]))
        out = []
        for row in rows[:limit]:
            cid = row["chronicler"]
            result = {"account_id": row["account_id"], "chronicler": cid,
                      "chronicler_name": view.names.get(cid, cid) if view is not None else cid,
                      "written_turn": row.get("turn"), "text": None}
            if counts[row["account_id"]] > 1:
                result["status"] = "ambiguous"
            elif _turn(row.get("turn")) is None:
                # Older/corrupt undated claims cannot be placed in an as-of
                # view. The event's date alone does not date their writing.
                result["status"] = "undated"
            elif row.get("_plain"):
                result.update(status="surviving", representation="plain_reference",
                              summary=event.get("description") or event.get("event_type", ""),
                              wording="Original wording, stance and citations were not retained.")
            elif row.get("lost_turn") is not None:
                # Retained simulator text/transform details are not a surviving
                # claim at this point. Never include them in either format.
                result.update(status="lost", lost_turn=row["lost_turn"],
                              lost_cause=row.get("lost_cause"))
            elif not row.get("text"):
                result["status"] = "silent"
            else:
                result.update(status="surviving", representation="account", text=row["text"],
                              stance=row.get("stance"), cited=list(row.get("cited") or []),
                              bias_kinds=sorted({t["kind"] for t in row.get("transforms") or []}))
            out.append(result)
        return out, max(0, len(rows) - limit)

    def inspect(self, event_id: str, *, as_of: AsOf | None = None,
                limits: Limits | None = None) -> dict[str, Any]:
        """Report the event, surviving accounts and dated causal ancestry.

        ``as_of`` uses historical_context's completed-turn convention; END T
        includes records/losses dated T, START T includes only dates < T.
        Selecting an event not yet known is an error. Unknown dates are not
        guessed. The default is the bundle's declared last completed turn,
        or the latest recorded event/account/loss when no horizon is given.
        """
        limits = limits or Limits()
        point = as_of or AsOf.after(self.declared_completed if self.declared_completed is not None
                                   else self.last_recorded)
        if type(point.turn) is not int or not isinstance(point.phase, Phase):
            raise ForensicsError("as_of must have an integer turn and a historical_context.Phase")
        selected_i = self._unique(event_id, point)
        event_key = lambda eid: self._key(eid, point)
        selected_turn = _turn(self.events[selected_i].get("turn"))
        if selected_turn is None:
            raise ForensicsError(f"event_id {event_id!r} has no integer turn")
        if not point.knows(selected_turn):
            raise ForensicsError(f"event_id {event_id!r} is not known after completed turn {point.completed}")
        view = self.account_index.as_of(point) if self.account_index is not None else None
        distance = {event_id: 0}
        queue = deque([event_id])
        edges: list[dict] = []
        diagnostics: list[dict] = []
        truncated: set[str] = set()

        def diagnostic(kind: str, effect: str, cause: str | None = None) -> None:
            row = {"kind": kind, "event_id": effect}
            if cause is not None:
                row["cause_id"] = cause
            diagnostics.append(row)

        while queue:
            effect = queue.popleft()
            i = self._unique(effect, point)
            ev = self.events[i]
            causes = ev.get("causes") or []
            if not isinstance(causes, list) or any(not isinstance(c, str) or not c for c in causes):
                diagnostic("invalid_causes", effect)
                continue
            for cause in sorted(set(causes), key=event_key):
                if len(edges) >= limits.max_edges:
                    truncated.add("max_edges")
                    break
                edge = {"cause_id": cause, "effect_id": effect, "status": "recorded"}
                matches = self._matches(cause, point)
                ct = _turn(self.events[matches[0]].get("turn")) if len(matches) == 1 else None
                if not matches:
                    if self.indices.get(cause):
                        edge["status"] = "after_as_of"
                        diagnostic("cause_after_as_of", effect, cause)
                    else:
                        edge["status"] = "dangling"
                        diagnostic("dangling_id", effect, cause)
                elif len(matches) > 1:
                    edge["status"] = "ambiguous"
                    diagnostic("duplicate_event_id", effect, cause)
                elif ct is None:
                    edge["status"] = "undated"
                    diagnostic("undated_cause", effect, cause)
                elif not point.knows(ct):
                    edge["status"] = "after_as_of"
                    diagnostic("cause_after_as_of", effect, cause)
                else:
                    if ct > ev["turn"] or (ct == ev["turn"] and matches[0] > i):
                        diagnostic("future_cause", effect, cause)
                    if cause not in distance:
                        if distance[effect] >= limits.max_depth:
                            edge["status"] = "depth_limit"
                            truncated.add("max_depth")
                        elif len(distance) >= limits.max_nodes:
                            edge["status"] = "node_limit"
                            truncated.add("max_nodes")
                        else:
                            distance[cause] = distance[effect] + 1
                            queue.append(cause)
                edges.append(edge)
        # Iterative DFS detects directed cycles in the visited dependency
        # graph, without recursion limits or exponential path enumeration.
        parents: dict[str, list[str]] = {eid: [] for eid in distance}
        for edge in edges:
            if edge["status"] == "recorded":
                parents[edge["effect_id"]].append(edge["cause_id"])
        color: dict[str, int] = {}
        for start in sorted(distance, key=event_key):
            if color.get(start):
                continue
            color[start] = 1
            stack = [(start, iter(parents[start]))]
            while stack:
                node, iterator = stack[-1]
                parent = next(iterator, None)
                if parent is None:
                    color[node] = 2
                    stack.pop()
                elif color.get(parent) == 1:
                    diagnostic("cycle", node, parent)
                elif not color.get(parent):
                    color[parent] = 1
                    stack.append((parent, iter(parents[parent])))

        def node(eid: str) -> dict:
            i = self._unique(eid, point)
            raw = self.events[i]
            accounts, omitted = self._accounts(eid, view, limits.max_accounts, as_of=point)
            if omitted:
                truncated.add("max_accounts")
            # Whitelist record fields; never copy mutable input objects out.
            out = {"event_id": eid, "timeline_index": i, "turn": raw["turn"],
                   "event_type": raw.get("event_type", ""), "description": raw.get("description", ""),
                   "actors": list(raw.get("actors") or []), "civs": list(raw.get("civs") or []),
                   "region": raw.get("region"), "source": raw.get("source", "aggregate"),
                   "distance": distance[eid], "accounts": accounts, "accounts_omitted": omitted}
            return out

        selected = node(event_id)
        ancestors = [node(eid) for eid in sorted(distance, key=event_key) if eid != event_id]
        edges.sort(key=lambda e: (event_key(e["effect_id"]), event_key(e["cause_id"]), e["status"]))
        diagnostics.sort(key=lambda d: (d["kind"], event_key(d["event_id"]), event_key(d.get("cause_id", ""))))
        return {
            "version": 1, "interpretation": INTERPRETATION,
            "as_of": {"turn": point.turn, "phase": point.phase.value, "completed_turn": point.completed},
            "bundle": {"seed": self.seed, "declared_completed_turn": self.declared_completed,
                       "events_without_ids": self.missing_ids,
                       "historiography": "available" if self.has_accounts else "unavailable"},
            "selected": selected, "ancestors": ancestors, "edges": edges, "diagnostics": diagnostics,
            "limits": asdict(limits), "truncated_by": sorted(truncated),
        }


def inspect_bundle(bundle: Mapping[str, Any], event_id: str, *, as_of: AsOf | None = None,
                   limits: Limits | None = None) -> dict[str, Any]:
    """One-shot form of :meth:`HistoryForensics.inspect`. Does not mutate the bundle."""
    return HistoryForensics(bundle).inspect(event_id, as_of=as_of, limits=limits)


def inspect_path(path: str | Path, event_id: str, *, as_of: AsOf | None = None,
                 limits: Limits | None = None) -> dict[str, Any]:
    """Read any shared-decoder-supported bundle and identify its source bytes."""
    path = Path(path)
    # Decode and hash the same read: a concurrently replaced input must not
    # give the report the identity of bytes it did not inspect.
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    report = inspect_bundle(decode_bundle(json.loads(raw)), event_id, as_of=as_of, limits=limits)
    report["source"] = {"name": path.name, "sha256": digest}
    return report


def _md(value: Any) -> str:
    """Escape untrusted record text for a forwardable Markdown document."""
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", "!", "|"):
        text = text.replace(char, "\\" + char)
    return " ".join(text.split())


def render_markdown(report: Mapping[str, Any]) -> str:
    """A deterministic report; no lost/silent account text is recoverable from it."""
    point = report["as_of"]
    lines = ["# Historical forensics", "", report["interpretation"], "",
             f"View: after completed turn {point['completed_turn']} "
             f"({point['phase']} of turn {point['turn']})."]
    if source := report.get("source"):
        lines += [f"Source: {_md(source['name'])}; SHA-256 `{source['sha256']}`."]
    if report["bundle"]["historiography"] == "unavailable":
        lines += ["In-world accounts are unavailable in this bundle; absence is not recorded silence."]
    if missing := report["bundle"]["events_without_ids"]:
        lines += [f"Legacy timeline records without stable ids: {missing}; these cannot be selected or linked."]
    for title, nodes in (("Selected event — simulation record", [report["selected"]]),
                         ("Recorded ancestry — chronological order", report["ancestors"])):
        lines += ["", f"## {title}", ""]
        if not nodes:
            lines += ["No dated ancestors were included. This does not establish that there was no cause."]
        for event in nodes:
            lines += [f"### {_md(event['event_id'])} — turn {event['turn']}", "",
                      f"Type: {_md(event['event_type'])}; actors: {_md(', '.join(event['actors'])) or 'none'}; "
                      f"region: {_md(event['region']) if event['region'] else 'unspecified'}.", "",
                      _md(event["description"]) or "No description recorded.", "", "Accounts as of this view:", ""]
            if not event["accounts"]:
                lines += ["- No account records available for this event; this is not evidence of silence."]
            for account in event["accounts"]:
                label = f"{_md(account['chronicler_name'])} ({_md(account['account_id'])})"
                status = account["status"]
                if status == "lost":
                    text = f"lost in turn {account['lost_turn']}; wording and claim details withheld"
                    if account.get("lost_cause"):
                        text += f" ({_md(account['lost_cause'])})"
                elif status == "silent":
                    text = "recorded silence; no account text"
                elif status == "ambiguous":
                    text = "duplicate account identity; wording withheld"
                elif status == "undated":
                    text = "writing date unknown; wording withheld from the as-of view"
                elif account["representation"] == "plain_reference":
                    text = f"surviving plain reference; summary: {_md(account['summary'])}. {account['wording']}"
                else:
                    text = "surviving claim: “" + _md(account["text"]) + "”"
                    if account["bias_kinds"]:
                        text += "; recorded transformations: " + _md(", ".join(account["bias_kinds"]))
                    if account["cited"]:
                        text += "; account cites: " + _md(", ".join(account["cited"]))
                lines += [f"- {label}: {text}."]
            if event["accounts_omitted"]:
                lines += [f"- {event['accounts_omitted']} further accounts omitted by the report limit."]
    lines += ["", "## Recorded dependency edges", ""]
    lines += [f"- {_md(e['cause_id'])} → {_md(e['effect_id'])}: {_md(e['status'])}." for e in report["edges"]]
    if not report["edges"]:
        lines += ["No dependency edges recorded for the selected event."]
    lines += ["", "## Diagnostics and limits", ""]
    lines += [f"- {_md(d['kind'])}: {_md(d['event_id'])}"
              + (f" references {_md(d['cause_id'])}" if "cause_id" in d else "") + "."
              for d in report["diagnostics"]]
    if not report["diagnostics"]:
        lines += ["- No anomalies found in the inspected subgraph."]
    lines += ["- Limits: " + ", ".join(f"{k}={v}" for k, v in report["limits"].items()) + ".",
              "- Truncated by: " + (", ".join(report["truncated_by"]) or "none") + "."]
    if report["truncated_by"]:
        lines += ["The report is partial; unexplored edges and cycles may remain."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("event_id", help="Exact Event.event_id, quoted if it contains spaces")
    parser.add_argument("--as-of", type=int, default=None, help="View at this turn (default: bundle end)")
    parser.add_argument("--phase", choices=("start", "end"), default="end", help="Default: end of turn")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="stdout format")
    parser.add_argument("--json", type=Path, help="Also write a JSON report")
    parser.add_argument("--markdown", type=Path, help="Also write a Markdown report")
    for key, value in asdict(Limits()).items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, default=value)
    args = parser.parse_args(argv)
    if args.as_of is None and args.phase != "end":
        parser.error("--phase start requires --as-of")
    try:
        for destination in (args.json, args.markdown):
            if destination is not None and (destination.resolve() == args.bundle.resolve()
                                            or (destination.exists() and destination.samefile(args.bundle))):
                raise ForensicsError("a report output must not overwrite the source bundle")
        if args.json is not None and args.markdown is not None:
            if (args.json.resolve() == args.markdown.resolve()
                    or (args.json.exists() and args.markdown.exists() and args.json.samefile(args.markdown))):
                raise ForensicsError("JSON and Markdown outputs must be different files")
        limits = Limits(**{key: getattr(args, key) for key in asdict(Limits())})
        point = AsOf(args.as_of, Phase(args.phase)) if args.as_of is not None else None
        report = inspect_path(args.bundle, args.event_id, as_of=point, limits=limits)
        json_text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        markdown = render_markdown(report)
        for destination, text in ((args.json, json_text), (args.markdown, markdown)):
            if destination is not None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(text, encoding="utf-8")
        print(json_text if args.format == "json" else markdown, end="")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"history-forensics: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
