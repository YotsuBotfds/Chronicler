# Explicit governance capture

`chronicler-governance-capture-v1` composes the accepted pure harness and public
measurement API. It is the supported new path for isolated embedding. It neither
imports nor installs the legacy example report's interception wrapper; that
separate entry point's accepted limitations and output remain unchanged.

Pass `opening`, `frame`, complete `policy`, `MeasurementOrigin` and `SourceIdentity`
to `capture_frame(enabled=True, ...)`. It calls `run_kernel_frame` directly, then
passes that identical opening and resulting result to `measure_governance_result`.
Only after both succeed does it return a frozen `GovernanceCapture`, retaining
opening, result, measurement, the exact frozen supplied `SyntheticFrame`, complete
policy and caller-declared source identity. The frame retains source/ownership
epochs, synthetic origin and explicit observations/draws.
An exception returns no successful capture. Both existing APIs are pure; no
external commit or rollback occurs. Inputs and Fraction balances are retained
exactly, including residuals smaller than the float view can represent.

With `enabled=False` (the default), the receipt has `status=disabled_no_measurement`,
the identical opening, and `None` result/measurement/frame/policy/provenance. It does not
read the frame, policy, observations, draws or provenance; neither public execution
nor measurement entry point is called. `enabled` must be an exact boolean.

Each caller owns its opening, policy and declared identity. Independent callers
can interleave without replacing the shared harness function or sharing a capture
buffer. A failed caller cannot publish another caller's capture. This does not
coordinate simultaneous writes to a shared carry and does not add durable
governance sessions, a storage format, locks or multi-file transactions.

The explicit standalone fixture driver uses only the existing two-turn synthetic
example's values. It reuses its read-only `synthetic_policy()` factory, constructs
the initial carry and both observations itself, and preserves the exact restart
boundary using the harness's public carry codec. It never invokes the example
experiment or the old report wrapper. Default invocation imports no fixture,
runs nothing, and prints a canonical disabled receipt with the unchanged M67
unavailable obligation catalogue. Before parsing optional fixture, origin or
provenance values, dispatch recognizes only the exact `--enabled`, `--help` and
`-h` flags. Without activation, invalid or missing optional values are ignored
and produce the same disabled receipt. Explicit help prints the full CLI help
and exits successfully, including alongside invalid optional values; it does not
construct a fixture. Enabled invocation retains normal strict argument choices,
required declarations and source-identity validation before fixture execution.
Enabled invocation requires every declaration and a separate fixture flag:

```sh
python scripts/governance_capture_report.py
python scripts/governance_capture_report.py --enabled --fixture existing-two-turn \
  --origin synthetic_four_kernel_harness \
  --revision 9b3fb5b579d539f54815449314556918b2ab384b \
  --tree c310e2050b4a590eea305090ed1d97919fe31633 \
  --source-label 'caller-declared accepted Python source' --json
```

Output goes only to stdout. JSON uses the existing carry and measurement encoders;
the result-carry and measurement records are report output, not a new restore
contract. Revision/tree/label are declarations, never on-disk Git verification or
evidence of capture authenticity. The capture contract identifies this composition
seam independently of the caller's declared kernel source identity.

Valid policies can share the same `POLICY_ID` while differing in costs, calibration,
conventions, accession choice or exact capital limit. The capture retains the exact
policy object. A future fixed-policy sequence must compare complete dataclass
structural equality, alongside carry continuity, source identity, origin and civ
registry. Contiguous carries and equal policy IDs alone do not satisfy that claim.
This lane implements no sequence processor.

`validate_capture(capture)` checks retained frame origin/epochs and reruns only the
pure measurement extractor, rejecting a cached frame that differs from fresh
measurement of the opening/result. It never reruns the governance kernel. Frozen
dataclasses can be constructed manually; revalidation establishes correspondence,
not authenticity or proof that an unrecorded historical execution used the declared
policy/frame. It neither serializes full policy into a new registry nor constructs
a float-normalized policy digest. JSON includes explicit source/ownership epochs
and synthetic frame origin; the in-process capture retains the complete frame.

Source turn N, opening watermark N-1, and effective turn N+1 remain distinct.
`accession_pool_applied` remains the accepted derived exact balance-change signal;
it is not a declared succession classification. Wrong epochs, unsupported policies,
missing/duplicate civilization coverage and inconsistent spend chains refuse
through the public validators rather than producing plausible measurements.

Every unavailable M67 obligation remains unavailable for its existing reason.
This adds no opportunity denominator, tenure/window/censoring convention, regime
classifier, PSI/MMP/SFD producer, exact-balance cap or global integer digit-limit
change. Exact capture is independent of Python's existing decimal JSON conversion
limit; that limit is not widened. No scientific, calibration, production, native,
scale, milestone or source-authenticity acceptance follows from these synthetic
observations. G05, M71, held serialization, V3 and full native A01 remain held.

The new tests compare both frames with direct public execution/measurement and the
existing example, preserve exact Fraction residuals, force real threaded interleave
at measurement with a failing independent caller, verify harness identity throughout,
exercise failures after pure execution, preserve unavailable fields and prove
fresh-process serial/concurrent and hash-seed output equivalence. Required existing
regressions are measurement, harness, institutions, elite metrics, governance
capital, ruler ambitions and governance dormancy. Test results and source hashes
belong to the coordinator's local evidence receipts; this document claims no run.
