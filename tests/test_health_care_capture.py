"""Owned model/primitive fakes only; no World, native, ordinary output or I/O."""
import ast
from dataclasses import replace
import hashlib
import inspect
import struct
from types import SimpleNamespace as NS
from unittest import mock

import pytest

from chronicler import health_care_capture as capture
from chronicler.health_care_state import HealthCareState, InjuryEpisode
from chronicler.health_care_observation_codec import (
    BYTE_CAP, CareFaultView, CareFrameView, decode_care_frame,
)

MANIFEST = b'm' * 32


def bits(value):
    return struct.unpack('<Q', struct.pack('<d', value))[0]


def f64(raw):
    return struct.unpack('<d', struct.pack('<Q', raw))[0]


def b32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def summary(turn, *, episodes=0):
    # Totals deliberately differ from regional sums: copy must not reconstruct.
    result = dict(source_turn=turn, censored_episodes=3, episodes=episodes,
        new_injuries=0, recoveries=7, care_recipients=5,
        impaired_work=42.25, care_work=-0.0, recovery_progress=19.5,
        cared_recovery_progress=f64(0x7ff8000000000042))
    result['regions'] = [dict(region=i, episodes=i, new_injuries=0, recoveries=0,
        care_recipients=0, impaired_work=float(i), care_work=0.0,
        recovery_progress=0.0, cared_recovery_progress=0.0) for i in range(8)]
    return result


def prefix(turn=0, *, policy=0, patients=(), failure=0, manifest=MANIFEST):
    """Independent empty-slot native layout; not a mechanics-valid producer."""
    body = bytearray(struct.pack('<II', b32(.5), b32(.2)))
    for aid in patients:
        body.extend(struct.pack('<H', 0) if aid == 0 else struct.pack('<HI', 65535, aid))
    body.extend(bytes(24 * 8))  # prepare regional result copies
    body.extend(struct.pack('<IIIB', 0, b32(1.), b32(1.), False) * 8)
    for i in range(8):
        body.extend(struct.pack('<HIIIIB', i, 0, 0, 0, 0, False))
    body.extend(bytes(8 + 12 * 8))  # coverage, wealth regional operands
    body.extend(struct.pack('<IIH', turn, b32(.01), 0))
    for i in range(8):
        body.extend(struct.pack('<HQQI', i, 0, 0, 0))
    head = bytearray(256)
    struct.pack_into('<8sHHIIIBBH', head, 0, b'CAREOBS1', 1, 256,
                     4 if failure else 0, turn, 256 + len(body), 15, policy, failure)
    counts = (0, 8, len(patients), 0, 0, 0, 0, 0, 0, 8, 0, 0, 8, 0, 0, 0)
    struct.pack_into('<16I', head, 28, *counts)
    head[92:124] = manifest
    head[196:200] = bytes((1, 1, 1, 1))
    struct.pack_into('<I', head, 200, turn)
    return bytes(head + body)


class Sim:
    def __init__(self, events):
        self.events = events
        self.prefix = None
        self.configure_answer = True
        self.configure_error = self.export_error = None

    def configure_health_care_observation(self, *args, **kwargs):
        self.events.append(('configure', args, kwargs))
        if self.configure_error is not None:
            raise self.configure_error
        return self.configure_answer

    def get_health_care_observation(self):
        self.events.append(('get',))
        if self.export_error is not None:
            raise self.export_error
        return self.prefix


class Rig:
    def __init__(self, *, policy='spouse', episodes=(), seed=2000):
        self.events, self.frames = [], []
        self.state = HealthCareState(episodes=list(episodes), care_policy=policy)
        self.world = NS(turn=0, seed=seed, agent_mode='hybrid', regions=[object() for _ in range(8)],
                        health_care=self.state)
        self.sim = Sim(self.events)
        self.bridge = NS(_sim=self.sim)
        self.kwargs = dict(agent_bridge=self.bridge, ecology_runtime=None, politics_runtime=None)
        self.results, self.delegate_calls = [], []
        self.effect = self.delegate_error = self.sink_error = None
        self.sink_answer = True
        self.adapter = capture.CareCaptureAdapter(self.delegate, self.sink,
                            capture.CaptureRegistration(MANIFEST, seed, policy))

    def delegate(self, world, *args, **kwargs):
        self.events.append(('delegate',))
        self.delegate_calls.append((world, args, kwargs))
        if self.delegate_error is not None:
            raise self.delegate_error
        entry = world.turn
        patients = tuple(row.agent_id for row in self.state.episodes)
        self.sim.prefix = prefix(entry, policy=0 if capture.get_health_care_policy(self.state) == 'spouse' else 1,
                                 patients=patients)
        if self.effect is not None:
            self.effect(self)
        self.state._prepared = None
        self.state.last_tick_turn = entry
        self.state.summary = summary(entry, episodes=len(self.state.episodes))
        world.turn = entry + 1
        result = NS(observation=NS(source_turn=entry, completed_turn=entry + 1),
                    phase10=object(), chronicle_text=object())
        self.results.append(result)
        return result

    def sink(self, frame):
        self.events.append(('retain',))
        self.frames.append(frame)
        if self.sink_error is not None:
            raise self.sink_error
        return self.sink_answer

    def run(self, *args, **kwargs):
        return self.adapter.run_turn_result(self.world, *args, **(self.kwargs | kwargs))

    def decoded(self, at=0):
        previous = None
        for frame in self.frames[:at + 1]:
            previous = decode_care_frame(frame.data, expected=frame.expected, previous=previous)
        return previous


def episode(aid=7, *, remaining=2.0):
    return InjuryEpisode.model_construct(agent_id=aid, onset_turn=-4,
        remaining=remaining, origin_region=3)


def test_capture_constructor_is_detached_and_performs_no_diagnostic_dispatch():
    rig = Rig()
    assert rig.events == [] and not rig.adapter.closed
    assert rig.adapter.complete_frames == rig.adapter.retained_frames == 0
    assert set(vars(rig.world)) == {'turn', 'seed', 'agent_mode', 'regions', 'health_care'}
    assert set(vars(rig.bridge)) == {'_sim'}


def test_capture_registration_has_closed_types_and_pilot_domains():
    for values in ((bytearray(MANIFEST), 2000, 'spouse'), (b'x', 2000, 'spouse'),
                   (MANIFEST, True, 'spouse'), (MANIFEST, 42, 'spouse'),
                   (MANIFEST, 2000, 'kin'), (MANIFEST, 2000, 0)):
        with pytest.raises(ValueError):
            capture.CaptureRegistration(*values)


def test_capture_one_delegate_forwards_original_argument_objects_and_result_identity():
    rig = Rig()
    positional, action, pending = object(), object(), []
    answer = rig.run(positional, action_selector=action, pending_injections=pending)
    world, args, kwargs = rig.delegate_calls[0]
    assert world is rig.world and args == (positional,) and args[0] is positional
    assert kwargs['action_selector'] is action and kwargs['pending_injections'] is pending
    assert kwargs['agent_bridge'] is rig.bridge and '_practice_trace' not in kwargs
    assert answer is rig.results[0]
    assert answer.phase10 is rig.results[0].phase10 and len(rig.delegate_calls) == 1


def test_capture_configures_once_before_delegate_then_gets_once_before_post_copy_and_retention():
    rig = Rig()
    original = capture.copy_care_post
    def copy(*args, **kwargs):
        rig.events.append(('copy',))
        return original(*args, **kwargs)
    with mock.patch.object(capture, 'copy_care_post', side_effect=copy):
        rig.run()
        rig.run()
    assert [event[0] for event in rig.events] == ['configure', 'delegate', 'get', 'copy', 'retain',
                                                 'delegate', 'get', 'copy', 'retain']
    assert rig.events[0] == ('configure', (0, MANIFEST), {'turns': 32})
    assert rig.adapter.complete_frames == 2 and not rig.adapter.closed


def test_capture_initial_copy_precedes_in_place_episode_mutation_and_replacement():
    old = episode(19)
    rig = Rig(episodes=[old, episode(7)])
    def mutate(rig):
        old.remaining = .75
        rig.state.episodes = [rig.state.episodes[1], old]
    rig.effect = mutate
    rig.run()
    view = rig.decoded()
    assert [row.agent_id for row in view.initial.episodes] == [19, 7]
    assert view.initial.episodes[0].remaining_b64 == 0x4000000000000000
    assert [row.agent_id for row in view.post.snapshot.episodes] == [7, 19]
    assert view.post.snapshot.episodes[1].remaining_b64 == 0x3fe8000000000000
    old.remaining = 9.0
    assert rig.decoded().post.snapshot.episodes[1].remaining_b64 == 0x3fe8000000000000


def test_capture_actual_summary_fields_are_copied_without_reconstructing_totals():
    rig = Rig()
    rig.run()
    view = rig.decoded()
    assert view.post.summary.impaired_work_b64 == 0x4045200000000000
    assert view.post.summary.care_work_b64 == 0x8000000000000000
    assert view.post.summary.cared_recovery_progress_b64 == 0x7ff8000000000042
    assert [row.region for row in view.post.regions] == list(range(8))
    assert view.post.summary.recoveries == 7
    assert [row.recoveries for row in view.post.regions] == [0] * 8
    assert view.structural_complete  # synthetic structure is not a mechanics verdict


def test_capture_copy_retains_raw_zero_id_signed_zero_and_nan_payloads_in_episode_order():
    rig = Rig(episodes=[episode(19), episode(0, remaining=-0.0),
                        episode(7, remaining=f64(0x7ff8000000000123))])
    copied = capture.copy_care_snapshot(rig.world)
    assert tuple(row.agent_id for row in copied.episodes) == (19, 0, 7)
    assert tuple(row.remaining_b64 for row in copied.episodes) == (
        0x4000000000000000, 0x8000000000000000, 0x7ff8000000000123)
    rig.run()
    assert rig.decoded().initial == copied


def test_capture_missing_legacy_policy_uses_actual_spouse_fallback():
    rig = Rig()
    rig.state.__dict__.pop('care_policy')
    rig.state.__pydantic_fields_set__.discard('care_policy')
    assert capture.copy_care_snapshot(rig.world).controls.policy == 0
    rig.run()
    assert rig.decoded().header.policy == 0 and not rig.adapter.closed


def test_capture_retained_kin_arm_is_bound_without_changing_dispatch_or_controls():
    for seed in (2000, 2001):
        rig = Rig(policy='retained_kin', seed=seed)
        rig.run()
        assert rig.decoded().initial.controls.policy == rig.decoded().header.policy == 1
        assert rig.delegate_calls[0][2] == rig.kwargs
        assert rig.state.care_policy == 'retained_kin' and rig.world.seed == seed


def test_capture_enabled_active_and_care_enabled_are_distinct_actual_predicates():
    rig = Rig()
    rig.state.care_enabled = False
    snapshot = capture.copy_care_snapshot(rig.world)
    assert snapshot.controls.enabled and snapshot.controls.active and not snapshot.controls.care_enabled
    rig.world.agent_mode = 'off'
    snapshot = capture.copy_care_snapshot(rig.world)
    assert snapshot.controls.enabled and not snapshot.controls.active
    rig.world.health_care = None
    with pytest.raises(ValueError):
        capture.copy_care_snapshot(rig.world)


def test_capture_setup_mismatch_still_delegates_once_without_configure_getter_or_sink():
    for change in (lambda r: setattr(r.world, 'turn', 2),
                   lambda r: setattr(r.world, 'seed', 2001),
                   lambda r: setattr(r.world, 'agent_mode', 'off'),
                   lambda r: r.world.regions.pop(),
                   lambda r: setattr(r.state, 'care_enabled', False),
                   lambda r: setattr(r.state, 'injury_rate', .02),
                   lambda r: setattr(r.state, 'care_policy', 'retained_kin')):
        rig = Rig()
        change(rig)
        answer = rig.run()
        assert answer is rig.results[0] and len(rig.delegate_calls) == 1
        assert [event[0] for event in rig.events] == ['delegate']
        assert rig.adapter.closed and rig.frames == []


def test_capture_strict_primitive_copy_refuses_narrowing_missing_fields_and_invalid_controls():
    for name, value in (('injury_rate', 0), ('impairment', True), ('care_fraction', float('nan')),
                        ('recovery_work', 11.0), ('care_enabled', 1), ('last_tick_turn', True)):
        rig = Rig()
        setattr(rig.state, name, value)
        with pytest.raises(ValueError):
            capture.copy_care_snapshot(rig.world)
    rig = Rig(episodes=[episode(1 << 32)])
    with pytest.raises(ValueError):
        capture.copy_care_snapshot(rig.world)
    rig = Rig()
    rig.state.__dict__.pop('impairment')
    with pytest.raises(AttributeError):
        capture.copy_care_snapshot(rig.world)


def test_capture_row_bound_is_checked_before_iteration_or_copy_allocation():
    rig = Rig()
    rig.state.episodes = [object()] * 4097
    with pytest.raises(ValueError) as caught:
        capture.copy_care_snapshot(rig.world)
    assert caught.value.code == 1


def test_capture_initial_and_post_snapshots_have_independent_immutable_primitives():
    rig = Rig(episodes=[episode()])
    first = capture.copy_care_snapshot(rig.world)
    rig.state.episodes[0].onset_turn = 91
    rig.state.episodes.clear()
    assert first.episodes[0].onset_turn == -4 and len(first.episodes) == 1
    with pytest.raises((AttributeError, TypeError)):
        first.controls.last_tick_turn = 4


def test_capture_configure_false_or_exception_closes_without_retry_and_preserves_returns():
    for answer, error in ((False, None), (1, None), (True, MemoryError()), (True, RuntimeError('private'))):
        rig = Rig()
        rig.sim.configure_answer, rig.sim.configure_error = answer, error
        rig.run()
        first = (rig.adapter.first_reason, rig.adapter.first_stage)
        rig.run()
        assert len(rig.delegate_calls) == 2 and rig.adapter.closed
        assert [event[0] for event in rig.events] == ['configure', 'delegate', 'delegate']
        assert (rig.adapter.first_reason, rig.adapter.first_stage) == first
        assert rig.frames == []


def test_capture_ordinary_exception_identity_and_traceback_never_trigger_diagnostic_callbacks():
    rig = Rig()
    error = RuntimeError('ordinary sentinel')
    rig.delegate_error = error
    with mock.patch.object(capture, 'copy_care_post', side_effect=AssertionError('copy')) as copy, \
         mock.patch.object(capture, 'finalize_care_frame', side_effect=AssertionError('finalize')) as finalize:
        with pytest.raises(RuntimeError) as caught:
            rig.run()
    assert caught.value is error and copy.call_count == finalize.call_count == 0
    frames = []
    tb = caught.value.__traceback__
    while tb is not None:
        frames.append(tb.tb_frame.f_code.co_name)
        tb = tb.tb_next
    assert frames[-1] == 'delegate'
    assert [event[0] for event in rig.events] == ['configure', 'delegate']
    assert rig.adapter.first_reason == 9 and rig.adapter.first_stage == capture.DELEGATE
    assert rig.adapter.first_entry_turn == 0 and rig.adapter.first_exit_turn is None


def test_capture_ordinary_baseexception_propagates_without_blanket_catch_or_replay():
    rig = Rig()
    error = KeyboardInterrupt()
    rig.delegate_error = error
    with pytest.raises(KeyboardInterrupt) as caught:
        rig.run()
    assert caught.value is error and rig.adapter.first_reason == 9
    assert len(rig.delegate_calls) == 1 and rig.frames == []
    assert [event[0] for event in rig.events] == ['configure', 'delegate']


def test_capture_export_exception_is_diagnostic_only_and_sticky():
    rig = Rig()
    rig.sim.export_error = MemoryError()
    first = rig.run()
    assert first is rig.results[0] and rig.adapter.first_stage == capture.EXPORT
    reason = rig.adapter.first_reason
    rig.sim.export_error = None
    second = rig.run()
    assert second is rig.results[1] and rig.adapter.first_reason == reason
    assert [event[0] for event in rig.events] == ['configure', 'delegate', 'get', 'delegate']


def test_capture_post_copy_and_finalize_exceptions_preserve_same_ordinary_result():
    for name, stage in (('copy_care_post', capture.COPY), ('finalize_care_frame', capture.FINALIZE)):
        rig = Rig()
        with mock.patch.object(capture, name, side_effect=MemoryError()):
            answer = rig.run()
        assert answer is rig.results[0] and rig.adapter.first_stage == stage
        assert rig.adapter.closed and rig.frames == []
        assert [event[0] for event in rig.events] == ['configure', 'delegate', 'get']


def test_capture_no_returned_bytes_is_explicit_unavailable_evidence():
    rig = Rig()
    with mock.patch.object(capture, 'finalize_care_frame', return_value=None):
        answer = rig.run()
    assert answer is rig.results[0] and rig.adapter.first_reason == 7
    assert rig.frames == [] and rig.adapter.complete_frames == 0


def test_capture_missing_stale_and_overflow_prefixes_are_incomplete_final_faults():
    def incomplete(offset):
        value = bytearray(prefix())
        value[offset] = 7 if offset == 24 else 2
        return bytes(value)
    for factory, reason in ((lambda: None, 7), (lambda: prefix(3), 8),
                            (lambda: b'x' * (BYTE_CAP + 1), 2),
                            (lambda: incomplete(24), 7), (lambda: incomplete(196), 7)):
        rig = Rig()
        original = rig.sim.get_health_care_observation
        def get():
            original()
            return factory()
        rig.sim.get_health_care_observation = get
        answer = rig.run()
        assert answer is rig.results[0] and rig.adapter.first_reason == reason
        assert len(rig.frames) == 1 and not rig.frames[0].structural_complete
        assert isinstance(rig.decoded(), CareFaultView)
        assert rig.adapter.retained_frames == 1 and rig.adapter.complete_frames == 0


def test_capture_native_first_fault_retains_opaque_bytes_and_does_not_claim_python_joins():
    rig = Rig()
    raw = prefix(failure=6)
    rig.sim.get_health_care_observation = lambda: raw
    rig.run()
    view = rig.decoded()
    assert isinstance(view, CareFaultView) and rig.adapter.first_reason == 6
    assert view.opaque_body.tobytes() == raw[256:]
    assert view.header.stage & 48 == 0 and view.header.flags == 4
    assert view.header.body_sha256 == hashlib.sha256(raw[256:]).digest()
    assert view.header.encoded_length == len(view.data) <= BYTE_CAP


def test_capture_mismatched_native_manifest_never_becomes_a_complete_frame():
    rig = Rig()
    rig.sim.get_health_care_observation = lambda: prefix(manifest=b'x' * 32)
    rig.run()
    assert rig.adapter.first_reason == 5 and rig.adapter.complete_frames == 0
    assert not rig.frames[0].structural_complete
    assert rig.decoded().header.manifest_sha256 == b'x' * 32


def test_capture_later_entry_requires_the_actual_preceding_post_snapshot():
    rig = Rig(episodes=[episode()])
    rig.run()
    rig.state.episodes[0].remaining = 8.0
    answer = rig.run()
    assert answer is rig.results[1] and rig.adapter.first_reason == 11
    assert len(rig.frames) == 1
    assert [event[0] for event in rig.events].count('get') == 1


def test_capture_prior_chain_loss_or_bound_byte_corruption_closes_before_next_getter():
    for lose in (True, False):
        rig = Rig()
        rig.run()
        if lose:
            rig.adapter._previous = None
        else:
            previous = rig.adapter._previous
            rig.adapter._previous = replace(previous, data=previous.data[:-1] + b'\x01')
        answer = rig.run()
        assert answer is rig.results[1] and rig.adapter.closed and len(rig.frames) == 1
        assert [event[0] for event in rig.events].count('get') == 1


def test_capture_cached_predecessor_fields_cannot_override_its_actual_bound_bytes():
    rig = Rig()
    rig.run()
    prior = rig.adapter._previous
    rig.adapter._previous = replace(prior, post=replace(prior.post,
        snapshot=replace(prior.post.snapshot, controls=replace(prior.post.snapshot.controls,
            last_tick_turn=999))), frame_sha256=b'z' * 32,
        structural_complete=False)
    rig.run()
    assert not rig.adapter.closed and rig.adapter.complete_frames == 2
    assert rig.decoded(1).header.predecessor_sha256 == hashlib.sha256(rig.frames[0].data).digest()


def test_capture_full_32_turn_chain_keeps_all_predecessors_and_refuses_ordinal_32():
    rig = Rig()
    for _ in range(32):
        assert rig.run() is rig.results[-1]
    assert not rig.adapter.closed and rig.adapter.complete_frames == 32
    view = rig.decoded(31)
    assert view.header.ordinal == 31
    depth = 0
    while view is not None:
        depth += 1
        view = view.previous
    assert depth == 32
    rig.run()
    assert rig.adapter.closed and len(rig.frames) == 32 and len(rig.delegate_calls) == 33
    assert [event[0] for event in rig.events].count('get') == 32
    assert [event[0] for event in rig.events].count('configure') == 1


def test_capture_turn_and_observation_mismatches_refuse_before_any_getter():
    for mode in ('world', 'source', 'completed', 'bool'):
        rig = Rig()
        real = rig.adapter._delegate
        def delegate(*args, **kwargs):
            answer = real(*args, **kwargs)
            if mode == 'world':
                rig.world.turn = 3
            elif mode == 'source':
                answer.observation.source_turn = 1
            elif mode == 'completed':
                answer.observation.completed_turn = 2
            else:
                answer.observation.source_turn = False
            return answer
        rig.adapter._delegate = delegate
        assert rig.run() is rig.results[0]
        assert rig.adapter.closed and rig.frames == []
        assert [event[0] for event in rig.events] == ['configure', 'delegate']


def test_capture_post_requires_consumed_preparation_current_summary_and_exact_region_order():
    for mode in ('prepared', 'summaryturn', 'lasttick', 'reverse', 'duplicate', 'missing', 'metric'):
        rig = Rig()
        rig.delegate(rig.world, **rig.kwargs)
        if mode == 'prepared':
            rig.state._prepared = []
        elif mode == 'summaryturn':
            rig.state.summary['source_turn'] = -1
        elif mode == 'lasttick':
            rig.state.last_tick_turn = -1
        elif mode == 'reverse':
            rig.state.summary['regions'].reverse()
        elif mode == 'duplicate':
            rig.state.summary['regions'][1]['region'] = 0
        elif mode == 'missing':
            rig.state.summary['regions'].pop()
        else:
            rig.state.summary['care_work'] = 0
        with pytest.raises((ValueError, KeyError)):
            capture.copy_care_post(rig.world, 0)


def test_capture_native_runtime_inventory_drift_closes_without_replacing_bridge():
    rig = Rig()
    rig.run()
    original = rig.bridge._sim
    rig.bridge._sim = Sim(rig.events)
    assert rig.run() is rig.results[1]
    assert rig.adapter.closed and rig.adapter._sim is original and len(rig.frames) == 1
    rig = Rig()
    assert rig.run(ecology_runtime=object()) is rig.results[0]
    assert rig.adapter.closed and [event[0] for event in rig.events] == ['delegate']


def test_capture_sink_refusal_or_retention_exception_never_claims_durable_complete_evidence():
    for answer, error, reason in ((False, None, 10), (True, OSError('short write'), 10),
                                   (True, MemoryError(), 10), (1, None, 4)):
        rig = Rig()
        rig.sink_answer, rig.sink_error = answer, error
        assert rig.run() is rig.results[0]
        assert rig.adapter.first_reason == reason and rig.adapter.first_stage == capture.RETAIN
        assert rig.adapter.complete_frames == rig.adapter.retained_frames == 0
        assert rig.frames[0].structural_complete  # parseability alone is not retention
        rig.run()
        assert len(rig.frames) == 1 and len(rig.delegate_calls) == 2


def test_capture_native_first_fault_survives_a_later_sink_failure_without_rebranding():
    rig = Rig()
    rig.sim.get_health_care_observation = lambda: prefix(failure=6)
    rig.sink_error = OSError('fsync sentinel')
    rig.run()
    assert rig.adapter.first_reason == 6 and rig.adapter.first_stage == capture.FINALIZE
    assert rig.adapter.retained_frames == 0 and not rig.frames[0].structural_complete


def test_capture_diagnostic_baseexception_closes_and_propagates_without_replaying_successful_physics():
    rig = Rig()
    interrupt = KeyboardInterrupt()
    rig.sim.export_error = interrupt
    with pytest.raises(KeyboardInterrupt) as caught:
        rig.run()
    assert caught.value is interrupt and rig.adapter.closed
    assert rig.world.turn == 1 and len(rig.delegate_calls) == 1 and rig.frames == []


def test_capture_closed_chain_keeps_first_fault_and_skips_all_later_diagnostic_reads():
    rig = Rig()
    rig.sim.configure_answer = False
    rig.run()
    first = (rig.adapter.first_reason, rig.adapter.first_stage,
             rig.adapter.first_entry_turn, rig.adapter.first_exit_turn)
    rig.world = NS()  # No readable diagnostic primitives remain.
    returned = object()
    rig.adapter._delegate = lambda *args, **kwargs: returned
    assert rig.adapter.run_turn_result(rig.world) is returned
    assert (rig.adapter.first_reason, rig.adapter.first_stage,
            rig.adapter.first_entry_turn, rig.adapter.first_exit_turn) == first
    assert [event[0] for event in rig.events] == ['configure', 'delegate']


def test_capture_adapter_does_not_attach_fields_retain_phase10_or_publish():
    rig = Rig()
    world_fields, state_fields, bridge_fields = set(vars(rig.world)), set(vars(rig.state)), set(vars(rig.bridge))
    rig.run()
    assert set(vars(rig.world)) == world_fields and set(vars(rig.state)) == state_fields
    assert set(vars(rig.bridge)) == bridge_fields
    assert not any(getattr(rig.adapter, slot) is rig.results[0] or
                   getattr(rig.adapter, slot) is rig.results[0].phase10 for slot in rig.adapter.__slots__)
    assert set(rig.frames[0].__slots__) == {'expected', 'data', 'structural_complete'}


def test_capture_module_has_no_implicit_io_runtime_imports_rng_or_persistence_hooks():
    tree = ast.parse(inspect.getsource(capture))
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert set(modules) == {'__future__', 'dataclasses', 'chronicler.health_care',
                           'chronicler.health_care_observation_codec'}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {'open', 'WorldState', 'random', 'numpy', 'os', 'Path', 'pickle'}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {'prepare_health_work', 'finish_health_work', 'snapshot_summary',
                             'checkpoint_state', 'from_checkpoint_state', '__closure__', 'publish'}
    assert not any(isinstance(node, ast.ExceptHandler) and
                   isinstance(node.type, ast.Name) and node.type.id == 'BaseException'
                   for node in ast.walk(tree))


def test_capture_ordinary_failure_is_recorded_separately_without_erasing_prior_diagnostic_fault():
    rig = Rig()
    rig.world.seed = 2001
    error = LookupError('ordinary sentinel')
    rig.delegate_error = error
    with pytest.raises(LookupError) as caught:
        rig.run()
    assert caught.value is error
    assert rig.adapter.first_reason == 5 and rig.adapter.first_stage == capture.ENTRY
    assert rig.adapter.first_entry_turn == 0 and rig.adapter.first_exit_turn is None
    assert rig.adapter.ordinary_failure_code == 9 and rig.adapter.ordinary_failure_entry_turn == 0
    assert [event[0] for event in rig.events] == ['delegate']


def test_capture_status_faults_after_success_never_replace_the_ordinary_result():
    rig = Rig()
    rig.adapter.ordinary_returns = object()
    assert rig.run() is rig.results[0]
    assert rig.adapter.first_reason == 4 and rig.adapter.first_stage == capture.STATUS
    assert [event[0] for event in rig.events] == ['configure', 'delegate']
    rig = Rig()
    with mock.patch.object(capture, 'min', side_effect=MemoryError(), create=True):
        assert rig.run() is rig.results[0]
    assert rig.adapter.first_stage == capture.STATUS and rig.frames == []
    assert rig.world.turn == 1 and len(rig.delegate_calls) == 1


def test_capture_combined_native_and_python_join_cap_refuses_without_claiming_python_bits():
    rig = Rig(episodes=[episode(i) for i in range(1, 4097)])
    assert rig.run() is rig.results[0]
    assert rig.adapter.first_reason == 3 and rig.adapter.complete_frames == 0
    view = rig.decoded()
    assert isinstance(view, CareFaultView) and len(view.data) <= BYTE_CAP
    assert view.header.stage & 48 == 0 and view.header.counts[13:15] == (0, 0)
    assert view.opaque_body.tobytes() == rig.sim.prefix[256:]


def test_capture_status_keyboard_interrupt_closes_chain_after_one_successful_delegate():
    rig = Rig()
    interrupt = KeyboardInterrupt()
    with mock.patch.object(capture, 'min', side_effect=interrupt, create=True):
        with pytest.raises(KeyboardInterrupt) as caught:
            rig.run()
    assert caught.value is interrupt
    assert rig.world.turn == 1 and len(rig.delegate_calls) == len(rig.results) == 1
    assert rig.adapter.closed and rig.adapter.first_reason == 4
    assert rig.adapter.first_stage == capture.STATUS and rig.adapter.first_entry_turn == 0
    assert rig.adapter.first_exit_turn is None and rig.adapter.ordinary_failure_code == 0
    assert rig.adapter.ordinary_returns == 0
    assert rig.adapter.complete_frames == rig.adapter.retained_frames == 0
    assert rig.frames == []
    assert [event[0] for event in rig.events] == ['configure', 'delegate']


def test_capture_public_fault_codes_stay_exact_int_one_through_eleven_at_configure_and_sink():
    for code in (99, True, 0, 12, 'private', None, object()):
        rig = Rig()
        rig.sim.configure_error = capture.CareFrameError(code)
        assert rig.run() is rig.results[0]
        assert rig.adapter.closed and type(rig.adapter.first_reason) is int
        assert rig.adapter.first_reason == 4 and rig.adapter.first_stage == capture.CONFIGURE
        assert rig.frames == [] and len(rig.delegate_calls) == 1
        assert [event[0] for event in rig.events] == ['configure', 'delegate']
        rig = Rig()
        rig.sink_error = capture.CareFrameError(code)
        assert rig.run() is rig.results[0]
        assert rig.adapter.closed and type(rig.adapter.first_reason) is int
        assert rig.adapter.first_reason == 10 and rig.adapter.first_stage == capture.RETAIN
        assert rig.adapter.complete_frames == rig.adapter.retained_frames == 0
        assert len(rig.delegate_calls) == len(rig.frames) == 1
        assert [event[0] for event in rig.events] == ['configure', 'delegate', 'get', 'retain']


def test_capture_deleted_public_error_code_uses_configure_and_sink_fallbacks():
    for stage in ('configure', 'sink'):
        error = capture.CareFrameError(99)
        del error.code
        rig = Rig()
        if stage == 'configure':
            rig.sim.configure_error = error
        else:
            rig.sink_error = error
        assert rig.run() is rig.results[0]
        assert rig.world.turn == 1 and len(rig.delegate_calls) == len(rig.results) == 1
        assert rig.adapter.closed and type(rig.adapter.first_reason) is int
        assert rig.adapter.first_reason == (4 if stage == 'configure' else 10)
        assert rig.adapter.first_stage == (capture.CONFIGURE if stage == 'configure' else capture.RETAIN)
        assert rig.adapter.ordinary_failure_code == 0
        assert rig.adapter.complete_frames == rig.adapter.retained_frames == 0
        assert len(rig.frames) == (0 if stage == 'configure' else 1)
        assert [event[0] for event in rig.events] == (
            ['configure', 'delegate'] if stage == 'configure' else
            ['configure', 'delegate', 'get', 'retain'])
