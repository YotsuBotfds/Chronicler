"""Guard: simulation decisions never read causal provenance (AUDIT-D 7.3 item 7).

``docs/integration/causal-provenance.md``: provenance records why; it draws
no random numbers, mutates no simulation state and no simulation decision
reads it. A decision that read ``WorldState.provenance`` (the causal index,
episodes, exciters) or an event's ``causes``/``episode`` would feed recorded
causes back into the outcomes and give agents omniscient causal links.

This test walks every module under ``src/chronicler`` (and the bundle readers
moved to ``src/chronicler_lab``) except the narration
and curation modules that exist to read provenance (``NOT_DECISION_CODE``)
and collects each read (``collect_reads``): a call of, or any other reference
to, a provenance read function through the module (``prov.recall``,
``provenance.open_episode``, an imported ``open_episode``, absolute or
relative imports, ``f = prov.recall``, ``getattr(prov, "recall")``), an
``import_module``/``__import__`` of the provenance module, and each read of
an attribute ``provenance``, ``causes`` or ``episode`` - as an attribute,
through ``getattr``/``hasattr`` with a constant name, as a constant subscript
(``vars(w)["provenance"]``) or through ``.get`` with a constant key. Every
read site - (module, enclosing function, read) with its number of
occurrences - must be registered in ``PROVENANCE_READS`` with a reviewed
classification:

* ``cites``: the value only becomes the causes of an emitted event (or of a
  record that is only ever cited), or is written back into provenance;
* ``labels``: the value only chooses an event's description text;
* ``filters``: an ``episode`` check that skips the closing events provenance
  adds to the timeline, so the decision sees what a provenance-free run sees;
* ``analysis``: a reader of saved bundles after a run (audit and forensics
  tools), which decides no simulation outcome;
* ``decision``: the value gates simulation state or an event. These are
  recorded breaches of the contract that predate this guard
  (``KNOWN_DECISION_READS``, documented in
  ``docs/integration/attribution-records.md``); four run on the default path
  of a new world (cities, diplomacy, epidemiology with the contact ledger and
  nomads are on by default), three only under ``--scholarship`` (off by
  default). They stay unchanged (any change goes behind a switch for the
  owner's decision).

The test fails closed on any unregistered read, a changed number of
occurrences, a stale row, or a new ``decision`` row, and on a new read
function in ``provenance.py`` that is not declared. The D-program record and
war modules read none.

Limits (not caught): a name computed at run time (``getattr(x, name)`` with a
non-constant ``name``, ``eval``/``exec``); the provenance module rebound to
another name (``p = prov; p.recall(...)``) or star-imported
(``from chronicler.provenance import *`` then ``recall(...)``); a value that flows from a
registered ``cites`` helper into a decision elsewhere (the classification is
a human review per reading function, so a new ``cites`` row must be read like
code, callers included); a read hidden behind a non-provenance helper that
returns provenance-derived values without the names above; and the
provenance-shaped timeline itself: ``provenance.observe`` folds chronic repeats
of some event types, so a decision that reads timeline events sees the folded
timeline (``causal-provenance.md``, Chronic conditions) - the guard does not
treat timeline reads as provenance reads.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "chronicler"
LAB = ROOT / "src" / "chronicler_lab"

#: Modules whose purpose is to read provenance for narration and curation
#: (they decide no simulation outcome), and provenance itself.
NOT_DECISION_CODE = frozenset({"provenance", "curator", "narrative", "narration_context", "historiography",
                               "narration_provenance", "narration_audit"})

#: Functions of ``chronicler.provenance`` that read the causal index, its
#: episodes or exciters (directly or through each other).
READ_FUNCTIONS = frozenset({"recall", "open_episode", "_wars_of", "_famines_of", "_distress",
                            "excitation_cause", "great_person_causes", "leader_death_causes"})
#: Functions of ``chronicler.provenance`` that write it or run the observer
#: (they read it only to maintain it). ``_rule_*`` cause rules are reads used
#: inside the observer only (``CAUSE_RULES``).
WRITE_FUNCTIONS = frozenset({"remember", "forget", "note_excitation", "_register", "_capital_taken", "_gate",
                             "_close_episodes", "_observe_conditions", "_close_conditions"})
#: Attributes whose loads read provenance: the world's causal index and an
#: event's recorded causes and episode marker.
READ_ATTRIBUTES = frozenset({"provenance", "causes", "episode"})

#: (module, enclosing function, read) -> (occurrences, classification).
PROVENANCE_READS: dict[tuple[str, str, str], tuple[int, str]] = {
    ('agent_movements', '_recall', 'recall'): (1, 'cites'),
    ('agent_movements', '_region_causes', 'open_episode'): (1, 'cites'),
    ('agent_movements', '_region_causes', 'recall'): (4, 'cites'),
    ('cities', '_fall', '.provenance'): (1, 'labels'),
    ('cities', '_fall', 'recall'): (1, 'labels'),
    ('cities', '_lord_change', 'recall'): (2, 'decision'),
    ('cities', '_occupation_sack', 'recall'): (1, 'cites'),
    ('cities', '_region_causes', 'open_episode'): (1, 'cites'),
    ('cities', '_region_causes', 'recall'): (2, 'cites'),
    ('cities', '_revolt', 'recall'): (2, 'cites'),
    ('cities', '_update_rank', 'recall'): (1, 'cites'),
    ('diplomacy', '_aid_convoys', '.episode'): (1, 'decision'),
    ('diplomacy', '_annex', 'recall'): (1, 'cites'),
    ('diplomacy', '_calls_to_arms', 'recall'): (1, 'cites'),
    ('diplomacy', '_crown_passes', 'recall'): (1, 'cites'),
    ('diplomacy', '_ladder_event', 'recall'): (1, 'cites'),
    ('diplomacy', '_threat_causes', 'recall'): (3, 'cites'),
    ('diplomacy', '_treaty_upkeep', 'recall'): (1, 'cites'),
    ('diplomacy', 'make_subject', 'open_episode'): (2, 'cites'),
    ('diplomacy', 'make_subject', 'recall'): (2, 'cites'),
    ('diplomacy', 'on_war_declared', 'recall'): (1, 'cites'),
    ('diplomacy', 'overlord_weakness', 'recall'): (4, 'cites'),
    ('diplomacy', 'resolve_diplomacy_action', '.causes'): (2, 'cites'),
    ('economy', 'detect_supply_shocks', 'open_episode'): (1, 'cites'),
    ('emergence', 'check_tech_regression', 'recall'): (7, 'cites'),
    ('emergence', 'tick_pandemic', 'recall'): (2, 'cites'),
    ('epidemiology', '_introduce', 'open_episode'): (1, 'cites'),
    ('expansion_audit', 'audit_bundle', ".get('causes')"): (1, 'analysis'),
    ('epidemiology', '_report_cause', 'open_episode'): (1, 'cites'),
    ('epidemiology', '_reports', 'open_episode'): (2, 'decision'),
    ('epidemiology', '_reports', 'recall'): (1, 'cites'),
    ('finance', '_deficit_causes', '_famines_of'): (1, 'cites'),
    ('finance', '_deficit_causes', '_wars_of'): (1, 'cites'),
    ('finance', '_deficit_causes', 'recall'): (4, 'cites'),
    ('finance', '_reports', 'recall'): (4, 'cites'),
    ('finance', '_write_off_dead', 'recall'): (3, 'cites'),
    ('finance', 'update_money', '.provenance'): (1, 'cites'),
    ('finance', 'update_money', 'recall'): (1, 'cites'),
    ('governance_runtime', '_advance_psi', '_famines_of'): (1, 'cites'),
    ('governance_runtime', '_advance_psi', 'recall'): (2, 'cites'),
    ('governance_runtime', '_revolt_and_civil_war', 'recall'): (2, 'cites'),
    ('governance_runtime', '_tick_civ', 'recall'): (2, 'cites'),
    ('gp_agendas', '_close', 'recall'): (1, 'cites'),
    ('gp_agendas', '_coup_motive', '_distress'): (1, 'cites'),
    ('gp_agendas', '_coup_motive', 'recall'): (6, 'cites'),
    ('gp_agendas', '_declare', 'recall'): (3, 'cites'),
    ('gp_agendas', '_raw_pool', 'recall'): (1, 'cites'),
    ('gp_agendas', '_state_cause', 'recall'): (2, 'cites'),
    ('gp_agendas', '_trade_deeds', 'recall'): (1, 'cites'),
    ('gp_agendas', 'note_succession', 'recall'): (1, 'cites'),
    ('grain_reserves', 'open_granaries', 'open_episode'): (2, 'cites'),
    ('guilds', '_update', 'recall'): (1, 'cites'),
    ('history_forensics', 'inspect', ".get('causes')"): (1, 'analysis'),
    ('maritime', '_commission', 'recall'): (1, 'cites'),
    ('maritime', '_war_cause', 'recall'): (1, 'cites'),
    ('nomads', '_conquest_waves', 'recall'): (3, 'cites'),
    ('nomads', '_detect_conquests', 'recall'): (3, 'cites'),
    ('nomads', '_form_hordes', 'recall'): (1, 'cites'),
    ('nomads', '_fragment', 'recall'): (1, 'cites'),
    ('nomads', '_herds', 'recall'): (2, 'decision'),
    ('nomads', '_horde_from_federation', 'recall'): (2, 'cites'),
    ('nomads', '_loose_hold', 'recall'): (1, 'cites'),
    ('nomads', '_raids', 'open_episode'): (1, 'cites'),
    ('nomads', '_raids', 'recall'): (1, 'cites'),
    ('nomads', '_tributes', 'recall'): (1, 'cites'),
    ('nomads', '_update_hordes', 'recall'): (1, 'cites'),
    ('scholarship', '_famine', '.episode'): (1, 'filters'),
    ('scholarship', '_in_famine', '.episode'): (1, 'filters'),
    ('scholarship', '_in_famine', '.provenance'): (1, 'decision'),
    ('scholarship', '_newly_occupied', 'recall'): (1, 'decision'),
    ('scholarship', '_persecution', 'recall'): (1, 'cites'),
    ('scholarship', '_sack_cause', 'recall'): (3, 'decision'),
    ('scientific_receipts_audit', '_events', ".get('causes')"): (1, 'analysis'),
    ('scientific_receipts_audit', 'dependency', ".get('causes')"): (1, 'analysis'),
    ('simulation', '_roll_leader_mortality', 'leader_death_causes'): (1, 'cites'),
    ('simulation', 'phase_consequences', 'great_person_causes'): (1, 'cites'),
    ('simulation', 'phase_environment', 'excitation_cause'): (1, 'cites'),
    ('simulation', 'phase_random_events', 'excitation_cause'): (1, 'cites'),
    ('techniques', '_advance', 'recall'): (1, 'cites'),
    ('techniques', '_decay_causes', 'open_episode'): (2, 'cites'),
    ('techniques', '_decay_causes', 'recall'): (6, 'cites'),
    ('techniques', '_gains_and_losses', 'recall'): (4, 'cites'),
    ('techniques', '_invent', 'recall'): (2, 'cites'),
    ('techniques', '_land_causes', 'recall'): (4, 'cites'),
    ('techniques', '_regress', 'recall'): (3, 'cites'),
}

#: Bundle readers run after a simulation (the only modules an ``analysis`` row may name).
ANALYSIS_MODULES = frozenset({"expansion_audit", "history_forensics", "scientific_receipts_audit"})

#: The ``decision`` rows: pre-existing reads of provenance by decisions.
KNOWN_DECISION_READS: frozenset[tuple[str, str, str]] = frozenset({
    # a conquest or occupation key within one turn turns a lord change into a sack
    ('cities', '_lord_change', 'recall'),
    # famine ticks are skipped, so aid follows crisis onsets only
    ('diplomacy', '_aid_convoys', '.episode'),
    # an open epidemic episode suppresses the arrival event and the row's source reset
    ('epidemiology', '_reports', 'open_episode'),
    # a recalled drought key gates the pasture_drought event
    ('nomads', '_herds', 'recall'),
    # an open famine episode blocks a founding
    ('scholarship', '_in_famine', '.provenance'),
    # an occupation key of this turn strikes the seat
    ('scholarship', '_newly_occupied', 'recall'),
    # a sack, conquest or occupation key makes a lord change hostile and blocks a founding
    ('scholarship', '_sack_cause', 'recall'),
})


def _aliases(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    """Names bound to the provenance module, and names imported from it
    (absolute and relative imports; ``import_module`` of it is a read site of
    its own)."""
    modules: set[str] = set()
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "chronicler.provenance" and alias.asname:
                    modules.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            package = node.module if node.level == 0 else ("chronicler" + ("." + node.module if node.module else "")
                                                           if node.level == 1 else None)
            if package == "chronicler":
                for alias in node.names:
                    if alias.name == "provenance":
                        modules.add(alias.asname or "provenance")
            elif package == "chronicler.provenance":
                for alias in node.names:
                    names[alias.asname or alias.name] = alias.name
    return modules, names


def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def collect_reads(src: Path = SRC) -> dict[tuple[str, str, str], int]:
    """Every read of provenance outside ``NOT_DECISION_CODE``, keyed by
    (module, innermost enclosing function, read). Reads: a call of, or any
    other reference to, a provenance read function through the module (also
    through ``getattr`` with a constant name); an import of the provenance
    module by ``import_module``/``__import__``; an attribute ``provenance``,
    ``causes`` or ``episode`` read as an attribute, through ``getattr``/``hasattr``
    with a constant name, as a constant subscript or through ``.get`` with a
    constant key."""
    found: dict[tuple[str, str, str], int] = {}
    for path in sorted(src.rglob("*.py")):
        module = path.relative_to(src).with_suffix("").as_posix().replace("/", ".")
        if module in NOT_DECISION_CODE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules, imported = _aliases(tree)
        called: set[int] = set()

        def add(where, read):
            key = (module, where, read)
            found[key] = found.get(key, 0) + 1

        def visit(node, where):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                where = node.name                          # the innermost enclosing function
            if isinstance(node, ast.Call):
                f = node.func
                called.add(id(f))
                name = None
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in modules:
                    name = f.attr
                elif isinstance(f, ast.Name) and f.id in imported:
                    name = imported[f.id]
                if name in READ_FUNCTIONS:
                    add(where, name)
                fname = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                first = _const(node.args[0]) if node.args else None
                second = _const(node.args[1]) if len(node.args) > 1 else None
                if fname in ("getattr", "hasattr") and second in READ_ATTRIBUTES:
                    add(where, f"{fname}('{second}')")
                if fname == "getattr" and second in READ_FUNCTIONS and isinstance(node.args[0], ast.Name) \
                        and node.args[0].id in modules:
                    add(where, f"getattr('{second}')")
                if fname in ("import_module", "__import__") and first in ("chronicler.provenance", ".provenance"):
                    add(where, "import_module(provenance)")
                if fname == "get" and isinstance(f, ast.Attribute) and first in READ_ATTRIBUTES:
                    add(where, f".get('{first}')")
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                if node.attr in READ_ATTRIBUTES:
                    add(where, "." + node.attr)
                if id(node) not in called and isinstance(node.value, ast.Name) and node.value.id in modules \
                        and node.attr in READ_FUNCTIONS:
                    add(where, "ref:" + node.attr)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and id(node) not in called \
                    and imported.get(node.id) in READ_FUNCTIONS:
                add(where, "ref:" + imported[node.id])
            elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                    and _const(node.slice) in READ_ATTRIBUTES:
                add(where, f"['{_const(node.slice)}']")
            for child in ast.iter_child_nodes(node):
                visit(child, where)
        visit(tree, "<module>")
    return found


def test_every_provenance_read_outside_narration_is_registered():
    found = collect_reads()
    for key, n in collect_reads(LAB).items():
        found[key] = found.get(key, 0) + n
    registered = {key: n for key, (n, _c) in PROVENANCE_READS.items()}
    unregistered = sorted(set(found) - set(registered))
    stale = sorted(set(registered) - set(found))
    changed = sorted(k for k in set(found) & set(registered) if found[k] != registered[k])
    assert not unregistered, f"unregistered provenance reads (classify them): {unregistered}"
    assert not stale, f"stale registry rows: {stale}"
    assert not changed, f"changed occurrence counts: {[(k, found[k], registered[k]) for k in changed]}"


def test_no_new_decision_reads_provenance():
    classes = {c for _n, c in PROVENANCE_READS.values()}
    assert classes <= {"cites", "labels", "filters", "analysis", "decision"}
    assert {key[0] for key, (_n, c) in PROVENANCE_READS.items() if c == "analysis"} <= ANALYSIS_MODULES
    decisions = {key for key, (_n, c) in PROVENANCE_READS.items() if c == "decision"}
    assert decisions == KNOWN_DECISION_READS


def test_the_d_program_records_and_war_modules_read_no_provenance():
    found = collect_reads()
    clean = ("attribution_records", "attribution_records_state", "action_engine", "war.",
             # X1: the residence ledger dates its anchors from region state, never from provenance.
             "residence_ledger")
    assert not [k for k in found if k[0].startswith(clean)]


def test_every_read_function_of_provenance_is_declared():
    tree = ast.parse((SRC / "provenance.py").read_text(encoding="utf-8"))
    declared = READ_FUNCTIONS | WRITE_FUNCTIONS
    touching = set()
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or fn.name.startswith("_rule_"):
            continue
        loads = any(isinstance(n, ast.Attribute) and n.attr == "provenance" for n in ast.walk(fn))
        calls = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        if loads or calls & READ_FUNCTIONS:
            touching.add(fn.name)
    assert touching == declared, (sorted(touching - declared), sorted(declared - touching))


def test_the_collector_sees_every_kind_of_read(tmp_path):
    pkg = tmp_path / "chronicler"
    pkg.mkdir()
    (pkg / "decider.py").write_text(
        "from chronicler import provenance as prov\n"
        "from chronicler.provenance import open_episode as oe\n"
        "def choose(world, ev):\n"
        "    if prov.recall(world, 'k') and oe(world, 'famine', 'R'):\n"
        "        return world.provenance.keys, ev.causes, ev.episode\n"
        "    prov.remember(world, 'k', ev)\n", encoding="utf-8")
    (pkg / "sneaky.py").write_text(
        "import importlib\n"
        "from . import provenance as p2\n"
        "from .provenance import recall as r\n"
        "def choose(world, ev):\n"
        "    f = p2.recall\n"
        "    g = r\n"
        "    h = getattr(p2, 'open_episode')\n"
        "    m = importlib.import_module('chronicler.provenance')\n"
        "    return (getattr(world, 'provenance'), hasattr(ev, 'causes'), ev.get('causes'),\n"
        "            vars(world)['provenance'], ev['episode'])\n", encoding="utf-8")
    (pkg / "narrative.py").write_text("def tell(world):\n    return world.provenance\n", encoding="utf-8")
    found = collect_reads(pkg)
    assert {k: v for k, v in found.items() if k[0] == "decider"} == {
        ("decider", "choose", "recall"): 1, ("decider", "choose", "open_episode"): 1,
        ("decider", "choose", ".provenance"): 1, ("decider", "choose", ".causes"): 1,
        ("decider", "choose", ".episode"): 1}
    assert {k[2] for k in found if k[0] == "sneaky"} == {
        "ref:recall", "getattr('open_episode')", "import_module(provenance)", "getattr('provenance')",
        "hasattr('causes')", ".get('causes')", "['provenance']", "['episode']"}
    assert not [k for k in found if k[0] == "narrative"]
