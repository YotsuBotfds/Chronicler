"""Guard: decisions read the residence ledger only through its dated accessors (audit A6 11.4).

``docs/integration/residence-ledger.md``: the residence ledger is the
lead-owned displacement contract. Its per-person rows are observer truth: a
decision may read a person's own row only through the A6 accessor
(:func:`chronicler.residence_ledger.own_row_accessor`, an :class:`OwnRow` bound to
that person: one's own experience), rulers and
physical effects read aggregates only (:func:`read_frame`), D3 asks
:func:`separation`, each dated (T's frame at T+1, never the same turn). This
test copies the D2 provenance guard's approach (``test_provenance_decision_guard.py``):
it walks every module under ``src/chronicler`` except the ledger's own modules
(``OWNERS``) and collects each read (``collect_reads``):

* an import of ``chronicler.residence_ledger_state`` (any name, absolute or
  relative, or ``import_module``/``__import__`` of it): the ledger's state;
* a load of an attribute ``residence_ledger`` (``world.livelihoods.residence_ledger``),
  through ``getattr``/``hasattr`` with a constant name, as a constant subscript
  or through ``.get`` with a constant key: the ledger's state;
* a reference to a name of ``chronicler.residence_ledger`` (imported, or
  through the module bound to a name, or ``getattr`` with a constant name);
* any constant string naming the ledger (``residence_ledger``,
  ``chronicler.residence_ledger`` and the state module's names), so a dynamic
  import such as ``livelihoods._module("residence_ledger")`` is caught
  (review m3); outside the owners only the switch wiring may hold one.

Every read site - (module, enclosing function, read) with its number of
occurrences - must be registered in ``LEDGER_READS`` with a classification:

* ``aggregate``: :func:`read_frame` (any decision module; aggregates dated T);
* ``own_row``: :func:`own_row_accessor`, only from ``OWN_ROW_MODULES`` (A6's
  dispatcher, which hands each agent's decision the accessor bound to it);
* ``separation``: :func:`separation`, only from ``SEPARATION_MODULES`` (D3);
* ``record``: :func:`record_status`/:func:`snapshot_summary`, only from modules
  that decide nothing (``RECORD_MODULES``: narration, analysis);
* ``wiring``: the switch's plumbing in ``livelihoods``, ``feature_catalog`` and
  ``batch_manifest`` (its name and value, not the state).

State reads are refused outright outside the owners and ``wiring`` rows. The
test fails closed on an unregistered read, a changed count, a stale row, a row
in a module its class does not allow, and a new public name in
``residence_ledger`` that is not declared. Today no decision module reads the
ledger: every consumer (C2, D3, A6, C4) registers its read here with its review.
It also checks that the ledger is structurally record-only (it assigns no
world attribute but its own container slot and calls only read methods on the
native simulator) and that the bridge's displaced share stays with narration
(audit 11.5).

Limits (not caught), as the D2 guard: a name computed at run time
(``getattr(x, name)`` with a non-constant ``name``, as ``livelihoods._module``
does for the package fan-out, which calls only the hook protocol), the module
rebound to another name or star-imported, and a value that flows from a
registered accessor into a decision elsewhere (each row is a human review of
the reading function, callers included).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "chronicler"

#: The ledger's own modules and the container that declares its slot.
OWNERS = frozenset({"residence_ledger", "residence_ledger_state", "livelihoods_state"})
LEDGER = "chronicler.residence_ledger"
STATE = "chronicler.residence_ledger_state"

#: Public names of ``chronicler.residence_ledger`` and what each is.
HOOKS = frozenset({"set_residence_ledger_enabled", "residence_ledger_active", "on_pool_reset", "phase10",
                   "snapshot_summary"})
ACCESSORS = {"read_frame": "aggregate", "own_row_accessor": "own_row", "separation": "separation"}
RECORD_READERS = frozenset({"record_status", "snapshot_summary"})
CONSTANTS = frozenset({"STAGE", "LABELS", "FRAME_KEYS", "NATIVE", "FAMINE_ONSET_COOLDOWN", "ADULT_AGE",
                       "LedgerReadRefused", "OwnRow"})
#: Constant strings that name the ledger (review m3).
NAMES = frozenset({"residence_ledger", LEDGER, "residence_ledger_state", "chronicler.residence_ledger_state"})
PUBLIC = HOOKS | set(ACCESSORS) | RECORD_READERS | CONSTANTS

#: A6 (``--adaptive-livelihoods``, audit A6 section 7.2): the only modules that
#: may read a person's own row.
OWN_ROW_MODULES = frozenset({"adaptive_livelihoods"})
#: D3's modules, registered by the lead with D3's review (none yet).
SEPARATION_MODULES: frozenset[str] = frozenset({"war_consequences"})
#: Modules that decide no simulation outcome (narration, curation, bundle analysis).
RECORD_MODULES = frozenset({"narrative", "narration_context", "narration_expansion_context", "narration_inputs",
                            "narration_provenance", "narration_audit", "curator", "historiography",
                            "history_forensics", "expansion_audit", "scientific_receipts_audit"})
WIRING_MODULES = frozenset({"livelihoods", "feature_catalog", "batch_manifest", "public_health"})

#: (module, enclosing function, read) -> (occurrences, classification).
LEDGER_READS: dict[tuple[str, str, str], tuple[int, str]] = {
    # Reviewed T-1 consumers: one own row, aggregate environment and separation.
    ("adaptive_livelihoods", "phase10", "own_row_accessor"): (1, "own_row"),
    ("public_health", "check_request", "const:residence_ledger"): (1, "wiring"),
    ("public_health", "environment_factors", "read_frame"): (1, "aggregate"),
    ("war_consequences", "before_agent_tick", "separation"): (1, "separation"),
    # The switch value (``--residence-ledger``) in the prerequisite check, not the state.
    ("livelihoods", "_check_prerequisites", "['residence_ledger']"): (1, "wiring"),
    ("livelihoods", "_check_prerequisites", "const:residence_ledger"): (4, "wiring"),
    # The parser destination and its help text.
    ("livelihoods", "<module>", "const:residence_ledger"): (2, "wiring"),
    # The catalog's declared requirements.
    ("feature_catalog", "<module>", "const:residence_ledger"): (4, "wiring"),
    # The manifest's simulation keys (recorded only when given).
    ("batch_manifest", "<module>", "const:residence_ledger"): (1, "wiring"),
    ("batch_manifest", "simulation_config", "const:residence_ledger"): (1, "wiring"),
}

#: Modules that may name the bridge's displaced share (narration only, audit 11.5).
BRIDGE_SHARE_MODULES = frozenset({"agent_bridge", "main", "narrative", "historical_context"})


def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _aliases(tree: ast.AST) -> tuple[set[str], dict[str, str], list[int]]:
    """Names bound to the ledger module; names imported from it (name -> its
    name there); line numbers of imports of the state module."""
    modules: set[str] = set()
    names: dict[str, str] = {}
    state_imports: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == LEDGER and alias.asname:
                    modules.add(alias.asname)
                if alias.name == STATE:
                    state_imports.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            package = node.module if node.level == 0 else ("chronicler" + ("." + node.module if node.module else "")
                                                           if node.level == 1 else None)
            if package == "chronicler":
                for alias in node.names:
                    if alias.name == "residence_ledger":
                        modules.add(alias.asname or "residence_ledger")
                    if alias.name == "residence_ledger_state":
                        state_imports.append(node.lineno)
            elif package == LEDGER:
                for alias in node.names:
                    names[alias.asname or alias.name] = alias.name
            elif package == STATE:
                state_imports.append(node.lineno)
    return modules, names, state_imports


def collect_reads(src: Path = SRC) -> dict[tuple[str, str, str], int]:
    """Every read of the ledger outside ``OWNERS``, keyed by (module, innermost
    enclosing function, read): ``state:import``, ``.residence_ledger``,
    ``getattr('residence_ledger')``, ``['residence_ledger']``,
    ``.get('residence_ledger')``, ``import_module(...)`` and each name of the
    ledger module referenced (``read_frame``, ``own_row``, ...)."""
    found: dict[tuple[str, str, str], int] = {}
    for path in sorted(src.rglob("*.py")):
        module = path.relative_to(src).with_suffix("").as_posix().replace("/", ".")
        if module in OWNERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules, imported, state_imports = _aliases(tree)

        def add(where, read):
            key = (module, where, read)
            found[key] = found.get(key, 0) + 1

        for _line in state_imports:
            add("<module>", "state:import")

        def visit(node, where):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                where = node.name
            if isinstance(node, ast.Call):
                f = node.func
                fname = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                first = _const(node.args[0]) if node.args else None
                second = _const(node.args[1]) if len(node.args) > 1 else None
                if fname in ("getattr", "hasattr") and second == "residence_ledger":
                    add(where, f"{fname}('residence_ledger')")
                if fname == "getattr" and isinstance(node.args[0], ast.Name) and node.args[0].id in modules \
                        and second is not None:
                    add(where, second)
                if fname in ("import_module", "__import__") and first in (LEDGER, STATE, ".residence_ledger",
                                                                       ".residence_ledger_state"):
                    add(where, f"import_module({first})")
                if fname == "get" and isinstance(f, ast.Attribute) and first == "residence_ledger":
                    add(where, ".get('residence_ledger')")
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                if node.attr == "residence_ledger":
                    add(where, ".residence_ledger")
                if isinstance(node.value, ast.Name) and node.value.id in modules:
                    add(where, node.attr)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in imported:
                add(where, imported[node.id])
            elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                    and _const(node.slice) == "residence_ledger":
                add(where, "['residence_ledger']")
            if isinstance(node, ast.Constant) and node.value in NAMES:
                add(where, f"const:{node.value}")
            for child in ast.iter_child_nodes(node):
                visit(child, where)
        visit(tree, "<module>")
    return found


_STATE_READS = frozenset({"state:import", ".residence_ledger", "getattr('residence_ledger')",
                          "hasattr('residence_ledger')", "['residence_ledger']", ".get('residence_ledger')",
                          f"import_module({STATE})", "import_module(.residence_ledger_state)"})


def _class_problems(reads: dict[tuple[str, str, str], tuple[int, str]]) -> list[str]:
    problems = []
    for (module, where, read), (_n, cls) in sorted(reads.items()):
        if read.startswith("const:"):
            ok = cls == "wiring" and module in WIRING_MODULES          # a name of the ledger: wiring only
        elif cls == "wiring":
            ok = module in WIRING_MODULES
        elif read in _STATE_READS:
            ok = False                                           # state is read only by its owners
        elif cls == "aggregate":
            ok = read == "read_frame"
        elif cls == "own_row":
            ok = read == "own_row_accessor" and module in OWN_ROW_MODULES
        elif cls == "separation":
            ok = read == "separation" and module in SEPARATION_MODULES
        elif cls == "record":
            ok = (read in RECORD_READERS or read in CONSTANTS) and module in RECORD_MODULES
        else:
            ok = False
        if not ok:
            problems.append(f"{module}.{where} reads {read!r} as {cls!r}")
    return problems


def test_every_ledger_read_outside_its_owners_is_registered():
    found = collect_reads()
    registered = {key: n for key, (n, _c) in LEDGER_READS.items()}
    unregistered = sorted(set(found) - set(registered))
    stale = sorted(set(registered) - set(found))
    changed = sorted(k for k in set(found) & set(registered) if found[k] != registered[k])
    assert not unregistered, f"unregistered residence-ledger reads (classify them): {unregistered}"
    assert not stale, f"stale registry rows: {stale}"
    assert not changed, f"changed occurrence counts: {[(k, found[k], registered[k]) for k in changed]}"


def test_each_read_is_allowed_for_its_class_and_module():
    assert _class_problems(LEDGER_READS) == []
    # No decision module reads the ledger today; every consumer registers here.
    assert {cls for _n, cls in LEDGER_READS.values()} == {"wiring", "own_row", "aggregate", "separation"}


def test_the_class_rules_refuse_person_rows_and_state_outside_their_owners():
    assert _class_problems({("cities", "f", "own_row_accessor"): (1, "own_row")})   # not A6
    assert not _class_problems({("adaptive_livelihoods", "f", "own_row_accessor"): (1, "own_row")})
    assert _class_problems({("adaptive_livelihoods", "f", "const:residence_ledger"): (1, "own_row")})
    assert _class_problems({("adaptive_livelihoods", "f", "read_frame"): (1, "own_row")})
    assert _class_problems({("war.runtime", "f", "separation"): (1, "separation")})   # D3 not registered yet
    assert _class_problems({("diplomacy", "f", "record_status"): (1, "record")})       # a decision module
    assert not _class_problems({("narrative", "f", "record_status"): (1, "record")})
    assert _class_problems({("cities", "f", ".residence_ledger"): (1, "aggregate")})   # the state itself
    assert _class_problems({("narrative", "f", "state:import"): (1, "record")})
    assert _class_problems({("cities", "f", "phase10"): (1, "aggregate")})            # a hook is no accessor
    assert not _class_problems({("diplomacy", "f", "read_frame"): (1, "aggregate")})


def test_the_ledgers_public_names_are_declared():
    tree = ast.parse((SRC / "residence_ledger.py").read_text(encoding="utf-8"))
    public = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            public.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            public |= {t.id for t in targets if isinstance(t, ast.Name) and not t.id.startswith("_")}
    assert public == PUBLIC, (sorted(public - PUBLIC), sorted(PUBLIC - public))


def test_the_ledger_is_structurally_record_only():
    """It assigns no world attribute but its own container slot, and calls only
    read methods on the native simulator."""
    tree = ast.parse((SRC / "residence_ledger.py").read_text(encoding="utf-8"))

    def chain(node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Subscript):
            return chain(node.value)
        return ([node.id] if isinstance(node, ast.Name) else ["?"]) + parts[::-1]

    written = set()
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
        for target in targets:
            for t in (target.elts if isinstance(target, ast.Tuple) else [target]):
                if isinstance(t, (ast.Attribute, ast.Subscript)):
                    written.add(".".join(chain(t)))
    assert {w for w in written if w.startswith(("world", "region", "army", "sim", "agent_bridge"))} == {
        "world.livelihoods.residence_ledger"}
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "sim"}
    assert calls == {"get_snapshot", "trip_agent_ids", "get_all_relationships"}
    hooks = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert not hooks & {"before_agent_tick", "after_agent_tick", "rollback_agent_tick", "prepare_phase2",
                        "reserve_first", "finish_phase2", "phase10_before_reserves"}   # Phase 10 only


def test_the_bridges_displaced_share_stays_with_narration():
    """Audit 11.5: no consumer may switch to ``AgentBridge.displacement_by_region``."""
    named = set()
    for path in sorted(SRC.rglob("*.py")):
        module = path.relative_to(SRC).with_suffix("").as_posix().replace("/", ".")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == "displacement_by_region") or \
                    (isinstance(node, ast.Name) and node.id == "displacement_by_region") or \
                    (isinstance(node, ast.arg) and node.arg == "displacement_by_region") or \
                    (isinstance(node, ast.keyword) and node.arg == "displacement_by_region"):
                named.add(module)
    assert named <= BRIDGE_SHARE_MODULES, sorted(named - BRIDGE_SHARE_MODULES)


def test_the_collector_sees_every_kind_of_read(tmp_path):
    pkg = tmp_path / "chronicler"
    pkg.mkdir()
    (pkg / "decider.py").write_text(
        "from chronicler import residence_ledger as RL\n"
        "from chronicler.residence_ledger import own_row_accessor as mine\n"
        "def choose(world, aid):\n"
        "    frame = RL.read_frame(world, consumer_turn=world.turn)\n"
        "    return frame, mine(world, aid, consumer_turn=world.turn), world.livelihoods.residence_ledger.rows\n",
        encoding="utf-8")
    (pkg / "sneaky.py").write_text(
        "import importlib\n"
        "from .residence_ledger_state import ResidenceRow\n"
        "from . import residence_ledger as r2\n"
        "def choose(world, lv):\n"
        "    f = r2.own_row_accessor\n"
        "    g = getattr(r2, 'separation')\n"
        "    m = importlib.import_module('chronicler.residence_ledger_state')\n"
        "    return (getattr(lv, 'residence_ledger'), vars(lv)['residence_ledger'], lv.__dict__.get('residence_ledger'))\n",
        encoding="utf-8")
    # Review m3: a dynamic import through a helper, by the module's name.
    (pkg / "dynamic.py").write_text(
        "from chronicler import livelihoods as LV\n"
        "def choose(world, aid):\n"
        "    return LV._module('residence_ledger').own_row_accessor(world, aid, consumer_turn=world.turn)\n",
        encoding="utf-8")
    (pkg / "residence_ledger.py").write_text("def own_row_accessor(world):\n    return world.livelihoods.residence_ledger\n",
                                             encoding="utf-8")
    found = collect_reads(pkg)
    assert {k: v for k, v in found.items() if k[0] == "decider"} == {
        ("decider", "choose", "read_frame"): 1, ("decider", "choose", "own_row_accessor"): 1,
        ("decider", "choose", ".residence_ledger"): 1}
    assert {k[2] for k in found if k[0] == "sneaky"} == {
        "state:import", "own_row_accessor", "separation", f"import_module({STATE})", "getattr('residence_ledger')",
        "['residence_ledger']", ".get('residence_ledger')", "const:residence_ledger", f"const:{STATE}"}
    assert {k: v for k, v in found.items() if k[0] == "dynamic"} == {
        ("dynamic", "choose", "const:residence_ledger"): 1}
    assert _class_problems({k: (v, cls) for k, v in found.items() if k[0] == "dynamic"
                            for cls in ("own_row",)})                   # refused in a decision module
    assert not [k for k in found if k[0] == "residence_ledger"]
    assert _class_problems({k: (v, "aggregate") for k, v in found.items() if k[0] == "sneaky"})
