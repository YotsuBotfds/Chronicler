"""Golden switch-state pickles (CON-2): the current source loads, rebuilds and
re-pickles every class of tests/fixtures/state_pickles as the base commit did.

The corpus was written by ``scripts/switch_state_identity.py dump`` from the
source before SwitchStateMixin existed. Pickled set items follow string
hashes, so bytes are compared for every pickle under ``PYTHONHASHSEED=0`` (the
oracle lane) and otherwise only for pickles without set items; the loaded
objects are compared in every case.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "state_pickles"
SCRIPT = ROOT / "scripts" / "switch_state_identity.py"
SPEC = importlib.util.spec_from_file_location("switch_state_identity_under_test", SCRIPT)
S = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = S
SPEC.loader.exec_module(S)


def test_corpus_matches_current_source():
    problems = S.check(CORPUS, bytes_exact=os.environ.get("PYTHONHASHSEED") == "0")
    assert problems == []


def test_corpus_covers_every_switch_state_and_stays_small():
    index = json.loads((CORPUS / S.INDEX).read_text(encoding="utf-8"))
    assert index["skipped"] == {}
    assert len(index["classes"]) == len(set(index["classes"])) == 71
    for key in ("livelihoods_state.LivelihoodsState", "recovery_crews_state.RecoveryCrewsState",
                "scholarship_state.ScholarshipState", "apprenticeship_state.Apprenticeship",
                "watershed_state.WatershedState", "timber_orders_state.TimberOrdersState"):
        assert key in index["classes"]
    expected = {"_index.json"}
    for key in index["classes"]:
        record = json.loads((CORPUS / f"{key}.json").read_text(encoding="utf-8"))
        expected.add(f"{key}.json")
        expected.update(v["pickle"] for v in record["variants"].values() if "pickle" in v)
        assert {"populated", "old"} <= set(record["variants"])
    assert {p.name for p in CORPUS.iterdir()} == expected
    assert sum(p.stat().st_size for p in CORPUS.iterdir()) < 1_000_000


def test_old_and_transient_variants_exercise_the_restore_hooks():
    record = json.loads((CORPUS / "recovery_crews_state.RecoveryCrewsState.json").read_text(encoding="utf-8"))
    old = record["variants"]["old"]["loaded"]
    # The hand-written __setstate__ refills every field and the private turn.
    assert old["dict_keys"][-1] == "counters" and old["private"] == {"_turn": None}
    transient = record["variants"]["transient"]
    assert transient["loaded"]["private"] == {"_turn": None}
    refused = json.loads((CORPUS / "learning_services_state.LearningServicesState.json").read_text(encoding="utf-8"))
    assert refused["variants"]["transient"] == {
        "pickle_error": "ValueError: cannot checkpoint pending academy teaching work"}
    plain = json.loads((CORPUS / "guild_leagues_state.GuildLeagueState.json").read_text(encoding="utf-8"))
    # No __setstate__: pydantic's own restore leaves an old pickle's fields missing.
    assert plain["variants"]["old"]["loaded"]["dict_keys"] == []
