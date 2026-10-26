"""Focused gates for durable local experiment sessions.

Standard library only, so the suite runs under ``python -m unittest`` and under
pytest. It reads the two existing hand-calculated demo tables without modifying
them, creates no world, draws no RNG, runs no scientific workload and writes only
temporary directories.
"""

import ast
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, asdict, fields, is_dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "experiment_session.py"
KERNEL = ROOT / "src" / "chronicler" / "experiment_sessions.py"
CAMPAIGN_DEMO = runpy.run_path(str(ROOT / "scripts" / "campaign_logistics_demo.py"))
MEMOME_DEMO = runpy.run_path(str(ROOT / "scripts" / "memome_demo.py"))


def policy():
    return es.documented_transport_policy()


def campaign_session():
    tables = CAMPAIGN_DEMO
    kernel_policy = tables["illustrative_policy"]()
    topology = tables["fixture_topology"]()
    admitted = tables["fixture_session"](kernel_policy, topology).state
    return es.create_campaign_session(
        policy=kernel_policy, topology=topology, campaign_id=admitted.campaign_id,
        turn=admitted.admission_turn, staging=admitted.staging, target=admitted.target,
        soldiers=admitted.soldiers, stocks=admitted.stocks)


def campaign_tick(session, turn):
    return CAMPAIGN_DEMO["fixture_tick"](session.session, turn)


def memome_batches():
    return list(MEMOME_DEMO["unit_tables"]()[1])


def memome_session(applied_batches=()):
    kernel_policy, (people, _batches) = (MEMOME_DEMO["illustrative_policy"](),
                                         MEMOME_DEMO["unit_tables"]())
    session = es.create_memome_session(policy=kernel_policy, genesis_turn=0,
                                       participants=people)
    for batch in applied_batches:
        session = es.apply_memome_batch(session, batch).session
    return session


def campaign_trace(turns=range(1, 8)):
    """Advance a fresh campaign session and return session, ticks and receipts."""
    session = campaign_session()
    ticks, receipts = [], []
    for turn in turns:
        tick = campaign_tick(session, turn)
        result = es.apply_campaign_tick(session, tick)
        ticks.append(tick)
        receipts.append(result.receipts[0])
        session = result.session
    return session, ticks, receipts


def memome_trace():
    """Apply the three demo batches and return session, batches and receipts."""
    session, receipts, batches = memome_session(), [], memome_batches()
    for batch in batches:
        result = es.apply_memome_batch(session, batch)
        receipts.extend(result.receipts)
        session = result.session
    return session, batches, receipts


def plain(value):
    """Recursive dataclass/tuple to plain JSON containers, mirroring asdict's keys."""
    if is_dataclass(value):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [plain(item) for item in value]
    return value


def tick_payload(tick):
    """A caller-supplied JSON tick body carrying exactly the kernel fields."""
    return plain(tick)


def batch_payload(batch):
    return plain(batch)


def substitute(text, old, new):
    """Replace exactly one literal fragment; the count assertion guards the fixture."""
    assert text.count(old) == 1, f"expected exactly one {old!r} in the encoded envelope"
    return text.replace(old, new)


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reseal(envelope, *, genesis=None, history=None, latest=None):
    """Rebuild an envelope with recomputed digests so content checks must catch it."""
    genesis = envelope.genesis if genesis is None else genesis
    history = envelope.history if history is None else history
    latest = envelope.latest if latest is None else latest
    combined = json.dumps({"genesis": genesis, "history": history, "latest": latest},
                          sort_keys=True, separators=(",", ":"))
    return es.Envelope(envelope.contract, envelope.envelope_version, envelope.kernel,
                       envelope.kernel_contract, envelope.source_head, envelope.source_tree,
                       envelope.transport, envelope.generation, envelope.turn, genesis,
                       history, latest, _digest(genesis), _digest(history), _digest(latest),
                       _digest(combined))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def condition_shift(payload):
    """Change one committed tick input so its replay contradicts the stored receipt."""
    shifted = dict(payload)
    conditions = [dict(condition) for condition in payload["conditions"]]
    conditions[0]["unmet_needs"] = 5
    shifted["conditions"] = conditions
    return shifted


def assert_primitives(case, value):
    """Recursively require JSON primitives only: no dataclasses or tuples leak out."""
    if isinstance(value, dict):
        for key, child in value.items():
            case.assertIsInstance(key, str)
            assert_primitives(case, child)
    elif isinstance(value, (list, tuple)):
        case.assertNotIsInstance(value, tuple)
        for child in value:
            assert_primitives(case, child)
    else:
        case.assertNotIsInstance(value, float)
        case.assertIsInstance(value, (str, int, bool, type(None)))


class _TempDirCase(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.workdir = Path(self._temporary.name)
        self.addCleanup(self._temporary.cleanup)

    def session_file(self, name="session.json"):
        return self.workdir / name

    def transport_file(self, overrides=None):
        chosen = policy() if overrides is None else replace(policy(), **overrides)
        target = self.workdir / "transport.json"
        target.write_text(canonical(chosen.as_payload()), encoding="utf-8")
        return target

    def leftovers(self):
        return sorted(item.name for item in self.workdir.glob(".*.tmp"))

    def listing(self):
        return sorted(item.name for item in self.workdir.iterdir())

    def commit(self, session, target=None, transport=None, generation=None, digest=None):
        target = self.session_file() if target is None else target
        return es.commit_session(target, session, transport=transport or policy(),
                                 expected_generation=generation, expected_digest=digest)


class DemoTraceTests(_TempDirCase):
    def test_campaign_demo_trace_matches_the_existing_hand_calculated_receipts(self):
        applied, _ticks, receipts = campaign_trace()
        expected = CAMPAIGN_DEMO["run_fixture"]()
        self.assertEqual([asdict(receipt) for receipt in receipts], expected["receipts"])
        self.assertEqual(asdict(applied.session.state), expected["state"])
        self.assertEqual(applied.session.state.phase, "closed")
        self.assertEqual(es.session_turn(applied), 7)
        # The hand-calculated turn-3 phase and roster, cross-checked with the demo.
        third = campaign_trace(turns=range(1, 4))[0]
        self.assertEqual(third.session.state.phase, "arrived")
        self.assertEqual(tuple(s.agent_id for s in third.session.state.soldiers),
                         (101, 202))
        self.assertEqual(third.session.cursor.receipts[-1].turn, 3)

    def test_memome_demo_trace_matches_the_existing_hand_calculated_checkpoint(self):
        applied, _batches, _receipts = memome_trace()
        expected = MEMOME_DEMO["run"](True)
        self.assertEqual(mm.checkpoint_json(applied.ledger, applied.policy),
                         canonical(expected["checkpoint"]) + "\n")
        self.assertEqual((es.session_turn(applied), len(applied.ledger.history)), (3, 3))

    def test_campaign_session_round_trips_through_seven_sequential_commits(self):
        complete, _ticks, receipts = campaign_trace()
        target = self.session_file()
        applied, generation, digest = campaign_session(), None, None
        for turn in range(1, 8):
            applied = es.apply_campaign_tick(applied, campaign_tick(applied, turn)).session
            result = self.commit(applied, target, generation=generation, digest=digest)
            self.assertEqual(result.generation, turn)
            generation, digest = result.generation, result.digest
        loaded = es.load_session(target, transport=policy())
        self.assertEqual(loaded.generation, 7)
        self.assertEqual(es.session_digest(loaded.session, policy()),
                         es.session_digest(complete, policy()))
        self.assertEqual([asdict(receipt)
                          for receipt in loaded.session.session.cursor.receipts],
                         [asdict(receipt) for receipt in receipts])
        self.assertEqual(loaded.digest, hashlib.sha256(target.read_bytes()).hexdigest())

    def test_interrupted_resume_equals_uninterrupted_complete_receipts(self):
        complete, ticks, receipts = campaign_trace()
        target = self.session_file()
        partial, _unused, partial_receipts = campaign_trace(turns=range(1, 4))
        self.commit(partial, target)
        resumed = es.load_session(target, transport=policy()).session
        for tick in ticks[3:]:
            resumed = es.apply_campaign_tick(resumed, tick).session
        self.assertEqual([asdict(receipt) for receipt in resumed.session.cursor.receipts],
                         [asdict(receipt) for receipt in receipts])
        self.assertEqual(cl.canonical_bytes(resumed.session),
                         cl.canonical_bytes(complete.session))
        self.assertEqual(len(partial_receipts), 3)
        self.assertEqual(es.session_digest(resumed, policy()),
                         es.session_digest(complete, policy()))

    def test_memome_interrupted_resume_equals_the_uninterrupted_ledger(self):
        batches = memome_batches()
        complete, _batches, _receipts = memome_trace()
        target = self.session_file("memome.json")
        self.commit(memome_session(batches[:2]), target)
        resumed = es.load_session(target, transport=policy()).session
        for batch in batches[2:]:
            resumed = es.apply_memome_batch(resumed, batch).session
        self.assertEqual(mm.checkpoint_json(resumed.ledger, resumed.policy),
                         mm.checkpoint_json(complete.ledger, complete.policy))
        self.assertEqual(es.session_digest(resumed, policy()),
                         es.session_digest(complete, policy()))
        self.assertEqual(len(resumed.ledger.history), 3)

    def test_loading_never_writes_and_reports_expose_primitives_only(self):
        applied, _ticks, _receipts = campaign_trace(turns=range(1, 4))
        target = self.session_file()
        self.commit(applied, target)
        before = (target.read_bytes(), target.stat().st_mtime_ns)
        report = es.session_report(es.load_session(target, transport=policy()))
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)
        self.assertEqual(report["kernel"], "m60a")
        self.assertEqual(report["turn"], 3)
        self.assertEqual(report["phase"], applied.session.state.phase)
        # The hand-calculated turn-3 phase, straight from the existing demo.
        self.assertEqual(report["phase"], "arrived")
        self.assertEqual(report["campaign_id"], "m60a-table-demo")
        self.assertEqual(len(report["turn_index"]), 3)
        self.assertEqual(report["latest_receipt"]["turn"], 3)
        self.assertEqual(report["commit_order"], list(es.SESSION_COMMIT_ORDER))
        self.assertEqual(json.loads(canonical(report))["turn"], 3)
        assert_primitives(self, report)
        self.assertIsInstance(report["roster"], list)
        self.assertEqual(report["roster"][0]["agent_id"], 101)


class ReplayAndConflictTests(_TempDirCase):
    def test_identical_campaign_replay_writes_nothing(self):
        applied, ticks, receipts = campaign_trace(turns=range(1, 5))
        target = self.session_file()
        self.commit(applied, target)
        stored = target.read_bytes()
        replayed = es.apply_campaign_tick(applied, ticks[1])
        self.assertFalse(replayed.changed)
        self.assertTrue(replayed.replayed)
        self.assertIs(replayed.session, applied)
        self.assertEqual(replayed.turn, 4)
        self.assertEqual(asdict(replayed.receipts[0]), asdict(receipts[1]))
        self.assertEqual(target.read_bytes(), stored)
        self.assertEqual(len(applied.session.cursor.receipts), 4)

    def test_contradictory_campaign_replay_gaps_and_reused_ids_are_atomic(self):
        full, ticks, _receipts = campaign_trace()
        applied = campaign_trace(turns=range(1, 5))[0]
        saved = cl.canonical_bytes(applied.session)
        contradictory = replace(ticks[3], credits=(cl.Credit("local-demo-credit-4", 4, 2, 3),))
        reused = replace(ticks[4], orders=(cl.Order("hold-4", 5, "hold"),
                                           cl.Order("return-5", 5, "return")))
        duplicated = replace(ticks[3], orders=(cl.Order("hold-4", 4, "hold"),
                                               cl.Order("hold-4", 4, "hold")))
        for bad in (contradictory, reused, duplicated, replace(ticks[3], turn=9),
                    replace(ticks[0], turn=0), replace(ticks[3], turn=2),
                    replace(ticks[3], orders=(cl.Order("hold-4", 4, "hold"),
                                              cl.Order("march-4", 4, "march")))):
            with self.subTest(tick=bad.turn), self.assertRaises(ValueError):
                es.apply_campaign_tick(applied, bad)
        self.assertEqual(cl.canonical_bytes(applied.session), saved)
        self.assertEqual(cl.canonical_bytes(full.session.state),
                         cl.canonical_bytes(campaign_trace()[0].session.state))

    def test_older_memome_replay_keeps_the_latest_ledger_and_generation(self):
        applied, batches, receipts = memome_trace()
        target = self.session_file("memome.json")
        self.commit(applied, target)
        stored = target.read_bytes()
        replayed = es.apply_memome_batch(applied, batches[0])
        self.assertEqual(batches[0], MEMOME_DEMO["unit_tables"]()[1][0])
        self.assertFalse(replayed.changed)
        self.assertTrue(replayed.replayed)
        self.assertIs(replayed.session, applied)
        self.assertEqual(replayed.turn, 3)
        self.assertEqual(len(replayed.receipts), 3)
        self.assertEqual(asdict(replayed.receipts[0]), asdict(receipts[0]))
        self.assertEqual(replayed.session.ledger.turn, 3)
        self.assertEqual(len(replayed.session.ledger.history), 3)
        self.assertEqual(target.read_bytes(), stored)
        loaded = es.load_session(target, transport=policy())
        self.assertEqual(loaded.generation, 1)
        self.assertEqual(loaded.session.ledger.turn, 3)

    def test_identical_memome_replay_at_the_latest_turn_writes_nothing(self):
        applied, batches, _receipts = memome_trace()
        replayed = es.apply_memome_batch(applied, batches[-1])
        self.assertFalse(replayed.changed)
        self.assertTrue(replayed.replayed)
        self.assertEqual(replayed.turn, 3)
        self.assertIs(replayed.session, applied)

    def test_contradictory_memome_replay_and_gaps_are_atomic(self):
        applied, batches, _receipts = memome_trace()
        saved = mm.checkpoint_json(applied.ledger, applied.policy)
        for bad in (replace(batches[0], proposals=(mm.Proposal("minority", "basic-1", 1, 3, 200),)),
                    replace(batches[1], turn=5),
                    replace(batches[1], turn=4),
                    replace(batches[2], proposals=(mm.Proposal("absent", "basic-0", 0, 0, 1),))):
            with self.subTest(batch=bad.turn), self.assertRaises(ValueError):
                es.apply_memome_batch(applied, bad)
        self.assertEqual(mm.checkpoint_json(applied.ledger, applied.policy), saved)


class StrictDecodingTests(_TempDirCase):
    def setUp(self):
        super().setUp()
        self.applied, self.ticks, _receipts = campaign_trace(turns=range(1, 4))
        self.envelope = es.encode_session(self.applied, transport=policy(), generation=3)
        self.text = es.encode_envelope_text(self.envelope, policy()).decode("utf-8")

    def reparse(self, text):
        return es.decode_envelope(es.decode_envelope_text(text.encode("utf-8"), policy()))

    def test_duplicate_keys_and_unknown_or_missing_envelope_fields_are_rejected(self):
        self.assertTrue(self.text.startswith("{"))
        with self.assertRaises(es.TransportDomainError):
            self.reparse(substitute(self.text, '"contract":',
                                    '"contract":"chronicler-experiment-session-v1","contract":'))
        with self.assertRaises(es.SessionError):
            self.reparse('{"unexpected":1,' + self.text[1:])
        with self.assertRaises(es.SessionError):
            self.reparse(substitute(self.text, '"kernel":"m60a",', ""))
        with self.assertRaises(es.SessionError):
            self.reparse(substitute(self.text, '"history_digest":"', '"extra":"x","digest":"'))
        with self.assertRaises(ValueError):
            self.reparse("not json at all")

    def test_nonfinite_boolean_float_and_string_integers_are_rejected(self):
        for bad in ('"generation":NaN', '"generation":Infinity', '"generation":-Infinity',
                    '"generation":3.0', '"generation":3e0'):
            with self.subTest(bad=bad):
                with self.assertRaises(es.TransportDomainError):
                    self.reparse(substitute(self.text, '"generation":3', bad))
        for bad in ('"generation":true', '"generation":null', '"generation":[3]',
                    '"generation":"3"', '"generation":0'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.reparse(substitute(self.text, '"generation":3', bad))
        with self.assertRaises(ValueError):
            self.reparse(substitute(self.text, '"turn":3', '"turn":"3"'))

    def test_malformed_tuple_containers_are_rejected_by_the_whitelisted_tables(self):
        genesis = json.loads(self.envelope.genesis)
        for broken in ({"neighbors": ""}, {"neighbors": [1, "1"]}, {"neighbors": {"0": 1}},
                       {"neighbors": None}, {"neighbors": [1.5]}):
            with self.subTest(broken=broken):
                topology = dict(genesis["topology"])
                topology["regions"] = [dict(topology["regions"][0], **broken)]
                tampered = reseal(self.envelope, genesis=canonical(
                    {"policy": genesis["policy"], "topology": topology,
                     "admission": genesis["admission"]}))
                with self.assertRaises(ValueError):
                    es.decode_envelope(tampered)
        history = json.loads(self.envelope.history)
        for field in ("supply_sources", "orders", "conditions", "draws"):
            with self.subTest(field=field):
                tampered = reseal(self.envelope, history=canonical(
                    [dict(tick, **{field: ""}) for tick in history]))
                with self.assertRaises(ValueError):
                    es.decode_envelope(tampered)

    def test_caller_supplied_batches_are_typed_and_strict(self):
        tick = self.ticks[0]
        self.assertEqual(es.campaign_tick_from_payload(tick_payload(tick),
                                                      transport=policy()), tick)
        for broken in ({"turn": "1"}, {"turn": True}, {"supply_sources": 1},
                       {"turn": 1, "orders": {}, "credits": [], "conditions": [],
                        "draws": [], "supply_sources": [1]},
                       dict(tick_payload(tick), unknown=1),
                       dict(tick_payload(tick), turn=-1)):
            with self.subTest(broken=sorted(broken)[0]), self.assertRaises(ValueError):
                es.campaign_tick_from_payload(broken, transport=policy())
        batch = es.memome_batch_from_payload(batch_payload(mm.Batch(1, ())), transport=policy())
        self.assertEqual(batch, mm.Batch(1, ()))
        for broken in ({"turn": True, "proposals": []}, {"turn": 1, "proposals": 0},
                       {"turn": 1, "proposals": [0]},
                       {"turn": 1, "proposals": [], "extra": []}):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                es.memome_batch_from_payload(broken, transport=policy())

    def test_typed_admission_requires_one_source_per_configuration_record(self):
        applied = self.applied
        with self.assertRaises(ValueError):
            es.campaign_session_from_payload({}, transport=policy(),
                                            policy=applied.policy, topology=applied.topology)
        with self.assertRaises(ValueError):
            es.memome_session_from_payload({"genesis_turn": 0, "participants": []},
                                           transport=policy())
        memome, _b, _r = memome_trace()
        rebuilt = es.memome_session_from_payload(
            {"genesis_turn": memome.genesis_turn,
             "participants": [plain(person) for person in memome.genesis]},
            transport=policy(), policy=memome.policy)
        self.assertEqual(mm.checkpoint_json(rebuilt.ledger, rebuilt.policy),
                         mm.checkpoint_json(memome_session().ledger, rebuilt.policy))


class IdentityAndDigestTests(_TempDirCase):
    def test_foreign_contract_kernel_and_source_identities_fail_explicitly(self):
        applied, _t, _r = campaign_trace(turns=range(1, 3))
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        for changed in (replace(envelope, contract="chronicler-other-session-v9"),
                        replace(envelope, envelope_version=2),
                        replace(envelope, kernel="m60b"),
                        replace(envelope, kernel_contract="chronicler-m60b-detached-v1"),
                        replace(envelope, source_head="0" * 40),
                        replace(envelope, source_tree="0" * 40),
                        replace(envelope, generation=True),
                        replace(envelope, turn=-1),
                        replace(envelope, genesis="")):
            with self.subTest(field=str(changed.kernel) + str(changed.envelope_version)):
                with self.assertRaises(ValueError):
                    es.decode_envelope(changed)
        self.assertEqual(es.KERNEL_CONTRACTS, {
            "m60a": "chronicler-m60a-detached-v1",
            "m68a": "chronicler-m68a-detached-v1"})
        self.assertEqual((es.BASELINE_SOURCE_HEAD, len(es.BASELINE_SOURCE_HEAD)),
                         ("208d140d47d9f2dee0788267f79fa7276df22b42", 40))

    def test_unsealed_digest_changes_are_rejected(self):
        applied, _t, _r = campaign_trace(turns=range(1, 3))
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        for field in ("genesis_digest", "history_digest", "latest_digest", "session_digest"):
            with self.subTest(field=field), self.assertRaises(es.IntegrityError):
                es.decode_envelope(replace(envelope, **{field: "0" * 64}))

    def test_resealed_history_content_changes_are_rejected_by_reconstruction(self):
        applied, _ticks, _r = campaign_trace(turns=range(1, 3))
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        broken = envelope.history.replace('"supply_sources":[1]', '"supply_sources":[2]')
        self.assertNotEqual(broken, envelope.history)
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(reseal(envelope, history=broken))
        shortened = json.loads(envelope.history)[:1]
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(reseal(envelope, history=canonical(shortened)))

    def test_changed_policy_history_and_state_content_are_rejected_after_resealing(self):
        applied, _ticks, _r = campaign_trace(turns=range(1, 5))
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        genesis = json.loads(envelope.genesis)
        changed_policy = dict(genesis["policy"])
        changed_policy["hunger_stress"] = genesis["policy"]["hunger_stress"] + 1
        with self.assertRaises(ValueError):
            es.decode_envelope(reseal(envelope, genesis=canonical(
                dict(genesis, policy=changed_policy))))
        history = json.loads(envelope.history)
        changed_credit = [dict(tick) for tick in history]
        changed_credit[3]["credits"] = [{"source_id": "local-demo-credit-4", "turn": 4,
                                         "region": 2, "rations": 3}]
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(reseal(envelope, history=canonical(changed_credit)))
        latest = json.loads(envelope.latest)
        changed_state = dict(latest["state"])
        changed_state["consumed_food"] = latest["state"]["consumed_food"] + 1
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(reseal(envelope, latest=canonical(dict(latest,
                                                                      state=changed_state))))
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(replace(envelope, turn=envelope.turn + 1))
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(replace(envelope, latest=canonical({})))

    def test_memome_checkpoint_and_envelope_content_are_cross_checked(self):
        applied, _batches, _r = memome_trace()
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        latest = json.loads(envelope.latest)
        checkpoint = json.loads(latest["checkpoint"])
        checkpoint["ledger"]["history"][1]["participants"][0]["prestige"] = 7
        with self.assertRaises(ValueError):
            es.decode_envelope(reseal(envelope, latest=canonical(
                {"checkpoint": canonical(checkpoint)})))
        genesis_only = mm.checkpoint_json(mm.Ledger(applied.genesis_turn, applied.genesis),
                                          applied.policy)
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(reseal(envelope, latest=canonical(
                {"checkpoint": genesis_only})))
        genesis = json.loads(envelope.genesis)
        with self.assertRaises(es.IntegrityError):
            es.decode_envelope(reseal(envelope, genesis=canonical(
                dict(genesis, genesis_turn=genesis["genesis_turn"] + 1))))
        other_policy = replace(applied.policy, draw_scale=2000)
        with self.assertRaises(ValueError):
            es.decode_envelope(reseal(envelope, latest=canonical(
                {"checkpoint": mm.checkpoint_json(applied.ledger, other_policy)})))

    def test_transport_policy_must_be_explicit_versioned_and_matching(self):
        applied, _t, _r = campaign_trace(turns=range(1, 2))
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        data = es.encode_envelope_text(envelope, policy())
        narrower = replace(policy(), max_history=5)
        with self.assertRaises(es.ContractError):
            es.decode_envelope_text(data, narrower)
        with self.assertRaises(es.ContractError):
            es.encode_envelope_text(envelope, narrower)
        matching = replace(policy(), max_history=1)
        # Coherent matching metadata re-encodes identically; digests are not
        # signatures binding an unknowable earlier object.
        self.assertEqual(es.encode_envelope_text(
            es.encode_session(applied, transport=matching, generation=1), matching),
            es.encode_envelope_text(es.encode_session(applied, transport=matching,
                                                     generation=1), matching))
        for bad in (replace(policy(), version="chronicler-session-transport-v9"),
                    replace(policy(), max_bytes=0),
                    replace(policy(), max_bytes=es.MAX_TRANSPORT_BYTES + 1),
                    replace(policy(), max_records=0),
                    replace(policy(), max_records=es.MAX_TRANSPORT_RECORDS + 1),
                    replace(policy(), max_history=-1),
                    replace(policy(), max_int_bits=0),
                    replace(policy(), max_int_bits=es.MAX_TRANSPORT_INT_BITS + 1)):
            with self.subTest(policy=bad.version), self.assertRaises(ValueError):
                es.transport_policy_from_payload(bad.as_payload())
        with self.assertRaises(es.TransportDomainError):
            es.encode_session(applied, transport=replace(policy(), max_history=0),
                              generation=1)
        with self.assertRaises(ValueError):
            es.encode_envelope_text(envelope, "chronicler-session-transport-v1")
        with self.assertRaises(ValueError):
            es.encode_session(applied, transport=policy().as_payload(), generation=1)
        self.assertEqual(es.transport_policy_from_text(canonical(policy().as_payload())),
                         policy())
        for bad_text in ('{"version":"chronicler-session-transport-v1"}',
                         '{"version":"chronicler-session-transport-v1","max_bytes":1,'
                         '"max_bytes":2,"max_records":1,"max_history":1,"max_int_bits":1}',
                         '{"version":"chronicler-session-transport-v1","max_bytes":NaN,'
                         '"max_records":1,"max_history":1,"max_int_bits":1}',
                         '{"version":"chronicler-session-transport-v1","max_bytes":1.5,'
                         '"max_records":1,"max_history":1,"max_int_bits":1}'):
            with self.subTest(text=bad_text[:48]), self.assertRaises(ValueError):
                es.transport_policy_from_text(bad_text)
        with self.assertRaises(ValueError):
            es.transport_policy_from_text(canonical(policy().as_payload()) + " " * 5000)


class TransportBoundaryTests(_TempDirCase):
    def wide_session(self, prestige):
        kernel_policy = MEMOME_DEMO["illustrative_policy"]()
        people = (mm.Participant("huge", "group", (1,) + (255,) * 7, prestige),
                  mm.Participant("peer", "group", (1,) + (255,) * 7, 1))
        ledger = mm.advance(mm.Ledger(0, people), mm.Batch(1, ()), kernel_policy,
                            enabled=True).ledger
        return es.MemomeSession(kernel_policy, 0, tuple(people), (mm.Batch(1, ()),), ledger)

    def test_independently_reviewed_121_bit_integers_are_supported(self):
        prestige = 2 ** 120
        self.assertEqual(prestige.bit_length(), 121)
        session = self.wide_session(prestige)
        exact = replace(policy(), max_int_bits=121)
        envelope = es.encode_session(session, transport=exact, generation=1)
        restored = es.decode_envelope(envelope)
        self.assertEqual(restored.ledger.participants[0].prestige, prestige)
        self.assertEqual(es.session_digest(restored, exact),
                         es.session_digest(session, exact))
        with self.assertRaises(es.TransportDomainError):
            es.encode_session(session, transport=replace(policy(), max_int_bits=120),
                              generation=1)
        # The reviewed kernel is untouched and still accepts the same value.
        self.assertEqual(session.ledger.participants[0].prestige, prestige)
        # The value is exact in both known persisted fields, read back by name
        # rather than by counting textual occurrences.
        payload = json.loads(es.encode_envelope_text(envelope, exact))
        self.assertEqual(json.loads(payload["genesis"])["participants"][0]["prestige"],
                         prestige)
        checkpoint = json.loads(json.loads(payload["latest"])["checkpoint"])
        self.assertEqual(checkpoint["ledger"]["genesis"][0]["prestige"], prestige)
        self.assertEqual(restored.ledger.genesis[0].prestige, prestige)

    def test_huge_prestige_is_an_intentional_transport_error_before_any_write(self):
        limit = sys.get_int_max_str_digits() if hasattr(sys, "get_int_max_str_digits") else None
        session = self.wide_session(10 ** 5000)
        with self.assertRaises(es.TransportDomainError) as caught:
            es.encode_session(session, transport=policy(), generation=1)
        self.assertIn("16610", str(caught.exception))
        with self.assertRaises(es.TransportDomainError):
            es.encode_session(session, transport=replace(
                policy(), max_int_bits=es.MAX_TRANSPORT_INT_BITS), generation=1)
        target = self.session_file()
        with self.assertRaises(es.TransportDomainError):
            es.commit_session(target, session, transport=policy(), expected_generation=None,
                              expected_digest=None)
        self.assertFalse(target.exists())
        self.assertEqual(self.leftovers(), [])
        # The unsupported value is never clamped, and no global limit was changed.
        self.assertEqual(session.ledger.participants[0].prestige, 10 ** 5000)
        if limit is not None:
            self.assertEqual(sys.get_int_max_str_digits(), limit)

    def test_byte_record_and_history_limits_are_explicit(self):
        applied, _t, _r = campaign_trace(turns=range(1, 4))
        for overrides in ({"max_bytes": 512}, {"max_records": 8}, {"max_history": 2}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(es.TransportDomainError):
                    es.encode_session(applied, transport=replace(policy(), **overrides),
                                      generation=1)
        target = self.session_file()
        with self.assertRaises(es.TransportDomainError):
            es.commit_session(target, applied, transport=replace(policy(), max_bytes=512),
                              expected_generation=None, expected_digest=None)
        self.assertFalse(target.exists())
        # The same bounds are TransportDomainError on the read side, too.
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        for overrides in ({"max_bytes": 512}, {"max_records": 8}, {"max_history": 2}):
            with self.subTest(read=overrides):
                with self.assertRaises(es.TransportDomainError):
                    es.decode_envelope(replace(envelope,
                                               transport=replace(policy(), **overrides)))
        data = es.encode_envelope_text(envelope, policy())
        with self.assertRaises(es.TransportDomainError):
            es.decode_envelope_text(data, replace(policy(), max_bytes=len(data) - 1))
        # An invalid *policy* is a SessionError, not a transport-domain failure.
        for overrides in ({"max_bytes": 0}, {"max_records": 0}, {"max_int_bits": 0},
                          {"max_history": -1}, {"max_bytes": es.MAX_TRANSPORT_BYTES + 1}):
            with self.subTest(policy=overrides):
                with self.assertRaises(es.SessionError) as caught:
                    es.transport_policy_from_payload(replace(policy(), **overrides).as_payload())
                self.assertNotIsInstance(caught.exception, es.TransportDomainError)

    def test_transport_limits_never_clamp_or_alter_persisted_content(self):
        applied, _t, _r = campaign_trace(turns=range(1, 3))
        narrow = es.encode_session(applied, transport=policy(), generation=1)
        wider = es.encode_session(applied, transport=replace(
            policy(), max_bytes=1 << 24, max_records=1 << 20, max_int_bits=8192),
            generation=1)
        self.assertEqual((narrow.genesis, narrow.history, narrow.latest),
                         (wider.genesis, wider.history, wider.latest))
        data = es.encode_envelope_text(narrow, policy())
        with self.assertRaises(es.ContractError):
            es.decode_envelope_text(data, replace(policy(), max_bytes=1 << 24))
        round_tripped = es.decode_envelope_text(data, policy())
        self.assertEqual((round_tripped.genesis, round_tripped.history,
                          round_tripped.latest),
                         (narrow.genesis, narrow.history, narrow.latest))
        with self.assertRaises(es.TransportDomainError):
            es.decode_envelope_text(data, replace(policy(), max_bytes=len(data) - 1))


class ImmutabilityTests(_TempDirCase):
    def test_every_exposed_record_is_frozen(self):
        applied, _t, _r = campaign_trace(turns=range(1, 2))
        memome = memome_session()
        envelope = es.encode_session(applied, transport=policy(), generation=1)
        for record, field, value in (
                (policy(), "max_bytes", 1),
                (applied, "history", ()),
                (applied.admission, "campaign_id", "other"),
                (applied.policy, "ration_demand", 2),
                (applied.session.state, "turn", 9),
                (applied.session.cursor, "receipts", ()),
                (memome, "batches", ()),
                (memome.ledger, "genesis", ()),
                (envelope, "generation", 9),
                (envelope, "transport", policy())):
            with self.subTest(record=type(record).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(record, field, value)
        self.assertEqual(es.session_digest(applied, policy()),
                         es.session_digest(es.decode_envelope(envelope), policy()))
        self.assertEqual(tuple(s.agent_id for s in applied.session.state.soldiers),
                         (101, 202))

    def test_apply_rejects_foreign_records_without_touching_state(self):
        applied, ticks, _r = campaign_trace(turns=range(1, 3))
        saved = cl.canonical_bytes(applied.session)
        for bad in (None, {"turn": 3}, [1], "tick", (3,)):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                es.apply_campaign_tick(applied, bad)
        with self.assertRaises(ValueError):
            es.apply_campaign_tick(applied, ticks[0].__class__(99, (), (), (), (), ()))
        with self.assertRaises(ValueError):
            es.apply_campaign_tick(applied, replace(ticks[0], turn=True))
        self.assertEqual(cl.canonical_bytes(applied.session), saved)
        memome, batches, _rr = memome_trace()
        memome_state = mm.checkpoint_json(memome.ledger, memome.policy)
        for bad in (None, {"turn": 4}, [1], "batch"):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                es.apply_memome_batch(memome, bad)
        self.assertEqual(mm.checkpoint_json(memome.ledger, memome.policy), memome_state)
        with self.assertRaises(ValueError):
            es.apply_memome_batch(memome, replace(batches[0], turn=True))


class PersistenceTests(_TempDirCase):
    def test_committed_sessions_require_a_matching_expected_generation_and_digest(self):
        applied, _t, _r = campaign_trace(turns=range(1, 3))
        target = self.session_file()
        first = self.commit(applied, target)
        self.assertEqual((first.generation, first.turn), (1, 2))
        stored = target.read_bytes()
        for generation, digest in ((9, first.digest), (None, None), (1, "0" * 64)):
            with self.subTest(generation=generation), self.assertRaises(
                    es.StaleGenerationError):
                self.commit(applied, target, generation=generation, digest=digest)
        with self.assertRaises(ValueError):
            self.commit(applied, target, generation=True, digest=first.digest)
        self.assertEqual(target.read_bytes(), stored)
        loaded = es.load_session(target, transport=policy())
        second = self.commit(loaded.session, target, generation=loaded.generation,
                             digest=loaded.digest)
        self.assertEqual(second.generation, 2)
        self.assertNotEqual(second.digest, first.digest)
        self.assertEqual(es.decode_envelope_text(target.read_bytes(),
                                                 policy()).generation, 2)
        with self.assertRaises(es.PersistenceError):
            self.commit(applied, self.session_file("gone.json"), generation=1, digest=first.digest)

    def test_write_failures_preserve_the_prior_bytes_and_leave_no_temporary_file(self):
        applied, _t, _r = campaign_trace(turns=range(1, 3))
        target = self.session_file()
        first = self.commit(applied, target)
        stored = target.read_bytes()
        real_fsync = os.fsync

        def failing_file_fsync(descriptor):
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("simulated file fsync failure")
            return real_fsync(descriptor)

        def failing_replace(source, destination):
            raise OSError("simulated replace failure")

        for patcher in (mock.patch.object(es.os, "fsync", failing_file_fsync),
                        mock.patch.object(es.os, "replace", failing_replace)):
            with self.subTest(patch=patcher.__class__.__name__), patcher:
                with self.assertRaises(es.PersistenceError) as caught:
                    self.commit(applied, target, generation=1, digest=first.digest)
                self.assertNotIsInstance(caught.exception, es.DurabilityUncertain)
                self.assertEqual(target.read_bytes(), stored)
                self.assertEqual(self.leftovers(), [])
                self.assertEqual(es.load_session(target, transport=policy()).generation, 1)

    def test_directory_fsync_failure_reports_an_explicit_uncertain_outcome(self):
        applied, _t, _r = campaign_trace(turns=range(1, 3))
        target = self.session_file()
        first = self.commit(applied, target)
        stored = target.read_bytes()
        real_open = os.open

        def open_without_directory(directory, flags, *arguments):
            if Path(directory) == target.parent:
                raise PermissionError("simulated directory fsync unsupported")
            return real_open(directory, flags, *arguments)

        with mock.patch.object(es.os, "open", open_without_directory):
            with self.assertRaises(es.DurabilityUncertain) as caught:
                self.commit(applied, target, generation=1, digest=first.digest)
        self.assertIn("read the file back", str(caught.exception))
        self.assertEqual(self.leftovers(), [])
        replaced = target.read_bytes()
        self.assertNotEqual(replaced, stored)
        # Readback and reconciliation is the documented recovery path.
        reconciled = es.load_session(target, transport=policy())
        self.assertEqual(reconciled.generation, 2)
        self.assertEqual(es.session_digest(reconciled.session, policy()),
                         es.session_digest(applied, policy()))

    def test_unsupported_platform_fails_before_any_mutation(self):
        applied, _t, _r = campaign_trace(turns=range(1, 2))
        target = self.session_file()
        with mock.patch.object(es, "fcntl", None):
            with self.assertRaises(es.UnsupportedPlatformError):
                es.commit_session(target, applied, transport=policy(),
                                  expected_generation=None, expected_digest=None)
        self.assertEqual(self.listing(), [])
        with self.assertRaises(es.PersistenceError):
            es.commit_session(self.workdir / "missing" / "session.json", applied,
                              transport=policy(), expected_generation=None,
                              expected_digest=None)
        self.assertEqual(self.listing(), [])
        victim = self.workdir / "victim"
        victim.write_bytes(b"untouched")
        link = self.workdir / "link.json"
        link.symlink_to(victim)
        with self.assertRaises(es.PersistenceError):
            es.commit_session(link, applied, transport=policy(), expected_generation=None,
                              expected_digest=None)
        self.assertEqual(self.listing(), ["link.json", "victim"])
        self.assertEqual(victim.read_bytes(), b"untouched")
        with self.assertRaises(es.PersistenceError):
            es.commit_session(self.workdir, applied, transport=policy(),
                              expected_generation=None, expected_digest=None)
        self.assertEqual(self.listing(), ["link.json", "victim"])

    def test_a_foreign_session_file_is_never_overwritten(self):
        applied, _t, _r = campaign_trace(turns=range(1, 2))
        target = self.session_file()
        foreign = '{"contract":"chronicler-other-session-v1"}\n'
        target.write_text(foreign, encoding="utf-8")
        with self.assertRaises(ValueError):
            es.commit_session(target, applied, transport=policy(), expected_generation=1,
                              expected_digest=hashlib.sha256(
                                  foreign.encode("utf-8")).hexdigest())
        self.assertEqual(target.read_text(encoding="utf-8"), foreign)
        with self.assertRaises(ValueError):
            es.load_session(target, transport=policy())

    def test_the_writer_lock_is_one_private_local_sibling_file(self):
        applied, _t, _r = campaign_trace(turns=range(1, 2))
        target = self.session_file()
        self.commit(applied, target)
        self.assertEqual(self.listing(), [".session.json.lock", "session.json"])
        self.assertEqual(stat.S_IMODE((self.workdir / ".session.json.lock").stat().st_mode),
                         0o600)


class CommandLineTests(_TempDirCase):
    def cli(self, arguments, seed="0"):
        environment = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT / "src"))
        return subprocess.run([sys.executable, str(DRIVER), *arguments], cwd=self.workdir,
                              env=environment, capture_output=True, check=False)

    def write_json(self, name, value):
        target = self.workdir / name
        target.write_text(canonical(value), encoding="utf-8")
        return target

    def test_default_invocation_is_a_no_op(self):
        before = self.listing()
        result = self.cli([])
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        payload = json.loads(result.stdout)
        self.assertEqual(payload["default_invocation"], "no-op")
        self.assertFalse(payload["reads_files"])
        self.assertFalse(payload["writes_files"])
        self.assertFalse(payload["calls_kernels"])
        self.assertEqual(payload["commands"], ["create", "apply", "inspect", "verify"])
        self.assertEqual(payload["source_head"], es.BASELINE_SOURCE_HEAD)
        self.assertEqual(payload["limits"]["one_writer"], True)
        self.assertEqual(self.listing(), before)
        self.assertEqual(self.cli(["--help"]).returncode, 0)

    def test_full_campaign_workflow_is_deterministic_across_hash_seeds(self):
        applied, ticks, _receipts = campaign_trace()
        transport_path = self.transport_file()
        target = self.session_file()
        batch_paths = [self.write_json(f"tick-{index}.json", tick_payload(tick))
                       for index, tick in enumerate(ticks)]
        transcripts, digests = [], []
        for seed in ("0", "1", "42", "101"):
            steps = [self.cli(["create", "--kernel", "m60a", "--path", str(target),
                               "--transport", str(transport_path), "--demo"], seed)]
            steps.extend(self.cli(["apply", "--path", str(target), "--transport",
                                   str(transport_path), "--batch", str(path)], seed)
                         for path in batch_paths)
            steps.append(self.cli(["verify", "--path", str(target), "--transport",
                                   str(transport_path)], seed))
            steps.append(self.cli(["inspect", "--path", str(target), "--transport",
                                   str(transport_path)], seed))
            for step in steps:
                self.assertEqual(step.returncode, 0, step.stderr.decode())
            transcripts.append(b"".join(step.stdout for step in steps))
            digests.append(hashlib.sha256(target.read_bytes()).hexdigest())
            target.unlink()
        self.assertEqual(len(set(transcripts)), 1)
        self.assertEqual(len(set(digests)), 1)
        lines = transcripts[0].splitlines()
        self.assertEqual(len(lines), 10)
        self.assertEqual((json.loads(lines[0])["generation"], json.loads(lines[0])["turn"]),
                         (1, 0))
        for line in lines[1:8]:
            self.assertTrue(json.loads(line)["committed"])
        verified = json.loads(lines[8])
        self.assertEqual((verified["generation"], verified["turn"], verified["verified"]),
                         (8, 7, True))
        self.assertEqual(verified["session_digest"], es.session_digest(applied, policy()))
        inspected = json.loads(lines[9])
        self.assertEqual((inspected["phase"], inspected["food"]["consumed"]), ("closed", 12))
        self.assertEqual(len(inspected["turn_index"]), 7)
        self.assertFalse(inspected["writes"])

    def test_replay_reports_no_write_and_conflicts_exit_with_an_error(self):
        transport_path = self.transport_file()
        target = self.session_file()
        created = self.cli(["create", "--kernel", "m60a", "--path", str(target),
                            "--transport", str(transport_path), "--demo"])
        self.assertEqual(created.returncode, 0, created.stderr.decode())
        _applied, ticks, _r = campaign_trace(turns=range(1, 2))
        tick_path = self.write_json("tick-1.json", tick_payload(ticks[0]))
        first = self.cli(["apply", "--path", str(target), "--transport", str(transport_path),
                          "--batch", str(tick_path)])
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertTrue(json.loads(first.stdout)["committed"])
        stored = target.read_bytes()
        replay = self.cli(["apply", "--path", str(target), "--transport", str(transport_path),
                           "--batch", str(tick_path)])
        self.assertEqual(replay.returncode, 0, replay.stderr.decode())
        report = json.loads(replay.stdout)
        self.assertFalse(report["committed"])
        self.assertFalse(report["changed"])
        self.assertTrue(report["replayed"])
        self.assertEqual(target.read_bytes(), stored)
        conflict = self.write_json("conflict.json", condition_shift(tick_payload(ticks[0])))
        rejected = self.cli(["apply", "--path", str(target), "--transport",
                             str(transport_path), "--batch", str(conflict)])
        self.assertEqual(rejected.returncode, 3)
        self.assertIn("ValueError", rejected.stderr.decode())
        self.assertEqual(target.read_bytes(), stored)

    def test_memome_cli_path_uses_the_existing_demo_inputs(self):
        transport_path = self.transport_file()
        target = self.session_file("memome.json")
        _applied, batches, _r = memome_trace()
        created = self.cli(["create", "--kernel", "m68a", "--path", str(target),
                            "--transport", str(transport_path), "--demo"])
        self.assertEqual(created.returncode, 0, created.stderr.decode())
        for index, batch in enumerate(batches):
            path = self.write_json(f"batch-{index}.json", batch_payload(batch))
            result = self.cli(["apply", "--path", str(target), "--transport",
                               str(transport_path), "--batch", str(path)])
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertTrue(json.loads(result.stdout)["committed"])
        verified = json.loads(self.cli(["verify", "--path", str(target), "--transport",
                                         str(transport_path)]).stdout)
        complete, _b, _rr = memome_trace()
        self.assertEqual((verified["turn"], verified["generation"]), (3, 4))
        self.assertEqual(verified["session_digest"], es.session_digest(complete, policy()))
        inspected = json.loads(self.cli(["inspect", "--path", str(target), "--transport",
                                          str(transport_path)]).stdout)
        self.assertEqual((inspected["kernel"], inspected["genesis_turn"]), ("m68a", 0))
        self.assertIn("probability_rejected",
                      [reason for turn in inspected["turn_index"]
                       for reason in turn["reasons"]])

    def test_caller_supplied_typed_admission_requires_exactly_one_source(self):
        transport_path = self.transport_file()
        target = self.session_file()
        neither = self.cli(["create", "--kernel", "m60a", "--path", str(target),
                            "--transport", str(transport_path)])
        self.assertEqual(neither.returncode, 3)
        self.assertFalse(target.exists())
        both = self.cli(["create", "--kernel", "m60a", "--path", str(target),
                         "--transport", str(transport_path), "--demo",
                         "--admission", str(transport_path)])
        self.assertEqual(both.returncode, 3)
        self.assertFalse(target.exists())
        tables = CAMPAIGN_DEMO
        kernel_policy, topology = tables["illustrative_policy"](), tables["fixture_topology"]()
        admitted = tables["fixture_session"](kernel_policy, topology).state
        admission = self.write_json("admission.json", {
            "policy": plain(kernel_policy), "topology": plain(topology),
            "campaign_id": admitted.campaign_id, "turn": admitted.admission_turn,
            "staging": admitted.staging, "target": admitted.target,
            "soldiers": [plain(soldier) for soldier in admitted.soldiers],
            "stocks": [plain(stock) for stock in admitted.stocks]})
        typed = self.cli(["create", "--kernel", "m60a", "--path", str(target),
                          "--transport", str(transport_path), "--admission", str(admission)])
        self.assertEqual(typed.returncode, 0, typed.stderr.decode())
        payload = json.loads(typed.stdout)
        self.assertEqual((payload["turn"], payload["generation"]), (0, 1))
        self.assertEqual(payload["session_digest"],
                         es.session_digest(campaign_session(), policy()))


def probe_policy(**changes):
    return replace(es.documented_transport_policy(), **changes)


class ReviewerRegressionTests(_TempDirCase):
    """Regression gates for the independent important-code review findings."""

    cli = CommandLineTests.cli

    def write_json(self, name, value):
        target = self.workdir / name
        target.write_text(value if type(value) is str else canonical(value), encoding="utf-8")
        return target

    def probe_campaign(self):
        return campaign_session()

    def probe_culture(self):
        batches = memome_batches()
        return memome_session(), batches

    def test_original_unordered_memome_replay_is_canonical_not_contradictory(self):
        session, batches = self.probe_culture()
        original = batches[0]
        session = es.apply_memome_batch(session, original).session
        self.assertNotEqual(tuple(p.proposal_id for p in original.proposals),
                            tuple(p.proposal_id for p in session.batches[0].proposals))
        for batch in batches[1:]:
            session = es.apply_memome_batch(session, batch).session
        target = self.session_file("memome.json")
        first = self.commit(session, target)
        before = target.read_bytes(), target.stat().st_mtime_ns
        kernel = mm.advance(session.ledger, original, session.policy, enabled=True)
        self.assertTrue(kernel.replayed)
        result = es.apply_memome_batch(session, original)
        self.assertIs(result.session, session)
        self.assertFalse(result.changed)
        self.assertTrue(result.replayed)
        self.assertEqual(result.turn, 3)
        self.assertEqual(result.receipts, kernel.receipts)
        self.assertEqual(len(result.session.ledger.history), 3)
        self.assertEqual(result.session.ledger.turn, 3)
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)
        self.assertEqual(es.load_session(target, transport=policy()).generation,
                         first.generation)
        reordered = es.apply_memome_batch(session, replace(
            original, proposals=tuple(reversed(original.proposals))))
        self.assertIs(reordered.session, session)
        self.assertFalse(reordered.changed)
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)
        before_digest = es.session_digest(session, policy())
        contradiction = replace(original, proposals=(replace(original.proposals[0],
                                                              draw=1),))
        with self.assertRaises(ValueError):
            es.apply_memome_batch(session, contradiction)
        self.assertEqual(es.session_digest(session, policy()), before_digest)
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)

    def test_decoded_integer_fields_obey_exact_bit_width(self):
        session = self.probe_campaign()
        huge = 2 ** 4096  # 4097 bits, still inside the 1234-digit 4096-bit length
        payload = tick_payload(campaign_tick(session, 1))
        payload["conditions"][0]["unmet_needs"] = huge
        with self.assertRaises(es.TransportDomainError):
            es.campaign_tick_from_payload(payload, transport=policy())
        admission = plain(session.admission)
        admission["soldiers"][0]["morale"] = huge
        with self.assertRaises(es.TransportDomainError):
            es.campaign_session_from_payload(
                dict(admission, policy=plain(session.policy),
                     topology=plain(session.topology)), transport=policy())
        batch = batch_payload(mm.Batch(1, ()))
        batch["turn"] = huge
        with self.assertRaises(es.TransportDomainError):
            es.memome_batch_from_payload(batch, transport=policy())
        nested = batch_payload(mm.Batch(1, (mm.Proposal("p", "a", 0, 1, 0),)))
        nested["proposals"][0]["draw"] = huge
        with self.assertRaises(es.TransportDomainError):
            es.memome_batch_from_payload(nested, transport=policy())
        # The same width inside a memome participant table and a topology.
        with self.assertRaises(es.TransportDomainError):
            es.memome_session_from_payload(
                {"genesis_turn": 0, "participants": [
                    {"agent_id": "a", "group": "g", "slots": [1] + [255] * 7,
                     "prestige": huge}]},
                transport=policy(), policy=MEMOME_DEMO["illustrative_policy"]())

    def test_sealed_and_outer_envelope_integers_obey_exact_bit_width(self):
        session = self.probe_campaign()
        big = 2 ** 4096
        wide = es.create_campaign_session(
            policy=session.policy, topology=session.topology,
            campaign_id=session.admission.campaign_id, turn=session.admission.turn,
            staging=session.admission.staging, target=session.admission.target,
            soldiers=session.admission.soldiers,
            stocks=(cl.Stock(0, big), cl.Stock(1, 0), cl.Stock(2, 4)))
        encoded = es.encode_session(wide, transport=probe_policy(max_int_bits=4097),
                                    generation=1)
        with self.assertRaises(es.TransportDomainError):
            es.decode_envelope(replace(encoded, transport=policy()))
        with self.assertRaises(es.TransportDomainError):
            es.encode_session(session, transport=policy(), generation=big)
        with self.assertRaises(es.TransportDomainError):
            es.decode_envelope(replace(encoded, transport=probe_policy(max_int_bits=4097),
                                       generation=2 ** 4097))

    def test_memome_derived_receipt_integers_obey_the_domain(self):
        kernel_policy = MEMOME_DEMO["illustrative_policy"]()
        people = tuple(mm.Participant(name, "group", (1,) + (255,) * 7, 2 ** 120)
                       for name in ("a", "b"))
        session = es.create_memome_session(policy=kernel_policy, genesis_turn=0,
                                           participants=people)
        session = es.apply_memome_batch(session, mm.Batch(
            1, (mm.Proposal("p", "a", 0, 1, 0),))).session
        receipt = session.ledger.history[0].receipts[0]
        self.assertEqual(receipt.electorate_weight.bit_length(), 122)
        with self.assertRaises(es.TransportDomainError):
            es.encode_session(session, transport=probe_policy(max_int_bits=121),
                              generation=1)
        envelope = es.encode_session(session, transport=probe_policy(max_int_bits=122),
                                     generation=1)
        with self.assertRaises(es.TransportDomainError):
            es.decode_envelope(replace(envelope, transport=probe_policy(max_int_bits=121)))

    def test_memome_policy_and_slot_integers_obey_the_domain(self):
        base = MEMOME_DEMO["illustrative_policy"]()
        huge = 2 ** 4096
        people = [plain(mm.Participant("a", "group", (1,) + (255,) * 7, 1))]
        wide = {"draw_scale": huge, "diagonal": huge, "empty": huge,
                "traits": (0, 1, huge), "allowed": ((0,), (huge,)) + (base.allowed[2],) * 6,
                "compatibility": ((0, 0, 0), (0, 1, huge)) + base.compatibility[2:]}
        for field, value in wide.items():
            with self.subTest(policy_field=field):
                malformed = plain(replace(base, **{field: value}))
                with self.assertRaises(es.TransportDomainError):
                    es.memome_session_from_payload(
                        {"genesis_turn": 0, "participants": people, "policy": malformed},
                        transport=policy())
        # An over-wide slot trait in the participant table, on the entrypoint and
        # again through a sealed envelope's own genesis text.
        wide_slots = {"agent_id": "a", "group": "g", "slots": [huge] + [255] * 7,
                      "prestige": 1}
        with self.assertRaises(es.TransportDomainError):
            es.memome_session_from_payload(
                {"genesis_turn": 0, "participants": [wide_slots]},
                transport=policy(), policy=base)
        session = es.create_memome_session(policy=base, genesis_turn=0,
                                           participants=(mm.Participant(
                                               "a", "group", (1,) + (255,) * 7, 1),))
        envelope = es.encode_session(session, transport=probe_policy(max_int_bits=4097),
                                     generation=1)
        genesis = json.loads(envelope.genesis)
        genesis["participants"][0]["slots"][0] = huge
        with self.assertRaises(es.TransportDomainError):
            es.decode_envelope(reseal(replace(envelope, transport=policy()),
                                      genesis=canonical(genesis)))

    def test_genesis_participants_and_kernel_records_count_toward_limits(self):
        session, _batches = self.probe_culture()
        self.assertEqual(len(session.genesis), 5)
        with self.assertRaises(es.TransportDomainError):
            es.encode_session(session, transport=probe_policy(max_history=0), generation=1)
        kernel_policy = MEMOME_DEMO["illustrative_policy"]()
        people = tuple(mm.Participant(name, "group", (1,) + (255,) * 7, 1)
                       for name in ("a", "b"))
        small = es.create_memome_session(policy=kernel_policy, genesis_turn=0,
                                         participants=people)
        small = es.apply_memome_batch(small, mm.Batch(
            1, (mm.Proposal("p", "a", 0, 1, 0),))).session
        for chosen in (probe_policy(max_records=5), probe_policy(max_records=12),
                       probe_policy(max_records=13)):
            with self.subTest(max_records=chosen.max_records):
                with self.assertRaises(es.TransportDomainError):
                    es.encode_session(small, transport=chosen, generation=1)
        # The same complete payload round-trips within a sufficient budget.
        allowed = probe_policy(max_records=32)
        envelope = es.encode_session(small, transport=allowed, generation=1)
        self.assertEqual(es.decode_envelope(envelope).ledger.turn, 1)
        with self.assertRaises(es.TransportDomainError):
            es.decode_envelope(replace(envelope, transport=probe_policy(max_records=8)))

    def test_transport_payload_booleans_and_malformed_identity_are_session_errors(self):
        chosen = probe_policy(max_history=1)
        envelope = es.encode_session(self.probe_campaign(), transport=chosen, generation=1)
        raw = json.loads(es.encode_envelope_text(envelope, chosen))
        for field in ("max_history", "max_bytes", "max_records", "max_int_bits"):
            for value in (True, "1", 1.0, None, [1]):
                with self.subTest(field=field, value=value):
                    tampered = json.loads(json.dumps(raw))
                    tampered["transport"][field] = value
                    target = self.session_file(f"bool-{field}.json")
                    target.write_bytes(json.dumps(tampered).encode("utf-8"))
                    with self.assertRaises(es.SessionError):
                        es.load_session(target, transport=chosen)
        for field, value in (("kernel", []), ("kernel", 1), ("contract", {}),
                             ("envelope_version", "1"), ("source_head", []),
                             ("kernel_contract", []), ("turn", "3")):
            with self.subTest(field=field):
                with self.assertRaises(es.SessionError):
                    es.decode_envelope(replace(
                        es.encode_session(self.probe_campaign(), transport=policy(),
                                          generation=1), **{field: value}))
        with self.assertRaises(es.SessionError):
            es.decode_envelope(replace(
                es.encode_session(self.probe_campaign(), transport=policy(), generation=1),
                kernel={}))

    def test_cli_rejects_duplicate_and_malformed_submissions_before_any_commit(self):
        transport_path = self.transport_file()
        session, batches = self.probe_culture()
        target = self.session_file("memome.json")
        self.commit(session, target)
        before = target.read_bytes(), target.stat().st_mtime_ns
        for body in ('{"turn":1,"turn":1,"proposals":[]}', '{"turn":NaN,"proposals":[]}',
                     '{"turn":1.5,"proposals":[]}', '{"turn":1}',
                     '{"turn":1,"proposals":[],"extra":[]}', "[]"):
            with self.subTest(body=body[:24]):
                path = self.write_json("bad-batch.json", body)
                rejected = self.cli(["apply", "--path", str(target), "--transport",
                                     str(transport_path), "--batch", str(path)])
                self.assertEqual(rejected.returncode, 3)
                self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)
        for body in ('{"genesis_turn":0,"genesis_turn":0,"participants":[]}',
                     '{"genesis_turn":NaN,"participants":[]}'):
            with self.subTest(body=body[:24]):
                admission = self.write_json("bad-admission.json", body)
                rejected = self.cli(["create", "--kernel", "m68a", "--path",
                                     str(self.session_file("new.json")), "--transport",
                                     str(transport_path), "--admission", str(admission)])
                self.assertEqual(rejected.returncode, 3)
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)
        with self.assertRaises(es.TransportDomainError):
            es.submission_from_bytes(b"{}", transport=probe_policy(max_bytes=1))
        oversized = self.session_file("huge.json")
        oversized.write_bytes(b" " * (policy().max_bytes + 1))
        with self.assertRaises(es.TransportDomainError):
            es.submission_from_bytes(oversized.read_bytes(), transport=policy())
        # A well-formed batch still commits afterwards.
        good = self.write_json("good-batch.json", batch_payload(batches[0]))
        accepted = self.cli(["apply", "--path", str(target), "--transport",
                             str(transport_path), "--batch", str(good)])
        self.assertEqual(accepted.returncode, 0, accepted.stderr.decode())
        self.assertTrue(json.loads(accepted.stdout)["committed"])

    def test_destination_shape_is_rechecked_under_the_writer_lock(self):
        session = self.probe_campaign()
        target = self.session_file()
        first = self.commit(session, target)
        victim = self.workdir / "victim.json"
        victim.write_bytes(target.read_bytes())
        original_lock = es._exclusive_lock

        @contextmanager
        def swapping_lock(_lock_path):
            target.unlink()
            target.symlink_to(victim)
            yield

        with mock.patch.object(es, "_exclusive_lock", swapping_lock):
            with self.assertRaises(es.PersistenceError):
                self.commit(session, target, generation=first.generation,
                            digest=first.digest)
        # The substituted link was refused and the victim file is byte-identical
        # to the last good commit, i.e. nothing was written through the link.
        self.assertTrue(target.is_symlink())
        self.assertEqual(hashlib.sha256(victim.read_bytes()).hexdigest(), first.digest)
        self.assertEqual(target.read_bytes(), victim.read_bytes())
        # With the real lock restored, the same commit still fails on the link.
        with mock.patch.object(es, "_exclusive_lock", original_lock):
            with self.assertRaises(es.PersistenceError):
                self.commit(session, target, generation=first.generation,
                            digest=first.digest)
        self.assertEqual(hashlib.sha256(victim.read_bytes()).hexdigest(), first.digest)

    def test_lock_file_must_be_a_regular_file(self):
        session = self.probe_campaign()
        lock = self.workdir / ".session.json.lock"
        lock.symlink_to(self.workdir / "victim")
        with self.assertRaises(es.PersistenceError):
            self.commit(session, self.session_file())
        self.assertTrue(lock.is_symlink())
        self.assertFalse(self.session_file().exists())
        self.assertEqual(lock.resolve(strict=False).name, "victim")

    def test_write_interruption_before_fsync_preserves_prior_bytes(self):
        session = self.probe_campaign()
        target = self.session_file()
        first = self.commit(session, target)
        advanced = es.apply_campaign_tick(
            session, campaign_tick(session, 1)).session
        before = target.read_bytes()

        class InterruptedWrite:
            def __init__(self, descriptor):
                self.descriptor = descriptor

            def __enter__(self):
                return self

            def write(self, data):
                raise OSError("injected write interruption")

            def __exit__(self, *arguments):
                os.close(self.descriptor)

        # Also cover an interruption after the write but before the file fsync.
        real_fsync = os.fsync

        def failing_file_fsync(descriptor):
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("injected file fsync interruption")
            return real_fsync(descriptor)

        patchers = (mock.patch.object(
            es.os, "fdopen", side_effect=lambda fd, mode: InterruptedWrite(fd)),
            mock.patch.object(es.os, "fsync", side_effect=failing_file_fsync))
        for patcher in patchers:
            # The patched name: subTest parameters are plain values (pytest-xdist serializes them).
            with self.subTest(patch=patcher.attribute), patcher:
                with self.assertRaises(es.PersistenceError) as caught:
                    self.commit(advanced, target, generation=first.generation,
                                digest=first.digest)
                self.assertNotIsInstance(caught.exception, es.DurabilityUncertain)
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(self.leftovers(), [])
                self.assertEqual(es.load_session(target, transport=policy()).generation, 1)

    def test_interrupted_resume_with_stale_generation_preserves_bytes(self):
        uninterrupted = self.probe_campaign()
        target = self.session_file()
        expected = self.commit(uninterrupted, target)
        for turn in range(1, 8):
            tick = campaign_tick(uninterrupted, turn)
            uninterrupted = es.apply_campaign_tick(uninterrupted, tick).session
            resumed = es.load_session(target, transport=policy())
            resumed_next = es.apply_campaign_tick(resumed.session, tick).session
            previous = expected
            expected = self.commit(resumed_next, target, generation=previous.generation,
                                   digest=previous.digest)
            before = target.read_bytes()
            with self.assertRaises(es.StaleGenerationError):
                self.commit(resumed_next, target, generation=previous.generation,
                            digest=previous.digest)
            self.assertEqual(target.read_bytes(), before)
        loaded = es.load_session(target, transport=policy())
        self.assertEqual(cl.canonical_bytes(loaded.session.session),
                         cl.canonical_bytes(uninterrupted.session))
        self.assertEqual(loaded.generation, 8)


class ImportScopeTests(unittest.TestCase):
    FORBIDDEN_NAMES = (
        "eval", "exec", "compile", "__import__", "pickle", "marshal", "importlib",
        "random", "secrets", "time", "datetime", "socket", "urllib", "requests",
        "subprocess", "tempfile", "urandom", "popen", "environ",
        "set_int_max_str_digits", "get_int_max_str_digits",
    )
    ALLOWED_IMPORTS = {
        str(KERNEL): {"__future__", "contextlib", "dataclasses", "fcntl", "hashlib", "json",
                      "os", "pathlib", "stat", "chronicler"},
        str(DRIVER): {"__future__", "argparse", "json", "pathlib", "runpy", "sys",
                      "chronicler"},
    }

    def imported_names(self, path):
        parsed = ast.parse(Path(path).read_text(encoding="utf-8"))
        names = {node.module for node in ast.walk(parsed) if isinstance(node, ast.ImportFrom)}
        names |= {alias.name for node in ast.walk(parsed) if isinstance(node, ast.Import)
                  for alias in node.names}
        return names

    def chronicler_import_targets(self, path):
        """Exact ``from chronicler import X`` targets, for the mutual-lane ban."""
        parsed = ast.parse(Path(path).read_text(encoding="utf-8"))
        return {alias.name for node in ast.walk(parsed)
                if isinstance(node, ast.ImportFrom) and node.module == "chronicler"
                for alias in node.names} | {
            alias.name for node in ast.walk(parsed)
            if isinstance(node, ast.Import)
            for alias in node.names if alias.name.startswith("chronicler")}

    def used_identifiers(self, path):
        """Every identifier the file actually uses, so prose cannot satisfy a gate."""
        parsed = ast.parse(Path(path).read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
        return names | {node.attr for node in ast.walk(parsed)
                        if isinstance(node, ast.Attribute)}

    def test_only_the_allowed_standard_library_and_two_kernels_are_imported(self):
        for path, allowed in self.ALLOWED_IMPORTS.items():
            with self.subTest(path=Path(path).name):
                self.assertEqual(self.imported_names(path), allowed)
        for path in self.ALLOWED_IMPORTS:
            with self.subTest(path=Path(path).name):
                self.assertEqual(self.used_identifiers(path)
                                 & set(self.FORBIDDEN_NAMES), set())
        # Exactly the two reviewed kernels; never another new lane's module.
        self.assertEqual(self.chronicler_import_targets(KERNEL),
                         {"campaign_logistics", "memome_experiment"})
        self.assertEqual(self.chronicler_import_targets(DRIVER), {"experiment_sessions"})
        kernel_source = Path(KERNEL).read_text(encoding="utf-8")
        for driver_reference in ("scripts/experiment_session", "import experiment_session",
                                 "campaign_logistics_demo", "memome_demo"):
            with self.subTest(reference=driver_reference):
                self.assertNotIn(driver_reference, kernel_source)

    def test_import_has_no_side_effects_and_leaves_the_global_rng_untouched(self):
        probe = (
            "import json, os, random\n"
            "before = random.getstate()\n"
            "listing = sorted(os.listdir('.'))\n"
            "from chronicler import experiment_sessions as es\n"
            "policy = es.documented_transport_policy()\n"
            "assert random.getstate() == before\n"
            "assert sorted(os.listdir('.')) == listing\n"
            "print(json.dumps({'version': es.ENVELOPE_VERSION,\n"
            "                  'limit': es.MAX_TRANSPORT_INT_BITS,\n"
            "                  'policy': policy.max_int_bits}))\n")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-c", probe], cwd=directory,
                                    env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
                                    capture_output=True, check=True)
            self.assertEqual(sorted(os.listdir(directory)), [])
        payload = json.loads(result.stdout)
        self.assertEqual(payload, {"version": es.ENVELOPE_VERSION,
                                   "limit": es.MAX_TRANSPORT_INT_BITS,
                                   "policy": 4096})
        isolation = subprocess.run(
            [sys.executable, "-c",
             "import random, sys\n"
             "before = random.getstate()\n"
             "import chronicler.experiment_sessions\n"
             "assert random.getstate() == before\n"
             "assert not any(n.startswith(('numpy', 'scipy', 'chronicler_agents',"
             " 'chronicler.models', 'chronicler.simulation', 'chronicler.main',"
             " 'pydantic')) for n in sys.modules), sorted(sys.modules)\n"
             "print('clean')\n"],
            env=dict(os.environ, PYTHONPATH=str(ROOT / "src")), capture_output=True,
            check=True)
        self.assertEqual(isolation.stdout.strip(), b"clean")

    def test_baseline_package_and_registry_identities_are_unchanged(self):
        package_init = (ROOT / "src" / "chronicler" / "__init__.py").read_text(encoding="utf-8")
        self.assertNotIn("experiment_sessions", package_init)
        self.assertNotIn("experiment_session", (ROOT / "pyproject.toml").read_text(
            encoding="utf-8"))
        # Exact AST import targets, not a prose prefix search.
        driver_imports = self.imported_names(DRIVER)
        self.assertEqual(driver_imports, {"__future__", "argparse", "json", "pathlib",
                                          "runpy", "sys", "chronicler"})
        self.assertNotIn("chronicler.experiment_session", driver_imports)


if __name__ == "__main__":
    unittest.main()