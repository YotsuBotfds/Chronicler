"""Explicit, bounded observation of the existing Python practice kernel.

No World attachment, writer, callbacks, native imports or automatic history.
Only the explicit run methods import and call the ordinary phase/turn owner.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math


@dataclass(frozen=True)
class KernelObservation:
    before: float
    cap: float
    prerequisites_met: bool
    population: int
    shortfall: float
    disruption: float
    effort_supplied: bool
    allowance_used: float | None
    ordinary_growth: float
    paid_growth_rhs: float | None
    total_growth: float
    forgetting: float
    inflow: float
    pre_clip: float
    clipped: float
    rounded: float
    kept: bool

    @property
    def paid_status(self):
        if not self.prerequisites_met:
            return "blocked_prerequisites"
        if not self.effort_supplied:
            return "not_supplied"
        if self.paid_growth_rhs is None:
            return "blocked_headroom"
        return "computed_zero" if self.paid_growth_rhs == 0 else "computed"


@dataclass(frozen=True)
class PaymentObservation:
    seat: int
    share: float
    confidence: float
    bookkeeping_paid: int
    allocation_group_paid: int
    event_id: str


@dataclass(frozen=True)
class PracticeGrowthRow:
    region: int
    recipe: str
    allowance: float | None
    allowance_present: bool
    allocations_observed: bool
    payments: tuple[PaymentObservation, ...]
    kernel: KernelObservation | None
    final_present: bool
    final_value: float | None

    @property
    def kernel_status(self):
        return "unobserved" if self.kernel is None else "computed"


@dataclass(frozen=True)
class PracticeGrowthReadout:
    status: str
    reason: str | None
    source_turn: int | None
    attempt: int
    scope: str
    rows: tuple[PracticeGrowthRow, ...] = ()
    encoded_row_bytes: int = 0


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("nonfinite or nonnumeric observation")
    return value


class _Capture:
    def __init__(self, owner):
        self.owner, self.attempt = owner, owner._attempt
        self.kernels, self.rows, self.failed = {}, None, False

    def refuse(self, reason="capture_failed"):
        self.failed = True
        self.rows = None
        self.kernels.clear()
        self.owner._reason = reason

    def selected(self, region, technique):
        return not self.failed and (region, technique) in self.owner._keys

    def kernel(self, region, technique, **values):
        key = region, technique
        if self.failed or key not in self.owner._keys:
            return
        if key in self.kernels:
            raise ValueError("duplicate selected kernel assignment")
        row = KernelObservation(**values)
        for name, value in values.items():
            if name not in ("prerequisites_met", "effort_supplied", "kept") and value is not None:
                _number(value)
        self.kernels[key] = row

    def commit(self, world, practice, effort):
        if self.failed:
            return
        if world.turn != self.owner._source:
            raise ValueError("practice source changed before commit")
        science = getattr(world, "scientific_claims", None)
        current = science is not None and science.last_effort_turn == world.turn
        allocations = science.last_effort if current else ()
        if type(allocations) not in (list, tuple) or len(allocations) > self.owner._payment_limit:
            raise ValueError("allocation observation bound")
        costs = {}
        for row in allocations:
            group = row.seat, row.region
            if type(row.paid) is not int or not 0 <= row.paid <= 1:
                raise ValueError("invalid accepted payment row")
            costs[group] = costs.get(group, 0) + row.paid
        rows = []
        for region, technique in self.owner._keys:
            recipe = self.owner._keys[region, technique]
            present = effort is not None and (region, technique) in effort
            allowance = None if effort is None else _number(effort.get((region, technique), 0.0))
            payments = []
            for row in allocations:
                if row.region != region or row.recipe != recipe:
                    continue
                if type(row.seat) is not int or not 0 <= row.seat <= 2**32 - 1:
                    raise ValueError("invalid seat identity")
                if type(row.event_id) is not str or len(row.event_id) > 128:
                    raise ValueError("allocation event identity bound")
                payments.append(PaymentObservation(row.seat, _number(row.share), _number(row.confidence),
                    row.paid, costs[row.seat, row.region], row.event_id))
            final_present = (region, technique) in practice
            value = _number(practice[region, technique]) if final_present else None
            rows.append(PracticeGrowthRow(region, recipe, allowance, present, current, tuple(payments),
                self.kernels.get((region, technique)), final_present, value))
        self.rows = tuple(rows)


class PracticeGrowthObserver:
    """Caller-owned latest capture; selected pairs are (region index, recipe)."""

    def __init__(self, selected_pairs, *, max_rows=64, max_encoded_bytes=65536):
        from chronicler.scientific_claims_state import MAX_SEATS
        from chronicler.techniques_state import TECHNIQUE_INDEX

        if type(max_rows) is not int or not 1 <= max_rows <= 64:
            raise ValueError("practice row limit must be an integer in 1..64")
        if type(max_encoded_bytes) is not int or not 1 <= max_encoded_bytes <= 65536:
            raise ValueError("practice encoded-row limit must be an integer in 1..65536")
        if type(selected_pairs) not in (list, tuple) or len(selected_pairs) > max_rows:
            raise ValueError("practice selection must be a bounded list or tuple")
        keys = {}
        for pair in selected_pairs:
            if type(pair) not in (list, tuple) or len(pair) != 2:
                raise ValueError("practice selection requires region/recipe pairs")
            region, recipe = pair
            if type(region) is not int or not 0 <= region <= 2**32 - 1 or type(recipe) is not str or recipe not in TECHNIQUE_INDEX:
                raise ValueError("invalid practice region or recipe")
            key = region, TECHNIQUE_INDEX[recipe]
            if key in keys:
                raise ValueError("duplicate practice selection")
            keys[key] = recipe
        self._keys = dict(sorted(keys.items()))
        self._byte_limit, self._payment_limit = max_encoded_bytes, MAX_SEATS * 2
        self._attempt, self._source, self._scope = 0, None, "not_started"
        self._latest, self._pending, self._reason, self._closed = None, None, "not_ready", False

    def _unavailable(self, reason):
        return PracticeGrowthReadout("unavailable", reason, self._source, self._attempt, self._scope)

    def _begin(self, source, scope):
        self._latest, self._pending = None, None
        if self._closed:
            return None
        self._source = source if type(source) is int and 0 <= source <= 2**32 - 1 else None
        self._scope, self._reason = scope, "attempt_incomplete"
        if self._source is None:
            self._reason = "frame_contract"
            return None
        capture = _Capture(self)
        self._pending = capture
        return capture

    def _finish(self, capture):
        if capture is None or capture is not self._pending:
            return
        self._pending = None
        try:
            if capture.failed:
                return
            if capture.rows is None:
                self._reason = "phase_unobserved"
                return
            size = len(json.dumps([asdict(row) for row in capture.rows], separators=(",", ":"), allow_nan=False).encode())
            if size > self._byte_limit:
                self._reason = "retention_limit"
                return
            self._latest = PracticeGrowthReadout("captured", None, self._source, self._attempt,
                self._scope, capture.rows, size)
        except Exception:
            self._reason = "capture_failed"

    def _run(self, world, scope, args, kwargs):
        # Invalidate before imports, argument conversion or ordinary preparation.
        self._latest, self._pending, self._source, self._scope = None, None, None, scope
        if not self._closed:
            self._attempt += 1
        try:
            capture = self._begin(world.turn, scope)
        except Exception:
            capture, self._pending, self._source, self._reason = None, None, None, "capture_failed"
        completed = False
        try:
            if scope == "phase":
                from chronicler.techniques import tick_techniques
                result = tick_techniques(world, *args, _practice_trace=capture, **kwargs)
            else:
                from chronicler.simulation import run_turn_result
                result = run_turn_result(world, *args, _practice_trace=capture, **kwargs)
            completed = True
            try:
                self._finish(capture)
            except Exception:
                self._latest, self._pending, self._reason = None, None, "capture_failed"
            return result
        finally:
            if not completed:
                self._latest, self._pending, self._reason = None, None, "attempt_incomplete"

    def run_phase(self, world, acc=None):
        return self._run(world, "phase", (), {"acc": acc})

    def run_turn_result(self, world, *args, **kwargs):
        return self._run(world, "turn", args, kwargs)

    def run_turn(self, world, *args, **kwargs):
        return self.run_turn_result(world, *args, **kwargs).chronicle_text

    def read_latest(self, *, expected_source_turn):
        if type(expected_source_turn) is not int or not 0 <= expected_source_turn <= 2**32 - 1:
            raise ValueError("expected source turn must be an exact uint32 integer")
        if self._source is not None and expected_source_turn != self._source:
            return self._unavailable("stale_request")
        return self._latest if self._latest is not None else self._unavailable(self._reason)

    def close(self):
        self._latest, self._pending, self._closed, self._reason = None, None, True, "closed"
        return self._unavailable("closed")

    def __getstate__(self):
        raise TypeError("practice observers are transient; reconstruct explicitly")
