"""Explicit, default-off composition of the pure governance harness and measurement.

No interception, shared capture state, persistence, RNG or runtime activation.
Source identity is caller-declared, never verified repository provenance.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import governance_kernel_harness as harness
from . import governance_measurements as measurements

CAPTURE_CONTRACT = "chronicler-governance-capture-v1"


@dataclass(frozen=True)
class GovernanceCapture:
    """One caller's immutable opening/result/measurement, or an explicit no-op.

    Disabled receipts retain only the identical opening. Enabled receipts also
    retain the exact supplied frame, complete policy and declared provenance. No value here
    is a durable commit or a claim of capture authenticity.
    """

    opening: harness.HarnessCarry
    result: harness.HarnessResult | None
    measurement: measurements.GovernanceMeasurementFrame | None
    policy: harness.HarnessPolicy | None
    origin: measurements.MeasurementOrigin | None
    source_identity: measurements.SourceIdentity | None
    frame: harness.SyntheticFrame | None
    contract: str = CAPTURE_CONTRACT

    @property
    def enabled(self) -> bool:
        return self.measurement is not None

    @property
    def status(self) -> str:
        return "captured" if self.enabled else "disabled_no_measurement"


def capture_frame(*, opening: harness.HarnessCarry, enabled: bool = False,
                  frame: harness.SyntheticFrame | None = None,
                  policy: harness.HarnessPolicy | None = None,
                  origin: measurements.MeasurementOrigin | None = None,
                  source_identity: measurements.SourceIdentity | None = None
                  ) -> GovernanceCapture:
    """Run directly, measure the exact pair, then publish one frozen capture.

    Disabled execution does not read frame, policy, origin or source identity,
    and calls neither harness nor measurement. Enabled execution requires every
    explicit input. Any validation or measurement failure raises with no capture
    returned and no externally committed state. Concurrent callers must own
    independent openings; this adds no shared-carry write coordination.
    """
    if type(enabled) is not bool:
        raise ValueError("enabled must be an explicit boolean")
    if not isinstance(opening, harness.HarnessCarry):
        raise ValueError("opening must be a HarnessCarry")
    if not enabled:
        return GovernanceCapture(opening, None, None, None, None, None, None)
    if not isinstance(frame, harness.SyntheticFrame):
        raise ValueError("enabled capture requires a SyntheticFrame")
    if not isinstance(policy, harness.HarnessPolicy):
        raise ValueError("enabled capture requires a complete HarnessPolicy")
    if not isinstance(origin, measurements.MeasurementOrigin):
        raise ValueError("origin must be a MeasurementOrigin")
    if not isinstance(source_identity, measurements.SourceIdentity):
        raise ValueError("source_identity must be a SourceIdentity")
    result = harness.run_kernel_frame(enabled=True, opening=opening,
                                      observations=frame, policy=policy)
    if result.policy_id != policy.policy_id:
        raise ValueError("result policy does not match supplied capture policy")
    measurement = measurements.measure_governance_result(
        opening=opening, result=result, origin=origin, source_identity=source_identity)
    return GovernanceCapture(opening, result, measurement, policy, origin, source_identity, frame)


def validate_capture(capture: GovernanceCapture) -> None:
    """Check a retained capture using pure measurement, never kernel execution.

    Frozen dataclasses can be constructed manually. This checks cached output
    correspondence and recorded epochs, not authenticity or causal provenance.
    Sequence consumers must separately compare complete policies across frames;
    a policy ID alone does not identify the coefficients or conventions.
    """
    if not isinstance(capture, GovernanceCapture) or capture.contract != CAPTURE_CONTRACT:
        raise ValueError("capture must use the supported GovernanceCapture contract")
    if not isinstance(capture.opening, harness.HarnessCarry):
        raise ValueError("capture opening must be a HarnessCarry")
    optional = (capture.result, capture.measurement, capture.policy, capture.origin,
                capture.source_identity, capture.frame)
    if capture.measurement is None:
        if any(value is not None for value in optional):
            raise ValueError("disabled capture must contain no optional values")
        return
    if not isinstance(capture.frame, harness.SyntheticFrame):
        raise ValueError("capture must retain its SyntheticFrame")
    if not isinstance(capture.policy, harness.HarnessPolicy):
        raise ValueError("capture must retain its complete HarnessPolicy")
    frame = capture.frame
    if (type(frame.source_turn) is not int or type(frame.ownership_epoch) is not int
            or frame.source_turn != capture.opening.effective_turn
            or frame.ownership_epoch != frame.source_turn
            or frame.origin != "explicit_synthetic_fixture"):
        raise ValueError("capture synthetic frame origin/epochs disagree with opening")
    if not isinstance(capture.result, harness.HarnessResult):
        raise ValueError("capture result must be a HarnessResult")
    if capture.result.policy_id != capture.policy.policy_id:
        raise ValueError("capture result policy does not match retained policy")
    fresh = measurements.measure_governance_result(opening=capture.opening,
        result=capture.result, origin=capture.origin, source_identity=capture.source_identity)
    if capture.measurement != fresh:
        raise ValueError("cached measurement does not match fresh pure measurement")
