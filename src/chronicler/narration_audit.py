"""Check narrated passages against what their narrators were given. No LLM.

``python -m chronicler.narration_audit BUNDLE [BUNDLE ...] [--narrated FILE] [--json OUT] [--show N] [--exit-zero]``

``--narrated`` reads the entries of a ``--narrate`` output file (which holds
no timeline) and checks them against the one source ``BUNDLE``.

Every chronicle entry with provenance (``ChronicleEntry.provenance``,
``chronicler.narration_provenance``) is checked against its own record and
the bundle. Flags:

``unsupplied_citation``
    a cited id that names a record of the bundle but was not among the
    facts the passage's narrator was given;
``unknown_citation``
    a cited id that names nothing in the bundle and was not given;
``future_citation``
    a cited fact dated after the narrated moment (``as_of``) that was not
    given as retrospective (the prompt's AFTER / LATER CONSEQUENCES);
``future_supplied``
    a fact dated after the moment given outside a retrospective section (the
    prompt builder leaked a later record);
``unsupplied_name``
    a character, civilization, region or faith the prose names that no
    given fact names;
``stray_marker``
    a fact id left in the shown prose (a citation written another way);
``unresolved_fact``, ``date_mismatch``
    a given fact the bundle does not hold, or holds with another date;
``bad_span``
    a span outside the prose or out of order;
``uncited_sentence``, ``uncovered_text``
    mechanical entries only: a sentence without facts, or prose outside
    every span (the mechanical narrator cites every sentence exactly).

Entries without provenance (older bundles, unnarrated turns) are counted,
not flagged. ``audit_bundle`` and ``audit_entry`` are the library forms.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from chronicler.narration_provenance import STRAY_ID, EntityUniverse, expand_entries, fact_rows

FLAG_KINDS = (
    "unsupplied_citation", "unknown_citation", "future_citation", "future_supplied",
    "unsupplied_name", "stray_marker", "unresolved_fact", "date_mismatch", "bad_span",
    "uncited_sentence", "uncovered_text",
)

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")


@dataclass
class Flag:
    entry: int
    kind: str
    detail: str
    ids: list[str] = field(default_factory=list)
    span: list[int] | None = None


@dataclass
class EntryStats:
    narrator: str
    facts: int = 0
    retrospective_facts: int = 0
    spans: int = 0
    cited: int = 0
    cited_retrospective: int = 0
    sentences: int = 0
    uncited_sentences: int = 0


@dataclass
class AuditReport:
    entries: int = 0
    with_provenance: int = 0
    stats: list[EntryStats] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        c = Counter(f.kind for f in self.flags)
        return {k: c[k] for k in FLAG_KINDS if c[k]}

    def totals(self) -> dict[str, Any]:
        by = Counter(s.narrator for s in self.stats)
        return {
            "entries": self.entries,
            "with_provenance": self.with_provenance,
            "by_narrator": dict(sorted(by.items())),
            "facts": sum(s.facts for s in self.stats),
            "retrospective_facts": sum(s.retrospective_facts for s in self.stats),
            "spans": sum(s.spans for s in self.stats),
            "cited": sum(s.cited for s in self.stats),
            "cited_retrospective": sum(s.cited_retrospective for s in self.stats),
            "sentences": sum(s.sentences for s in self.stats),
            "uncited_sentences": sum(s.uncited_sentences for s in self.stats),
            "flags": self.counts(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"totals": self.totals(), "flags": [asdict(f) for f in self.flags]}


class BundleRecords:
    """What a bundle holds, for resolving fact ids: ``resolve(fid)`` gives
    (exists, date): exists None when the bundle cannot tell (a field it
    lacks), date None when the id carries none."""

    def __init__(self, bundle: dict) -> None:
        self.events = bundle.get("events_timeline") or []
        self.named = bundle.get("named_events") or []
        self.snapshots = {s.get("turn") for s in bundle.get("history") or []}
        world = bundle.get("world_state") or {}
        self.artifacts = {a.get("artifact_id"): a for a in world.get("artifacts", []) or []}
        self.agents: set[int] = set()
        for civ in world.get("civilizations", []) or []:
            for gp in civ.get("great_persons", []) or []:
                if gp.get("agent_id") is not None:
                    self.agents.add(gp["agent_id"])
        for gp in world.get("retired_persons", []) or []:
            if gp.get("agent_id") is not None:
                self.agents.add(gp["agent_id"])
        self.has_world = bool(world)
        hist = bundle.get("historiography")
        self.chroniclers: set[str] | None = None
        self.accounts: dict[tuple[str, str], int | None] = {}
        self.plain: dict[str, set[str]] = {}
        if isinstance(hist, dict):
            self.chroniclers = {c.get("id") for c in hist.get("chroniclers", [])}
            columns = list(hist.get("account_columns") or ["event_id", "chronicler", "turn"])
            ie, ic, it = (columns.index(k) if k in columns else None for k in ("event_id", "chronicler", "turn"))
            for row in hist.get("accounts", []) or []:
                if ie is not None and ic is not None:
                    self.accounts[(row[ic], row[ie])] = row[it] if it is not None else None
            self.plain = {k: set(v) for k, v in (hist.get("plain") or {}).items()}
        langs = bundle.get("languages")
        self.languages = langs if isinstance(langs, dict) else None

    def event_turn(self, i: int) -> int | None:
        return self.events[i].get("turn") if 0 <= i < len(self.events) else None

    def resolve(self, fid: str, entry: dict) -> tuple[bool | None, int | None]:
        m = re.fullmatch(r"e(\d+)", fid)
        if m:
            i = int(m.group(1))
            return (True, self.event_turn(i)) if i < len(self.events) else (False, None)
        m = re.fullmatch(r"n(\d+)", fid)
        if m:
            i = int(m.group(1))
            return (True, self.named[i].get("turn")) if i < len(self.named) else (False, None)
        m = re.fullmatch(r"((?:court|temple|seat):\d+)/e(\d+)", fid)
        if m:
            chronicler, i = m.group(1), int(m.group(2))
            if i >= len(self.events):
                return False, None
            if self.chroniclers is None:
                return None, None
            event_id = self.events[i].get("event_id")
            if (chronicler, event_id) in self.accounts:
                return True, self.accounts[(chronicler, event_id)]
            if event_id in self.plain.get(chronicler, ()):
                return True, self.event_turn(i)
            return False, None
        m = re.fullmatch(r"k(\d+)", fid)
        if m:
            return int(m.group(1)) < len(entry.get("causal_links") or []), None
        m = re.fullmatch(r"art(\d+)", fid)
        if m:
            art = self.artifacts.get(int(m.group(1)))
            if not self.has_world:
                return None, None
            return (art is not None), (art.get("origin_turn") if art else None)
        m = re.fullmatch(r"p(\d+)", fid)
        if m:
            return (int(m.group(1)) in self.agents) if self.has_world else None, None
        m = re.fullmatch(r"s(\d+)\..+", fid)
        if m:
            s = int(m.group(1))
            return s in self.snapshots, s - 1
        m = re.fullmatch(r"d(\d+)-(\d+)\..+", fid)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return (a in self.snapshots and b in self.snapshots), b - 1
        m = re.fullmatch(r"w(\d+)-(\d+)(?:\.\w+)?", fid)
        if m:
            return int(m.group(1)) <= int(m.group(2)), int(m.group(2))
        m = re.fullmatch(r"o(\d+)\..+", fid)
        if m:
            return None, int(m.group(1))
        m = re.fullmatch(r"L\.([crsfp])(\d+)", fid)
        if m:
            if self.languages is None:
                return False, None
            kind, ref = m.group(1), int(m.group(2))
            table = {"c": ("civs", "civ"), "r": ("regions", "region"), "s": ("settlements", "id"),
                     "f": ("faiths", "faith")}.get(kind)
            if kind == "p":
                return ref < len(self.languages.get("persons", []) or []), None
            rows, key = table
            return any(r.get(key) == ref for r in self.languages.get(rows, []) or []), None
        return None, None  # a fallback id (e:..., p:..., c:...): nothing to resolve


#: Fact kinds whose date the bundle gives exactly.
_EXACT_DATES = re.compile(r"^(?:e\d+|n\d+|s\d+\..+|d\d+-\d+\..+|w\d+-\d+.*|art\d+)$")


def _sentences(text: str) -> list[tuple[int, int]]:
    out = []
    for m in _SENTENCE.finditer(text):
        s, e = m.start(), m.end()
        while s < e and text[s].isspace():
            s += 1
        if s < e and text[s:e].strip():
            out.append((s, e))
    return out


def audit_entry(index: int, entry: dict, records: BundleRecords | None,
                universe: EntityUniverse | None) -> tuple[EntryStats | None, list[Flag]]:
    """Flags for one chronicle entry (a ``ChronicleEntry`` dict)."""
    prov = entry.get("provenance")
    if not prov:
        return None, []
    flags: list[Flag] = []
    narrative = entry.get("narrative") or ""
    as_of = prov.get("as_of")
    narrator = prov.get("narrator", "?")
    facts: dict[str, tuple[int | None, bool]] = {fid: (turn, retro) for fid, turn, retro in fact_rows(prov)}
    stats = EntryStats(narrator=narrator, facts=len(facts),
                       retrospective_facts=sum(1 for _t, r in facts.values() if r))

    def add(kind: str, detail: str, ids: Iterable[str] = (), span=None) -> None:
        flags.append(Flag(index, kind, detail, list(ids), list(span) if span is not None else None))

    # The facts given: in the bundle, with their dates, none later than the
    # moment outside a retrospective section.
    for fid, (turn, retro) in facts.items():
        if records is not None:
            exists, real = records.resolve(fid, entry)
            if exists is False:
                add("unresolved_fact", f"{fid} names no record of the bundle", [fid])
            elif real is not None and turn is not None and _EXACT_DATES.match(fid) and real != turn:
                add("date_mismatch", f"{fid} is dated {turn} in the provenance and {real} in the bundle", [fid])
        if turn is not None and as_of is not None and turn > as_of and not retro:
            add("future_supplied", f"{fid} (turn {turn}) was given as of turn {as_of} outside a "
                                   "retrospective section", [fid])

    # Spans and citations.
    spans = prov.get("spans") or []
    stats.spans = len(spans)
    last_end = 0
    cited: list[str] = []
    for span in spans:
        if not (isinstance(span, list) and len(span) == 3):
            add("bad_span", f"malformed span {span!r}")
            continue
        s, e, ids = span
        if not (0 <= s <= e <= len(narrative)) or (narrator == "mechanical" and s < last_end):
            add("bad_span", f"span {s}-{e} outside the prose ({len(narrative)} characters) or out of order",
                ids, [s, e])
        last_end = max(last_end, e)
        if narrator == "mechanical" and not ids and narrative[s:e].strip():
            add("uncited_sentence", f"mechanical text without facts: {narrative[s:e][:80]!r}", [], [s, e])
        for fid in ids:
            if fid not in cited:
                cited.append(fid)
            given = facts.get(fid)
            if given is None:
                exists, real = records.resolve(fid, entry) if records is not None else (None, None)
                kind = "unsupplied_citation" if exists else "unknown_citation"
                add(kind, f"{fid} is cited but was not given to the narrator"
                    + ("" if exists else " (and names no record of the bundle)"), [fid], [s, e])
                if real is not None and as_of is not None and real > as_of:
                    add("future_citation", f"{fid} (turn {real}) is after the moment (turn {as_of}) "
                                           "and was not given", [fid], [s, e])
                continue
            turn, retro = given
            if retro:
                stats.cited_retrospective += 1
            elif turn is not None and as_of is not None and turn > as_of:
                add("future_citation", f"{fid} (turn {turn}) is after the moment (turn {as_of}) "
                                       "outside a retrospective section", [fid], [s, e])
    stats.cited = len(cited)

    # Sentences without citations (LLM: counted) and text outside spans (mechanical: flagged).
    sentences = _sentences(narrative)
    stats.sentences = len(sentences)
    covered = [(s, e) for s, e, ids in (sp for sp in spans if isinstance(sp, list) and len(sp) == 3) if ids]
    stats.uncited_sentences = sum(1 for s, e in sentences if not any(a < e and s < b for a, b in covered))
    if narrator == "mechanical":
        mask = [False] * len(narrative)
        for sp in spans:
            if isinstance(sp, list) and len(sp) == 3:
                for k in range(max(0, sp[0]), min(len(narrative), sp[1])):
                    mask[k] = True
        gaps = [k for k, ch in enumerate(narrative) if not mask[k] and not ch.isspace()]
        if gaps:
            add("uncovered_text", f"{len(gaps)} characters outside every span, from "
                                  f"{narrative[gaps[0]:gaps[0] + 40]!r}", [], [gaps[0], gaps[-1] + 1])

    # Names the prose uses that no given fact names.
    if universe:
        supplied = set(prov.get("names") or [])
        seen: dict[str, list] = {}
        for s, e, names in universe.mentions(narrative):
            if any(n in supplied for n in names):
                continue
            key = narrative[s:e]
            if key in seen:
                seen[key][1] += 1
                continue
            seen[key] = [[s, e], 1, names]
        for form, (span, count, names) in seen.items():
            what = ", ".join(f"{n} ({universe.kind.get(n, '?')})" for n in names)
            add("unsupplied_name", f"{form!r} ({what}) is named {count} time(s) but no given fact names it",
                [], span)

    # Fact ids left in the shown prose.
    for m in STRAY_ID.finditer(narrative):
        add("stray_marker", f"{m.group(0)!r} left in the prose", [m.group(0)], [m.start(), m.end()])
    return stats, flags


def audit_bundle(bundle: dict, universe: EntityUniverse | None = None,
                 narrated: dict | None = None) -> AuditReport:
    """Audit every chronicle entry of a decoded bundle (any version), or,
    with ``narrated`` (a ``--narrate`` output), that file's entries against
    the bundle."""
    from chronicler.snapshot_pruning import restore_bundle
    bundle = restore_bundle(bundle)
    records = BundleRecords(bundle)
    if universe is None:
        universe = EntityUniverse.from_bundle(bundle)
    report = AuditReport()
    raw = (narrated if narrated is not None else bundle).get("chronicle_entries") or []
    if isinstance(raw, dict):  # legacy {turn: text}
        report.entries = len(raw)
        return report
    entries = expand_entries(narrated if narrated is not None else bundle)
    report.entries = len(entries)
    for i, entry in enumerate(entries):
        stats, flags = audit_entry(i, entry, records, universe)
        if stats is None:
            continue
        report.with_provenance += 1
        report.stats.append(stats)
        report.flags.extend(flags)
    return report


def audit_path(path: Path, narrated: Path | None = None) -> AuditReport:
    from chronicler.bundle_codec import load_bundle
    extra = json.loads(narrated.read_text(encoding="utf-8")) if narrated is not None else None
    return audit_bundle(load_bundle(path), narrated=extra)


def format_report(path: Path | str, report: AuditReport, show: int = 20) -> str:
    t = report.totals()
    lines = [f"{path}: {t['entries']} entries, {t['with_provenance']} with provenance "
             f"({', '.join(f'{n} {k}' for k, n in t['by_narrator'].items()) or 'none'})",
             f"  facts given {t['facts']} ({t['retrospective_facts']} retrospective); "
             f"spans {t['spans']}; distinct facts cited {t['cited']} ({t['cited_retrospective']} retrospective); "
             f"sentences {t['sentences']}, uncited {t['uncited_sentences']}"]
    if not report.flags:
        lines.append("  flags: none")
    else:
        lines.append("  flags: " + ", ".join(f"{k} {n}" for k, n in report.counts().items()))
        for f in report.flags[:show]:
            lines.append(f"  - entry {f.entry} {f.kind}: {f.detail}")
        if len(report.flags) > show:
            lines.append(f"  ... {len(report.flags) - show} more")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m chronicler.narration_audit",
                                description=__doc__.split("\n\n")[0])
    p.add_argument("bundles", nargs="+", type=Path)
    p.add_argument("--narrated", type=Path, default=None,
                   help="A --narrate output: check its entries against the (one) source bundle")
    p.add_argument("--json", type=Path, default=None, help="Write the full report (every flag) as JSON")
    p.add_argument("--show", type=int, default=20, help="Flags to print per bundle (default 20)")
    p.add_argument("--exit-zero", action="store_true", help="Exit 0 even when entries are flagged")
    a = p.parse_args(argv)
    if a.narrated is not None and len(a.bundles) != 1:
        p.error("--narrated takes one source bundle")
    out: dict[str, Any] = {}
    flagged = 0
    for path in a.bundles:
        report = audit_path(path, a.narrated)
        print(format_report(a.narrated or path, report, a.show))
        out[str(path)] = report.to_dict()
        flagged += len(report.flags)
    if a.json is not None:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if a.exit_zero or not flagged else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
