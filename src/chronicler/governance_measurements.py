"""Read-only measurement seam over the detached four-kernel governance harness.

This module adds instrumentation, not a governance mechanic, PSI substitute or
calibration campaign. It imports only the reviewed kernels (``institutions``,
``elite_metrics``, ``governance_capital``, ``ruler_ambitions``) plus the harness
that publishes their immutable records. It never calls ``run_kernel_frame``,
never reads a ``SyntheticFrame``, never consumes an observation or a selection
draw, never touches an RNG, and never imports simulation, models, analytics, the
agent bridge, native code, the CLI registry or persistence.

Inputs are an explicit frozen opening ``HarnessCarry``, an *already produced*
``HarnessResult``, an explicit declared ``origin`` and an explicit
``SourceIdentity``. Outputs are one immutable ``GovernanceMeasurementFrame`` plus
deterministic text and JSON renderings of it. Nothing is written to disk, no
process is spawned and no caller object is mutated.

Boundaries (documented with sources in ``docs/governance/m67-readiness.md``):

* Turn ``N`` is the source turn. Spend decisions are charged on ``N``; every
  published effect -- institution snapshot, accrual, elite signals -- is
  effective ``N+1`` and is never backdated to ``N``. Each record carries both
  epochs so a reader cannot confuse them.
* ``MeasurementStatus.AVAILABLE`` means the value was read from a public field of
  the measured result. ``MeasurementStatus.UNAVAILABLE`` means it is not
  available, and carries a reason. Missing output is never rendered as numeric
  zero, and the two states cannot be confused in a report or in the JSON frame.
* A disabled harness result is refused outright: it publishes no policy and no
  receipt, so measuring it would manufacture an empty-but-passing frame.
* PSI, MMP, SFD, commons overshoot/collapse markers, production treasury commits,
  scale qualification, institutional regime classification, secular-cycle recovery
  and crisis predictiveness have no producer in this harness. They stay
  explicitly unavailable. No substitute, proxy, threshold or classifier is
  invented here.
* The roadmap's frozen/fluctuating/cycling regime classifiers are recorded as
  *preregistration requirements only*, with their unresolved window, censoring
  and overlap conventions named rather than guessed. No classifier is
  implemented; two turns of synthetic fixtures cannot classify a regime.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from fractions import Fraction
import json
import math
import re

from . import elite_metrics as g02
from . import governance_capital as g03
from . import governance_kernel_harness as harness
from . import institutions as g01
from . import ruler_ambitions as g04

__all__ = [
    "MEASUREMENT_SCHEMA",
    "REPORT_KIND",
    "ROADMAP_PATH",
    "SYNTHETIC_BANNER",
    "REVIEWED_HARNESS_SOURCE",
    "LEGITIMACY_SOURCE_ORDER",
    "REQUEST_RECEIPT_STATUSES",
    "MeasurementStatus",
    "MeasurementOrigin",
    "SourceIdentity",
    "ExactFraction",
    "Metric",
    "InstitutionMeasurement",
    "InstitutionFundingMeasurement",
    "InstitutionEventMeasurement",
    "ProposalOutcomeMeasurement",
    "RepealOutcomeMeasurement",
    "SpendMeasurement",
    "RequestReceiptMeasurement",
    "AccrualMeasurement",
    "AmbitionMeasurement",
    "ContributionMeasurement",
    "ReignMeasurement",
    "EliteIdentityMeasurement",
    "EliteMeasurement",
    "CapitalMeasurement",
    "CivilizationMeasurement",
    "RegimeClassifierRequirement",
    "REGIME_CLASSIFIER_REQUIREMENTS",
    "M67Obligation",
    "M67_OBLIGATIONS",
    "m67_measurement_obligation_catalogue",
    "render_obligation_catalogue",
    "GovernanceMeasurementFrame",
    "measure_governance_result",
    "measurement_json",
    "render_report",
]

MEASUREMENT_SCHEMA = 1
REPORT_KIND = "governance-measurement-report"
ROADMAP_PATH = "docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md"
SYNTHETIC_BANNER = (
    "SYNTHETIC FIXTURES ONLY: explicit synthetic fixture inputs; no production "
    "extraction, no PSI/MMP/SFD computation, G05 permission-blocked, no treasury "
    "commit, no calibration and no acceptance claim."
)
#: Each request receipt status the reviewed harness emits, with the approval flag
#: the harness constructs it with. Derived once so the two never drift.
_REQUEST_STATUS_APPROVAL = {
    "acknowledged": True,
    "acknowledged_mock": True,
    "ineligible_mock": False,
    "insufficient_capital": False,
    "structurally_unused": False,
}
REQUEST_RECEIPT_STATUSES = tuple(sorted(_REQUEST_STATUS_APPROVAL))
#: Legitimacy source order is the kernel's own declaration order, never a copy.
LEGITIMACY_SOURCE_ORDER = tuple(f.name for f in fields(g03.LegitimacySources))

_HEX40 = re.compile(r"\A[0-9a-f]{40}\Z")


class MeasurementStatus(str, Enum):
    """Presence of a measurement. Unavailable is a state, not a zero value."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class MeasurementOrigin(str, Enum):
    """Explicitly declared provenance of a measured result.

    The reviewed harness only accepts ``explicit_synthetic_fixture`` frames
    (``harness.SyntheticFrame.origin``), so every measurable result is synthetic.
    The declaration is still required so a report can never silently imply a
    production or simulation origin.
    """

    SYNTHETIC_FOUR_KERNEL_HARNESS = "synthetic_four_kernel_harness"


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _require_int(name: str, value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _require_finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite real number")
    try:
        numeric = float(value)
    except OverflowError as exc:  # pragma: no cover - kernel invariant
        raise ValueError(f"{name} must be a finite real number") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be a finite real number")
    return numeric


def _require_hash(name: str, value: object) -> str:
    if not isinstance(value, str) or not _HEX40.match(value):
        raise ValueError(f"{name} must be a 40 character lowercase hex identifier")
    return value


def _require_enum(name: str, value: object, cls: type[Enum]) -> None:
    if not isinstance(value, cls):
        raise ValueError(f"{name} must be a {cls.__name__}")


@dataclass(frozen=True)
class SourceIdentity:
    """Reviewed source identity recorded with every measurement.

    ``revision``/``tree`` identify the source tree that supplied the measured
    kernels; ``label`` is free text naming what that identity refers to. Nothing
    here is verified against a Git object: this seam performs no repository,
    network or filesystem access.
    """

    revision: str
    tree: str
    label: str

    def __post_init__(self) -> None:
        _require_hash("source revision", self.revision)
        _require_hash("source tree", self.tree)
        _require_text("source label", self.label)


#: Accepted reviewed parent that supplied the four kernels and the harness at
#: this lane's authoring. Override it explicitly to measure a different tree.
REVIEWED_HARNESS_SOURCE = SourceIdentity(
    revision="208d140d47d9f2dee0788267f79fa7276df22b42",
    tree="0762c7cff65e28ff326291ce31111b71e1d61ae3",
    label="accepted private candidate HEAD supplying the detached four-kernel harness",
)


@dataclass(frozen=True)
class ExactFraction:
    """Canonical ``numerator/denominator`` pair; never a float spelling.

    Exact political capital survives report encoding here, including residuals a
    float view cannot represent. Canonical form (positive denominator, coprime
    terms) is enforced so one value cannot be spelled two ways in a deterministic
    report. The accepted domain is exactly the public kernel domain: no transport
    cap is applied here, because a hidden cap would reject balances that
    ``GovernanceState`` and the harness already accept and publish.
    """

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if type(self.numerator) is not int:
            raise ValueError("fraction numerator must be an integer")
        if type(self.denominator) is not int or self.denominator <= 0:
            raise ValueError("fraction denominator must be a positive integer")
        if math.gcd(abs(self.numerator), self.denominator) != 1:
            raise ValueError("fraction must be in canonical reduced form")

    @classmethod
    def of(cls, value: Fraction) -> "ExactFraction":
        if not isinstance(value, Fraction):
            raise ValueError("exact value must be a Fraction")
        return cls(value.numerator, value.denominator)

    def as_fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def __str__(self) -> str:
        if self.denominator == 1:
            return str(self.numerator)
        return f"{self.numerator}/{self.denominator}"


def _exact(value: object, name: str) -> ExactFraction:
    """Coerce a kernel balance. Every constructed kernel balance is a Fraction."""
    if not isinstance(value, Fraction):
        raise ValueError(f"{name} must be an exact Fraction balance")
    return ExactFraction.of(value)


@dataclass(frozen=True)
class Metric:
    """One M67 measurement obligation and its presence in this frame.

    ``status=AVAILABLE`` requires a value and forbids a reason;
    ``status=UNAVAILABLE`` requires a nonempty reason and forbids a value. That
    invariant is what keeps "absent" distinguishable from a true measured zero.
    """

    key: str
    label: str
    roadmap_reference: str
    required_input: str
    required_epoch: str
    status: MeasurementStatus
    value: object | None
    reason: str | None

    def __post_init__(self) -> None:
        _require_text("metric key", self.key)
        _require_text("metric label", self.label)
        _require_text("metric roadmap_reference", self.roadmap_reference)
        _require_text("metric required_input", self.required_input)
        _require_text("metric required_epoch", self.required_epoch)
        _require_enum("metric status", self.status, MeasurementStatus)
        if self.status is MeasurementStatus.AVAILABLE:
            if self.value is None:
                raise ValueError(f"{self.key} is available but carries no value")
            if self.reason is not None:
                raise ValueError(f"{self.key} is available but carries a reason")
        else:
            if self.value is not None:
                raise ValueError(f"{self.key} is unavailable but carries a value")
            _require_text(f"{self.key} reason", self.reason)


@dataclass(frozen=True)
class InstitutionMeasurement:
    """One active institution at ``effective_turn``; never backdated to ``N``."""

    institution_type: g01.InstitutionType
    enacted_turn: int
    effective_turn: int
    legitimacy: float
    enforcement_cost: float
    faction_alignment: g01.Faction
    opposing_faction: g01.Faction

    def __post_init__(self) -> None:
        _require_enum("institution_type", self.institution_type, g01.InstitutionType)
        _require_enum("faction_alignment", self.faction_alignment, g01.Faction)
        _require_enum("opposing_faction", self.opposing_faction, g01.Faction)
        _require_int("enacted_turn", self.enacted_turn)
        _require_int("effective_turn", self.effective_turn)
        if self.enacted_turn >= self.effective_turn:
            raise ValueError("enactment on N is only effective on N+1")
        _require_finite("institution legitimacy", self.legitimacy)
        _require_finite("enforcement cost", self.enforcement_cost)


@dataclass(frozen=True)
class InstitutionFundingMeasurement:
    """The opening-portfolio fiscal quote charged on the source turn ``N``.

    This is a detached fixture quote. It performs no treasury write, and its
    treasury values are synthetic amounts rather than production fiscal state.
    """

    policy: g01.FundingPolicy
    effective_turn: int
    treasury_before: float
    treasury_after: float
    base_governing_cost: float
    enforcement_demand: float
    funding_ratio: float

    def __post_init__(self) -> None:
        _require_enum("funding policy", self.policy, g01.FundingPolicy)
        _require_int("funding effective_turn", self.effective_turn)
        for name in ("treasury_before", "treasury_after"):
            _require_finite(name, getattr(self, name))
        for name in ("base_governing_cost", "enforcement_demand"):
            _require_finite(name, getattr(self, name))
        _require_finite("funding ratio", self.funding_ratio)


@dataclass(frozen=True)
class InstitutionEventMeasurement:
    """A named institution lifecycle event, carrying both epochs."""

    event_type: str
    institution_type: g01.InstitutionType
    turn: int
    effective_turn: int
    reason: str

    def __post_init__(self) -> None:
        _require_text("event_type", self.event_type)
        _require_enum("institution_type", self.institution_type, g01.InstitutionType)
        _require_int("event turn", self.turn)
        _require_int("event effective_turn", self.effective_turn)
        _require_text("event reason", self.reason)


@dataclass(frozen=True)
class ProposalOutcomeMeasurement:
    institution_type: g01.InstitutionType
    status: g01.ProposalStatus

    def __post_init__(self) -> None:
        _require_enum("institution_type", self.institution_type, g01.InstitutionType)
        _require_enum("proposal status", self.status, g01.ProposalStatus)


@dataclass(frozen=True)
class RepealOutcomeMeasurement:
    institution_type: g01.InstitutionType
    status: g01.RepealStatus

    def __post_init__(self) -> None:
        _require_enum("institution_type", self.institution_type, g01.InstitutionType)
        _require_enum("repeal status", self.status, g01.RepealStatus)


@dataclass(frozen=True)
class SpendMeasurement:
    """One political-capital decision charged on the source turn ``N``.

    Exact before/after balances are carried through unchanged, so an approved
    debit of a sub-float-view cost stays visible in the report and in JSON.
    """

    request_id: str
    action: g03.GovernanceAction
    effective_turn: int
    cost: float
    approved: bool
    exact_capital_before: ExactFraction
    exact_capital_after: ExactFraction

    def __post_init__(self) -> None:
        _require_text("request_id", self.request_id)
        _require_enum("action", self.action, g03.GovernanceAction)
        _require_int("spend effective_turn", self.effective_turn)
        _require_finite("spend cost", self.cost)
        if type(self.approved) is not bool:
            raise ValueError("approved must be an explicit boolean")


@dataclass(frozen=True)
class RequestReceiptMeasurement:
    """A diagnostic request receipt, including requests that were never spent."""

    request_id: str
    action: g03.GovernanceAction
    status: str
    approved: bool

    def __post_init__(self) -> None:
        _require_text("request_id", self.request_id)
        _require_enum("action", self.action, g03.GovernanceAction)
        if self.status not in REQUEST_RECEIPT_STATUSES:
            raise ValueError(f"unknown request receipt status {self.status!r}")
        if type(self.approved) is not bool:
            raise ValueError("approved must be an explicit boolean")


@dataclass(frozen=True)
class AccrualMeasurement:
    """Late-phase generation, effective ``N+1``.

    ``opening_capital`` equals the post-spend balance unless the reviewed harness
    applied its explicit accession carry/reset pool, which
    ``accession_pool_applied`` records by observing exactly that difference. This
    seam never classifies a succession or chooses a transfer policy.
    """

    effective_turn: int
    opening_capital: ExactFraction
    generated_capital: ExactFraction
    closing_capital: ExactFraction
    ruler_legitimacy: float
    accession_pool_applied: bool
    legitimacy_sources: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        _require_int("accrual effective_turn", self.effective_turn)
        if type(self.accession_pool_applied) is not bool:
            raise ValueError("accession_pool_applied must be an explicit boolean")
        if self.closing_capital.as_fraction() != (
            self.opening_capital.as_fraction() + self.generated_capital.as_fraction()
        ):
            raise ValueError("accrual closing balance is not opening plus generated")
        _require_finite("ruler legitimacy", self.ruler_legitimacy)
        names = tuple(name for name, _ in self.legitimacy_sources)
        if names != LEGITIMACY_SOURCE_ORDER:
            raise ValueError("legitimacy sources must follow the kernel's own order")
        for name, value in self.legitimacy_sources:
            _require_finite(f"legitimacy source {name}", value)


@dataclass(frozen=True)
class AmbitionMeasurement:
    """One terminal ambition outcome and its collision-free contribution key."""

    contribution_id: str
    civ_id: str
    ruler_id: str
    accession_turn: int
    accession_event_cursor: int
    ambition_type: g04.AmbitionType
    target: str | None
    outcome_turn: int
    event_type: str
    tag: str
    legitimacy_delta: float

    def __post_init__(self) -> None:
        _require_text("contribution_id", self.contribution_id)
        _require_text("civ_id", self.civ_id)
        _require_text("ruler_id", self.ruler_id)
        _require_int("accession_turn", self.accession_turn)
        _require_int("accession_event_cursor", self.accession_event_cursor)
        _require_enum("ambition_type", self.ambition_type, g04.AmbitionType)
        if self.target is not None:
            _require_text("ambition target", self.target)
        _require_int("outcome_turn", self.outcome_turn)
        _require_text("event_type", self.event_type)
        _require_text("tag", self.tag)
        _require_finite("legitimacy_delta", self.legitimacy_delta)


@dataclass(frozen=True)
class ContributionMeasurement:
    """A retained, signed, reign-scoped contribution in the published carry."""

    contribution_id: str
    civ_id: str
    ruler_id: str
    accession_turn: int
    accession_event_cursor: int
    ambition_type: g04.AmbitionType
    delta: float

    def __post_init__(self) -> None:
        _require_text("contribution_id", self.contribution_id)
        _require_text("civ_id", self.civ_id)
        _require_text("ruler_id", self.ruler_id)
        _require_int("accession_turn", self.accession_turn)
        _require_int("accession_event_cursor", self.accession_event_cursor)
        _require_enum("ambition_type", self.ambition_type, g04.AmbitionType)
        _require_finite("contribution delta", self.delta)


@dataclass(frozen=True)
class ReignMeasurement:
    """Reign, objective and evidence-ledger surface of the published carry."""

    civ_id: str
    ruler_id: str
    accession_turn: int
    accession_event_cursor: int
    objective_count: int
    completed_objectives: int
    failed_objectives: int
    archived_ruler_ids: tuple[str, ...]
    archived_contributions: int
    evidence_cursor: int
    pending_event_count: int
    stored_event_count: int
    event_tags: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("civ_id", self.civ_id)
        _require_text("ruler_id", self.ruler_id)
        _require_int("accession_turn", self.accession_turn)
        _require_int("accession_event_cursor", self.accession_event_cursor)
        for name in ("objective_count", "completed_objectives", "failed_objectives",
                     "archived_contributions", "evidence_cursor",
                     "pending_event_count", "stored_event_count"):
            _require_int(name, getattr(self, name))
        if self.completed_objectives + self.failed_objectives > self.objective_count:
            raise ValueError("terminal objectives exceed the objective count")
        for name in ("archived_ruler_ids", "event_tags"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(v, str) for v in values):
                raise ValueError(f"{name} must be a tuple of strings")


@dataclass(frozen=True)
class EliteIdentityMeasurement:
    """Exactly one of a numeric agent ID or a stable synthetic GP key."""

    agent_id: int | None
    great_person_key: str | None

    def __post_init__(self) -> None:
        if (self.agent_id is None) == (self.great_person_key is None):
            raise ValueError("exactly one elite identity must be populated")
        if self.agent_id is not None:
            _require_int("agent_id", self.agent_id)
        else:
            _require_text("great_person_key", self.great_person_key)


def _elite_identities(
        values: tuple[g02.EliteIdentity, ...]) -> tuple[EliteIdentityMeasurement, ...]:
    return tuple(EliteIdentityMeasurement(v.agent_id, v.great_person_key) for v in values)


def _identity_key(identity: EliteIdentityMeasurement) -> tuple[int | None, str | None]:
    return (identity.agent_id, identity.great_person_key)


def _is_ordered_subsequence(candidate: tuple, sequence: tuple) -> bool:
    """Order-preserving containment, as G02 filters aspirants from its own suffix."""
    remaining = iter(sequence)
    return all(any(item == other for other in remaining) for item in candidate)


@dataclass(frozen=True)
class EliteMeasurement:
    """Exact public G02 counts and EMP for one civilization at ``N`` -> ``N+1``.

    Counts are re-derived from the published identity lists, so a report cannot
    restate the kernel's summary properties without the underlying records. The
    lists must be the partition G02 actually publishes: unique identities, the
    leading ``elite_positions`` qualifiers as office holders, and aspirants drawn
    in order from the non-holding suffix. No ranking rule is recomputed here.
    """

    civ_id: int
    snapshot_turn: int
    effective_turn: int
    elite_positions: int
    qualifiers: tuple[EliteIdentityMeasurement, ...]
    office_holders: tuple[EliteIdentityMeasurement, ...]
    frustrated_aspirants: tuple[EliteIdentityMeasurement, ...]
    conspicuous_consumption_index: float
    emp: float

    def __post_init__(self) -> None:
        _require_int("elite civ_id", self.civ_id)
        _require_int("snapshot_turn", self.snapshot_turn)
        _require_int("elite effective_turn", self.effective_turn)
        _require_int("elite_positions", self.elite_positions, minimum=1)
        for name in ("qualifiers", "office_holders", "frustrated_aspirants"):
            identities = getattr(self, name)
            if not isinstance(identities, tuple):
                raise ValueError(f"{name} must be a tuple of identities")
            keys = [_identity_key(identity) for identity in identities]
            if len(set(keys)) != len(keys):
                raise ValueError(f"{name} contains duplicate elite identities")
        if len(self.office_holders) > len(self.qualifiers):
            raise ValueError("office holders cannot exceed qualifiers")
        if self.office_holders != self.qualifiers[:self.elite_positions]:
            raise ValueError("office holders must be the leading qualifiers by published rank")
        if not _is_ordered_subsequence(self.frustrated_aspirants,
                                       self.qualifiers[self.elite_positions:]):
            raise ValueError("frustrated aspirants must come from the non-holding suffix")
        _require_finite("conspicuous consumption index", self.conspicuous_consumption_index)
        _require_finite("emp", self.emp)
        if self.conspicuous_consumption_index < 0:
            raise ValueError("conspicuous consumption index must be nonnegative")
        if self.emp < 0:
            raise ValueError("EMP must be nonnegative")

    @property
    def qualifier_count(self) -> int:
        return len(self.qualifiers)

    @property
    def office_holder_count(self) -> int:
        return len(self.office_holders)

    @property
    def frustrated_aspirant_count(self) -> int:
        return len(self.frustrated_aspirants)


@dataclass(frozen=True)
class CapitalMeasurement:
    """Published political-capital balance for one epoch, exact and float view."""

    effective_turn: int
    ruler_legitimacy: float
    exact_balance: ExactFraction
    float_view: float

    def __post_init__(self) -> None:
        _require_int("capital effective_turn", self.effective_turn)
        _require_finite("ruler legitimacy", self.ruler_legitimacy)
        _require_finite("capital float view", self.float_view)


@dataclass(frozen=True)
class CivilizationMeasurement:
    """Everything this harness publishes for one civilization, in epoch order."""

    civ_id: int
    opening_capital: CapitalMeasurement
    opening_institution_count: int
    institutions: tuple[InstitutionMeasurement, ...]
    funding: InstitutionFundingMeasurement
    events: tuple[InstitutionEventMeasurement, ...]
    proposal_outcomes: tuple[ProposalOutcomeMeasurement, ...]
    repeal_outcomes: tuple[RepealOutcomeMeasurement, ...]
    used_spend_operations: int
    spending: tuple[SpendMeasurement, ...]
    spend_total: ExactFraction
    capital_after_spend: ExactFraction
    accrual: AccrualMeasurement
    published_capital: CapitalMeasurement
    requests: tuple[RequestReceiptMeasurement, ...]
    ambition_outcomes: tuple[AmbitionMeasurement, ...]
    retained_contributions: tuple[ContributionMeasurement, ...]
    reign: ReignMeasurement | None
    elite: EliteMeasurement | None

    def __post_init__(self) -> None:
        _require_int("civ_id", self.civ_id)
        _require_int("opening_institution_count", self.opening_institution_count)
        for name in ("institutions", "events", "proposal_outcomes", "repeal_outcomes",
                     "spending", "requests", "ambition_outcomes",
                     "retained_contributions"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"{name} must be a tuple")
        if self.published_capital.effective_turn != self.accrual.effective_turn:
            raise ValueError("published capital and accrual must share one effective epoch")
        if self.published_capital.exact_balance != self.accrual.closing_capital:
            raise ValueError("published carry balance disagrees with the accrual ledger")
        _require_int("used_spend_operations", self.used_spend_operations)
        order = tuple(g01.InstitutionType)
        types = [institution.institution_type for institution in self.institutions]
        if list(types) != sorted(types, key=order.index):
            raise ValueError("institutions must follow G01 enum order")
        if (self.opening_capital.exact_balance.as_fraction() - self.spend_total.as_fraction()
                != self.capital_after_spend.as_fraction()):
            raise ValueError("opening capital minus spend must equal the post-spend balance")
        if self.reign is not None and not isinstance(self.reign, ReignMeasurement):
            raise ValueError("reign must be a ReignMeasurement or None")
        if self.elite is not None and not isinstance(self.elite, EliteMeasurement):
            raise ValueError("elite must be an EliteMeasurement or None")


@dataclass(frozen=True)
class M67Obligation:
    """An M67 measurement obligation this seam can never satisfy on its own.

    ``reason`` states the missing producer or decision lock, not a numeric value.
    The catalogue is data, evaluated at import time, and is the single source for
    both the measured frame and the default-off script notice.
    """

    key: str
    label: str
    roadmap_reference: str
    required_input: str
    required_epoch: str
    reason: str

    def __post_init__(self) -> None:
        for name in ("key", "label", "roadmap_reference", "required_input",
                     "required_epoch", "reason"):
            _require_text(f"M67 obligation {name}", getattr(self, name))


@dataclass(frozen=True)
class RegimeClassifierRequirement:
    """A roadmap regime classifier recorded as preregistration, not as code.

    ``implemented`` is fixed to ``False``: two turns of synthetic fixtures cannot
    classify an institutional regime, and this lane is not authorized to choose
    the missing conventions.
    """

    label: str
    roadmap_definition: str
    required_measurements: tuple[str, ...]
    unresolved_conventions: tuple[str, ...]
    implemented: bool = False

    def __post_init__(self) -> None:
        _require_text("classifier label", self.label)
        _require_text("classifier definition", self.roadmap_definition)
        for name in ("required_measurements", "unresolved_conventions"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(v, str) for v in values):
                raise ValueError(f"{name} must be a tuple of strings")
        if type(self.implemented) is not bool:
            raise ValueError("implemented must be an explicit boolean")
        if self.implemented:
            raise ValueError("no regime classifier is implemented or authorized here")


_UNRESOLVED_CLASSIFIER_CONVENTIONS = (
    "analysis window length and alignment for '<= 1 institution change per 100 turns'",
    "whether 'institution change' counts neglect auto-repeals, forced repeals, or both",
    "censoring of institutions still active at the end of the observation window",
    "'repeated enact / repeal churn': the repetition count that qualifies as churn",
    "the mean-tenure bound separating 'highly fluctuating' from 'complex cycling'",
    "aggregation level of 'mean active count >= 1' (per civ, per turn, per run, per seed)",
    "whether one run may satisfy several regime labels, and any precedence order",
    "the run length, seed count and confidence rule behind '>= 10% of tested runs'",
)

REGIME_CLASSIFIER_REQUIREMENTS = (
    RegimeClassifierRequirement(
        label="frozen_stable",
        roadmap_definition=(
            "<= 1 institution change per 100 turns and mean active count >= 1."
        ),
        required_measurements=(
            "institution change count per 100 turns",
            "mean active institution count",
        ),
        unresolved_conventions=_UNRESOLVED_CLASSIFIER_CONVENTIONS,
    ),
    RegimeClassifierRequirement(
        label="highly_fluctuating",
        roadmap_definition=(
            "mean institution tenure < 10 turns with repeated enact / repeal churn."
        ),
        required_measurements=(
            "mean institution tenure in turns",
            "enact / repeal churn count",
        ),
        unresolved_conventions=_UNRESOLVED_CLASSIFIER_CONVENTIONS,
    ),
    RegimeClassifierRequirement(
        label="complex_cycling",
        roadmap_definition=(
            "repeated regime shifts with mean tenure between the two extremes and "
            "at least 2 distinct institutional configurations."
        ),
        required_measurements=(
            "regime shift count",
            "mean institution tenure in turns",
            "distinct institutional configurations observed",
        ),
        unresolved_conventions=_UNRESOLVED_CLASSIFIER_CONVENTIONS,
    ),
)


@dataclass(frozen=True)
class GovernanceMeasurementFrame:
    """One immutable measurement of one already-produced harness result."""

    schema: int
    report_kind: str
    origin: MeasurementOrigin
    source_identity: SourceIdentity
    policy_id: str
    source_turn: int
    effective_turn: int
    opening_last_committed_turn: int
    identity_registry: tuple[int, ...]
    opening_institution_count: int
    civilizations: tuple[CivilizationMeasurement, ...]
    metrics: tuple[Metric, ...]
    regime_classifier_requirements: tuple[RegimeClassifierRequirement, ...]
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.schema) is not int or self.schema != MEASUREMENT_SCHEMA:
            raise ValueError("unsupported measurement schema")
        if self.report_kind != REPORT_KIND:
            raise ValueError("unsupported measurement report kind")
        _require_enum("origin", self.origin, MeasurementOrigin)
        if not isinstance(self.source_identity, SourceIdentity):
            raise ValueError("source_identity must be a SourceIdentity")
        _require_text("policy_id", self.policy_id)
        for name in ("source_turn", "effective_turn", "opening_institution_count"):
            _require_int(name, getattr(self, name))
        if self.effective_turn != self.source_turn + 1:
            raise ValueError("every measured effect must be effective one turn later")
        if not isinstance(self.identity_registry, tuple):
            raise ValueError("identity_registry must be a tuple")
        civ_ids = tuple(civ.civ_id for civ in self.civilizations)
        if civ_ids != tuple(sorted(civ_ids)) or civ_ids != self.identity_registry:
            raise ValueError("measured civilizations must match the identity registry in order")
        for name in ("metrics", "regime_classifier_requirements", "diagnostics"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError(f"{name} must be a tuple")
        for diagnostic in self.diagnostics:
            if type(diagnostic) is not str or not diagnostic:
                raise ValueError("frame diagnostics must be exact immutable strings")

    def civilization(self, civ_id: int) -> CivilizationMeasurement:
        """Registry-ordered lookup; raises ``KeyError`` for an unregistered civ."""
        for measurement in self.civilizations:
            if measurement.civ_id == civ_id:
                return measurement
        raise KeyError(civ_id)

    def metric(self, key: str) -> Metric:
        for measurement in self.metrics:
            if measurement.key == key:
                return measurement
        raise KeyError(key)

    @property
    def unavailable(self) -> tuple[Metric, ...]:
        return tuple(m for m in self.metrics if m.status is MeasurementStatus.UNAVAILABLE)


def _metric(key: str, label: str, reference: str, required_input: str,
            required_epoch: str, value: object) -> Metric:
    return Metric(key, label, reference, required_input, required_epoch,
                  MeasurementStatus.AVAILABLE, value, None)


def _missing(key: str, label: str, reference: str, required_input: str,
             required_epoch: str, reason: str) -> Metric:
    return Metric(key, label, reference, required_input, required_epoch,
                  MeasurementStatus.UNAVAILABLE, None, reason)


NO_CIVILIZATIONS = "frame has no registered civilizations; nothing was measured"
NO_ELITE_OUTPUT = "harness result carries no elite metrics output for this frame"
SINGLE_FRAME = ("one measured frame is a single observation; this harness does not "
                "run the 200-seed, 500-turn campaign M67 measures")

#: Obligations this seam can never satisfy on its own, each with its own reason.
M67_OBLIGATIONS = (
    M67Obligation(
        "institution_tenure", "Institution tenure", ":881,:898",
        "per-civ institution tenure in turns over a run", "N+1 per turn",
        f"{SINGLE_FRAME}, so no tenure series exists"),
    M67Obligation(
        "enact_rate", "Enact rate", ":877-885",
        "enacted institutions divided by a stated opportunity denominator", "N+1 per turn",
        "the harness supplies enactment counts, not an opportunity denominator; "
        "selecting one is an M67 decision"),
    M67Obligation(
        "repeal_rate", "Repeal rate", ":877-885",
        "repealed institutions divided by a stated opportunity denominator", "N+1 per turn",
        "the harness supplies repeal counts, not an opportunity denominator; "
        "selecting one is an M67 decision"),
    M67Obligation(
        "institutional_effect_modifiers", "M63b institutional effect modifiers",
        ":284-293", "per-institution action-weight and satisfaction modifier tables",
        "N policy-time",
        "the detached harness has no action-weight pipeline; M63b modifier tables are "
        "not implemented and uncalibrated"),
    M67Obligation(
        "legitimacy_distribution", "Legitimacy distribution", ":877-885",
        "per-civ ruler legitimacy distribution across seeds", "N+1",
        f"{SINGLE_FRAME}; only this frame's per-civ extrema are reported"),
    M67Obligation(
        "political_capital_distribution", "Political-capital distribution", ":877-885",
        "per-civ exact political-capital distribution across seeds", "N+1",
        f"{SINGLE_FRAME}; only this frame's per-civ extrema are reported"),
    M67Obligation(
        "commons_overshoot_marker", "Commons overshoot markers", ":878,:1232",
        "per-region exploitation / sustainable-yield markers from M64", "N+1",
        "no M64 commons kernel exists in this harness; commons state is not observable "
        "here"),
    M67Obligation(
        "commons_collapse_marker", "Commons collapse markers", ":878,:1233",
        "per-region commons-health collapse markers from M64", "N+1",
        "no M64 commons kernel exists in this harness; commons state is not observable "
        "here"),
    M67Obligation(
        "psi", "Political Stress Index", ":878,:888-890,:922",
        "PSI = MMP^a * EMP^b * SFD^c with a calibrated crisis threshold", "N+1 lagged",
        "no M65b PSI producer exists; this harness computes no PSI and holds no "
        "crisis threshold"),
    M67Obligation(
        "mmp", "Mass Mobilization Potential", ":878,:889",
        "MMP from median/mean agent wealth, urbanization and youth bulge", "N+1 lagged",
        "the measured HarnessResult lacks the complete production MMP inputs and "
        "extractors plus any urbanization or youth-bulge series; no M61b extractor or "
        "calibrated M65b producer exists here"),
    M67Obligation(
        "sfd", "State Fiscal Distress", ":878,:889",
        "SFD from last_governing_cost / treasury and institutional burden", "N+1 lagged",
        "no M65b producer exists; the harness fixture treasury is synthetic and is not "
        "production fiscal bookkeeping"),
    M67Obligation(
        "psi_subindex_cooccurrence", "PSI sub-index co-occurrence", ":889,:923",
        "all three sub-indices above threshold in one 20-turn window", "N+1 lagged",
        "requires MMP/SFD/PSI time series, which have no producer here"),
    M67Obligation(
        "crisis_predictiveness", "Crisis predictiveness", ":887-888,:922",
        "share of crisis seeds with an outcome 10-40 turns after a PSI crossing",
        "N+1 lagged",
        "requires production PSI, production crisis outcomes and the 200-seed 500-turn "
        "campaign; none exist in this harness"),
    M67Obligation(
        "secular_cycle_recovery", "Secular-cycle recovery", ":892-895,:924",
        "share of crisis seeds recovering within 120 turns of peak PSI", "N+1 lagged",
        "a two-turn synthetic frame cannot show a recovery trajectory; no PSI or "
        "demographic series exists"),
    M67Obligation(
        "institutional_regime_classification", "Institutional regime classification",
        ":879-882,:925", "frozen / highly fluctuating / complex cycling labels per run",
        "N+1 per turn",
        "no classifier is implemented or authorized here; the roadmap's window, "
        "censoring and overlap conventions are unresolved"),
    M67Obligation(
        "transient_reset_matrix", "Transient-reset matrix", ":883,:929",
        "an integration test per one-turn M63-M66 signal proving reset after consumption",
        "N+1 lagged",
        "requires production phase wiring and a phase-scheduling decision this lane is "
        "not authorized to make"),
    M67Obligation(
        "production_treasury_commits", "Production treasury commits", ":274-275,:281",
        "persisted per-civ governing-cost and treasury funding bookkeeping", "N",
        "the harness publishes a detached synthetic funding quote and performs no "
        "treasury write or persistence commit"),
    M67Obligation(
        "scale_qualification", "Scale qualification (M61b)", ":871,:959,:1011",
        "validated governance behaviour at 500K-1M agents", "N+1",
        "synthetic fixtures at fixture population; M61b scale validation is a separate "
        "held milestone"),
    M67Obligation(
        "legitimacy_action_success_by_quartile", "Legitimacy quartile action success",
        ":903-904,:926",
        "governance-action success for the bottom and top legitimacy quartiles", "N",
        "requires per-civ action outcomes and cross-seed quartiles; the harness "
        "receives an explicit proposal choice and executes no real action"),
    M67Obligation(
        "degenerate_condition_guards", "Degenerate condition guards", ":908-912,:927",
        "the four documented degenerate-condition guards", "N",
        "requires production faction, clergy and commons paths that are not wired here"),
)


def m67_measurement_obligation_catalogue() -> tuple[M67Obligation, ...]:
    """The obligations no measurement from this harness can satisfy.

    Useful before any frame exists: it names each obligation, its required input
    and epoch, and the specific missing producer or decision lock.
    """
    return M67_OBLIGATIONS


def render_obligation_catalogue(source_identity: SourceIdentity) -> str:
    """Deterministic default-off notice: nothing measured, everything unmeasured.

    This is what the opt-in script prints when no result is supplied. It runs no
    experiment and produces no measurement frame.
    """
    if not isinstance(source_identity, SourceIdentity):
        raise ValueError("source_identity must be a SourceIdentity")
    lines = [
        f"REPORT {REPORT_KIND} schema={MEASUREMENT_SCHEMA} (no measurement taken)",
        SYNTHETIC_BANNER,
        "NO MEASUREMENT: no harness result was supplied and no example was invoked.",
        f"source_revision: {source_identity.revision}",
        f"source_tree: {source_identity.tree}",
        f"source_label: {source_identity.label}",
        f"M67 OBLIGATIONS THAT REMAIN UNAVAILABLE ({ROADMAP_PATH}:859-940)",
        f"  'ship measurement first' obligations: {ROADMAP_PATH}:877-885",
    ]
    for obligation in M67_OBLIGATIONS:
        lines.append(f"  [unavailable] {obligation.key} = {obligation.reason}"
                     f"  | roadmap {obligation.roadmap_reference}"
                     f" | epoch {obligation.required_epoch}"
                     f" | input {obligation.required_input}")
    lines.append("REGIME CLASSIFIER PREREGISTRATION (definitions only, not implemented)")
    for requirement in REGIME_CLASSIFIER_REQUIREMENTS:
        lines.append(f"  - {requirement.label}: {requirement.roadmap_definition}")
        lines.append("      requires: " + ", ".join(requirement.required_measurements))
        lines.append(f"      implemented: {_render_value(requirement.implemented)}")
    lines.append("  unresolved conventions (recorded here, not decided here):")
    for convention in REGIME_CLASSIFIER_REQUIREMENTS[0].unresolved_conventions:
        lines.append(f"    - {convention}")
    return "\n".join(lines) + "\n"


def _elite_values(civs: tuple[CivilizationMeasurement, ...], extract) -> object | None:
    """Per-civ elite values in registry order, or None when unavailable."""
    values = []
    for civ in civs:
        if civ.elite is None:
            return None
        values.append(extract(civ.elite))
    return tuple(values)


def _frame_metrics(civs: tuple[CivilizationMeasurement, ...], *,
                   elite_available: bool) -> tuple[Metric, ...]:
    """Fixed-order obligation list: one entry, one status, per M67 obligation."""
    metrics: list[Metric] = []
    populated = bool(civs)
    balances = [civ.published_capital.exact_balance for civ in civs]
    legitimacies = [civ.published_capital.ruler_legitimacy for civ in civs]
    enacted = sum(1 for civ in civs for outcome in civ.proposal_outcomes
                  if outcome.status is g01.ProposalStatus.ENACTED)
    # A forced repeal publishes both a RepealOutcome and an institution_repealed
    # event; a neglect repeal publishes only the event. Count each actual repeal
    # once by cause, and keep the per-cause counts beside the generic total.
    forced = 0
    neglect = 0
    for civ in civs:
        forced_types = {outcome.institution_type for outcome in civ.repeal_outcomes
                        if outcome.status is g01.RepealStatus.REPEALED}
        observed_types = {event.institution_type for event in civ.events
                          if event.event_type == "institution_repealed"}
        forced += len(forced_types)
        neglect += len(observed_types - forced_types)

    def observed(key: str, label: str, reference: str, required_input: str,
                 required_epoch: str, value: object | None) -> None:
        if not populated:
            metrics.append(_missing(key, label, reference, required_input,
                                    required_epoch, NO_CIVILIZATIONS))
        elif value is None:
            metrics.append(_missing(key, label, reference, required_input,
                                    required_epoch, NO_ELITE_OUTPUT))
        else:
            metrics.append(_metric(key, label, reference, required_input,
                                   required_epoch, value))

    observed("institution_count", "Active institution count", ":877-885",
             "per-civ active institution snapshot", "N+1",
             sum(len(civ.institutions) for civ in civs))
    observed("enact_count", "Enacted institutions", ":877-885",
             "per-civ enacted proposal outcomes", "N+1", enacted)
    observed("repeal_count", "Repealed institutions", ":877-885",
             "per-civ forced and observed neglect repeals, each counted once", "N+1",
             forced + neglect)
    observed("forced_repeal_count", "Faction-forced repeals", ":877-885",
             "per-civ RepealOutcome(REPEALED) records", "N+1", forced)
    observed("neglect_repeal_count", "Neglect repeals", ":877-885,:448,:550",
             "per-civ institution_repealed events with no RepealOutcome", "N+1", neglect)
    observed("legitimacy_min", "Minimum ruler legitimacy", ":877-885",
             "per-civ published ruler legitimacy", "N+1",
             min(legitimacies) if populated else None)
    observed("legitimacy_max", "Maximum ruler legitimacy", ":877-885",
             "per-civ published ruler legitimacy", "N+1",
             max(legitimacies) if populated else None)
    observed("political_capital_min", "Minimum exact political capital", ":877-885",
             "per-civ exact political-capital balance", "N+1",
             min(balances, key=lambda pair: pair.as_fraction()) if populated else None)
    observed("political_capital_max", "Maximum exact political capital", ":877-885",
             "per-civ exact political-capital balance", "N+1",
             max(balances, key=lambda pair: pair.as_fraction()) if populated else None)
    observed("elite_positions", "Elite positions", ":878",
             "per-civ elite position count from G02", "N+1",
             _elite_values(civs, lambda elite: elite.elite_positions) if elite_available else None)
    observed("elite_qualifier_count", "Elite qualifier count", ":878",
             "per-civ elite qualifier identities from G02", "N+1",
             _elite_values(civs, lambda elite: elite.qualifier_count) if elite_available else None)
    observed("elite_office_holder_count", "Elite office-holder count", ":878",
             "per-civ elite office-holder identities from G02", "N+1",
             _elite_values(civs, lambda elite: elite.office_holder_count) if elite_available else None)
    observed("frustrated_aspirant_count", "Frustrated aspirant count", ":878",
             "per-civ frustrated aspirant identities from G02", "N+1",
             _elite_values(civs, lambda elite: elite.frustrated_aspirant_count)
             if elite_available else None)
    observed("conspicuous_consumption_index", "Conspicuous consumption index",
             ":463-468,:489", "per-civ ratchet index from G02", "N+1",
             _elite_values(civs, lambda elite: elite.conspicuous_consumption_index)
             if elite_available else None)
    observed("emp", "Elite Mobilization Potential by civilization", ":473-477,:878",
             "per-civ EMP scalar from G02, not a time series", "N+1",
             _elite_values(civs, lambda elite: elite.emp) if elite_available else None)
    metrics.extend(
        _missing(obligation.key, obligation.label, obligation.roadmap_reference,
                 obligation.required_input, obligation.required_epoch, obligation.reason)
        for obligation in M67_OBLIGATIONS)
    return tuple(metrics)


def _institution(state: g01.InstitutionState, effective_turn: int) -> InstitutionMeasurement:
    return InstitutionMeasurement(
        state.institution_type, state.enacted_turn, effective_turn, state.legitimacy,
        state.enforcement_cost, state.faction_alignment, state.opposing_faction)


def _spend_ledger(receipt: harness.CivReceipt, opening: Fraction, source_turn: int
                  ) -> tuple[tuple[SpendMeasurement, ...], ExactFraction, ExactFraction]:
    """Re-derive the exact spend ledger from the published decisions."""
    entries: list[SpendMeasurement] = []
    remaining = opening
    spent = Fraction()
    for decision in receipt.spending.decisions:
        if not isinstance(decision, g03.SpendDecision):
            raise ValueError("spending decisions must be SpendDecision records")
        cost = Fraction(str(decision.cost))
        before = _exact(decision.exact_capital_before, "exact_capital_before")
        after = _exact(decision.exact_capital_after, "exact_capital_after")
        if before.as_fraction() != remaining:
            raise ValueError("spend ledger does not chain from the opening balance")
        if decision.approved:
            if remaining < cost or after.as_fraction() != remaining - cost:
                raise ValueError("an approved spend did not debit its exact cost")
            remaining -= cost
            spent += cost
        elif after.as_fraction() != remaining:
            raise ValueError("a denied spend consumed political capital")
        entries.append(SpendMeasurement(
            decision.request.request_id, decision.request.action, source_turn,
            decision.cost, decision.approved, before, after))
    if _exact(receipt.spending.state.exact_political_capital,
              "spending balance") != ExactFraction.of(remaining):
        raise ValueError("published spending state disagrees with its own ledger")
    return tuple(entries), ExactFraction.of(spent), ExactFraction.of(remaining)


def _reign(carry: harness.CivCarry) -> ReignMeasurement | None:
    if carry.reign is None:
        if carry.contributions or carry.archives:
            raise ValueError("an uninitialized reign cannot own retained history")
        return None
    reign = carry.reign
    objectives = reign.ambitions
    return ReignMeasurement(
        civ_id=reign.civ_id, ruler_id=reign.ruler_id,
        accession_turn=reign.accession_turn,
        accession_event_cursor=reign.accession_event_cursor,
        objective_count=len(objectives),
        completed_objectives=sum(1 for ambition in objectives if ambition.completed),
        failed_objectives=sum(1 for ambition in objectives if ambition.failed),
        archived_ruler_ids=tuple(archive.reign.ruler_id for archive in carry.archives),
        archived_contributions=sum(len(archive.contributions) for archive in carry.archives),
        evidence_cursor=carry.evidence_cursor,
        pending_event_count=len(carry.pending_events),
        stored_event_count=len(carry.evidence_log),
        event_tags=tuple(reign.ruler_event_tags),
    )


def _contributions(carry: harness.CivCarry) -> tuple[ContributionMeasurement, ...]:
    return tuple(ContributionMeasurement(
        harness.contribution_id(item.key), item.key.civ_id, item.key.ruler_id,
        item.key.accession_turn, item.key.accession_event_cursor,
        item.key.ambition_type, item.delta) for item in carry.contributions)


def _request_receipts(receipt: harness.CivReceipt) -> tuple[RequestReceiptMeasurement, ...]:
    """Unique request receipts reconciled with the complete ordered spend ledger.

    Every spend decision must have exactly one matching receipt with the same
    request identity and the same approval. ``structurally_unused`` and
    ``ineligible_mock`` receipts never enter the ledger, so they are retained
    exactly as recorded; no eligibility rule is recomputed here.
    """
    recorded: dict[str, harness.RequestReceipt] = {}
    for item in receipt.requests:
        if not isinstance(item, harness.RequestReceipt):
            raise ValueError("requests must be RequestReceipt records")
        if not isinstance(item.request, g03.SpendRequest):
            raise ValueError("a request receipt must carry a SpendRequest")
        if type(item.approved) is not bool or not isinstance(item.status, str):
            raise ValueError("a request receipt must carry an exact status and boolean")
        identifier = item.request.request_id
        if identifier in recorded:
            raise ValueError("duplicate request receipt identity")
        if item.status not in _REQUEST_STATUS_APPROVAL:
            raise ValueError(f"unknown request receipt status {item.status!r}")
        if item.approved is not _REQUEST_STATUS_APPROVAL[item.status]:
            raise ValueError("request receipt status disagrees with its own approval flag")
        recorded[identifier] = item
    eligible = tuple(item.request for item in receipt.requests
                     if item.status not in ("structurally_unused", "ineligible_mock"))
    if any(not isinstance(decision, g03.SpendDecision)
           for decision in receipt.spending.decisions):
        raise ValueError("spending decisions must be SpendDecision records")
    if tuple(decision.request for decision in receipt.spending.decisions) != eligible:
        raise ValueError("ordered spend decisions disagree with eligible request receipts")
    for decision in receipt.spending.decisions:
        if not isinstance(decision, g03.SpendDecision):
            raise ValueError("spending decisions must be SpendDecision records")
        item = recorded.get(decision.request.request_id)
        if item is None or item.request != decision.request:
            raise ValueError("spend decision lacks its matching request receipt")
        if item.approved != decision.approved:
            raise ValueError("request receipt approval disagrees with its spend decision")
        expected_status = ("acknowledged_mock"
                           if decision.request.action is g03.GovernanceAction.SUPPRESS_SECESSION
                           else "acknowledged") if decision.approved else "insufficient_capital"
        if item.status != expected_status:
            raise ValueError("request receipt status disagrees with its spend decision action")
    return tuple(RequestReceiptMeasurement(item.request.request_id, item.request.action,
                                           item.status, item.approved)
                 for item in receipt.requests)


def _ambitions(receipt: harness.CivReceipt, published: harness.CivCarry,
               source_turn: int) -> tuple[AmbitionMeasurement, ...]:
    """Terminal ambition outcomes reconciled with the published reign ledger.

    Checks the source epoch, the redundant identity/type fields against the
    contribution key, uniqueness of keys, the terminal objective actually
    published in the reign, and the retained contribution's identical delta.
    """
    reign = published.reign
    objectives = {ambition.ambition_type: ambition
                  for ambition in (() if reign is None else reign.ambitions)}
    contributions = {harness.contribution_id(item.key): item
                     for item in published.contributions}
    outcomes: list[AmbitionMeasurement] = []
    seen: set[str] = set()
    for outcome in receipt.ambition_outcomes:
        if not isinstance(outcome, g04.AmbitionOutcome):
            raise ValueError("ambition outcomes must be AmbitionOutcome records")
        key = outcome.contribution_key
        if (key.civ_id != outcome.civ_id or key.ruler_id != outcome.ruler_id
                or key.ambition_type != outcome.ambition_type):
            raise ValueError("ambition outcome identity disagrees with its contribution key")
        if key.civ_id != str(receipt.civ_id):
            raise ValueError("ambition outcome belongs to another civilization")
        if outcome.turn != source_turn:
            raise ValueError("ambition outcome must be dated on the source turn")
        identifier = harness.contribution_id(key)
        if identifier in seen:
            raise ValueError("duplicate ambition outcome contribution key")
        seen.add(identifier)
        if reign is None or (key.ruler_id != reign.ruler_id
                             or key.accession_turn != reign.accession_turn
                             or key.accession_event_cursor != reign.accession_event_cursor):
            raise ValueError("ambition outcome does not belong to the published reign")
        objective = objectives.get(key.ambition_type)
        if objective is None or not (objective.completed or objective.failed):
            raise ValueError("ambition outcome lacks a terminal published objective")
        if objective.target != outcome.target:
            raise ValueError("ambition outcome target disagrees with the published objective")
        if outcome.event_type != ("ambition_fulfilled" if objective.completed
                                  else "ambition_failed"):
            raise ValueError("ambition event type disagrees with the terminal objective")
        contribution = contributions.get(identifier)
        if contribution is None or contribution.delta != outcome.legitimacy_delta:
            raise ValueError("ambition outcome is not matched by its retained contribution")
        outcomes.append(AmbitionMeasurement(
            identifier, key.civ_id, key.ruler_id, key.accession_turn,
            key.accession_event_cursor, key.ambition_type, outcome.target, outcome.turn,
            outcome.event_type, outcome.tag, outcome.legitimacy_delta))
    return tuple(outcomes)


def _civ_measurement(receipt: harness.CivReceipt, opening: harness.CivCarry,
                     published: harness.CivCarry, elite: g02.CivEliteMetrics | None,
                     source_turn: int, effective_turn: int) -> CivilizationMeasurement:
    if not isinstance(receipt, harness.CivReceipt):
        raise ValueError("receipts must be CivReceipt records")
    civ_id = receipt.civ_id
    if civ_id != opening.civ_id or civ_id != published.civ_id:
        raise ValueError("receipt, opening carry and published carry must name one civilization")
    turn_result = receipt.institutions
    if turn_result.next_state.effective_turn != effective_turn:
        raise ValueError("institution snapshot is not effective on N+1")
    if turn_result.next_state != published.institutions:
        raise ValueError("published institution state disagrees with the measured turn result")
    events = []
    for event in turn_result.events:
        if (event.turn, event.effective_turn) != (source_turn, effective_turn):
            raise ValueError("institution event epochs must be N resolving to N+1")
        events.append(InstitutionEventMeasurement(
            event.event_type, event.institution_type, event.turn, event.effective_turn,
            event.reason))
    funding = turn_result.funding
    if funding.charged_snapshot != opening.institutions:
        raise ValueError("funding quote does not match the frozen opening portfolio")
    if receipt.spending.state.effective_turn != source_turn:
        raise ValueError("political capital is spent on the source turn N")
    accrual = receipt.accrual
    if not isinstance(accrual, g03.CapitalAccrual):
        raise ValueError("receipts must carry a CapitalAccrual record")
    if accrual.state.effective_turn != effective_turn:
        raise ValueError("accrued capital is only effective on N+1")
    if accrual.state != published.governance:
        raise ValueError("published governance state disagrees with the measured accrual")
    spending, spend_total, after_spend = _spend_ledger(
        receipt, opening.governance.exact_political_capital, source_turn)
    accrual_opening = _exact(accrual.exact_opening_political_capital, "accrual opening")
    accrual_measurement = AccrualMeasurement(
        effective_turn, accrual_opening,
        _exact(accrual.exact_generated_capital, "accrual generated"),
        _exact(accrual.state.exact_political_capital, "accrual closing"),
        accrual.state.ruler_legitimacy,
        accrual_opening != after_spend,
        tuple((name, float(getattr(accrual.legitimacy_sources, name)))
              for name in LEGITIMACY_SOURCE_ORDER))
    elite_measurement = None
    if elite is not None:
        if not isinstance(elite, g02.CivEliteMetrics):
            raise ValueError("elite metrics must be CivEliteMetrics records")
        if elite.civ_id != civ_id:
            raise ValueError("elite metrics belong to another civilization")
        if elite.next_ratchet_state != published.ratchet:
            raise ValueError("published elite ratchet disagrees with the measured G02 output")
        elite_measurement = EliteMeasurement(
            civ_id, source_turn, effective_turn, elite.elite_positions,
            _elite_identities(elite.qualifiers), _elite_identities(elite.office_holders),
            _elite_identities(elite.frustrated_aspirants),
            elite.conspicuous_consumption_index, elite.emp)
    return CivilizationMeasurement(
        civ_id=civ_id,
        opening_capital=CapitalMeasurement(
            opening.governance.effective_turn, opening.governance.ruler_legitimacy,
            _exact(opening.governance.exact_political_capital, "opening balance"),
            opening.governance.political_capital),
        opening_institution_count=len(opening.institutions.institutions),
        institutions=tuple(_institution(state, effective_turn)
                           for state in turn_result.next_state.institutions),
        funding=InstitutionFundingMeasurement(
            funding.policy, source_turn, funding.treasury_before, funding.treasury_after,
            funding.last_base_governing_cost, funding.last_institution_enforcement_cost,
            funding.last_institution_funding_ratio),
        events=tuple(events),
        proposal_outcomes=tuple(ProposalOutcomeMeasurement(outcome.institution_type,
                                                          outcome.status)
                                for outcome in turn_result.proposal_outcomes),
        repeal_outcomes=tuple(RepealOutcomeMeasurement(outcome.institution_type,
                                                      outcome.status)
                              for outcome in turn_result.repeal_outcomes),
        used_spend_operations=len(turn_result.used_spend_decisions),
        spending=spending,
        spend_total=spend_total,
        capital_after_spend=after_spend,
        accrual=accrual_measurement,
        published_capital=CapitalMeasurement(
            published.governance.effective_turn, published.governance.ruler_legitimacy,
            _exact(published.governance.exact_political_capital, "published balance"),
            published.governance.political_capital),
        requests=_request_receipts(receipt),
        ambition_outcomes=_ambitions(receipt, published, source_turn),
        retained_contributions=_contributions(published),
        reign=_reign(published),
        elite=elite_measurement,
    )


def measure_governance_result(*, opening: harness.HarnessCarry,
                              result: harness.HarnessResult,
                              origin: MeasurementOrigin | str,
                              source_identity: SourceIdentity
                              ) -> GovernanceMeasurementFrame:
    """Measure one already-produced result; never run, replay or re-simulate it.

    ``opening`` is the explicit frozen carry the result was produced from and
    ``result`` is that exact published result. This function calls no kernel,
    reads no observation or draw, consumes no RNG, mutates neither argument and
    performs no I/O. A disabled result is refused rather than measured into an
    empty-but-passing frame; mismatched civilization identities or epochs raise
    before any measurement is built.
    """
    if not isinstance(opening, harness.HarnessCarry):
        raise ValueError("opening must be a HarnessCarry")
    if not isinstance(result, harness.HarnessResult):
        raise ValueError("result must be a HarnessResult")
    if not isinstance(source_identity, SourceIdentity):
        raise ValueError("source_identity must be a SourceIdentity")
    _require_enum("origin", origin, MeasurementOrigin)
    if not isinstance(result.diagnostics, tuple):
        raise ValueError("harness diagnostics must be a tuple")
    for diagnostic in result.diagnostics:
        if type(diagnostic) is not str or not diagnostic:
            raise ValueError("harness diagnostics must be exact immutable strings")
    if result.policy_id is None:
        raise ValueError("harness result is disabled; it publishes no measurement to read")
    if result.policy_id != harness.POLICY_ID:
        raise ValueError(f"unreviewed harness policy id {result.policy_id!r}")

    source_turn = opening.effective_turn
    published = result.carry
    if opening.last_committed_turn != source_turn - 1:
        raise ValueError("opening watermark must precede its own effective turn")
    if published.last_committed_turn != source_turn:
        raise ValueError("result was not produced from this opening carry epoch")
    effective_turn = published.effective_turn
    if effective_turn != source_turn + 1:
        raise ValueError("result effective epoch must be the source turn plus one")
    if published.identity_registry != opening.identity_registry:
        raise ValueError("result identity registry does not match the opening carry")
    registry = tuple(published.identity_registry)
    receipt_ids = tuple(receipt.civ_id for receipt in result.receipts)
    if len(set(receipt_ids)) != len(receipt_ids):
        raise ValueError("duplicate civilization receipt in the measured result")
    if tuple(sorted(receipt_ids)) != registry:
        raise ValueError("receipts must cover the persisted identity registry exactly")
    if tuple(civ.civ_id for civ in published.civilizations) != registry:
        raise ValueError("published civilizations must cover the identity registry in order")
    openings = {civ.civ_id: civ for civ in opening.civilizations}
    if tuple(sorted(openings)) != registry:
        raise ValueError("opening civilizations must cover the identity registry exactly")

    elite = result.elite_metrics
    if elite is not None:
        if (elite.snapshot_turn, elite.effective_turn) != (source_turn, effective_turn):
            raise ValueError("elite metrics epochs must be the source turn and its successor")
        if tuple(record.civ_id for record in elite.civilizations) != registry:
            raise ValueError("elite metrics must cover the identity registry in order")
    by_civ = {record.civ_id: record for record in elite.civilizations} if elite is not None else {}
    published_by_civ = {civ.civ_id: civ for civ in published.civilizations}
    civilizations = tuple(
        _civ_measurement(receipt, openings[receipt.civ_id],
                         published_by_civ[receipt.civ_id], by_civ.get(receipt.civ_id),
                         source_turn, effective_turn)
        for receipt in sorted(result.receipts, key=lambda receipt: receipt.civ_id))
    return GovernanceMeasurementFrame(
        schema=MEASUREMENT_SCHEMA, report_kind=REPORT_KIND,
        origin=MeasurementOrigin(origin), source_identity=source_identity,
        policy_id=result.policy_id, source_turn=source_turn, effective_turn=effective_turn,
        opening_last_committed_turn=opening.last_committed_turn,
        identity_registry=registry,
        opening_institution_count=sum(
            len(openings[civ_id].institutions.institutions) for civ_id in registry),
        civilizations=civilizations,
        metrics=_frame_metrics(civilizations, elite_available=elite is not None),
        regime_classifier_requirements=REGIME_CLASSIFIER_REQUIREMENTS,
        diagnostics=tuple(result.diagnostics))


def _encode(value: object) -> object:
    """Tagged, closed-registry JSON encoding; exact Fractions keep integer pairs."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ExactFraction):
        return {"fraction": [value.numerator, value.denominator]}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    if is_dataclass(value):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    raise ValueError(f"unsupported measurement value {type(value).__name__}")


def measurement_json(frame: GovernanceMeasurementFrame) -> str:
    """Canonical JSON: sorted keys, no whitespace, exact Fraction pairs."""
    if not isinstance(frame, GovernanceMeasurementFrame):
        raise ValueError("frame must be a GovernanceMeasurementFrame")
    return json.dumps(_encode(frame), sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False)


def _render_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if type(value) in (int, float):
        return repr(value)
    if isinstance(value, ExactFraction):
        return str(value)
    return json.dumps(_encode(value), sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False)


def _reign_line(reign: ReignMeasurement) -> str:
    return (f"ruler={reign.ruler_id} accession_turn={reign.accession_turn}"
            f" accession_cursor={reign.accession_event_cursor}"
            f" objectives={reign.objective_count}"
            f" completed={reign.completed_objectives}"
            f" failed={reign.failed_objectives}"
            f" archived_reigns={list(reign.archived_ruler_ids)}"
            f" archived_contributions={reign.archived_contributions}"
            f" evidence_cursor={reign.evidence_cursor}"
            f" pending_events={reign.pending_event_count}"
            f" stored_events={reign.stored_event_count}"
            f" tags={list(reign.event_tags)}")


def _elite_line(elite: EliteMeasurement) -> str:
    return (f"snapshot_turn={elite.snapshot_turn} effective_turn={elite.effective_turn}"
            f" positions={elite.elite_positions}"
            f" qualifiers={elite.qualifier_count}"
            f" office_holders={elite.office_holder_count}"
            f" aspirants={elite.frustrated_aspirant_count}"
            f" cci={_render_value(elite.conspicuous_consumption_index)}"
            f" emp={_render_value(elite.emp)}")


def _civilization_lines(civ: CivilizationMeasurement) -> list[str]:
    opening = civ.opening_capital
    lines = [
        f"CIVILIZATION {civ.civ_id}",
        f"  opening@{opening.effective_turn}: capital={opening.exact_balance}"
        f" (view={_render_value(opening.float_view)})"
        f" legitimacy={_render_value(opening.ruler_legitimacy)}"
        f" institutions={civ.opening_institution_count}",
        f"  institutions@{civ.published_capital.effective_turn}: count={len(civ.institutions)}",
    ]
    for institution in civ.institutions:
        lines.append(
            f"    - {institution.institution_type.value}"
            f" enacted_turn={institution.enacted_turn}"
            f" effective_turn={institution.effective_turn}"
            f" legitimacy={_render_value(institution.legitimacy)}"
            f" enforcement_cost={_render_value(institution.enforcement_cost)}"
            f" alignment={institution.faction_alignment.value}"
            f" opposing={institution.opposing_faction.value}")
    lines.append(
        f"  funding@{civ.funding.effective_turn}: policy={civ.funding.policy.value}"
        f" treasury_before={_render_value(civ.funding.treasury_before)}"
        f" treasury_after={_render_value(civ.funding.treasury_after)}"
        f" base_governing_cost={_render_value(civ.funding.base_governing_cost)}"
        f" enforcement_demand={_render_value(civ.funding.enforcement_demand)}"
        f" funding_ratio={_render_value(civ.funding.funding_ratio)}")
    lines.append(f"  institution_events: {len(civ.events)}")
    for event in civ.events:
        lines.append(
            f"    - {event.event_type} {event.institution_type.value}"
            f" turn={event.turn} effective_turn={event.effective_turn}"
            f" reason={event.reason}")
    lines.append(f"  proposal_outcomes: {len(civ.proposal_outcomes)}")
    for outcome in civ.proposal_outcomes:
        lines.append(f"    - {outcome.institution_type.value} -> {outcome.status.value}")
    lines.append(f"  repeal_outcomes: {len(civ.repeal_outcomes)}")
    for outcome in civ.repeal_outcomes:
        lines.append(f"    - {outcome.institution_type.value} -> {outcome.status.value}")
    lines.append(f"  used_spend_operations: {civ.used_spend_operations}")
    lines.append(f"  spending: {len(civ.spending)} total={civ.spend_total}"
                 f" capital_after_spend={civ.capital_after_spend}")
    for spend in civ.spending:
        lines.append(
            f"    - {spend.action.value} {spend.request_id}"
            f" approved={_render_value(spend.approved)}"
            f" cost={_render_value(spend.cost)}"
            f" before={spend.exact_capital_before} after={spend.exact_capital_after}"
            f" charged_turn={spend.effective_turn}")
    lines.append(f"  request_receipts: {len(civ.requests)}")
    for request in civ.requests:
        lines.append(f"    - {request.action.value} {request.request_id}"
                     f" status={request.status}"
                     f" approved={_render_value(request.approved)}")
    accrual = civ.accrual
    lines.append(
        f"  accrual@{accrual.effective_turn}: opening={accrual.opening_capital}"
        f" generated={accrual.generated_capital} closing={accrual.closing_capital}"
        f" legitimacy={_render_value(accrual.ruler_legitimacy)}"
        f" accession_pool_applied={_render_value(accrual.accession_pool_applied)}")
    lines.append("  legitimacy_sources: " + " ".join(
        f"{name}={_render_value(value)}" for name, value in accrual.legitimacy_sources))
    lines.append("  published_capital@"
                 f"{civ.published_capital.effective_turn}: "
                 f"{civ.published_capital.exact_balance}"
                 f" (view={_render_value(civ.published_capital.float_view)})")
    lines.append(f"  ambition_outcomes: {len(civ.ambition_outcomes)}")
    for outcome in civ.ambition_outcomes:
        lines.append(
            f"    - {outcome.ambition_type.value} target={outcome.target}"
            f" outcome_turn={outcome.outcome_turn}"
            f" delta={_render_value(outcome.legitimacy_delta)}"
            f" event={outcome.event_type} tag={outcome.tag}"
            f" key={outcome.contribution_id}")
    lines.append(f"  retained_contributions: {len(civ.retained_contributions)}")
    for contribution in civ.retained_contributions:
        lines.append(
            f"    - {contribution.ambition_type.value}"
            f" delta={_render_value(contribution.delta)}"
            f" reign={contribution.ruler_id}"
            f" accession_turn={contribution.accession_turn}"
            f" accession_cursor={contribution.accession_event_cursor}"
            f" key={contribution.contribution_id}")
    lines.append("  reign: " + (_reign_line(civ.reign) if civ.reign is not None
                                else "uninitialized (no reign has started)"))
    lines.append("  elite: " + (_elite_line(civ.elite) if civ.elite is not None
                                else f"unavailable: {NO_ELITE_OUTPUT}"))
    return lines


def render_report(frame: GovernanceMeasurementFrame) -> str:
    """Deterministic human-readable report.

    Identical frames always render identical bytes: fixed section order, registry
    and enum ordering, ``repr`` float spellings, and no timestamp, path or
    process identifier.
    """
    if not isinstance(frame, GovernanceMeasurementFrame):
        raise ValueError("frame must be a GovernanceMeasurementFrame")
    lines: list[str] = [
        f"REPORT {frame.report_kind} schema={frame.schema}",
        SYNTHETIC_BANNER,
        f"origin: {frame.origin.value}",
        f"source_revision: {frame.source_identity.revision}",
        f"source_tree: {frame.source_identity.tree}",
        f"source_label: {frame.source_identity.label}",
        f"policy_id: {frame.policy_id}",
        f"source_turn: {frame.source_turn}  effective_turn: {frame.effective_turn}"
        f"  opening_last_committed_turn: {frame.opening_last_committed_turn}",
        f"identity_registry: {list(frame.identity_registry)}",
        f"opening_institution_count: {frame.opening_institution_count}",
    ]
    for diagnostic in frame.diagnostics:
        lines.append(f"diagnostic: {diagnostic}")
    for civ in frame.civilizations:
        lines.append("")
        lines.extend(_civilization_lines(civ))
    lines.append("")
    lines.append(f"M67 MEASUREMENT OBLIGATIONS ({ROADMAP_PATH}:859-940)")
    lines.append(f"  'ship measurement first' obligations: {ROADMAP_PATH}:877-885")
    for metric in frame.metrics:
        if metric.status is MeasurementStatus.AVAILABLE:
            lines.append(f"  [available]   {metric.key} = {_render_value(metric.value)}"
                         f"  | roadmap {metric.roadmap_reference}"
                         f" | epoch {metric.required_epoch}"
                         f" | input {metric.required_input}")
        else:
            lines.append(f"  [unavailable] {metric.key} = {metric.reason}"
                         f"  | roadmap {metric.roadmap_reference}"
                         f" | epoch {metric.required_epoch}"
                         f" | input {metric.required_input}")
    lines.append("")
    lines.append("REGIME CLASSIFIER PREREGISTRATION (definitions only, not implemented)")
    for requirement in frame.regime_classifier_requirements:
        lines.append(f"  - {requirement.label}: {requirement.roadmap_definition}")
        lines.append("      requires: "
                     + ", ".join(requirement.required_measurements))
        lines.append(f"      implemented: {_render_value(requirement.implemented)}")
    lines.append("  unresolved conventions (recorded here, not decided here):")
    for convention in REGIME_CLASSIFIER_REQUIREMENTS[0].unresolved_conventions:
        lines.append(f"    - {convention}")
    return "\n".join(lines) + "\n"
