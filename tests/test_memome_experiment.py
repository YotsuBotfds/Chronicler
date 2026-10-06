"""Standalone unittest suite: no production fixtures or scientific workloads."""

import ast
from dataclasses import FrozenInstanceError, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from chronicler.memome_experiment import (
    CONTRACT, Batch, Ledger, Participant, Policy, Proposal, advance,
    checkpoint_json, restore_checkpoint,
)


ROOT = Path(__file__).resolve().parents[1]


def policy():
    traits = (0, 1, 2)
    return Policy(CONTRACT, True, traits, 255, (traits,) * 8,
                  tuple((a, b, -1 if {a, b} == {1, 2} else 0)
                        for a in traits for b in traits), 0, 1000)


def person(name, trait=0, prestige=1, group="group", **kwargs):
    return Participant(name, group, kwargs.get("slots", (trait,) + (255,) * 7), prestige)


def proposal(name="p", recipient="a", slot=0, candidate=1, draw=0):
    return Proposal(name, recipient, slot, candidate, draw)


def apply(people, proposals, p=None):
    return advance(Ledger(0, tuple(people)), Batch(1, tuple(proposals)), p or policy(), enabled=True)


class MemomeTests(unittest.TestCase):
    def test_hand_calculated_probabilities_and_boundaries(self):
        # w/W=0,1/2,1,1/3,2/3,5/6; scaled floors 0,500,1000,200,800,961.
        cases = [([person("a")], 0, 0, "absent_candidate"),
                 ([person("a"), person("b", 1)], 499, 500, "accepted"),
                 ([person("a"), person("b", 1)], 500, 500, "probability_rejected"),
                 ([person("a", 255), person("b", 1)], 999, 1000, "accepted"),
                 ([person("a"), person("b", 1), person("c")], 199, 200, "accepted"),
                 ([person("a"), person("b", 1), person("c")], 200, 200, "probability_rejected"),
                 ([person("a"), person("b", 1), person("c", 1)], 799, 800, "accepted"),
                 ([person("a"), person("b", 1), person("c", 1)], 800, 800, "probability_rejected"),
                 ([person("a"), person("b", 1, 5)], 960, 961, "accepted"),
                 ([person("a"), person("b", 1, 5)], 961, 961, "probability_rejected")]
        for people, draw, threshold, reason in cases:
            with self.subTest(threshold=threshold, draw=draw):
                receipt = apply(people, [proposal(draw=draw)]).receipts[0]
                self.assertEqual((receipt.threshold, receipt.reason), (threshold, reason))

    def test_empty_unchanged_groups_and_slot_local_votes(self):
        self.assertEqual(apply([person("a", 255)], [proposal()]).receipts[0].reason, "empty_electorate")
        self.assertEqual(apply([person("a", 1)], [proposal()]).receipts[0].reason, "unchanged")
        people = [person("a"), person("b", 1, 100, "other")]
        self.assertEqual(apply(people, [proposal()]).receipts[0].candidate_weight, 0)
        # Empty slots do not vote; a candidate in another slot does not vote here.
        people = [person("a", slots=(0, 1) + (255,) * 6), person("b", 255)]
        receipt = apply(people, [proposal()]).receipts[0]
        self.assertEqual((receipt.electorate_weight, receipt.candidate_weight), (1, 0))

    def test_supplied_prestige_changes_weight(self):
        for weight, threshold in [(1, 500), (5, 961)]:
            receipt = apply([person("a"), person("b", 1, weight)], [proposal()]).receipts[0]
            self.assertEqual((receipt.candidate_weight, receipt.electorate_weight, receipt.threshold),
                             (weight, weight + 1, threshold))

    def test_compatibility_and_replaced_slot_exclusion(self):
        with self.assertRaises(ValueError):
            apply([person("a", slots=(1, 2) + (255,) * 6)], [])
        people = [person("a", slots=(0, 2) + (255,) * 6), person("b", 1)]
        self.assertEqual(apply(people, [proposal()]).receipts[0].reason, "incompatible")
        people = [person("a", 2), person("b", 1, 5)]
        self.assertEqual(apply(people, [proposal()]).receipts[0].reason, "accepted")
        # +1 permits adoption but adds no boost; diagonal +1 is explicit.
        p = replace(policy(), diagonal=1,
                    compatibility=tuple((a, b, 1) for a in range(3) for b in range(3)))
        self.assertEqual(apply(people, [proposal()], p).receipts[0].threshold, 961)

    def test_synchronous_order_independence(self):
        people = (person("a"), person("b", 1), person("c", 1), person("d", 0, group="other"))
        proposals = (proposal("a", "a", draw=799), proposal("b", "b", candidate=0, draw=200))
        result = apply(people, proposals)
        # b still sees frozen minority 1/3 after a adopted 1; it is rejected at 200.
        self.assertEqual([r.reason for r in result.receipts], ["accepted", "probability_rejected"])
        p = policy()
        reverse = replace(p, traits=p.traits[::-1], allowed=tuple(d[::-1] for d in p.allowed),
                          compatibility=p.compatibility[::-1])
        self.assertEqual(result, apply(people[::-1], proposals[::-1], reverse))

    def test_atomic_malformed_batches(self):
        ledger = Ledger(0, (person("a"), person("b", 1)))
        original = checkpoint_json(ledger, policy())
        invalid = [proposal(draw=True), proposal(draw=-1), proposal(draw=1000),
                   proposal(slot=True), proposal(slot=-1), proposal(slot=8),
                   proposal(candidate=True), proposal(candidate=255), proposal(candidate=9),
                   proposal(recipient="unknown"), proposal(name=""),
                   proposal(draw=0.1)]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                advance(ledger, Batch(1, (proposal("good", "b", candidate=0), bad)), policy(), enabled=True)
            self.assertEqual(checkpoint_json(ledger, policy()), original)
        for batch in [Batch(True, ()), Batch(-1, ()), Batch(2, ()), Batch(0, ()),
                      Batch(1, (proposal(), proposal())),
                      Batch(1, (proposal("one"), proposal("two"))), Batch(1, [])]:
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                advance(ledger, batch, policy(), enabled=True)

    def test_invalid_ledgers(self):
        invalid = [replace(person("a"), prestige=True), replace(person("a"), prestige=0),
                   replace(person("a"), prestige=-1), replace(person("a"), prestige=1.1),
                   replace(person("a"), slots=(0,) * 7), replace(person("a"), slots=(0,) * 9),
                   replace(person("a"), slots=(True,) + (255,) * 7),
                   replace(person("a"), slots=(9,) + (255,) * 7),
                   replace(person("a"), slots=[0] * 8), replace(person("a"), group=""),
                   replace(person("a"), agent_id="")]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                apply([bad], [])
        with self.assertRaises(ValueError):
            apply([person("a"), person("a")], [])
        for turn in [True, -1, 0.0]:
            with self.assertRaises(ValueError):
                advance(Ledger(turn, ()), Batch(1, ()), policy(), enabled=True)

    def test_invalid_policies(self):
        p = policy()
        bad = [replace(p, version="future"), replace(p, illustrative=False),
               replace(p, illustrative=1), replace(p, draw_scale=True),
               replace(p, draw_scale=0), replace(p, draw_scale=float("inf")),
               replace(p, empty=True), replace(p, empty=0), replace(p, empty=256),
               replace(p, traits=(0, 0)), replace(p, traits=()), replace(p, traits=(True, 1)),
               replace(p, traits=(256,)), replace(p, allowed=p.allowed[:7]),
               replace(p, allowed=((True,),) * 8), replace(p, allowed=((9,),) * 8),
               replace(p, compatibility=p.compatibility[:-1]),
               replace(p, compatibility=p.compatibility + (p.compatibility[0],)),
               replace(p, compatibility=((0, 0, True),) + p.compatibility[1:]),
               replace(p, compatibility=((0, 0, 2),) + p.compatibility[1:]),
               replace(p, compatibility=((0, 0, 1),) + p.compatibility[1:]),
               replace(p, compatibility=tuple((a, b, 1 if (a, b) == (0, 1) else v)
                                              for a, b, v in p.compatibility)),
               replace(p, diagonal=-1), None]
        for malformed in bad:
            with self.subTest(policy=malformed), self.assertRaises(ValueError):
                advance(Ledger(0, (person("a"),)), Batch(1, ()), malformed, enabled=True)
        restricted = replace(p, allowed=((0,),) + p.allowed[1:])
        with self.assertRaises(ValueError):
            apply([person("a")], [proposal()], restricted)

    def test_replay_conflicts_and_admission_cursors(self):
        p = policy()
        start = Ledger(0, (person("a"), person("b", 1)))
        batch = Batch(1, (proposal(draw=499),))
        one = advance(start, batch, p, enabled=True)
        replay = advance(one.ledger, batch, p, enabled=True)
        self.assertTrue(replay.replayed)
        self.assertEqual((one.ledger, one.receipts), (replay.ledger, replay.receipts))
        with self.assertRaises(ValueError):
            advance(one.ledger, replace(batch, proposals=(proposal(draw=500),)), p, enabled=True)
        with self.assertRaises(ValueError):
            advance(one.ledger, Batch(2, batch.proposals), p, enabled=True)
        with self.assertRaises(ValueError):
            advance(one.ledger, Batch(2, (proposal(draw=900),)), p, enabled=True)
        two = advance(one.ledger, Batch(2, ()), p, enabled=True)
        old = advance(two.ledger, batch, p, enabled=True)
        self.assertEqual((old.ledger, old.receipts), (one.ledger, one.receipts))
        with self.assertRaises(ValueError):
            advance(two.ledger, Batch(4, ()), p, enabled=True)
        with self.assertRaises(ValueError):
            advance(two.ledger, Batch(3, ()), replace(p, draw_scale=100), enabled=True)

    def test_interrupted_resume_and_tamper_rejection(self):
        p = policy()
        state = Ledger(0, (person("a"), person("b", 1)))
        batches = [Batch(1, (proposal(draw=499),)), Batch(2, ()),
                   Batch(3, (proposal("p3", "a", candidate=0),))]
        uninterrupted, resumed = state, state
        for batch in batches:
            uninterrupted = advance(uninterrupted, batch, p, enabled=True).ledger
            resumed, restored_policy = restore_checkpoint(checkpoint_json(resumed, p))
            resumed = advance(resumed, batch, restored_policy, enabled=True).ledger
        self.assertEqual(uninterrupted, resumed)
        payload = json.loads(checkpoint_json(resumed, p))
        for field, value in [("threshold", 499), ("candidate_weight", True), ("reason", "accepted")]:
            corrupt = json.loads(json.dumps(payload))
            corrupt["ledger"]["history"][-1]["receipts"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                restore_checkpoint(json.dumps(corrupt))
        corrupt = json.loads(json.dumps(payload))
        corrupt["ledger"]["history"][0]["participants"][0]["slots"][0] = 0
        with self.assertRaises(ValueError):
            restore_checkpoint(json.dumps(corrupt))
        for text in ['{"format":1,"format":2}', '{"format":NaN}', '{}']:
            with self.assertRaises(ValueError):
                restore_checkpoint(text)
        corrupt = json.loads(json.dumps(payload))
        corrupt["ledger"]["unexpected"] = 1
        with self.assertRaises(ValueError):
            restore_checkpoint(json.dumps(corrupt))
        restored, restored_policy = restore_checkpoint(checkpoint_json(resumed, p))
        before = checkpoint_json(restored, restored_policy)
        with self.assertRaises(ValueError):
            advance(restored, Batch(4, (proposal("fresh", "b", candidate=0),
                                      proposal("invalid", "a", draw=1000))),
                    restored_policy, enabled=True)
        self.assertEqual(checkpoint_json(restored, restored_policy), before)

    def test_disabled_immutability_and_no_admission(self):
        people = (person("a"), person("b", 1))
        state = Ledger(0, people)
        batch = Batch(1, (proposal(),))
        result = advance(state, batch, policy())
        self.assertIs(result.ledger, state)
        self.assertEqual(result.receipts, ())
        self.assertTrue(result.disabled)
        self.assertEqual(state.turn, 0)
        self.assertEqual(state.history, ())
        active = advance(state, batch, policy(), enabled=True)
        self.assertFalse(active.replayed)
        for record, field, value in [(state, "genesis_turn", 9), (people[0], "prestige", 7),
                                     (batch, "turn", 7), (policy(), "draw_scale", 7)]:
            with self.assertRaises(FrozenInstanceError):
                setattr(record, field, value)
        self.assertEqual(people[0].slots[0], 0)
        with self.assertRaises(ValueError):
            advance(state, batch, policy(), enabled=1)

    def test_fresh_process_determinism_and_default_off(self):
        script = str(ROOT / "scripts/memome_demo.py")
        outputs = [subprocess.check_output([sys.executable, script, "--enable"],
                                           env={**os.environ, "PYTHONHASHSEED": seed})
                   for seed in ("1", "999", "random")]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])
        payload = json.loads(outputs[0])
        self.assertEqual(payload["checkpoint"]["ledger"]["history"][-1]["batch"]["turn"], 3)
        reasons = [r["reason"] for event in payload["events"] for r in event["receipts"]]
        self.assertIn("incompatible", reasons)
        self.assertIn("accepted", reasons)
        off = json.loads(subprocess.check_output([sys.executable, script]))
        self.assertFalse(off["enabled"])
        self.assertEqual(off["checkpoint"]["ledger"]["history"], [])

    def test_import_scope_and_global_rng_untouched(self):
        kernel = ROOT / "src/chronicler/memome_experiment.py"
        parsed = ast.parse(kernel.read_text())
        modules = {n.module for n in ast.walk(parsed) if isinstance(n, ast.ImportFrom)}
        modules |= {a.name for n in ast.walk(parsed) if isinstance(n, ast.Import) for a in n.names}
        self.assertEqual(modules, {"dataclasses", "json"})
        code = ('import random; before=random.getstate(); '
                'from chronicler.memome_experiment import *; '
                'import runpy; demo=runpy.run_path("scripts/memome_demo.py"); '
                'demo["run"](True); assert random.getstate()==before; '
                'import sys; assert not any(n.startswith(("numpy", "chronicler_agents", '
                '"chronicler.models", "chronicler.main")) for n in sys.modules)')
        subprocess.check_call([sys.executable, "-c", code], cwd=ROOT,
                              env={**os.environ, "PYTHONPATH": str(ROOT / "src")})


if __name__ == "__main__":
    unittest.main()
