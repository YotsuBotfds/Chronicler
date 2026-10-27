"""Claim provenance for narration: fact ids, per-passage provenance, the audit.

docs/integration/narration-provenance.md. No LLM is called: the mechanical
narrator and scripted fake clients stand in for one.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

from chronicler import narration_provenance as npv
from chronicler.bundle_codec import load_bundle
from chronicler.llm import AnthropicClient, MechanicalClient
from chronicler.main import execute_run
from chronicler.narration_audit import BundleRecords, audit_bundle, audit_entry, main as audit_main
from chronicler.narration_inputs import from_bundle
from chronicler.narrative import NarrativeEngine, compose_mechanical, mechanical_narrative


@pytest.fixture
def pure_python(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def _args(folder: Path, turns: int, seed: int = 42, **kw) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=seed, turns=turns, civs=3, regions=6,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="off", narrator="mechanical",
    )
    for key, value in kw.items():
        setattr(args, key, value)
    return args


def _run(folder: Path, turns: int = 60, seed: int = 42, client=None, **kw) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    execute_run(_args(folder, turns, seed, **kw), narrative_client=client or MechanicalClient())
    return load_bundle(folder / "chronicle_bundle.json")


@pytest.fixture(scope="module")
def mechanical_bundles(tmp_path_factory):
    """Mechanical narration of three template seeds and a procedural world."""
    import chronicler.main as cm
    saved = cm._create_ecology_runtime, cm._create_politics_runtime
    cm._create_ecology_runtime = lambda world: None
    cm._create_politics_runtime = lambda world: None
    try:
        root = tmp_path_factory.mktemp("mechanical")
        out = {}
        for name, seed, extra in (("s42", 42, {}), ("s7", 7, {}), ("s1234", 1234, {}),
                                  ("proc16", 11, {"regions": 16, "civs": 5})):
            out[name] = _run(root / name, 60, seed, **extra)
        return out
    finally:
        cm._create_ecology_runtime, cm._create_politics_runtime = saved


# ---------------------------------------------------------------------------
# Citation grammar
# ---------------------------------------------------------------------------


def test_parse_citations_strips_ids_and_keeps_spans():
    text = ('The walls fell [e12]. The Kethani mourned [e13, n2] and the [turn 4] note stayed '
            '[s84.ruler.c2][court:2/e13]. Peace came [d12-30.c2.population]!\nAt last [L.r5] [p77] quiet')
    clean, spans = npv.parse_citations(text)
    assert clean == ('The walls fell. The Kethani mourned and the [turn 4] note stayed. Peace came!\n'
                     'At last quiet')
    assert [(clean[s:e], ids) for s, e, ids in spans] == [
        ("The walls fell.", ["e12"]),
        ("The Kethani mourned", ["e13", "n2"]),
        ("and the [turn 4] note stayed.", ["s84.ruler.c2", "court:2/e13"]),
        ("Peace came!", ["d12-30.c2.population"]),
        ("At last", ["L.r5", "p77"]),
    ]


def test_fact_id_grammar():
    for good in ("e0", "e123", "n4", "k2", "art9", "p501", "p:Old_Name|12", "w30-35", "w30-35.mood",
                 "s36.ruler.c3", "s36.war.c0-c3", "s36.food.r1", "d29-34.c3.stability", "d29-34.r2",
                 "o35.displacement", "o12.civ.c1", "L.c3", "L.p0", "court:2/e293", "temple:1/e44",
                 "seat:0/e7", "e:12:Mass_Migration:0"):
        assert npv.is_fact_id(good), good
    for bad in ("turn", "turn 4", "e", "x12", "s36", "court:2/293"):
        assert not npv.is_fact_id(bad), bad
    clean, spans = npv.parse_citations("Kept [turn 4] and [e12 and more].")
    assert clean == "Kept [turn 4] and [e12 and more]." and spans == []


def test_fact_ids_resolve_records_by_identity_event_id_and_content(sample_world=None):
    from chronicler.models import Event, NamedEvent
    a = Event(turn=1, event_type="war", actors=["A", "B"], description="A attacks B", event_id="1:war:0")
    b = Event(turn=2, event_type="drought", actors=["A"], description="")
    ne = NamedEvent(name="Battle of X", event_type="battle", turn=2, actors=["A"], description="d")
    ids = npv.FactIds([a, b], [ne])
    assert ids.event(a) == "e0" and ids.event(b) == "e1"
    assert ids.event(a.model_copy()) == "e0"                       # by event_id
    assert ids.event(b.model_copy()) == "e1"                       # by content
    assert ids.named(ne.model_copy()) == "n0"
    assert ids.event_by_id("1:war:0") == "e0"
    assert ids.account({"chronicler": "court:1", "event_id": "1:war:0"}) == "court:1/e0"
    assert ids.civ("Nowhere") == "c:Nowhere" and ids.snapshot(5, "ruler", ("civ", "A B")) == "s5.ruler.c:A_B"
    assert ids.change(3, 8, ("civ", "A"), "population") == "d3-8.c:A.population"
    ids.sync([a, b, Event(turn=3, event_type="trade", actors=["A"], description="t")], [ne])
    assert ids.event(ids.timeline[2]) == "e2"


def test_entity_universe_forms():
    u = npv.EntityUniverse.from_parts(civs=["Kethani Empire", "Upper Iron Peaks"], regions=["Iron Peaks"],
                                      faiths=["Faith of Kethani Empire"], persons=["Consul Ulveth"])
    assert u.find("The Kethani wept in Iron Peaks") == {"Kethani Empire", "Iron Peaks"}
    assert u.find("Upper Iron Peaks rose") == {"Upper Iron Peaks"}
    assert u.find("the Faith of Kethani spread") == {"Faith of Kethani Empire"}
    assert u.find("Ulveth fell; consul Ulveth too") == {"Consul Ulveth"}
    assert u.find("kethani empire") == set()  # case-sensitive


# ---------------------------------------------------------------------------
# Mechanical narration: exact provenance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["s42", "s7", "s1234", "proc16"])
def test_mechanical_provenance_passes_the_audit(mechanical_bundles, name):
    bundle = mechanical_bundles[name]
    entries = bundle["chronicle_entries"]
    assert entries and all(e["provenance"]["narrator"] == "mechanical" for e in entries)
    report = audit_bundle(bundle)
    assert report.with_provenance == len(entries)
    assert report.flags == [], [f.detail for f in report.flags[:5]]
    t = report.totals()
    assert t["facts"] > 0 and t["spans"] > 0 and t["uncited_sentences"] == 0
    table = bundle[npv.BUNDLE_FIELD]["names"]
    for e in entries:
        p = e["provenance"]
        # Every span cites facts given, and the spans tile the prose.
        rows = npv.fact_rows(p)
        given = {fid for fid, _turn, _retro in rows}
        assert all(set(ids) <= given and ids for _s, _e, ids in p["spans"])
        assert "".join(e["narrative"][s:t] for s, t, _ in p["spans"]).replace(" ", "").replace("\n", "") \
            == e["narrative"].replace(" ", "").replace("\n", "")
        assert all(turn is None or turn <= p["as_of"] for _fid, turn, _retro in rows)
        assert p["as_of"] == e["covers_turns"][1]
        # In the file, names are indices into the bundle's one table.
        assert all(isinstance(n, int) and 0 <= n < len(table) for n in p["names"])


def test_mechanical_ids_name_the_bundle_records(mechanical_bundles):
    bundle = mechanical_bundles["s42"]
    timeline = bundle["events_timeline"]
    hist = bundle.get("historiography") or {}
    accounts = 0
    for entry in bundle["chronicle_entries"]:
        p = entry["provenance"]
        for fid, turn, _retro in npv.fact_rows(p):
            m = re.fullmatch(r"e(\d+)", fid)
            if m:
                assert timeline[int(m.group(1))]["turn"] == turn
            m = re.fullmatch(r"(court|temple|seat):(\d+)/e(\d+)", fid)
            if m:
                accounts += 1
                full = f"{m.group(1)}:{m.group(2)}/{timeline[int(m.group(3))]['event_id']}"
                assert full in entry["accounts"]
    assert hist and accounts  # the in-world accounts are cited by their own ids


def test_mechanical_text_is_unchanged_by_composition(mechanical_bundles):
    """``mechanical_narrative`` (the public text) is the composed text."""
    bundle = mechanical_bundles["s7"]
    inputs = from_bundle(bundle)
    from chronicler.curator import curate
    moments, _ = curate(inputs.events, inputs.named_events, inputs.history, budget=6, seed=inputs.seed,
                        **inputs.curate_kwargs())
    for m in moments:
        comp = compose_mechanical(m)
        assert comp.text == mechanical_narrative(m)
        assert comp.spans and comp.spans[-1][1] == len(comp.text)


def test_narrate_bundle_gives_the_same_ids_as_the_run(mechanical_bundles, tmp_path):
    """Fact ids are stable: re-narrating the saved bundle cites the same records."""
    bundle = mechanical_bundles["s1234"]
    inputs = from_bundle(bundle)
    from chronicler.curator import curate
    moments, _ = curate(inputs.events, inputs.named_events, inputs.history, budget=50, seed=inputs.seed,
                        **inputs.curate_kwargs())
    engine = NarrativeEngine(sim_client=MechanicalClient(), narrative_client=MechanicalClient())
    entries = engine.narrate_batch(moments, inputs.history, **inputs.narrate_kwargs())
    before = [e["provenance"]["facts"] for e in bundle["chronicle_entries"]]
    after = [e.model_dump(mode="json")["provenance"]["facts"] for e in entries]
    assert before == after


# ---------------------------------------------------------------------------
# LLM narration: prompts, parsed citations, the audit's flags
# ---------------------------------------------------------------------------


class ScriptedClient:
    """A fake LLM: ``script(prompt)`` writes the prose."""

    model = "scripted"

    def __init__(self, script):
        self.script = script
        self.prompts: list[str] = []

    def complete(self, prompt: str, max_tokens: int = 500, system: str | None = None) -> str:
        self.prompts.append(prompt)
        return self.script(prompt)


_LINE = re.compile(r"^- \[turn \d+\] [\w ]+: (?P<text>.+?) \(importance [^\n]*\) \[(?P<ids>[^\]]+)\]$", re.M)


def _offered(prompt: str) -> list[str]:
    body = prompt.split("SOURCES:", 1)[0]
    return [i for g in npv.CITATION.findall(body) for i in npv.split_ids(g)]


def _faithful(prompt: str) -> str:
    """Retell the first two event lines, each with its id."""
    out = []
    for m in list(_LINE.finditer(prompt))[:2]:
        out.append(f"{m.group('text')} [{m.group('ids')}].")
    return " ".join(out) or "Little was written [w0-0]."


@pytest.fixture(scope="module")
def source_bundle(mechanical_bundles):
    return mechanical_bundles["s42"]


def _llm_entries(bundle: dict, script, budget: int = 8, batch=False, **engine_kw):
    from chronicler.curator import curate
    inputs = from_bundle(bundle)
    moments, _ = curate(inputs.events, inputs.named_events, inputs.history, budget=budget,
                        seed=inputs.seed, **inputs.curate_kwargs())
    client = ScriptedClient(script)
    if batch:
        class FakeBatch(AnthropicClient):
            def __init__(self):
                super().__init__(client=None, model="fake")

            def batch_complete(self, requests):
                return [None if k == 1 else script(r["prompt"]) for k, r in enumerate(requests)]
        client = FakeBatch()
    engine = NarrativeEngine(sim_client=client, narrative_client=client, **engine_kw)
    entries = engine.narrate_batch(moments, inputs.history, **inputs.narrate_kwargs())
    out = dict(bundle)
    out["chronicle_entries"] = [e.model_dump(mode="json") for e in entries]
    return out, client


def test_prompt_lines_carry_ids_and_the_request_to_cite(source_bundle):
    narrated, client = _llm_entries(source_bundle, _faithful, budget=4)
    prompt = client.prompts[0]
    assert "SOURCES:" in prompt
    lines = [ln for ln in prompt.split("EVENTS:", 1)[1].split("\n\n", 1)[0].splitlines() if ln.startswith("- ")]
    assert lines and all(re.search(r" \[e\d+\]$", ln) for ln in lines)
    entry = narrated["chronicle_entries"][0]
    p = entry["provenance"]
    assert p["narrator"] == "llm" and set(_offered(prompt)) <= {fid for fid, _t, _r in npv.fact_rows(p)}
    assert "[e" not in entry["narrative"]  # the citations are removed from the shown prose
    assert p["spans"] and all(ids for _s, _e, ids in p["spans"])


def test_faithful_llm_passes_the_audit(source_bundle):
    narrated, _client = _llm_entries(source_bundle, _faithful)
    report = audit_bundle(narrated)
    assert report.with_provenance == len(narrated["chronicle_entries"])
    assert report.flags == [], [f.detail for f in report.flags[:5]]
    assert report.totals()["cited"] > 0


def test_bad_future_and_unknown_citations_and_names_are_flagged(source_bundle):
    timeline = source_bundle["events_timeline"]
    world = source_bundle["world_state"]
    places = [r["name"] for r in world["regions"]] + [c["name"] for c in world["civilizations"]]
    later_cited, strangers = [], []

    def script(prompt: str) -> str:
        offered = set(_offered(prompt))
        end = int(re.search(r"TURNS \d+-(\d+):", prompt).group(1))
        earlier = next(i for i, ev in enumerate(timeline) if ev["turn"] <= end and f"e{i}" not in offered)
        later = next((i for i, ev in enumerate(timeline) if ev["turn"] > end and f"e{i}" not in offered), None)
        stranger = next((p for p in places if p not in prompt), None)
        later_cited.append(later is not None)
        strangers.append(stranger)
        doom = f" Doom would come [e{later}]." if later is not None else ""
        pilgrims = f" Pilgrims came from {stranger} [{sorted(offered)[0]}]." if stranger else ""
        return (f"{_faithful(prompt)} The old wars were remembered [e{earlier}].{doom} "
                f"A ghost spoke [e999999].{pilgrims} The scribe wrote (e1).")

    narrated, _client = _llm_entries(source_bundle, script, budget=3)
    assert all(e["provenance"]["narrator"] == "llm" for e in narrated["chronicle_entries"])
    report = audit_bundle(narrated)
    kinds = report.counts()
    n = len(narrated["chronicle_entries"])
    assert sum(later_cited) >= 2 and sum(1 for s in strangers if s) >= 2
    assert kinds["unsupplied_citation"] == n + sum(later_cited)  # an earlier and a later record not given
    assert kinds["future_citation"] == sum(later_cited)          # the later one, dated after the moment
    assert kinds["unknown_citation"] == n                        # e999999
    assert kinds["unsupplied_name"] >= sum(1 for s in strangers if s)  # a place no fact names
    assert kinds["stray_marker"] == n                            # (e1)
    assert not set(kinds) - {"unsupplied_citation", "future_citation", "unknown_citation",
                             "unsupplied_name", "stray_marker"}
    names = [f for f in report.flags if f.kind == "unsupplied_name"]
    shown = {narrated["chronicle_entries"][f.entry]["narrative"][f.span[0]:f.span[1]] for f in names}
    assert {s for s in strangers if s} <= shown


def test_retrospective_citations_are_allowed_and_counted(source_bundle):
    def script(prompt: str) -> str:
        later = prompt.split("LATER CONSEQUENCES", 1)
        if len(later) < 2:
            return _faithful(prompt)
        block = later[1].split("\n\n", 1)[0]
        ids = npv.CITATION.findall(block)
        return f"{_faithful(prompt)} It was not the end [{ids[0]}]." if ids else _faithful(prompt)

    narrated, _client = _llm_entries(source_bundle, script, budget=12)
    report = audit_bundle(narrated)
    assert report.flags == [], [f.detail for f in report.flags[:5]]
    assert report.totals()["cited_retrospective"] > 0
    retro = [(turn, e["provenance"]["as_of"]) for e in narrated["chronicle_entries"]
             for _fid, turn, is_retro in npv.fact_rows(e["provenance"]) if is_retro]
    assert retro and any(turn > as_of for turn, as_of in retro)  # later consequences, after the moment


def test_batch_api_path_and_its_mechanical_fallback(source_bundle):
    narrated, _client = _llm_entries(source_bundle, _faithful, budget=4, batch=True)
    narrators = [e["provenance"]["narrator"] for e in narrated["chronicle_entries"]]
    assert narrators[1] == "mechanical" and narrators.count("llm") == len(narrators) - 1
    assert audit_bundle(narrated).flags == []


def test_no_citations_sends_untagged_prompts_and_still_records_facts(source_bundle):
    narrated, client = _llm_entries(source_bundle, lambda p: "A quiet age passed.", budget=3, citations=False)
    assert all("SOURCES:" not in p and not _offered(p) for p in client.prompts)
    for e in narrated["chronicle_entries"]:
        assert e["provenance"]["facts"] and e["provenance"]["spans"] == []
    report = audit_bundle(narrated)
    assert report.flags == [] and report.totals()["uncited_sentences"] == len(client.prompts)


def test_sequential_failure_falls_back_with_mechanical_provenance(source_bundle):
    def script(prompt: str) -> str:
        raise RuntimeError("offline")

    narrated, _client = _llm_entries(source_bundle, script, budget=3)
    assert all(e["provenance"]["narrator"] == "mechanical" for e in narrated["chronicle_entries"])
    assert audit_bundle(narrated).flags == []


def test_agent_context_lines_carry_character_ids(sample_world):
    """Characters by agent id (dated by their latest deed, memory or bond),
    their relationships, the mood and the settlements of the snapshot."""
    from chronicler.models import (
        CivSnapshot, Event, GreatPerson, GreatPersonDeed, NarrativeMoment, NarrativeRole,
        SettlementSummary, TurnSnapshot,
    )
    civ = sample_world.civilizations[0]
    region = sample_world.regions[0].name
    kiran = GreatPerson(name="General Kiran", role="general", trait="bold", civilization=civ.name,
                        origin_civilization=civ.name, born_turn=5, source="agent", agent_id=42,
                        deeds=[GreatPersonDeed(text="Won at the ford", region=region, turn=8)],
                        memories=[{"event_type": 1, "turn": 9, "intensity": 70, "source_civ": 0}],
                        agent_bonds=[{"target_id": 43, "bond_type": 1, "formed_turn": 7, "sentiment": 50}])
    mira = GreatPerson(name="Prophet Mira", role="prophet", trait="wise", civilization=civ.name,
                       origin_civilization=civ.name, born_turn=6, source="agent", agent_id=43)
    moment = NarrativeMoment(anchor_turn=10, turn_range=(10, 10), score=8.0, causal_links=[],
                             named_events=[], narrative_role=NarrativeRole.CLIMAX, bonus_applied=0.0,
                             events=[Event(turn=10, event_type="local_rebellion", actors=[civ.name],
                                           description="Unrest", importance=6, source="agent")])
    settlement = SettlementSummary(settlement_id=17, name="Fordtown", region_name=region, population_estimate=40,
                                   centroid_x=0.0, centroid_y=0.0, founding_turn=3, status="active")
    history = [TurnSnapshot(
        turn=11, civ_stats={civ.name: CivSnapshot(
            population=50, military=30, economy=40, culture=35, stability=55, treasury=20, asabiya=0.5,
            tech_era="iron", trait="bold", regions=list(civ.regions), leader_name=civ.leader.name, alive=True)},
        region_control={region: civ.name}, relationships={}, active_settlements=[settlement])]
    engine = NarrativeEngine(sim_client=MechanicalClient(), narrative_client=MechanicalClient())
    engine._world = sample_world
    [prep] = engine._prepare_narration_prompts(
        [moment], history, great_persons=[kiran, mira],
        agent_name_map={42: "General Kiran", 43: "Prophet Mira"})
    prompt = prep["prompt"]
    assert "- General General Kiran [bold] (" in prompt and "[active]: [p42]" in prompt
    assert re.search(r"- General Kiran and Prophet Mira \(rival, since turn 7\) \[p42, p43\]", prompt)
    assert "Population mood: desperate [w10-10.mood]" in prompt
    assert "- Fordtown (" in prompt and "[s11.settlement.17]" in prompt
    rows = {fid: (turn, retro) for fid, turn, retro in npv.fact_rows(prep["sheet"].export("llm"))}
    assert rows["p42"] == (9, False) and rows["p43"] == (7, False)

    # A character line dated after the moment (a leaked later record) is flagged.
    from chronicler.narrative import build_agent_context_block
    from chronicler.models import AgentContext
    sheet = npv.FactSheet(npv.FactIds(), None, 10)
    ctx = AgentContext(named_characters=[{"name": "General Kiran", "role": "General", "civ": civ.name,
                                          "status": "active", "agent_id": 42, "born_turn": 5,
                                          "recent_history": [{"event": "Fell", "region": region, "turn": 20}]}])
    build_agent_context_block(ctx, sheet=sheet)
    _stats, flags = audit_entry(0, _entry("Kiran fell.", sheet.export("llm")["facts"], [], as_of=10), None, None)
    assert [f.kind for f in flags] == ["future_supplied"] and flags[0].ids == ["p42"]


# ---------------------------------------------------------------------------
# The audit on hand-made provenance
# ---------------------------------------------------------------------------


def _bundle_with(entry: dict) -> dict:
    return {
        "events_timeline": [{"turn": 1, "event_type": "war", "actors": ["A"], "description": "x",
                             "event_id": "1:war:0"},
                            {"turn": 9, "event_type": "famine", "actors": ["A"], "description": "y",
                             "event_id": "9:famine:0"}],
        "named_events": [], "history": [{"turn": 2, "civ_stats": {}, "region_control": {}}],
        "world_state": {"civilizations": [{"name": "Kethani Empire", "leader": {"name": "Consul Ulveth"}}],
                        "regions": [{"name": "Iron Peaks"}, {"name": "Amber Valley"}]},
        "chronicle_entries": [entry],
    }


def _entry(narrative: str, facts, spans, names=(), narrator="llm", as_of=5) -> dict:
    return {"turn": 1, "covers_turns": [1, as_of], "narrative": narrative, "causal_links": [],
            "provenance": {"v": 1, "narrator": narrator, "as_of": as_of, "facts": facts,
                           "names": list(names), "spans": spans}}


def test_audit_flags_a_future_fact_given_outside_a_retrospective_section():
    text = "Famine came to Iron Peaks."
    entry = _entry(text, [["e1", 9]], [[0, len(text), ["e1"]]], names=["Iron Peaks"])
    kinds = [f.kind for f in audit_bundle(_bundle_with(entry)).flags]
    assert kinds == ["future_supplied", "future_citation"]
    entry = _entry(text, [["e1", 9, "r"]], [[0, len(text), ["e1"]]], names=["Iron Peaks"])
    assert audit_bundle(_bundle_with(entry)).flags == []


def test_audit_flags_names_dates_spans_and_mechanical_gaps():
    text = "Consul Ulveth of the Kethani held Amber Valley. Then silence."
    entry = _entry(text, [["e0", 2], ["e7", 1], ["s2.ruler.c0", 1]], [[0, 48, ["e0"]], [40, 200, ["e0"]]],
                   names=["Kethani Empire"], narrator="mechanical")
    kinds = sorted(f.kind for f in audit_bundle(_bundle_with(entry)).flags)
    assert kinds == ["bad_span", "date_mismatch", "unresolved_fact", "unsupplied_name", "unsupplied_name"]
    named = {f.detail.split("'")[1] for f in audit_bundle(_bundle_with(entry)).flags if f.kind == "unsupplied_name"}
    assert named == {"Consul Ulveth", "Amber Valley"}
    mech = _entry("One. Two.", [["e0", 1]], [[0, 4, ["e0"]], [5, 7, []]], narrator="mechanical")
    assert [f.kind for f in audit_bundle(_bundle_with(mech)).flags] == ["uncited_sentence", "uncovered_text"]


def test_audit_entry_without_bundle_records():
    entry = _entry("It ended [x].", [["e0", 1]], [[0, 8, ["e3"]]])
    stats, flags = audit_entry(0, entry, None, None)
    assert stats.cited == 1 and [f.kind for f in flags] == ["unknown_citation"]
    assert BundleRecords({}).resolve("o3.displacement", {}) == (None, 3)


def test_audit_cli(source_bundle, tmp_path, capsys):
    from chronicler.bundle import write_bundle
    clean = tmp_path / "clean.json"
    write_bundle(source_bundle, clean)
    assert audit_main([str(clean), "--json", str(tmp_path / "r.json")]) == 0
    assert "flags: none" in capsys.readouterr().out
    report = json.loads((tmp_path / "r.json").read_text())
    assert report[str(clean)]["totals"]["with_provenance"] == len(source_bundle["chronicle_entries"])
    bad = json.loads(json.dumps(source_bundle))
    bad["chronicle_entries"][0]["provenance"]["spans"][0][2].append("e999999")
    write_bundle(bad, tmp_path / "bad.json")
    assert audit_main([str(tmp_path / "bad.json")]) == 1
    assert audit_main([str(tmp_path / "bad.json"), "--exit-zero"]) == 0


# ---------------------------------------------------------------------------
# Runs: per-turn narration, simulate-only, provenance through the bundle
# ---------------------------------------------------------------------------


def test_per_turn_narrator_records_provenance(tmp_path, pure_python):
    def script(prompt: str) -> str:
        ids = _offered(prompt)
        return f"The age turned [{ids[0]}]." if ids else "The age turned."

    bundle = _run(tmp_path / "local", 12, simulate_only=False, narrator="local", client=ScriptedClient(script))
    entries = bundle["chronicle_entries"]
    assert len(entries) == 12 and all(e["provenance"]["narrator"] == "llm" for e in entries)
    assert all("[" not in e["narrative"] for e in entries)
    assert all(e["provenance"]["as_of"] == e["turn"] - 1 for e in entries)
    assert audit_bundle(bundle).flags == []


def test_simulate_only_entries_carry_no_provenance(tmp_path, pure_python):
    bundle = _run(tmp_path / "sim", 8, narrator="local")
    assert bundle["chronicle_entries"] and all("provenance" not in e for e in bundle["chronicle_entries"])
    assert npv.BUNDLE_FIELD not in bundle
    raw = (tmp_path / "sim" / "chronicle_bundle.json").read_text()
    assert '"narrator":"llm"' not in raw and '"narrator":"mechanical"' not in raw


def test_names_table_round_trip():
    entries = [{"provenance": {"names": ["B", "A"]}}, {"provenance": None}, {"provenance": {"names": ["A", "C"]}}]
    field = npv.compact_entries(entries)
    assert field == {"version": 1, "names": ["B", "A", "C"]}
    assert [e["provenance"]["names"] for e in entries if e["provenance"]] == [[0, 1], [1, 2]]
    restored = npv.expand_entries({"chronicle_entries": entries, npv.BUNDLE_FIELD: field})
    assert [e["provenance"]["names"] for e in restored if e["provenance"]] == [["B", "A"], ["A", "C"]]
    assert entries[0]["provenance"]["names"] == [0, 1]  # the bundle's own entries are not changed
    assert npv.compact_entries([{"provenance": None}]) is None
    assert npv.fact_rows({"as_of": 9, "facts": ["e1", ["e2", 3], ["e3", 12, "r"]]}) == [
        ("e1", 9, False), ("e2", 3, False), ("e3", 12, True)]


def test_narrate_output_is_checked_against_its_source_bundle(mechanical_bundles, tmp_path, capsys):
    from chronicler.bundle import write_bundle
    from chronicler.main import main as cli
    source = tmp_path / "source.json"
    write_bundle(mechanical_bundles["s7"], source)
    out = tmp_path / "narrated.json"
    import sys
    saved = sys.argv
    sys.argv = ["chronicler", "--narrate", str(source), "--narrator", "mechanical", "--narrate-output", str(out),
                "--budget", "6"]
    try:
        cli()
    finally:
        sys.argv = saved
    narrated = json.loads(out.read_text())
    assert narrated[npv.BUNDLE_FIELD]["names"] and len(narrated["chronicle_entries"]) == 6
    capsys.readouterr()
    assert audit_main([str(source), "--narrated", str(out)]) == 0
    assert "6 entries, 6 with provenance (6 mechanical)" in capsys.readouterr().out
