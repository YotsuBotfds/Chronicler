"""In-world languages and names (chronicler.languages): sound systems, sound
change, splits, contact, toponym layering, narration, persistence, and the
proof that the layer changes no simulation output."""
from __future__ import annotations

import argparse
import ast
import json
import random
import shutil
from pathlib import Path

import pytest

import chronicler.languages as L
from chronicler.languages_phonology import (
    STYLES, adapt, choose_change, parse_stem, problem, proto_phonology, roman, rule_by_id,
)
from chronicler.llm import MechanicalClient
from chronicler.main import _build_parser, execute_run
from chronicler.memory import MemoryStream
from chronicler.models import Belief, GreatPerson, Leader, Region, Settlement, WorldState

ROOT = Path(__file__).resolve().parents[1]

try:
    from chronicler_agents import AgentSimulator  # noqa: F401
    HAS_RUST = True
except ImportError:
    HAS_RUST = False

# ---------------------------------------------------------------------------
# Hand-built worlds: a chain of regions, civ k holding region k
# ---------------------------------------------------------------------------

_REGIONS = [("Verdant Plains", "plains"), ("Iron Peaks", "mountains"), ("Amber Valley", "plains"),
            ("Thornwood", "forest"), ("Ashara Desert", "desert"), ("Sapphire Coast", "coast")]
_STYLE_NAMES = {"maritime": ["Kethani Empire", "Selurian Republic"], "mountain": ["Dorrathi Clans"],
                "forest": ["Thornwall Confederacy"], "desert": ["Ashkari Nomads"]}


def _world(make_civ, styles=("maritime", "mountain"), *, chain=True, seed=7) -> WorldState:
    regions = []
    for k, (name, terrain) in enumerate(_REGIONS):
        adj = [_REGIONS[j][0] for j in (k - 1, k + 1) if chain and 0 <= j < len(_REGIONS)]
        regions.append(Region(name=name, terrain=terrain, carrying_capacity=50, resources="fertile",
                              adjacencies=adj))
    civs = []
    used: dict[str, int] = {}
    for k, style in enumerate(styles):
        name = _STYLE_NAMES[style][used.get(style, 0)]
        used[style] = used.get(style, 0) + 1
        civs.append(make_civ(name, regions=[regions[k].name], capital_region=regions[k].name,
                             domains=[style],
                             leader=Leader(name="Warchief Seren", trait="bold", reign_start=0,
                                           throne_name="Seren")))
        regions[k].controller = name
        regions[k].cultural_identity = name
    w = WorldState(name="T", seed=seed, turn=0, regions=regions, civilizations=civs,
                   relationships={})
    L.set_languages_enabled(w, True)
    return w


def _end(w, n=1):
    for _ in range(n):
        w.turn += 1
        L.observe_turn(w)


def _st(w):
    return L.state_of(w)


def _lang_of(w, civ):
    return _st(w).civ_lang[civ][-1][1]


def _name(w, lang, kind, ref):
    return w._languages.name(lang, kind, ref)


# ---------------------------------------------------------------------------
# Phonology
# ---------------------------------------------------------------------------


def test_spelling_parsing_and_adaptation():
    assert parse_stem("Thornwall") == "θornwal"
    assert roman("θornwal") == "Thornwal"
    assert roman("kaj") == "Kai" and roman("jakaw", title=False) == "yakau"
    assert parse_stem("Tamurai") == "tamuraj"
    stems = ["Kethani", "Thornwall", "Seren", "Cohortis", "Ashkari", "Selurian", "Driftmere",
             "Qushtu", "Zhara", "Bouldergate"]
    for style in STYLES:
        ph = proto_phonology(3, style, style)
        allowed = set(ph.consonants) | set(ph.vowels) | {" "}
        for stem in stems:
            word = adapt(parse_stem(stem), ph, max_syllables=3)
            assert set(word) <= allowed, (style, stem, word)
            assert problem(word, ph) is None, (style, stem, word)


def test_sound_change_is_regular():
    ph = proto_phonology(3, "maritime", "maritime").model_copy(update={"consonants": "ptkmnslr"})
    lenition = rule_by_id(ph, "lenition")
    assert lenition.desc == "p t k > b d g between vowels"
    assert lenition.apply("patakama") == "padagama"   # only between vowels
    assert lenition.apply("pat ka") == "pat ka"       # word edges stay
    merger = rule_by_id(ph.model_copy(update={"consonants": "ptkθ"}), "merger_th")
    after = merger.update(ph.model_copy(update={"consonants": "ptkθ"}), ["tata", "kata"])
    assert "θ" not in after.consonants
    # A drawn change is deterministic and alters at least two roots.
    roots = ["patak", "tika", "kopa", "lamo", "rasi"]
    a = choose_change(9, "x", ph, roots, set())
    b = choose_change(9, "x", ph, roots, set())
    assert a.rid == b.rid and sum(a.apply(r) != r for r in roots) >= 2


def test_name_tokens():
    assert L.name_tokens("Free Verdant Plains") == [("m", "free"), ("m", "green"), ("m", "plain")]
    assert L.name_tokens("Kethani Empire") == [("s", "Kethani")]
    assert L.name_tokens("Thornwood") == [("m", "thorn"), ("m", "wood")]
    assert L.name_tokens("Kingdom of Tamurai") == [("s", "Tamurai")]
    assert L.name_tokens("Faith of Kethani Empire (Reformed)") == [("s", "Kethani"), ("m", "new")]
    assert L.short_name("Kingdom of Tamurai") == "Tamurai"


# ---------------------------------------------------------------------------
# Founding, naming, change
# ---------------------------------------------------------------------------


def test_founding_cultures_and_families(make_civ):
    w = _world(make_civ, styles=("maritime", "maritime", "mountain"))
    _end(w)
    st = _st(w)
    langs = st.languages
    proto = [x for x in langs if x.origin == "proto"]
    assert len(proto) == 1 and proto[0].status == "reconstructed" and proto[0].name == "Proto-Coastal"
    daughters = [x for x in langs if x.parent == proto[0].lang_id]
    assert len(daughters) == 2 and all(x.origin == "prehistory" for x in daughters)
    assert all(1 <= len(x.changes) <= 2 and all(c.prehistoric for c in x.changes) for x in daughters)
    # The sisters already differ.
    words = st.words
    lex = [{m: words[i].form for m, i in d.lexicon.items()} for d in daughters]
    assert lex[0] != lex[1]
    single = [x for x in langs if x.origin == "founding"]
    assert len(single) == 1 and single[0].family == single[0].lang_id
    assert {_lang_of(w, i) for i in range(3)} == {daughters[0].lang_id, daughters[1].lang_id,
                                                  single[0].lang_id}


def test_peoples_name_themselves_their_land_and_their_neighbours(make_civ):
    w = _world(make_civ)
    _end(w)
    la, lb = _lang_of(w, 0), _lang_of(w, 1)
    endo = _name(w, la, "civ", 0)
    assert endo.how == "native" and [g for _f, g in endo.parts] in (["Kethani", "people"],
                                                                  ["people", "Kethani"])
    home = _name(w, la, "region", 0)
    assert home.how == "native" and sorted(g for _f, g in home.parts) == ["green", "plain"]
    # The neighbours (adjacent regions) know each other's land and people.
    other = _name(w, lb, "region", 0)
    assert other.how in ("loan", "calque") and other.source == home.word_id
    exo = _name(w, lb, "civ", 0)
    assert exo.how in ("loan", "descriptive")
    # Uninhabited land a people knows gets a descriptive name of its own.
    empty = _name(w, lb, "region", 2)
    assert empty.how == "native" and sorted(g for _f, g in empty.parts) == ["gold", "valley"]
    # Far land nobody borders stays unnamed.
    assert _name(w, la, "region", 5) is None


def test_sound_changes_erode_every_word_and_keep_its_history(make_civ, monkeypatch):
    monkeypatch.setattr(L, "CHANGE_INTERVAL", (1, 1))
    w = _world(make_civ)
    _end(w, 8)
    st = _st(w)
    for lang in st.languages:
        assert lang.changes and all(c.words >= 1 for c in lang.changes)
        rules = [f"{c.rule}:{c.desc}" for c in lang.changes]
        assert len(rules) == len(set(rules))   # a change is not repeated
    changed = [x for x in st.words if len(x.forms) > 1]
    assert any(x.kind == "region" for x in changed)
    for x in changed:
        lang = st.languages[x.lang]
        for turn, _form, index in x.forms[1:]:
            assert lang.changes[index].turn == turn


def test_secession_branches_a_daughter_language(make_civ):
    w = _world(make_civ)
    w.civilizations[0].regions.append("Amber Valley")
    w.regions[2].controller = w.regions[2].cultural_identity = "Kethani Empire"
    _end(w, 2)
    parent = _lang_of(w, 0)
    assert _st(w).regions[2].speech[-1][1] == parent
    breakaway = make_civ("Free Amber Valley", regions=["Amber Valley"], capital_region="Amber Valley",
                         domains=["maritime"])
    w.civilizations.append(breakaway)
    w.civilizations[0].regions.remove("Amber Valley")
    w.regions[2].controller = "Free Amber Valley"   # cultural identity stays Kethani for now
    _end(w)
    st = _st(w)
    daughter = st.languages[_lang_of(w, 2)]
    assert daughter.parent == parent and daughter.origin == "secession"
    assert daughter.name == "Free Amber Valley"
    assert st.regions[2].speech[-1][1] == daughter.lang_id
    assert [2, "dialect", daughter.lang_id] in st.regions[2].story
    # It starts from its parent's words, then goes its own way.
    inherited = _name(w, daughter.lang_id, "region", 0)
    assert inherited.how == "inherited" and st.words[inherited.source].lang == parent
    assert inherited.form == _name(w, parent, "region", 0).form
    # A people named in plain words keeps two of them ("free ... valley").
    endo = _name(w, daughter.lang_id, "civ", 2)
    assert sorted(g for _f, g in endo.parts) == ["free", "valley"]


def test_conquest_leaves_a_substrate_name_that_becomes_local_after_a_shift(make_civ):
    w = _world(make_civ, chain=False)
    _end(w)
    la, lb = _lang_of(w, 0), _lang_of(w, 1)
    assert _name(w, lb, "region", 0) is None   # not neighbours
    local = _name(w, la, "region", 0)
    # Dorrathi conquer the Verdant Plains: the conqueror takes over the local name.
    w.civilizations[0].regions.remove("Verdant Plains")
    w.civilizations[1].regions.append("Verdant Plains")
    w.regions[0].controller = "Dorrathi Clans"
    _end(w)
    sub = _name(w, lb, "region", 0)
    assert sub.how == "substrate" and sub.source == local.word_id
    assert _st(w).regions[0].speech[-1][1] == la   # its people still speak Kethani
    # Assimilated: the people shift language and the substrate name is now local.
    w.regions[0].cultural_identity = "Dorrathi Clans"
    _end(w)
    rec = _st(w).regions[0]
    assert rec.speech[-1] == [2, lb] and rec.story[-1] == [2, "shift", lb]
    index = L.NameIndex(L.export(w))
    view = index.views("region", 0, 2)
    assert view["name"] == roman(sub.form) and view["lang"] == lb
    assert view["former"] == [(la, roman(local.form))]
    assert index.views("region", 0, 0)["lang"] == la   # names are read as of a turn


def test_a_shift_replaces_the_conquerors_own_name_with_the_local_one(make_civ):
    w = _world(make_civ)
    _end(w)   # Amber Valley is empty: the Dorrathi next door coin a name of their own
    la, lb = _lang_of(w, 0), _lang_of(w, 1)
    own_b = _name(w, lb, "region", 2)
    assert own_b.how == "native"
    w.civilizations[0].regions.append("Amber Valley")
    w.regions[2].controller = w.regions[2].cultural_identity = "Kethani Empire"
    _end(w)
    local = _name(w, la, "region", 2)
    w.civilizations[0].regions.remove("Amber Valley")
    w.civilizations[1].regions.append("Amber Valley")
    w.regions[2].controller = "Dorrathi Clans"
    _end(w)
    assert _name(w, lb, "region", 2).word_id == own_b.word_id   # the court keeps its own name
    w.regions[2].cultural_identity = "Dorrathi Clans"
    _end(w)
    sub = _name(w, lb, "region", 2)
    assert sub.how == "substrate" and sub.source == local.word_id and sub.turn == 3
    assert own_b.until == 3
    index = L.NameIndex(L.export(w))
    assert index.name("region", 2, lb, 2)[1]["id"] == own_b.word_id   # read as of turn 2
    assert index.name("region", 2, lb, 3)[1]["id"] == sub.word_id


def test_a_cut_off_province_grows_a_dialect(make_civ, monkeypatch):
    monkeypatch.setattr(L, "SEPARATION_TURNS", 3)
    w = _world(make_civ, styles=("maritime", "mountain", "forest"))
    # Kethani also hold Thornwood, beyond the Dorrathi and Thornwall lands.
    w.civilizations[0].regions.append("Thornwood")
    w.regions[3].controller = w.regions[3].cultural_identity = "Kethani Empire"
    _end(w, 3)
    assert _st(w).regions[3].speech[-1][1] == _lang_of(w, 0)
    _end(w, 2)
    st = _st(w)
    dialect = st.languages[st.regions[3].speech[-1][1]]
    assert dialect.origin == "separation" and dialect.parent == _lang_of(w, 0)
    assert dialect.name == "Thornwood Kethani"
    assert _lang_of(w, 0) == dialect.parent   # the court keeps the old language
    # A province that later secedes takes its dialect as the state's language.
    w.civilizations.append(make_civ("Free Thornwood", regions=["Thornwood"],
                                    capital_region="Thornwood", domains=["maritime"]))
    w.civilizations[0].regions.remove("Thornwood")
    w.regions[3].controller = "Free Thornwood"
    _end(w)
    assert _lang_of(w, 3) == dialect.lang_id


def test_a_conquered_province_that_keeps_its_language_grows_a_dialect(make_civ, monkeypatch):
    monkeypatch.setattr(L, "SEPARATION_TURNS", 3)
    w = _world(make_civ)
    w.civilizations[0].regions.append("Amber Valley")
    w.regions[2].controller = w.regions[2].cultural_identity = "Kethani Empire"
    _end(w)
    la = _lang_of(w, 0)
    # The Dorrathi take Amber Valley; its people keep speaking Kethani.
    w.civilizations[0].regions.remove("Amber Valley")
    w.civilizations[1].regions.append("Amber Valley")
    w.regions[2].controller = "Dorrathi Clans"
    _end(w, 3)
    assert _st(w).regions[2].speech[-1][1] == la
    _end(w)
    dialect = _st(w).languages[_st(w).regions[2].speech[-1][1]]
    assert dialect.origin == "separation" and dialect.parent == la
    assert dialect.name == "Amber Valley Kethani"
    _end(w, 5)   # it branches once
    assert sum(x.origin == "separation" for x in _st(w).languages) == 1


def test_contact_brings_loanwords_and_exonyms(make_civ, monkeypatch):
    from chronicler.contact_ledger import set_contact_ledger_enabled
    monkeypatch.setattr(L, "LOAN_RATE", 1.0)
    w = _world(make_civ, chain=False)
    set_contact_ledger_enabled(w, True)
    w.contact_ledger.pairs = [("Dorrathi Clans", "Kethani Empire", 80.0, 0.0, 0.0, 0.0)]
    _end(w, 6)
    st = _st(w)
    loans = [x for x in st.words if x.kind == "root" and x.how == "loan"]
    assert loans and all(L.MEANINGS[x.ref] == "trade" for x in loans)
    for x in loans:
        donor = st.words[x.source]
        assert donor.lang != x.lang and donor.kind == "root" and donor.ref == x.ref
        lang = st.languages[x.lang]
        assert lang.lexicon[x.ref] == x.word_id
        old = [y for y in st.words if y.lang == x.lang and y.ref == x.ref and y.until is not None]
        assert old
    # Trade partners name each other even without a shared border.
    assert _name(w, _lang_of(w, 0), "civ", 1) is not None
    assert st.counts["loans:trade"] == len(loans)


def test_a_change_spreads_to_a_related_language_in_contact(make_civ, monkeypatch):
    monkeypatch.setattr(L, "CHANGE_INTERVAL", (1, 1))
    monkeypatch.setattr(L, "WAVE_MAX", 1.0)
    monkeypatch.setattr(L, "WAVE_SCALE", 0.1)
    monkeypatch.setattr(L, "WAVE_CONTACT", 0.1)   # a shared border is enough here
    w = _world(make_civ, styles=("maritime", "maritime"))   # sisters, and neighbours
    _end(w, 8)
    spread = [c for x in _st(w).languages for c in x.changes if c.source is not None]
    assert spread
    st = _st(w)
    for x in st.languages:
        for c in x.changes:
            if c.source is not None:
                assert st.languages[c.source].family == x.family
                assert any(d.rule == c.rule and d.turn == c.turn and d.source is None
                           for d in st.languages[c.source].changes)


def test_settlements_faiths_and_persons_are_named(make_civ):
    w = _world(make_civ)
    w.regions[0].settlements.append(Settlement(settlement_id=1, name="Verdant Plains Settlement 1",
                                               region_name="Verdant Plains", last_seen_turn=0))
    w.belief_registry = [Belief(faith_id=0, name="Faith of Kethani Empire", civ_origin=0,
                                doctrines=[0, 0, 0, 0, 0])]
    w.civilizations[1].civ_majority_faith = 0
    k = w.civilizations[0]
    k.leader = Leader(name="Emperor Vaelith II", trait="bold", reign_start=0,
                      throne_name="Vaelith", regnal_ordinal=2)
    k.great_persons.append(GreatPerson(name="High Priestess Cohortis", role="prophet", trait="bold",
                                       civilization=k.name, origin_civilization=k.name, born_turn=0))
    _end(w)
    la = _lang_of(w, 0)
    town = _name(w, la, "settlement", 1)
    assert town.how == "native" and len(town.parts) == 2
    faith = _name(w, la, "faith", 0)
    assert {g for _f, g in faith.parts} == {"Kethani", "holy"}
    assert _name(w, _lang_of(w, 1), "faith", 0).how == "loan"   # adherents borrow the name
    ruler = _name(w, la, "person", "Emperor Vaelith II|0")
    assert ruler.tail == " II"
    index = L.NameIndex(L.export(w))
    assert index.gloss(index.words[ruler.word_id]) == "great king"
    gp = index.words[_name(w, la, "person", "High Priestess Cohortis|0").word_id]
    assert index.gloss(gp) == "high priest"
    assert index.form_at(index.words[ruler.word_id], 0).endswith(" II")


def test_a_restored_people_speaks_its_old_language(make_civ):
    w = _world(make_civ)
    _end(w)
    old = _lang_of(w, 1)
    w.civilizations[1].regions = []
    w.regions[1].controller = w.regions[1].cultural_identity = "Kethani Empire"
    w.civilizations[0].regions.append("Iron Peaks")
    _end(w)
    assert _st(w).languages[old].status == "extinct"
    w.civilizations.append(make_civ("Dorrathi Clans", regions=["Iron Peaks"],
                                    capital_region="Iron Peaks", domains=["mountain"]))
    w.regions[1].controller = "Dorrathi Clans"
    _end(w)
    assert _lang_of(w, 2) == old and _st(w).languages[old].status == "living"


# ---------------------------------------------------------------------------
# Narration helpers
# ---------------------------------------------------------------------------


def test_name_index_localizes_and_glosses(make_civ):
    from chronicler.models import Event
    w = _world(make_civ)
    _end(w)
    index = L.NameIndex(L.export(w))
    la = _lang_of(w, 0)
    own = roman(_name(w, la, "region", 0).form)
    text = "The Raid on Verdant Plains: Kethani Empire (5) vs Dorrathi Clans (3). Verdant Plains burns."
    out = index.localize(text, la, 1)
    assert f"{own} [Verdant Plains]" in out and out.count("[Verdant Plains]") == 1
    assert out.endswith(f"{own} burns.")
    assert index.localize(text, None, 1) == text
    ev = Event(turn=0, event_type="war", actors=["Kethani Empire", "Dorrathi Clans"],
               description=text, region="Verdant Plains")
    block = index.prompt_block([ev], 1)
    assert "IN-WORLD NAMES" in block and "- Verdant Plains: its people say" in block
    glossed: set = set()
    first, second = index.passage([ev], 1, glossed), index.passage([ev], 1, glossed)
    assert first.startswith("In their own tongues: Kethani Empire, ")   # two entities a moment
    assert second.startswith("In their own tongues: Verdant Plains, ")
    assert index.passage([ev], 1, glossed) == ""   # each is glossed once per chronicle


def test_historiography_accounts_are_told_in_their_chroniclers_names(make_civ):
    import chronicler.historiography as H
    data = {
        "chroniclers": [{"id": "court:0", "name": "the Kethani chronicles"}],
        "archives": [], "account_columns": list(H.ACCOUNT_COLUMNS),
        "accounts": [["1:war:0", "court:0", 1, "victory", [["inflate", {}]], [],
                      "At the Raid on Verdant Plains the Kethani host won the day.", None, None]],
        "contested": [],
    }
    from chronicler.models import Event
    ev = Event(turn=1, event_type="war", actors=[], description="d", event_id="1:war:0")
    plain = H.AccountIndex(data)
    assert plain.passage([ev])[0].endswith("won the day.”")
    w = _world(make_civ)
    _end(w, 2)
    names = L.NameIndex(L.export(w))
    rich = H.AccountIndex(data, names=names)
    passage = rich.passage([ev])[0]
    own = roman(_name(w, _lang_of(w, 0), "region", 0).form)
    assert f"{own} [Verdant Plains]" in passage and "[Kethani]" in passage
    assert rich.prompt_block([ev])[1] == plain.prompt_block([ev])[1]
    assert H.AccountIndex(data, names=None).passage([ev]) == plain.passage([ev])


# ---------------------------------------------------------------------------
# Observation is read-only and draws no simulation randomness
# ---------------------------------------------------------------------------


def test_observation_reads_only(make_civ):
    import numpy as np
    w = _world(make_civ, styles=("maritime", "maritime", "mountain"))
    w.turn += 1
    before = w.model_dump_json()
    py_state, np_state = random.getstate(), np.random.get_state()
    caches = (w._region_map, w._civ_map, w._civ_index_map, w._history_index,
              w._active_trade_routes_cache)
    L.observe_turn(w)
    assert w.model_dump_json() == before
    assert random.getstate() == py_state
    assert all((x == y).all() if hasattr(x, "all") else x == y
               for x, y in zip(np.random.get_state(), np_state))
    assert (w._region_map, w._civ_map, w._civ_index_map, w._history_index,
            w._active_trade_routes_cache) == caches == (None, None, None, None, None)
    assert _st(w).words


def test_no_simulation_module_imports_languages():
    allowed = {"main.py", "models.py", "live.py", "languages.py"}
    importers = []
    for path in sorted((ROOT / "src" / "chronicler").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                     else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            if any("languages" in n for n in names):
                importers.append(path.name)
    assert set(importers) <= allowed, importers
    for module in ("languages.py", "languages_phonology.py"):
        tree = ast.parse((ROOT / "src/chronicler" / module).read_text(encoding="utf-8"))
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                    for a in n.names}
        imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree)
                     if isinstance(n, ast.ImportFrom)}
        assert not imported & {"random", "numpy"}, module


def test_slot_is_equality_neutral_and_copies_carry_the_state(make_civ):
    w = _world(make_civ)
    _end(w)
    other = w.model_copy(deep=True)
    other._languages = None
    assert w == other
    clone = w.model_copy(deep=True)
    assert clone._languages.state is not w._languages.state
    assert clone._languages.state == w._languages.state
    import pickle
    assert pickle.loads(pickle.dumps(w._languages)).state == w._languages.state
    assert "languages" not in w.model_dump_json()


def test_sidecar_round_trip_and_stale_or_missing_sidecars(make_civ, tmp_path):
    w = _world(make_civ)
    _end(w, 3)
    path = tmp_path / "state.json"
    w.save(path)
    assert L.sidecar_path(path) == tmp_path / "state.languages.json"
    loaded = WorldState.load(path)
    assert L.state_of(loaded) == L.state_of(w)
    assert "languages" not in path.read_text()
    L.sidecar_path(path).unlink()
    assert L.state_of(WorldState.load(path)) is None   # old saves load with the layer off
    w.save(path)
    w.turn += 5
    w.save(tmp_path / "later.json")
    shutil.copy(tmp_path / "state.languages.json", tmp_path / "later.languages.json")
    restarted = WorldState.load(tmp_path / "later.json")
    assert L.state_of(restarted).words == [] and L.state_of(restarted).enabled_turn == w.turn
    L.set_languages_enabled(w, False)
    w.save(path)
    assert not L.sidecar_path(path).exists()


# ---------------------------------------------------------------------------
# Whole runs
# ---------------------------------------------------------------------------


@pytest.fixture
def pure_python(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def _args(folder: Path, turns: int, **kw):
    args = argparse.Namespace(
        seed=42, turns=turns, civs=3, regions=6,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents="off", languages=True,
    )
    for key, value in kw.items():
        setattr(args, key, value)
    return args


def _bundle(folder: Path) -> dict:
    return json.loads((folder / "chronicle_bundle.json").read_text())


def _sim_view(bundle: dict) -> dict:
    """The bundle without the languages field and the entries' prose (the
    curated moments themselves must not change)."""
    out = {k: v for k, v in bundle.items() if k != "languages"}
    out["chronicle_entries"] = [{k: v for k, v in e.items() if k != "narrative"}
                                for e in bundle["chronicle_entries"]]
    out["metadata"] = {k: v for k, v in bundle["metadata"].items() if k != "generated_at"}
    return out


def test_resume_from_a_checkpoint_continues_identically(tmp_path, pure_python):
    full, part = tmp_path / "full", tmp_path / "part"
    copy_at = tmp_path / "at8"

    def hook(snapshot, text, events, named):
        if snapshot.turn == 9:
            shutil.copytree(full, copy_at)

    full.mkdir()
    execute_run(_args(full, 30, state_every=4), on_turn=hook)
    shutil.copytree(copy_at, part)
    world = WorldState.load(part / "state.json")
    assert world.turn == 8 and L.languages_on(world)
    memories = {}
    for f in part.glob("memories_*.json"):
        stream = MemoryStream.load(f)
        memories[stream.civilization_name] = stream
    execute_run(_args(part, 30, state_every=4), world=world, memories=memories)
    assert (part / "state.languages.json").read_bytes() == (full / "state.languages.json").read_bytes()
    assert _bundle(part)["languages"] == _bundle(full)["languages"]
    assert (part / "state.json").read_bytes() == (full / "state.json").read_bytes()
    assert L.state_of(WorldState.load(full / "state.json")).words


def test_flag_on_changes_no_simulation_output(tmp_path, pure_python):
    """The outcome-neutral proof in the suite: state, snapshots, events, memories."""
    runs = {}
    for flag in (False, True):
        folder = tmp_path / ("on" if flag else "off")
        folder.mkdir()
        snaps = []
        execute_run(_args(folder, 40, languages=flag, narrator="mechanical"),
                    narrative_client=MechanicalClient(),
                    on_turn=lambda s, t, e, n: snaps.append(s.model_dump_json()))
        runs[flag] = (folder, snaps)
    (off, off_snaps), (on, on_snaps) = runs[False], runs[True]
    assert on_snaps == off_snaps
    files_off = sorted(p.name for p in off.iterdir())
    files_on = sorted(p.name for p in on.iterdir())
    assert files_on == sorted(files_off + ["state.languages.json"])
    for name in files_off:
        if name in ("chronicle_bundle.json", "chronicle.md"):
            continue
        assert (on / name).read_bytes() == (off / name).read_bytes(), name
    b_on, b_off = _bundle(on), _bundle(off)
    assert _sim_view(b_on) == _sim_view(b_off)
    assert "languages" not in b_off and b_on["languages"]["words"]
    assert "In their own tongues" not in (off / "chronicle.md").read_text()
    assert "In their own tongues" in (on / "chronicle.md").read_text()
    # Every word, source, language and entity in the field resolves.
    import importlib.util
    spec = importlib.util.spec_from_file_location("lid", ROOT / "scripts/languages_identity.py")
    lid = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lid)
    assert lid.check_field(on / "chronicle_bundle.json") == []
    assert lid.compare(off, on, languages=True)[1] == []


def test_flag_off_never_runs_the_layer(tmp_path, pure_python, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()

    def forbidden(*args, **kwargs):
        raise AssertionError("languages ran while off")

    with monkeypatch.context() as m:
        m.setattr(L, "observe_turn", forbidden)
        m.setattr(L, "export", forbidden)
        m.setattr(L.NameIndex, "__init__", forbidden)
        execute_run(_args(a, 12, languages=False, narrator="mechanical"),
                    narrative_client=MechanicalClient())
        m.setattr(L, "DEFAULT_ENABLED_FOR_NEW_WORLDS", False)
        execute_run(_args(b, 12, languages=None, narrator="mechanical"),
                    narrative_client=MechanicalClient())
    for name in sorted(p.name for p in a.iterdir()):
        if name == "chronicle_bundle.json":
            assert _bundle(a) | {"metadata": None} == _bundle(b) | {"metadata": None}
        else:
            assert (a / name).read_bytes() == (b / name).read_bytes(), name
    assert not (a / "state.languages.json").exists()
    assert "languages" not in _bundle(a)


def test_runs_are_deterministic(tmp_path, pure_python):
    outs = []
    for k in range(2):
        folder = tmp_path / f"r{k}"
        folder.mkdir()
        execute_run(_args(folder, 30))
        outs.append((folder / "state.languages.json").read_bytes())
    assert outs[0] == outs[1]


def test_narrate_bundle_uses_the_field_when_present(tmp_path, pure_python):
    from chronicler.main import _run_narrate
    folder = tmp_path / "n"
    folder.mkdir()
    execute_run(_args(folder, 40))
    for flag, expect in ((None, True), (False, False)):
        out = tmp_path / f"narrated_{flag}.json"
        args = _build_parser().parse_args(["--narrate", str(folder / "chronicle_bundle.json"),
                                           "--narrator", "mechanical", "--narrate-output", str(out)])
        args.languages = flag
        _run_narrate(args)
        entries = json.loads(out.read_text())["chronicle_entries"]
        assert any("In their own tongues" in e["narrative"] for e in entries) is expect
    bundle = _bundle(folder)
    bundle.pop("languages")
    assert L.NameIndex.from_bundle(bundle) is None


def test_prompt_gains_the_names_block_only_with_an_index(tmp_path, pure_python):
    from chronicler.curator import curate
    from chronicler.models import Event
    from chronicler.narrative import NarrativeEngine
    folder = tmp_path / "p"
    folder.mkdir()
    execute_run(_args(folder, 40))
    bundle = _bundle(folder)
    events = [Event.model_validate(e) for e in bundle["events_timeline"]]
    moments, _ = curate(events, [], [], budget=8, seed=42)
    engine = NarrativeEngine(MechanicalClient(), MechanicalClient())
    engine._accounts = None
    engine._names = None
    plain = engine._prepare_narration_prompts(moments, [])
    engine._names = L.NameIndex.from_bundle(bundle)
    rich = engine._prepare_narration_prompts(moments, [])
    assert not any("IN-WORLD NAMES" in p["prompt"] for p in plain)
    assert any("IN-WORLD NAMES" in p["prompt"] for p in rich)


def test_cli_flag_and_gate_forwarding():
    parser = _build_parser()
    assert parser.parse_args([]).languages is None
    assert parser.parse_args(["--languages"]).languages is True
    assert parser.parse_args(["--no-languages"]).languages is False
    import importlib.util
    spec = importlib.util.spec_from_file_location("m53b", ROOT / "scripts/m53b_run_validation.py")
    m53b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m53b)
    assert m53b._languages_args(argparse.Namespace(languages=None)) == []
    assert m53b._languages_args(argparse.Namespace(languages=True)) == ["--languages"]
    assert m53b._languages_args(argparse.Namespace(languages=False)) == ["--no-languages"]


def test_resumed_world_keeps_its_setting_and_can_switch(tmp_path, pure_python):
    folder = tmp_path / "s"
    folder.mkdir()
    execute_run(_args(folder, 6, languages=False))
    world = WorldState.load(folder / "state.json")
    assert not L.languages_on(world)
    execute_run(_args(folder, 10, languages=None), world=world)
    assert not (folder / "state.languages.json").exists()   # the saved setting holds
    world = WorldState.load(folder / "state.json")
    execute_run(_args(folder, 14, languages=True), world=world)
    st = L.state_of(WorldState.load(folder / "state.json"))
    assert st.enabled_turn == 10 and all(w.turn >= 10 for w in st.words)


def test_bundle_without_the_field_is_unchanged(make_civ):
    from chronicler.bundle import assemble_bundle
    w = _world(make_civ)
    kwargs = dict(world=w, history=[], chronicle_entries=[], era_reflections={},
                  sim_model="s", narrative_model="n", interestingness_score=None)
    plain = assemble_bundle(**kwargs)
    assert "languages" not in plain
    with_field = assemble_bundle(**kwargs, languages={"version": 1})
    assert list(with_field)[-1] == "languages"


@pytest.mark.skipif(not HAS_RUST, reason="Rust crate not built")
def test_native_hybrid_run_is_outcome_identical_with_the_flag(tmp_path):
    outs = {}
    for flag in (False, True):
        folder = tmp_path / str(flag)
        folder.mkdir()
        execute_run(_args(folder, 20, agents="hybrid", languages=flag))
        outs[flag] = folder
    for name in ("state.json", "agent_events.arrow"):
        assert (outs[True] / name).read_bytes() == (outs[False] / name).read_bytes()
    assert _sim_view(_bundle(outs[True])) == _sim_view(_bundle(outs[False]))


# ---------------------------------------------------------------------------
# The frozen exact-trajectory oracles, with the layer switched on
# ---------------------------------------------------------------------------

_FIXTURES = ROOT / "tests" / "fixtures" / "performance"


def _frozen():
    baseline = json.loads((_FIXTURES / "corrected_hunger_2026_10.json").read_text())
    return baseline


@pytest.mark.parametrize("name", sorted(_frozen()["workloads"]))
def test_frozen_oracles_hold_with_languages_on(name, tmp_path, monkeypatch):
    """Every turn's snapshot, events and narration hash and the ordered RNG
    trace match the frozen corrected oracle with the languages kept."""
    import hashlib
    from scripts.benchmark_headless import rng_trace, run
    from scripts.third_wave_controls import legacy_event_dump
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.provenance.LEGACY_TIMELINE", True)
    expected = _frozen()["workloads"][name]
    turns = []

    def capture(snapshot, text, events, named):
        data = [snapshot.model_dump(mode="json"), text,
                [legacy_event_dump(event) for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(
            data, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest())

    out = tmp_path / "artifacts"
    with rng_trace(tmp_path / "rng.jsonl") as trace:
        run({**expected["spec"], "languages": True}, out, on_turn=capture)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]
    assert L.state_of(WorldState.load(out / "state.json")).words
    assert json.loads((out / "chronicle_bundle.json").read_bytes())["languages"]["words"]
