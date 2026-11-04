"""Bounded deterministic care checks, conditional on captured primitive facts.

No capture, ordinary turn, native import, RNG, file writer or producer attestation
is supplied. Missing draws, input provenance and efficacy remain unqualified.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
import sys

from chronicler import health_care_observation_codec as codec

INTEGER_BITS = 8192
ONE32 = 0x3F800000
BASE32 = 0x3E99999A
DECAY32 = 0x3CA3D70A
MAX32 = 0x42C80000
ONE64 = 0x3FF0000000000000
FIVE64 = 0x4014000000000000
SOURCE_BINDINGS = (
    ("native_tree", "09ec301efc5c52a0a75f7a6edd9b99636d2953ff"),
    ("codec", "e18a2aefa25a512d1073f77506517221f4b98766d45c0c0a79b5cb343e2a7349"),
    ("health_care_rs", "d853edb7b7d4b584e22aa919dde02696580ffaa5b10f49127007102cc7aabac7"),
    ("health_care_py", "fc96d7c2f859865fc95023201c4c5c436cde0b8b39f53def02beb6f8557cd8ff"),
    ("health_care_state_py", "43ea4162dd65e2a59fde602be5b670b3d4699dfe2bb4580f8402d88760a04ec8"),
)
COMPONENTS = (
    "preparation_selection", "preparation_numeric", "consumed_loss",
    "labor_adjustment", "worked_predicate", "scoped_wealth",
    "finish_alive_statistics", "injury_necessary_conditions", "python_transition",
    "regional_metrics", "integer_totals", "floating_totals",
)
UNQUALIFIED = (
    "source_copy_truth", "raw_army_city_provenance", "raw_farmer_count_factor_origin",
    "full_goods_production", "nonfarmer_base_origin", "native_injury_draws",
    "random_outcome_set_completeness", "global_rng_trajectory", "display_event_text",
    "ordinary_output_parity", "counterfactual_benefit_efficacy_science", "performance",
)


class UnsupportedArithmetic(ValueError):
    """A fixed unsupported arithmetic case, never a rounded approximation."""


class _Mismatch(ValueError):
    def __init__(self, section, index=-1):
        self.section, self.index = section, index
        super().__init__("care mechanics mismatch")


def _equal(actual, expected, section, index=-1):
    if actual != expected:
        raise _Mismatch(section, index)


def _bounded(value):
    if value.bit_length() > INTEGER_BITS:
        raise UnsupportedArithmetic("internal_integer_bound")
    return value


def _shift(value, shift):
    if shift < 0 or shift > INTEGER_BITS or value.bit_length() + shift > INTEGER_BITS:
        raise UnsupportedArithmetic("internal_integer_bound")
    return value << shift


def _format(width):
    if width == 32:
        return 23, 8, 127
    if width == 64:
        return 52, 11, 1023
    raise ValueError("invalid care float format")


def _parts(bits, width):
    fraction, exponent, bias = _format(width)
    if type(bits) is not int or not 0 <= bits < (1 << width):
        raise ValueError("invalid care float bits")
    field = (bits >> fraction) & ((1 << exponent) - 1)
    if field == (1 << exponent) - 1:
        raise UnsupportedArithmetic("nonfinite_operand")
    significand = bits & ((1 << fraction) - 1)
    power = 1 - bias - fraction
    if field:
        significand |= 1 << fraction
        power = field - bias - fraction
    return bits >> (width - 1), significand, power


def _round(sign, numerator, denominator, power, width):
    """Round exact signed numerator/denominator * 2**power, once.

    Legal binary64 operands have <=53 significand bits and powers -1074..971.
    Aligned sums need <=2099 bits; products <=106 before scaling. Across the
    callers, power is -2148..2045 and the non-overflow rounding quantum is
    -1074..971, so the crude independent shift bound is3119. Even combining the
    largest2099-bit numerator with that shift needs <=5218 bits; denominator
    scaling/remainder doubling and a rounding carry stay below5300. The actual
    operation-specific bounds are tighter. The fixed8192 guard exceeds all
    legal operations; no caller can
    supply an arbitrary integer through a public primitive frame input.
    """
    fraction, exponent, bias = _format(width)
    _bounded(numerator); _bounded(denominator)
    if numerator < 0 or denominator <= 0 or sign not in (0, 1):
        raise ValueError("invalid exact care arithmetic")
    sign_bit = sign << (width - 1)
    if numerator == 0:
        return sign_bit
    estimate = numerator.bit_length() - denominator.bit_length() + power
    offset = power - estimate
    below = (_shift(numerator, offset) < denominator if offset >= 0
             else numerator < _shift(denominator, -offset))
    if below:
        estimate -= 1
    minimum, maximum = 1 - bias, bias
    if estimate > maximum:
        raise UnsupportedArithmetic("nonfinite_result")
    quantum = max(estimate, minimum) - fraction
    shift = power - quantum
    n, d = (_shift(numerator, shift), denominator) if shift >= 0 else (numerator, _shift(denominator, -shift))
    rounded, remainder = divmod(n, d)
    twice = _bounded(remainder * 2)
    if twice > d or (twice == d and rounded & 1):
        rounded += 1
    if rounded == 0:
        return sign_bit
    if estimate < minimum:
        if rounded > 1 << fraction:
            raise UnsupportedArithmetic("internal_integer_bound")
        # Subnormal or the minimum normal rounded up from below.
        return sign_bit | rounded
    if rounded == 1 << (fraction + 1):
        rounded >>= 1
        estimate += 1
    if estimate > maximum:
        raise UnsupportedArithmetic("nonfinite_result")
    return sign_bit | ((estimate + bias) << fraction) | (rounded - (1 << fraction))


def _add(a, b, width):
    sa, ma, ea = _parts(a, width)
    sb, mb, eb = _parts(b, width)
    if ma == mb == 0:
        return (sa & sb) << (width - 1)
    power = min(ea, eb)
    total = (-1 if sa else 1) * _shift(ma, ea - power)
    total += (-1 if sb else 1) * _shift(mb, eb - power)
    _bounded(total)
    return _round(int(total < 0), abs(total), 1, power, width)


def _sub(a, b, width):
    _parts(b, width)
    return _add(a, b ^ (1 << (width - 1)), width)


def _mul(a, b, width):
    sa, ma, ea = _parts(a, width)
    sb, mb, eb = _parts(b, width)
    return _round(sa ^ sb, _bounded(ma * mb), 1, ea + eb, width)


def _div(a, b, width):
    sa, ma, ea = _parts(a, width)
    sb, mb, eb = _parts(b, width)
    if mb == 0:
        raise UnsupportedArithmetic("zero_divisor")
    return _round(sa ^ sb, ma, mb, ea - eb, width)


def _add32(a, b): return _add(a, b, 32)
def _sub32(a, b): return _sub(a, b, 32)
def _mul32(a, b): return _mul(a, b, 32)
def _div32(a, b): return _div(a, b, 32)
def _add64(a, b): return _add(a, b, 64)
def _sub64(a, b): return _sub(a, b, 64)
def _mul64(a, b): return _mul(a, b, 64)


def _widen32(bits):
    sign, significand, power = _parts(bits, 32)
    return _round(sign, significand, 1, power, 64)


def _uint_to32(value):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError("invalid care u32")
    return _round(0, value, 1, 0, 32)


def _compare(a, b, width):
    _parts(a, width); _parts(b, width)
    sign = 1 << (width - 1)
    mask = sign - 1
    if a & mask == b & mask == 0:
        return 0
    if bool(a & sign) != bool(b & sign):
        return -1 if a & sign else 1
    order = (a > b) - (a < b)
    return -order if a & sign else order


def _positive(bits, width):
    fraction, exponent, _ = _format(width)
    magnitude = bits & ((1 << (width - 1)) - 1)
    field = (bits >> fraction) & ((1 << exponent) - 1)
    nan = field == (1 << exponent) - 1 and bool(bits & ((1 << fraction) - 1))
    return not nan and not bits >> (width - 1) and magnitude != 0


def _max32_zero(bits):
    comparison = _compare(bits, 0, 32)
    if comparison == 0 and bits != 0:
        raise UnsupportedArithmetic("ambiguous_rust_zero_tie")
    return 0 if comparison < 0 else bits


def _clamp32(bits):
    if _compare(bits, 0, 32) < 0:
        return 0
    if bits == 0x80000000:
        raise UnsupportedArithmetic("ambiguous_rust_zero_tie")
    return MAX32 if _compare(bits, MAX32, 32) > 0 else bits


def _min64(first, second):
    return first if _compare(first, second, 64) <= 0 else second


@dataclass(frozen=True, slots=True)
class MechanicsContext:
    manifest_sha256: bytes
    producer_implementation: str
    producer_version: tuple[int, int, int]
    producer_runtime: str
    producer_float_info: tuple[int, int, int, int] | None
    native_profile: str = "release"
    source_bindings: tuple[tuple[str, str], ...] = SOURCE_BINDINGS


@dataclass(frozen=True, slots=True)
class CareMechanicsReport:
    frame_sha256: bytes
    verdict: str
    components: tuple[tuple[str, bool | None], ...]
    claims: tuple[tuple[str, None], ...]
    unavailable: tuple[str, ...]
    failure_section: str | None
    failure_index: int
    source_bindings: tuple[tuple[str, str], ...] = SOURCE_BINDINGS


def _context_valid(context, expected):
    if type(context) is not MechanicsContext or type(expected) is not codec.FrameExpected:
        return False
    return (type(context.manifest_sha256) is bytes and len(context.manifest_sha256) == 32
        and type(expected.manifest_sha256) is bytes and len(expected.manifest_sha256) == 32
        and context.manifest_sha256 == expected.manifest_sha256
        and type(context.source_bindings) is tuple and len(context.source_bindings) == len(SOURCE_BINDINGS)
        and all(type(row) is tuple and len(row) == 2
            and all(type(value) is str and len(value) <= 64 for value in row)
            for row in context.source_bindings)
        and context.source_bindings == SOURCE_BINDINGS
        and type(context.producer_implementation) is str and len(context.producer_implementation) <= 16
        and type(context.producer_runtime) is str and len(context.producer_runtime) <= 256
        and type(context.producer_version) is tuple and len(context.producer_version) == 3
        and all(type(x) is int and 0 <= x <= 65535 for x in context.producer_version)
        and (context.producer_float_info is None or (type(context.producer_float_info) is tuple
            and len(context.producer_float_info) == 4
            and all(type(x) is int and -4096 <= x <= 4096 for x in context.producer_float_info)))
        and type(context.native_profile) is str and context.native_profile in ("release", "debug", "unknown"))


def _sum_runtime_admitted(context):
    observed = (sys.float_info.radix, sys.float_info.mant_dig, sys.float_info.max_exp, sys.float_info.min_exp)
    return (sys.implementation.name == "cpython" and context.producer_implementation == "CPython"
        and tuple(sys.version_info[:3]) == context.producer_version == (3, 13, 17)
        and context.producer_runtime == sys.version
        and context.producer_float_info == observed == (2, 53, 1024, -1021)
        and sys.float_info.rounds == 1)


def _builtin_sum64(values, context):
    if not _sum_runtime_admitted(context):
        raise UnsupportedArithmetic("unqualified_CPython_sum")
    for value in values:
        _parts(value, 64)
    # Actual same-runtime builtin sum, in the unchanged insertion order. Never a
    # hand-written left fold, sorted sum, fsum, or guessed CPython algorithm.
    total = sum(struct.unpack("<d", struct.pack("<Q", value))[0] for value in values)
    result = struct.unpack("<Q", struct.pack("<d", total))[0]
    _parts(result, 64)
    return result


@dataclass(frozen=True, slots=True)
class _Prepared:
    patients: tuple[int, ...]
    workers: tuple[tuple[int, int, int, int], ...]
    rows: tuple[tuple[int, int, int, int], ...]
    health_loss: tuple[tuple[int, int], ...]
    regions: tuple[tuple[int, int, int, int], ...]


def _derive_preparation(native, policy, profile):
    n, r = len(native.ids), len(native.preparation_regions)
    live = {agent_id: slot for slot, agent_id in enumerate(native.ids) if native.alive[slot]}
    excluded = set(native.excluded)
    urban = {settlement for settlement in native.urban if settlement != 0}
    patients = set(native.inputs)
    edges = []
    cursor = 0
    for slot in range(n):
        row = []
        for index in range(native.rel_counts[slot]):
            mask = 1 << index
            if (native.marriage_masks[slot] | native.kin_masks[slot]) & mask:
                row.append((2 if native.marriage_masks[slot] & mask else 5, native.targets[cursor]))
                cursor += 1
        edges.append(tuple(row))
    _equal(cursor, len(native.targets), "relationship_targets")

    def eligible(slot):
        return (native.alive[slot] and native.ages[slot] >= 20
            and native.occupations[slot] == 0 and native.trips[slot] == 0
            and native.ids[slot] not in excluded and native.settlements[slot] not in urban)

    deductions = {}
    assigned = set()
    out_patients, rows = [], []
    losses, impaired, care, recipients = [0] * r, [0] * r, [0] * r, [0] * r
    fraction, impairment = native.care_fraction_b32, native.impairment_b32
    for patient in sorted(patients):
        if patient not in live:
            continue
        slot = live[patient]
        region = native.regions[slot]
        if region >= r:
            continue
        out_patients.append(patient)
        giver = 0
        if eligible(slot):
            deductions[slot] = impairment
            impaired[region] = _add64(impaired[region], _widen32(impairment))
            if _positive(fraction, 32):
                marriages = [target for kind, target in edges[slot] if kind == 2]
                if len(marriages) > 1:
                    if profile == "debug":
                        raise _Mismatch("multiple_marriage_debug_assert", slot)
                    if profile != "release":
                        raise UnsupportedArithmetic("unqualified_Marriage_profile")
                if marriages:
                    spouse = marriages[0]  # Some(0) is not None.
                    if spouse in live:
                        donor = live[spouse]
                        if (eligible(donor) and native.regions[donor] == native.regions[slot]
                                and spouse not in patients and spouse not in assigned):
                            assigned.add(spouse)
                            giver = spouse
                            deductions[donor] = fraction
                            care[region] = _add64(care[region], _widen32(fraction))
                            recipients[region] += 1
        # ID0 is also the unchanged giver sentinel; do not normalize that collision.
        rows.append((patient, region, giver, 0 if giver == 0 else fraction))
    health_loss = [(0, 0)] * n if deductions else []
    for slot, loss in sorted(deductions.items()):
        health_loss[slot] = (native.ids[slot], loss)
        region = native.regions[slot]
        losses[region] = _add32(losses[region], loss)
    workers = []
    for slot in range(n):
        region = native.regions[slot]
        if region < r and eligible(slot):
            loss = health_loss[slot][1] if slot < len(health_loss) else 0
            workers.append((slot, native.ids[slot], region, _sub32(ONE32, loss)))
    if policy == 1 and _positive(fraction, 32) and any(row[2] == 0 for row in rows):
        # This map is last ELIGIBLE worker, distinct from global last ALIVE lookup.
        lookup = {agent_id: slot for slot, agent_id, _, _ in workers}
        assigned = {row[2] for row in rows if row[2] != 0}
        kin_assigned = set()
        for index, row in enumerate(rows):
            patient, region, old_giver, _ = row
            if old_giver != 0 or patient not in lookup:
                continue
            slot = lookup[patient]
            targets = sorted({target for kind, target in edges[slot]
                              if kind == 5 and target != 0 and target != patient})
            for target in targets:
                if target in patients or target in assigned or target not in lookup:
                    continue
                donor = lookup[target]
                if native.regions[donor] != native.regions[slot]:
                    continue
                if not any(kind == 5 and related == patient for kind, related in edges[donor]):
                    continue
                assigned.add(target); kin_assigned.add(target)
                rows[index] = (patient, region, target, fraction)
                if not health_loss:
                    health_loss = [(0, 0)] * n
                health_loss[donor] = (target, fraction)
                # Actual source order: append Kin after initial physical-slot sum.
                # Actual source region: existing patient row, not donor slot.
                losses[region] = _add32(losses[region], fraction)
                care[region] = _add64(care[region], _widen32(fraction))
                recipients[region] += 1
                break
        workers = [(slot, agent_id, region,
                    _sub32(ONE32, health_loss[slot][1] if slot < len(health_loss) else 0)
                    if agent_id in kin_assigned else available)
                   for slot, agent_id, region, available in workers]
    return _Prepared(tuple(out_patients), tuple(workers), tuple(rows), tuple(health_loss),
        tuple(zip(losses, impaired, care, recipients)))


def _check_consumed(native, header, prepared):
    _equal(header.counts[7], len(prepared.health_loss), "consumed_length")
    expected = tuple((slot, agent_id, loss) for slot, (agent_id, loss) in enumerate(prepared.health_loss)
                     if agent_id != 0 or loss != 0)
    _equal(tuple((row.slot, row.consumed_id, row.loss_b32) for row in native.scoped),
           expected, "consumed_rows")


def _check_labor(native, prepared):
    for region, (count, before, after, observed_branch) in enumerate(native.economy_inputs):
        farmers = _uint_to32(count)
        loss = prepared.regions[region][0]
        branch = _positive(farmers, 32) and _positive(loss, 32)
        _equal(observed_branch, branch, "labor_branch", region)
        expected = (_div32(_max32_zero(_sub32(_mul32(farmers, before), loss)), farmers)
                    if branch else before)
        _equal(after, expected, "labor_factor", region)


def _check_worked(native):
    worked = [False] * len(native.preparation_regions)
    for index, (region, outputs, forage, actual) in enumerate(native.economy_outputs):
        expected = any(_positive(value, 32) for value in outputs) or _positive(forage, 32)
        _equal(actual, expected, "worked_output", index)
        worked[region] = expected
    return tuple(worked)


def _check_wealth(native):
    for row in native.scoped:
        slot, actual = row.slot, row.numbers
        if not row.flags & 1:
            _equal(actual, (0,) * 6, "wealth_no_slot", slot)
            continue
        if not row.flags & 2 or not row.flags & 4:
            _equal(actual, (actual[0], 0, 0, 0, 0, actual[0]), "wealth_skipped", slot)
            continue
        base = actual[1]
        if row.occupation == 0:
            yield_bits, modifier, productivity = native.wealth_regions[row.region]
            base = _mul32(_mul32(BASE32, modifier), yield_bits)
            if _compare(productivity, ONE32, 32) != 0:
                base = _mul32(base, productivity)
            _equal(actual[1], base, "farmer_base", slot)
        applied = (row.occupation == 0 and row.consumed_id == row.current_id
                   and row.loss_b32 & 0x7FFFFFFF != 0)
        charged = _mul32(base, _sub32(ONE32, row.loss_b32)) if applied else base
        _equal(actual[2], charged, "health_income", slot)
        added = _add32(actual[0], charged)
        _equal(actual[3], added, "wealth_add", slot)
        decayed = _mul32(added, _sub32(ONE32, DECAY32))
        _equal(actual[4], decayed, "wealth_decay", slot)
        _equal(actual[5], _clamp32(decayed), "wealth_clamp", slot)


def _check_finish(native, prepared):
    lookup = {agent_id: slot for slot, agent_id in enumerate(native.finish_ids) if native.finish_alive[slot]}
    alive = tuple((agent_id, native.finish_regions[lookup[agent_id]])
                  for agent_id in prepared.patients if agent_id in lookup)
    _equal(native.alive_results, alive, "finish_alive")
    statistics = tuple((region, row[1], row[2], row[3]) for region, row in enumerate(prepared.regions))
    _equal(native.regional_results, statistics, "finish_statistics")


def _check_injuries(native, prepared, worked):
    patients = set(prepared.patients)
    possible = {}
    for slot, agent_id, region, available in prepared.workers:
        if not worked[region] or not _positive(available, 32) or agent_id in patients:
            continue
        if slot >= len(native.finish_ids):
            raise _Mismatch("finish_slot_out_of_bounds", slot)
        if not native.finish_alive[slot] or native.finish_ids[slot] != agent_id:
            continue
        threshold = _mul32(native.rate_b32, available)
        if _positive(threshold, 32):
            key = (agent_id, region, native.finish_regions[slot])
            possible[key] = possible.get(key, 0) + 1
    _equal(native.injuries, tuple(sorted(native.injuries)), "injury_order")
    for index, row in enumerate(native.injuries):
        if possible.get(row, 0) == 0:
            raise _Mismatch("injury_necessary_conditions", index)
        possible[row] -= 1


def _derive_python(view):
    native = view.native
    incoming = view.initial if view.header.ordinal == 0 else view.previous.post.snapshot
    alive = dict(native.alive_results)
    assignments = {agent_id: (region, giver, care) for agent_id, region, giver, care in native.assignments}
    # Integer metrics followed by bit-valued float metrics, matching codec field
    # names, not the different order of health_care.py's local metrics tuple.
    regions = [[0, 0, 0, recipients, impaired, care, 0, 0]
               for _, impaired, care, recipients in native.regional_results]
    kept = []
    censored = 0
    for index, episode in enumerate(incoming.episodes):
        agent_id = episode.agent_id
        if agent_id not in alive:
            censored += 1
            continue
        if agent_id not in assignments:
            raise _Mismatch("python_missing_assignment", index)
        region, giver, care32 = assignments[agent_id]
        care64 = _widen32(care32)
        progress = _min64(episode.remaining_b64,
            _add64(ONE64, _min64(ONE64, _mul64(FIVE64, care64))))
        remaining = _sub64(episode.remaining_b64, progress)
        regions[region][6] = _add64(regions[region][6], progress)
        if giver != 0:
            regions[region][7] = _add64(regions[region][7], progress)
        if _positive(remaining, 64):
            kept.append(codec.EpisodeBits(agent_id, episode.onset_turn, remaining, episode.origin_region))
        else:
            regions[region][2] += 1
    for index, (agent_id, work_region, current_region) in enumerate(native.injuries):
        # New InjuryEpisode construction validates these fields, unlike arbitrary
        # existing mutated episodes which the source does not fully revalidate.
        if agent_id == 0 or not _positive(incoming.controls.recovery_work_b64, 64):
            raise _Mismatch("python_new_episode_domain", index)
        kept.append(codec.EpisodeBits(agent_id, view.header.source_turn,
            incoming.controls.recovery_work_b64, work_region))
        regions[work_region][1] += 1
        alive[agent_id] = current_region
    kept.sort(key=lambda episode: episode.agent_id)  # Python stable sort.
    for index, episode in enumerate(kept):
        if episode.agent_id not in alive or alive[episode.agent_id] >= len(regions):
            raise _Mismatch("python_missing_current_region", index)
        regions[alive[episode.agent_id]][0] += 1
    records = tuple(codec.RegionalSummaryBits(region, *values) for region, values in enumerate(regions))
    return tuple(kept), records, censored


def _check_integer_totals(view, regions, censored):
    summary = view.post.summary
    _equal(summary.source_turn, view.header.source_turn, "summary_source_turn")
    _equal(summary.censored_episodes, censored, "summary_censored")
    _equal((summary.episodes, summary.new_injuries, summary.recoveries, summary.care_recipients),
        tuple(sum(getattr(row, name) for row in regions)
              for name in ("episodes", "new_injuries", "recoveries", "care_recipients")),
        "summary_integer_totals")


def _check_floating_totals(view, regions, context):
    for name in ("impaired_work_b64", "care_work_b64", "recovery_progress_b64", "cared_recovery_progress_b64"):
        expected = _builtin_sum64(tuple(getattr(row, name) for row in regions), context)
        _equal(getattr(view.post.summary, name), expected, "summary_float_totals")


def _report(frame_digest, verdict, results, unavailable=(), section=None, index=-1):
    return CareMechanicsReport(frame_digest, verdict, tuple(zip(COMPONENTS, results)),
        tuple((name, None) for name in UNQUALIFIED), unavailable, section, index)


def _verify(data, expected, previous, context):
    digest = (hashlib.sha256(data).digest() if type(data) is bytes
              and codec.HEADER_BYTES <= len(data) <= codec.BYTE_CAP else bytes(32))
    results = [None] * len(COMPONENTS)
    try:
        view = codec.decode_care_frame(data, expected=expected, previous=previous)
    except codec.CareFrameError:
        return _report(digest, "INCOMPLETE", results, ("malformed_frame",))
    if type(view) is not codec.CareFrameView:
        return _report(digest, "INCOMPLETE", results, ("aborted_frame",))
    if not _context_valid(context, expected):
        return _report(digest, "INCOMPLETE", results, ("invalid_source_context",))
    phase = 0
    try:
        # Actual Python prepare validates duplicate incoming IDs before calling
        # native preparation. Raw pool duplicates/ID0 remain source-replayable.
        if len(set(view.native.inputs)) != len(view.native.inputs):
            raise _Mismatch("duplicate_incoming_episode")
        prepared = _derive_preparation(view.native, view.header.policy, context.native_profile)
        _equal(view.native.assignments, prepared.rows, "preparation_assignments")
        _equal(view.native.workers, tuple((slot, available) for slot, _, _, available in prepared.workers),
               "preparation_workers")
        results[phase] = True; phase += 1
        _equal(view.native.preparation_regions, prepared.regions, "preparation_regions")
        results[phase] = True; phase += 1
        _check_consumed(view.native, view.header, prepared)
        results[phase] = True; phase += 1
        _check_labor(view.native, prepared)
        results[phase] = True; phase += 1
        worked = _check_worked(view.native)
        results[phase] = True; phase += 1
        _check_wealth(view.native)
        results[phase] = True; phase += 1
        _check_finish(view.native, prepared)
        results[phase] = True; phase += 1
        _check_injuries(view.native, prepared, worked)
        results[phase] = True; phase += 1
        episodes, regions, censored = _derive_python(view)
        _equal(view.post.snapshot.episodes, episodes, "post_episodes")
        results[phase] = True; phase += 1
        _equal(view.post.regions, regions, "post_regional_metrics")
        results[phase] = True; phase += 1
        _check_integer_totals(view, regions, censored)
        results[phase] = True; phase += 1
        _check_floating_totals(view, regions, context)
        results[phase] = True
    except _Mismatch as error:
        results[phase] = False
        return _report(digest, "MISMATCH", results, (), error.section, error.index)
    except UnsupportedArithmetic as error:
        return _report(digest, "PARTIAL", results, (str(error),), COMPONENTS[phase])
    return _report(digest, "DETERMINISTIC_MATCH", results)


def verify_care_mechanics(data: bytes, *, expected: codec.FrameExpected,
        previous: codec.CareFrameView | None = None,
        context: MechanicsContext) -> CareMechanicsReport | None:
    """Check freshly decoded captured deterministic mechanics; never ordinary work.

    Local unsupported arithmetic/runtime yields PARTIAL, not a repaired frame or
    a tolerance match. Diagnostic allocation failure yields missing evidence.
    Every claims entry remains None even after DETERMINISTIC_MATCH: draws/source
    truth/economy provenance/RNG/efficacy/default/performance are outside scope.
    """
    try:
        return _verify(data, expected, previous, context)
    except MemoryError:
        return None
