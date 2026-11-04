"""Detached first-step care capture; caller owns dispatch, retention and publication.

No World attachment, runtime import, implicit I/O or mechanics qualification.
Recording-off callers keep the existing practice_observer=None dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from chronicler.health_care import (
    get_health_care_policy, health_care_active, health_care_on,
)
from chronicler.health_care_observation_codec import (
    BYTE_CAP, ROW_CAP, CareFrameError, CareFrameView, ControlsBits, EpisodeBits,
    FrameExpected, NumericSummaryBits, PostJoinBits, RegionalSummaryBits,
    SnapshotBits, decode_care_frame, finalize_care_frame,
)

TURNS = 32
REGIONS = 8
# Closed diagnostic stage numbers, independent of the native stage bitmap.
ENTRY, CONFIGURE, DELEGATE, EXPORT, COPY, FINALIZE, RETAIN, STATUS = range(8)


def _need(condition, code=4):
    if not condition:
        raise CareFrameError(code)


def _failure_code(error, fallback):
    code = getattr(error, 'code', None) if type(error) is CareFrameError else None
    return code if type(code) is int and 1 <= code <= 11 else fallback


def _int(value, bits, *, signed=False):
    _need(type(value) is int)
    low = -(1 << (bits - 1)) if signed else 0
    high = 1 << (bits - 1) if signed else 1 << bits
    _need(low <= value < high)
    return value


def _boolean(value):
    _need(type(value) is bool)
    return value


def _bits(value):
    # No float(value), numeric equality elision, decimal or arithmetic copy.
    _need(type(value) is float)
    return struct.unpack('<Q', struct.pack('<d', value))[0]


def _control(value, low, high):
    bits = _bits(value)
    _need(math.isfinite(value) and low <= value <= high)
    return bits


def _rows(value, cap=ROW_CAP):
    _need(type(value) is list)
    _need(len(value) <= cap, 1)
    return value


def copy_care_snapshot(world) -> SnapshotBits:
    """Copy current actual primitives, preserving source episode order and bits.

    Missing/disabled health has no invented controls. A nonhybrid enabled state
    can be copied with active=False, but cannot satisfy this pilot's admission.
    """
    enabled, active = health_care_on(world), health_care_active(world)
    _need(enabled)
    state = world.health_care
    policy = get_health_care_policy(state)
    controls = ControlsBits(
        _control(state.injury_rate, 0.0, 0.25),
        _control(state.impairment, 0.0, 1.0),
        _control(state.care_fraction, 0.0, 1.0),
        _control(state.recovery_work, 1.0, 10.0),
        enabled, active, _boolean(state.care_enabled),
        0 if policy == 'spouse' else 1,
        _int(state.last_tick_turn, 64, signed=True),
    )
    # Bound before allocating; do not retain episodes or the mutable list.
    episodes = _rows(state.episodes)
    copied = tuple(EpisodeBits(_int(row.agent_id, 32),
        _int(row.onset_turn, 64, signed=True), _bits(row.remaining),
        _int(row.origin_region, 16)) for row in episodes)
    return SnapshotBits(controls, copied)


def _metrics(row):
    _need(type(row) is dict)
    return (_int(row['episodes'], 32), _int(row['new_injuries'], 32),
        _int(row['recoveries'], 32), _int(row['care_recipients'], 32),
        _bits(row['impaired_work']), _bits(row['care_work']),
        _bits(row['recovery_progress']), _bits(row['cared_recovery_progress']))


def copy_care_post(world, entry_turn: int, *, regions: int = REGIONS) -> PostJoinBits:
    """Read actual post summary; never sum, sort or call snapshot_summary."""
    _int(entry_turn, 32)
    _int(regions, 16)
    _need(regions <= ROW_CAP, 1)
    state = world.health_care
    _need(state._prepared is None, 7)
    snapshot = copy_care_snapshot(world)
    summary = state.summary
    _need(type(summary) is dict)
    turn = _int(summary['source_turn'], 64, signed=True)
    _need(turn == snapshot.controls.last_tick_turn == entry_turn, 8)
    totals = NumericSummaryBits(turn, _int(summary['censored_episodes'], 32),
                                *_metrics(summary))
    rows = _rows(summary['regions'])
    _need(len(rows) == regions)
    copied = []
    for index, row in enumerate(rows):
        _need(type(row) is dict)
        region = _int(row['region'], 16)
        _need(region == index)
        copied.append(RegionalSummaryBits(region, *_metrics(row)))
    return PostJoinBits(snapshot, totals, tuple(copied))


@dataclass(frozen=True, slots=True)
class CaptureRegistration:
    """Caller-owned immutable digest and fixed pilot arm; no file loading."""
    manifest_sha256: bytes
    seed: int
    policy: str

    def __post_init__(self):
        _need(type(self.manifest_sha256) is bytes and len(self.manifest_sha256) == 32)
        _need(type(self.seed) is int and self.seed in (2000, 2001))
        _need(type(self.policy) is str and self.policy in ('spouse', 'retained_kin'))


@dataclass(frozen=True, slots=True)
class CapturedCareFrame:
    """One validated binary payload; structural completeness is not durability.

    sink(frame) must return exact True only after caller-owned bounded admission
    and durable exclusive retention. False means owner refusal (code 10). A
    raised Exception means failed retention. No publication is performed here.
    """
    expected: FrameExpected
    data: bytes
    structural_complete: bool


class CareCaptureAdapter:
    """Exactly one ordinary delegate, then one post-success saved-prefix getter.

    Diagnostic Exceptions close evidence and preserve the ordinary result.
    BaseException interruptions propagate with no replay. The first numeric
    fault is sticky; status never includes arbitrary exception representations.
    """
    __slots__ = ('_delegate', '_sink', '_registration', '_sim', '_bridge',
        '_previous', '_configured', 'first_reason', 'first_stage',
        'first_entry_turn', 'first_exit_turn', 'complete_frames',
        'retained_frames', 'ordinary_returns', 'ordinary_failure_code',
        'ordinary_failure_entry_turn')

    def __init__(self, delegate, sink, registration: CaptureRegistration):
        _need(callable(delegate) and callable(sink))
        _need(type(registration) is CaptureRegistration)
        # Revalidate even an object.__setattr__-mutated frozen registration.
        registration.__post_init__()
        self._registration = CaptureRegistration(registration.manifest_sha256,
                                                 registration.seed, registration.policy)
        self._delegate, self._sink = delegate, sink
        self._sim = self._bridge = self._previous = None
        self._configured = False
        self.first_reason = self.first_stage = 0
        self.first_entry_turn = self.first_exit_turn = None
        self.complete_frames = self.retained_frames = self.ordinary_returns = 0
        self.ordinary_failure_code = 0
        self.ordinary_failure_entry_turn = None

    @property
    def closed(self):
        return self.first_reason != 0

    def _fault(self, reason, stage, entry, completed=None):
        # Only pre-existing scalar slots are written, including on ordinary
        # failure. No callback, traceback formatting or fresh fault allocation.
        if not self.closed:
            self.first_reason, self.first_stage = reason, stage
            self.first_entry_turn, self.first_exit_turn = entry, completed

    def _admit_entry(self, world, kwargs, entry):
        _need(entry == self.complete_frames and entry < TURNS, 8)
        _need(type(world.seed) is int and world.seed == self._registration.seed, 5)
        _need(type(world.regions) is list and len(world.regions) == REGIONS, 5)
        snapshot = copy_care_snapshot(world)
        controls = snapshot.controls
        _need(controls.enabled and controls.active and controls.care_enabled, 5)
        policy = 0 if self._registration.policy == 'spouse' else 1
        _need(controls.policy == policy, 5)
        # The fixed registered pilot controls, compared by exact primitive bits.
        _need((controls.injury_rate_b64, controls.impairment_b64,
               controls.care_fraction_b64, controls.recovery_work_b64) ==
              (_bits(0.01), _bits(0.5), _bits(0.2), _bits(2.0)), 5)
        _need(controls.last_tick_turn < entry, 8)
        _need(kwargs.get('ecology_runtime') is None and kwargs.get('politics_runtime') is None, 5)
        bridge = kwargs['agent_bridge']
        sim = bridge._sim
        if self.complete_frames == 0:
            _need(entry == 0 and self._previous is None, 11)
        else:
            _need(type(self._previous) is CareFrameView, 11)
            prior_expected = FrameExpected(self._registration.manifest_sha256, 0,
                entry - 1, entry, self.complete_frames - 1, policy, REGIONS)
            prior = decode_care_frame(self._previous.data, expected=prior_expected,
                                      previous=self._previous.previous)
            _need(type(prior) is CareFrameView and snapshot == prior.post.snapshot, 11)
            self._previous = prior
            _need(bridge is self._bridge and sim is self._sim, 5)
        return entry, snapshot, bridge, sim

    def run_turn_result(self, world, *args, **kwargs):
        entry = initial = expected = None
        stage = ENTRY
        # All pending primitives are local to this attempt, never attached to
        # World/state/runtime. A closed chain performs no more diagnostic reads.
        if not self.closed:
            diagnostic_done = False
            try:
                entry = _int(world.turn, 32)
                entry, incoming, bridge, sim = self._admit_entry(world, kwargs, entry)
                initial = incoming if self.complete_frames == 0 else None
                expected = FrameExpected(self._registration.manifest_sha256, 0,
                    entry, entry + 1, self.complete_frames,
                    0 if self._registration.policy == 'spouse' else 1, REGIONS)
                if not self._configured:
                    stage = CONFIGURE
                    self._configured = True  # one attempt, never repair/retry
                    self._bridge, self._sim = bridge, sim
                    _need(sim.configure_health_care_observation(0,
                        self._registration.manifest_sha256, turns=TURNS) is True, 7)
                diagnostic_done = True
            except Exception as error:
                self._fault(_failure_code(error, 4), stage, entry)
            finally:
                if not diagnostic_done:
                    self._fault(4, stage, entry)
        # No diagnostic callback is part of the ordinary exception boundary.
        ordinary_done = False
        try:
            result = self._delegate(world, *args, **kwargs)
            ordinary_done = True
        finally:
            if not ordinary_done:
                if self.ordinary_failure_code == 0:
                    self.ordinary_failure_code = 9
                    self.ordinary_failure_entry_turn = entry
                self._fault(9, DELEGATE, entry)
        # Even caller-owned status corruption/allocation failure belongs to the
        # diagnostic boundary, never to the successfully completed delegate.
        status_done = False
        try:
            _need(type(self.ordinary_returns) is int and 0 <= self.ordinary_returns <= TURNS + 1)
            self.ordinary_returns = min(TURNS + 1, self.ordinary_returns + 1)
            status_done = True
        except Exception:
            self._fault(4, STATUS, entry)
            return result
        finally:
            if not status_done:
                self._fault(4, STATUS, entry)
        if self.closed:
            return result
        stage = EXPORT
        diagnostic_done = False
        completed = None
        try:
            completed = _int(world.turn, 32)
            _need(completed == expected.exit_turn, 8)
            observation = result.observation
            _need(_int(observation.source_turn, 32) == entry and
                  _int(observation.completed_turn, 32) == completed, 8)
            # Exactly one getter immediately after success/turn identity checks.
            prefix = self._sim.get_health_care_observation()
            stage = COPY
            post = copy_care_post(world, entry)
            stage = FINALIZE
            data = finalize_care_frame(prefix, expected=expected, initial=initial,
                                       post=post, previous=self._previous)
            _need(type(data) is bytes and len(data) <= BYTE_CAP, 7)
            view = decode_care_frame(data, expected=expected, previous=self._previous)
            if not view.structural_complete:
                self._fault(view.header.failure, FINALIZE, entry, completed)
            frame = CapturedCareFrame(expected, data, view.structural_complete)
            stage = RETAIN
            admitted = self._sink(frame)
            _need(type(admitted) is bool)
            _need(admitted, 10)
            self.retained_frames += 1
            if view.structural_complete:
                self._previous = view
                self.complete_frames += 1
            diagnostic_done = True
        except Exception as error:
            self._fault(_failure_code(error, 10 if stage == RETAIN else 4),
                        stage, entry, completed)
        finally:
            if not diagnostic_done:
                self._fault(4, stage, entry, completed)
        return result
