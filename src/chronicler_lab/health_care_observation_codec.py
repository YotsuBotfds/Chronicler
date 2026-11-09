"""Pure bounded CAREOBS1 joining and structural decoding; no runtime hooks.

Structural COMPLETE records all required joins. It is not mechanics, RNG,
scientific or producer-truth qualification. Float fields remain raw unsigned bits.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
import hashlib
import struct

BYTE_CAP = 131072
ROW_CAP = 4096
REL_CAP = 32768
HEADER_BYTES = 256
ZERO_HASH = bytes(32)


class CareFrameError(ValueError):
    """A bounded diagnostic refusal, never arbitrary payload text."""
    def __init__(self, code: int, reason: str = "invalid care frame"):
        self.code = code
        super().__init__(reason)


def _need(condition, code=4, reason="invalid care primitive"):
    if not condition:
        raise CareFrameError(code, reason)


def _uint(value, bits):
    _need(type(value) is int and 0 <= value < (1 << bits))
    return value


def _i64(value):
    _need(type(value) is int and -(1 << 63) <= value < (1 << 63))
    return value


def _bool(value):
    _need(type(value) is bool)
    return value


def _tuple(value, kind=None, cap=ROW_CAP):
    _need(type(value) is tuple)
    _need(len(value) <= cap, 1, "care row bound")
    if kind is not None:
        _need(all(type(row) is kind for row in value))
    return value


@dataclass(frozen=True, slots=True)
class ControlsBits:
    injury_rate_b64: int
    impairment_b64: int
    care_fraction_b64: int
    recovery_work_b64: int
    enabled: bool
    active: bool
    care_enabled: bool
    policy: int
    last_tick_turn: int


@dataclass(frozen=True, slots=True)
class EpisodeBits:
    agent_id: int
    onset_turn: int
    remaining_b64: int
    origin_region: int


@dataclass(frozen=True, slots=True)
class SnapshotBits:
    controls: ControlsBits
    episodes: tuple[EpisodeBits, ...]


@dataclass(frozen=True, slots=True)
class NumericSummaryBits:
    source_turn: int
    censored_episodes: int
    episodes: int
    new_injuries: int
    recoveries: int
    care_recipients: int
    impaired_work_b64: int
    care_work_b64: int
    recovery_progress_b64: int
    cared_recovery_progress_b64: int


@dataclass(frozen=True, slots=True)
class RegionalSummaryBits:
    region: int
    episodes: int
    new_injuries: int
    recoveries: int
    care_recipients: int
    impaired_work_b64: int
    care_work_b64: int
    recovery_progress_b64: int
    cared_recovery_progress_b64: int


@dataclass(frozen=True, slots=True)
class PostJoinBits:
    snapshot: SnapshotBits
    summary: NumericSummaryBits
    regions: tuple[RegionalSummaryBits, ...]


@dataclass(frozen=True, slots=True)
class FrameExpected:
    manifest_sha256: bytes
    source_start_turn: int
    entry_turn: int
    exit_turn: int
    ordinal: int
    policy: int
    regions: int


@dataclass(frozen=True, slots=True)
class CareHeader:
    flags: int
    source_turn: int
    encoded_length: int
    stage: int
    policy: int
    failure: int
    counts: tuple[int, ...]
    manifest_sha256: bytes
    predecessor_sha256: bytes
    body_sha256: bytes
    entry_turn: int
    exit_turn: int
    calls: tuple[int, ...]
    ordinal: int


@dataclass(frozen=True, slots=True)
class ScopedBits:
    slot: int
    consumed_id: int
    loss_b32: int
    current_id: int
    region: int
    occupation: int
    flags: int
    reason: int
    numeric_mask: int
    numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class NativeFacts:
    impairment_b32: int
    care_fraction_b32: int
    inputs: tuple[int, ...]
    excluded: tuple[int, ...]
    urban: tuple[int, ...]
    ids: tuple[int, ...]
    ages: tuple[int, ...]
    regions: tuple[int, ...]
    settlements: tuple[int, ...]
    occupations: tuple[int, ...]
    trips: tuple[int, ...]
    rel_counts: tuple[int, ...]
    marriage_masks: tuple[int, ...]
    kin_masks: tuple[int, ...]
    alive: tuple[bool, ...]
    targets: tuple[int, ...]
    workers: tuple[tuple[int, int], ...]
    assignments: tuple[tuple[int, int, int, int], ...]
    preparation_regions: tuple[tuple[int, int, int, int], ...]
    economy_inputs: tuple[tuple[int, int, int, bool], ...]
    economy_outputs: tuple[tuple[int, tuple[int, ...], int, bool], ...]
    wealth_coverage: tuple[int, ...]
    scoped: tuple[ScopedBits, ...]
    wealth_regions: tuple[tuple[int, ...], ...]
    finish_turn: int
    rate_b32: int
    finish_ids: tuple[int, ...]
    finish_regions: tuple[int, ...]
    finish_alive: tuple[bool, ...]
    alive_results: tuple[tuple[int, int], ...]
    injuries: tuple[tuple[int, int, int], ...]
    regional_results: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True, slots=True)
class CareFrameView:
    data: bytes
    header: CareHeader
    native: NativeFacts
    initial: SnapshotBits | None
    post: PostJoinBits
    previous: CareFrameView | None
    frame_sha256: bytes
    # This name deliberately does not confer mechanics/producer qualification.
    structural_complete: bool = True


@dataclass(frozen=True, slots=True)
class CareFaultView:
    data: bytes
    header: CareHeader
    frame_sha256: bytes
    structural_complete: bool = False

    @property
    def opaque_body(self):
        return memoryview(self.data)[HEADER_BYTES:]


def _expected(value):
    _need(type(value) is FrameExpected)
    _need(type(value.manifest_sha256) is bytes and len(value.manifest_sha256) == 32)
    for number in (value.source_start_turn, value.entry_turn, value.exit_turn):
        _uint(number, 32)
    _uint(value.ordinal, 32)
    _need(value.ordinal < 32, 8, "care ordinal bound")
    _uint(value.policy, 8)
    _need(value.policy in (0, 1))
    _uint(value.regions, 32)
    _need(value.regions <= ROW_CAP, 1, "care region bound")


def _candidate_header(data):
    _need(type(data) is bytes)
    _need(HEADER_BYTES <= len(data) <= BYTE_CAP, 2, "care byte bound")
    _need(data[:8] == b"CAREOBS1" and struct.unpack_from("<HH", data, 8) == (1, 256))
    flags, turn, length = struct.unpack_from("<III", data, 12)
    stage, policy, failure = struct.unpack_from("<BBH", data, 24)
    return CareHeader(flags, turn, length, stage, policy, failure,
        struct.unpack_from("<16I", data, 28), data[92:124], data[124:156], data[156:188],
        *struct.unpack_from("<II", data, 188), tuple(data[196:200]),
        struct.unpack_from("<I", data, 200)[0])


def _check_header(data, header, *, prefix):
    _need(header.flags & ~7 == 0 and header.stage & ~63 == 0)
    _need(header.policy in (0, 1) and header.failure <= 11 and header.ordinal < 32)
    _need(header.encoded_length == len(data) and data[204:256] == bytes(52))
    if prefix:
        _need(header.flags in (0, 4) and header.stage & 48 == 0, 6, "invalid native stage")
        _need(header.predecessor_sha256 == header.body_sha256 == ZERO_HASH
              and header.entry_turn == header.exit_turn == 0)
        _need(header.counts[13:15] == (0, 0))
    else:
        _need(header.body_sha256 == hashlib.sha256(memoryview(data)[256:]).digest(),
              5, "care body hash mismatch")
    if header.flags & 4:
        _need(header.failure != 0 and not header.flags & 1)
        if prefix:
            _need(header.flags == 4)
        return
    _need(header.failure == 0)
    if prefix:
        _need(header.flags == 0 and header.stage == 15 and header.calls == (1, 1, 1, 1),
              7, "native stages incomplete")
    else:
        first = header.ordinal == 0
        _need(header.flags == (3 if first else 1)
              and header.stage == (63 if first else 31)
              and header.calls == (1, 1, 1, 1), 7, "joined stages incomplete")


class _Cursor:
    def __init__(self, data):
        self.data = data
        self.at = HEADER_BYTES
        self.dictionary = ()
        self.sorted_ids = ()

    def scalar(self, fmt, width):
        _need(width <= len(self.data) - self.at)
        value = struct.unpack_from(fmt, self.data, self.at)[0]
        self.at += width
        return value

    def u8(self): return self.scalar("<B", 1)
    def u16(self): return self.scalar("<H", 2)
    def u32(self): return self.scalar("<I", 4)
    def u64(self): return self.scalar("<Q", 8)
    def i64(self): return self.scalar("<q", 8)

    def boolean(self):
        value = self.u8()
        _need(value in (0, 1))
        return bool(value)

    def rows(self, count, width, read):
        _need(count <= (len(self.data) - self.at) // width)
        return tuple(read() for _ in range(count))

    def bitmap(self, count):
        raw = self.rows((count + 7) // 8, 1, self.u8)
        if count % 8:
            _need(raw[-1] >> (count % 8) == 0)
        return tuple(bool(raw[i // 8] & (1 << (i % 8))) for i in range(count))

    def raw_ref(self):
        tag = self.u16()
        return (tag, self.u32() if tag == 65535 else None)

    def resolve(self, ref):
        tag, literal = ref
        if tag == 0:
            return 0
        if tag == 65535:
            _need(literal != 0)
            index = bisect_left(self.sorted_ids, (literal, -1))
            _need(index == len(self.sorted_ids) or self.sorted_ids[index][0] != literal)
            return literal
        _need(1 <= tag <= len(self.dictionary))
        value = self.dictionary[tag - 1]
        _need(value != 0 and self.sorted_ids[bisect_left(self.sorted_ids, (value, -1))][1] == tag - 1)
        return value

    def idref(self): return self.resolve(self.raw_ref())


def _scope_check(row, coverage, length, region_count):
    exists = row.slot < coverage[0]
    _need(row.slot < length and row.flags & ~7 == 0)
    _need(row.consumed_id != 0 or row.loss_b32 != 0)
    _need(bool(row.flags & 1) == exists)
    alive = bool(row.flags & 2)
    valid = bool(row.flags & 4)
    _need(not alive or exists)
    _need(valid == (exists and row.region < region_count))
    if not exists:
        _need((row.current_id, row.region, row.occupation, row.flags) == (0, 0, 0, 0))
        reason, mask = 6, 0
    elif not alive:
        reason, mask = 4, 33
    elif not valid:
        reason, mask = 5, 33
    elif row.occupation != 0:
        reason, mask = 3, 63
    elif row.consumed_id != row.current_id:
        reason, mask = 2, 63
    elif row.loss_b32 & 0x7fffffff == 0:
        reason, mask = 1, 63
    else:
        reason, mask = 0, 63
    _need(row.reason == reason and row.numeric_mask == mask)
    if mask == 0:
        _need(row.numbers == (0,) * 6)
    elif mask == 33:
        _need(row.numbers[0] == row.numbers[5] and row.numbers[1:5] == (0,) * 4)


def _native(cursor, header, regions):
    n, r, i, x, u, w, p, length, s, q, a, j, f, e, e0, k = header.counts
    _need(all(count <= ROW_CAP for count in header.counts[:15]) and k <= REL_CAP,
          1, "care row bound")
    _need(r == q == f == regions)
    impairment, fraction = cursor.u32(), cursor.u32()
    inputs = cursor.rows(i, 2, cursor.raw_ref)
    excluded = cursor.rows(x, 2, cursor.raw_ref)
    urban = cursor.rows(u, 2, cursor.u16)
    ids = cursor.rows(n, 4, cursor.u32)
    cursor.dictionary = ids
    cursor.sorted_ids = tuple(sorted((value, slot) for slot, value in enumerate(ids)))
    inputs = tuple(cursor.resolve(ref) for ref in inputs)
    excluded = tuple(cursor.resolve(ref) for ref in excluded)
    ages = cursor.rows(n, 2, cursor.u16)
    slots_regions = cursor.rows(n, 2, cursor.u16)
    settlements = cursor.rows(n, 2, cursor.u16)
    occupations = cursor.rows(n, 1, cursor.u8)
    trips = cursor.rows(n, 1, cursor.u8)
    rel_counts = cursor.rows(n, 1, cursor.u8)
    marriages = cursor.rows(n, 1, cursor.u8)
    kin = cursor.rows(n, 1, cursor.u8)
    alive = cursor.bitmap(n)
    _need(sum(rel_counts) <= REL_CAP, 1, "care relation bound")
    _need(all(count <= 8 for count in rel_counts))
    _need(all(not (m & t) and not ((m | t) >> count)
              for m, t, count in zip(marriages, kin, rel_counts)))
    _need(sum((m | t).bit_count() for m, t in zip(marriages, kin)) == k)
    targets = cursor.rows(k, 2, cursor.idref)
    workers = cursor.rows(w, 6, lambda: (cursor.u16(), cursor.u32()))
    _need(all(slot < n and slots_regions[slot] < r for slot, _ in workers))
    assignments = cursor.rows(p, 10, lambda: (cursor.idref(), cursor.u16(), cursor.idref(), cursor.u32()))
    _need(all(row[1] < r for row in assignments))
    prep = cursor.rows(r, 24, lambda: (cursor.u32(), cursor.u64(), cursor.u64(), cursor.u32()))
    economy = cursor.rows(r, 13, lambda: (cursor.u32(), cursor.u32(), cursor.u32(), cursor.boolean()))
    _need(all(branch or before == after for _, before, after, branch in economy), 5, "care factor mismatch")
    output = cursor.rows(q, 19, lambda: (cursor.u16(), cursor.rows(3, 4, cursor.u32), cursor.u32(), cursor.boolean()))
    _need(all(row[0] < r for row in output))
    coverage = cursor.rows(4, 2, cursor.u16)
    _need(coverage[0] <= ROW_CAP and coverage[1] == coverage[0]
          and coverage[2] + coverage[3] == coverage[0])
    scoped = cursor.rows(s, 42, lambda: ScopedBits(cursor.u16(), cursor.idref(), cursor.u32(),
        cursor.u32(), cursor.u16(), cursor.u8(), cursor.u8(), cursor.u8(), cursor.u8(),
        cursor.rows(6, 4, cursor.u32)))
    _need(all(scoped[index - 1].slot < scoped[index].slot for index in range(1, len(scoped))))
    for row in scoped:
        _scope_check(row, coverage, length, r)
    _need(sum(row.slot < coverage[0] for row in scoped) == coverage[2])
    operands = cursor.rows(r, 12, lambda: cursor.rows(3, 4, cursor.u32))
    finish_turn, rate, capacity = cursor.u32(), cursor.u32(), cursor.u16()
    _need(capacity <= ROW_CAP, 1, "care finish bound")
    finish_ids = cursor.rows(capacity, 4, cursor.u32)
    finish_regions = cursor.rows(capacity, 2, cursor.u16)
    finish_alive = cursor.bitmap(capacity)
    actual_alive = cursor.rows(a, 4, lambda: (cursor.idref(), cursor.u16()))
    injuries = cursor.rows(j, 6, lambda: (cursor.idref(), cursor.u16(), cursor.u16()))
    stats = cursor.rows(f, 22, lambda: (cursor.u16(), cursor.u64(), cursor.u64(), cursor.u32()))
    _need(tuple(row[0] for row in stats) == tuple(range(r)))
    return NativeFacts(impairment, fraction, inputs, excluded, urban, ids, ages, slots_regions,
        settlements, occupations, trips, rel_counts, marriages, kin, alive, targets,
        workers, assignments, prep, economy, output, coverage, scoped, operands,
        finish_turn, rate, finish_ids, finish_regions, finish_alive, actual_alive, injuries, stats)


def _controls(cursor):
    return ControlsBits(cursor.u64(), cursor.u64(), cursor.u64(), cursor.u64(),
        cursor.boolean(), cursor.boolean(), cursor.boolean(), cursor.u8(), cursor.i64())


def _snapshot(cursor, count):
    controls = _controls(cursor)
    episodes = cursor.rows(count, 20, lambda: EpisodeBits(cursor.idref(), cursor.i64(), cursor.u64(), cursor.u16()))
    return SnapshotBits(controls, episodes)


def _post(cursor, count, regions):
    snapshot = _snapshot(cursor, count)
    summary = NumericSummaryBits(cursor.i64(), cursor.u32(),
        *cursor.rows(4, 4, cursor.u32), *cursor.rows(4, 8, cursor.u64))
    regional = cursor.rows(regions, 50, lambda: RegionalSummaryBits(cursor.u16(),
        *cursor.rows(4, 4, cursor.u32), *cursor.rows(4, 8, cursor.u64)))
    return PostJoinBits(snapshot, summary, regional)


def _control_values(controls):
    _need(type(controls) is ControlsBits)
    bits = (controls.injury_rate_b64, controls.impairment_b64,
            controls.care_fraction_b64, controls.recovery_work_b64)
    for value in bits: _uint(value, 64)
    for value in (controls.enabled, controls.active, controls.care_enabled): _bool(value)
    _need(type(controls.policy) is int and controls.policy in (0, 1))
    _i64(controls.last_tick_turn)
    return bits


def _snapshot_check(snapshot):
    _need(type(snapshot) is SnapshotBits)
    _control_values(snapshot.controls)
    _tuple(snapshot.episodes, EpisodeBits)
    for episode in snapshot.episodes:
        _uint(episode.agent_id, 32); _i64(episode.onset_turn)
        _uint(episode.remaining_b64, 64); _uint(episode.origin_region, 16)


def _metric_values(row):
    integers = (row.episodes, row.new_injuries, row.recoveries, row.care_recipients)
    bits = (row.impaired_work_b64, row.care_work_b64,
            row.recovery_progress_b64, row.cared_recovery_progress_b64)
    for value in integers: _uint(value, 32)
    for value in bits: _uint(value, 64)
    return integers, bits


def _post_check(post, regions):
    _need(type(post) is PostJoinBits)
    _snapshot_check(post.snapshot)
    _need(type(post.summary) is NumericSummaryBits)
    _i64(post.summary.source_turn); _uint(post.summary.censored_episodes, 32)
    _metric_values(post.summary)
    _tuple(post.regions, RegionalSummaryBits)
    _need(len(post.regions) == regions)
    for index, row in enumerate(post.regions):
        _uint(row.region, 16); _need(row.region == index); _metric_values(row)


def _control_identity(controls):
    return (_control_values(controls), controls.enabled, controls.active,
            controls.care_enabled, controls.policy)


def _f32_from_b64(bits):
    _need((bits >> 52) & 2047 != 2047, 5, "nonfinite care control")
    value = struct.unpack("<d", struct.pack("<Q", bits))[0]
    try:
        return struct.unpack("<I", struct.pack("<f", value))[0]
    except OverflowError:
        raise CareFrameError(5, "care control conversion") from None


def _trusted_previous(previous, expected):
    if expected.ordinal == 0:
        _need(previous is None, 11, "unexpected care predecessor")
        return None
    _need(type(previous) is CareFrameView, 11, "missing care predecessor")
    # Trust only re-decoded bound bytes and their recursively bound ancestry.
    # dataclasses.replace/object mutation of header/native/post/digest is ignored.
    _need(expected.entry_turn > 0 and expected.exit_turn > 0, 8, "stale care turn")
    prior_expected = replace(expected, entry_turn=expected.entry_turn - 1,
        exit_turn=expected.exit_turn - 1, ordinal=expected.ordinal - 1)
    prior = decode_care_frame(previous.data, expected=prior_expected, previous=previous.previous)
    _need(type(prior) is CareFrameView, 11, "incomplete care predecessor")
    return prior


def _join_check(header, native, initial, post, expected, previous):
    _need(expected.source_start_turn + expected.ordinal == expected.entry_turn
          and expected.entry_turn < (1 << 32) - 1
          and expected.exit_turn == expected.entry_turn + 1, 8, "stale care turn")
    _need(header.source_turn == native.finish_turn == expected.entry_turn
          and header.ordinal == expected.ordinal, 8, "stale care turn")
    _need(header.manifest_sha256 == expected.manifest_sha256
          and header.policy == expected.policy, 5, "care binding mismatch")
    _post_check(post, expected.regions)
    if expected.ordinal == 0:
        _need(initial is not None, 11, "missing care initial join")
        _snapshot_check(initial)
        incoming = initial
        predecessor = ZERO_HASH
    else:
        _need(initial is None and previous is not None, 11, "care chain mismatch")
        incoming = previous.post.snapshot
        predecessor = previous.frame_sha256
    _need(post.summary.source_turn == post.snapshot.controls.last_tick_turn == expected.entry_turn,
          8, "stale care summary")
    _need(incoming.controls.last_tick_turn < expected.entry_turn, 8, "stale care input")
    _need(_control_identity(incoming.controls) == _control_identity(post.snapshot.controls),
          5, "care control mismatch")
    controls = incoming.controls
    # These are the unchanged source control domains, not tunable codec limits.
    # Even a care-disabled input must retain valid controls for an ordinary turn.
    control_bits = _control_values(controls)
    _need(all((value >> 52) & 2047 != 2047 for value in control_bits), 5, "nonfinite care control")
    values = tuple(struct.unpack("<d", struct.pack("<Q", value))[0] for value in control_bits)
    _need(all(low <= value <= high for value, (low, high) in zip(values,
              ((0.0, 0.25), (0.0, 1.0), (0.0, 1.0), (1.0, 10.0)))),
          4, "care control domain")
    _need(controls.enabled and controls.active and controls.policy == expected.policy,
          5, "inactive care controls")
    _need(tuple(row.agent_id for row in incoming.episodes) == native.inputs, 5, "care episode input mismatch")
    _need(native.impairment_b32 == _f32_from_b64(controls.impairment_b64)
          and native.care_fraction_b32 == (_f32_from_b64(controls.care_fraction_b64) if controls.care_enabled else 0)
          and native.rate_b32 == _f32_from_b64(controls.injury_rate_b64), 5, "care native control mismatch")
    _need(post.summary.episodes == len(post.snapshot.episodes)
          and post.summary.new_injuries == len(native.injuries), 5, "care summary shape mismatch")
    return predecessor


def decode_care_frame(data: bytes, *, expected: FrameExpected,
                      previous: CareFrameView | None = None) -> CareFrameView | CareFaultView:
    """Validate final bytes; an aborted body is opaque and always incomplete."""
    _expected(expected)
    header = _candidate_header(data)
    _check_header(data, header, prefix=False)
    digest = hashlib.sha256(data).digest()
    if header.flags & 4:
        return CareFaultView(data, header, digest)
    cursor = _Cursor(data)
    native = _native(cursor, header, expected.regions)
    initial = _snapshot(cursor, header.counts[14]) if header.ordinal == 0 else None
    _need(header.ordinal == 0 or header.counts[14] == 0)
    post = _post(cursor, header.counts[13], expected.regions)
    _need(cursor.at == len(data))
    prior = _trusted_previous(previous, expected)
    predecessor = _join_check(header, native, initial, post, expected, prior)
    _need(header.predecessor_sha256 == predecessor, 11, "care predecessor hash mismatch")
    _need(header.entry_turn == expected.entry_turn and header.exit_turn == expected.exit_turn,
          8, "stale care observer turn")
    return CareFrameView(data, header, native, initial, post, prior, digest)


def _ref_width(agent_id, dictionary):
    if agent_id == 0:
        return 2
    index = bisect_left(dictionary, (agent_id, -1))
    return 2 if index < len(dictionary) and dictionary[index][0] == agent_id else 6


def _bounded_extend(output, data):
    _need(len(data) <= BYTE_CAP - len(output), 3, "care join byte bound")
    output.extend(data)


def _ref_bytes(agent_id, dictionary):
    if agent_id == 0:
        return struct.pack("<H", 0)
    index = bisect_left(dictionary, (agent_id, -1))
    if index < len(dictionary) and dictionary[index][0] == agent_id:
        return struct.pack("<H", dictionary[index][1] + 1)
    return struct.pack("<HI", 65535, agent_id)


def _snapshot_size(snapshot, dictionary):
    _snapshot_check(snapshot)
    size = 44
    for episode in snapshot.episodes:
        size += 18 + _ref_width(episode.agent_id, dictionary)
        _need(size <= BYTE_CAP, 3, "care join byte bound")
    return size


def _append_snapshot(output, snapshot, dictionary):
    controls = snapshot.controls
    _bounded_extend(output, struct.pack("<4Q4Bq", *_control_values(controls), controls.enabled,
        controls.active, controls.care_enabled, controls.policy, controls.last_tick_turn))
    for episode in snapshot.episodes:
        _bounded_extend(output, _ref_bytes(episode.agent_id, dictionary))
        _bounded_extend(output, struct.pack("<qQH", episode.onset_turn, episode.remaining_b64, episode.origin_region))


def _header_bytes(header):
    output = bytearray(HEADER_BYTES)
    output[:8] = b"CAREOBS1"
    struct.pack_into("<HHIIIBBH16I", output, 8, 1, 256, header.flags, header.source_turn,
        header.encoded_length, header.stage, header.policy, header.failure, *header.counts)
    output[92:124] = header.manifest_sha256
    output[124:156] = header.predecessor_sha256
    output[156:188] = header.body_sha256
    struct.pack_into("<II4BI", output, 188, header.entry_turn, header.exit_turn,
        *header.calls, header.ordinal)
    return output


def _seal_care_fault(prefix, header, expected, code):
    # Only admitted-size bytes are retained. No supplied Python joins are copied;
    # their stage/initial bits stay clear, so no claim is made to retain them.
    body = memoryview(prefix)[256:] if header is not None else memoryview(b"")
    known = header is not None
    first = header.failure if known and 1 <= header.failure <= 11 else code
    fault = CareHeader(4, header.source_turn if known else 0, 256 + len(body),
        header.stage & 15 if known else 0, header.policy if known and header.policy in (0, 1) else 0,
        first, header.counts if known else (0,) * 16,
        header.manifest_sha256 if known else expected.manifest_sha256, ZERO_HASH,
        hashlib.sha256(body).digest(), expected.entry_turn, expected.exit_turn,
        header.calls if known else (0,) * 4,
        header.ordinal if known and header.ordinal < 32 else expected.ordinal)
    output = _header_bytes(fault)
    _bounded_extend(output, body)
    return bytes(output)


def finalize_care_frame(native_prefix: bytes | None, *, expected: FrameExpected,
                        initial: SnapshotBits | None, post: PostJoinBits | None,
                        previous: CareFrameView | None = None) -> bytes | None:
    """Pure exact join. Refusals yield a bounded fault; allocation failure None."""
    _expected(expected)  # Invalid programmer bindings are not manufactured data.
    header = None
    try:
        try:
            _need(native_prefix is not None, 7, "missing native care prefix")
            header = _candidate_header(native_prefix)
            _check_header(native_prefix, header, prefix=True)
            if header.flags & 4:
                return _seal_care_fault(native_prefix, header, expected, header.failure)
            cursor = _Cursor(native_prefix)
            native = _native(cursor, header, expected.regions)
            _need(cursor.at == len(native_prefix))
            _need(post is not None, 7, "missing care post join")
            prior = _trusted_previous(previous, expected)
            predecessor = _join_check(header, native, initial, post, expected, prior)
            dictionary = cursor.sorted_ids
            size = len(native_prefix)
            if initial is not None:
                _need(expected.ordinal == 0, 11, "unexpected care initial join")
                size += _snapshot_size(initial, dictionary)
            size += _snapshot_size(post.snapshot, dictionary) + 60 + 50 * expected.regions
            _need(size <= BYTE_CAP, 3, "care join byte bound")
            output = bytearray(native_prefix)
            if initial is not None:
                _append_snapshot(output, initial, dictionary)
            _append_snapshot(output, post.snapshot, dictionary)
            integers, bits = _metric_values(post.summary)
            _bounded_extend(output, struct.pack("<qI4I4Q", post.summary.source_turn,
                post.summary.censored_episodes, *integers, *bits))
            for row in post.regions:
                integers, bits = _metric_values(row)
                _bounded_extend(output, struct.pack("<H4I4Q", row.region, *integers, *bits))
            _need(len(output) == size, 4, "care encoded shape mismatch")
            counts = list(header.counts)
            counts[13] = len(post.snapshot.episodes)
            counts[14] = len(initial.episodes) if initial is not None else 0
            final_header = replace(header, flags=3 if initial is not None else 1,
                encoded_length=len(output), stage=63 if initial is not None else 31,
                counts=tuple(counts), predecessor_sha256=predecessor,
                body_sha256=hashlib.sha256(memoryview(output)[256:]).digest(),
                entry_turn=expected.entry_turn, exit_turn=expected.exit_turn)
            output[:256] = _header_bytes(final_header)
            final = bytes(output)
            decode_care_frame(final, expected=expected, previous=prior)
            return final
        except CareFrameError as error:
            return _seal_care_fault(native_prefix, header, expected, error.code)
    except MemoryError:
        return None
