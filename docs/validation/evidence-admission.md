# Experiment evidence admission

`scripts/admit_experiment.py` seals and validates experiment evidence without
running simulations, editing source, rewriting outputs, or changing scientific
gate tolerances. It also runs as `python -m chronicler.evidence_admission` with
`PYTHONPATH=src`. Python 3.12+ and Git are sufficient; no native extension, paid
service, network access, or third-party dependency is required.

Admission means that the evidence package satisfies its independently pinned
policy and has final review attestations. It does **not** imply that simulation
balance, population viability, numerical science gates, or a promotion decision
passed. Keep existing lane-specific gates and their tolerances. In particular,
the subset M53b gate still leaves regression informational.

## Trust and baseline boundaries

Create and approve a policy **before** producing/reviewing evidence. Preserve its
SHA-256 outside the package and pass it as `--policy-sha256`. The CLI never derives
its trusted policy from the evidence manifest. If a policy changes, obtain a new
approved pin and repeat all reviews; changing the CLI argument to whatever hash
an untrusted package supplies defeats this boundary.

Use separate policy files and `baseline_domain` identifiers for public `edf7299`
and private frozen `b665e198`. Use full commit/tree IDs from each repository, never
abbreviated IDs. The validator does not infer that two domains are scientifically
comparable. A package must have exactly the domain, runs, seed grid, metric
columns, and identities approved in its policy. An explicit domain label is an
operator assertion; it cannot authenticate historical provenance by itself.

For each run, source provenance pins a commit, tree, and a nonempty map of source
file SHA-256 anchors. `checkout: "live"` also requires the repository HEAD to
match, no tracked/untracked changes, no hidden index flags, and all tracked blob
contents and executable modes to match the pinned tree. Source verification does
not trust Git status alone. Live submodules require a separate source contract
and are rejected by this version. Ignored outputs/build products are not source
identity; pin the actual imported native binary and effective config separately.
Git inspection disables replacement objects, optional index writes, and filesystem
monitor hooks, so replacement refs cannot redefine the pinned source objects.

`checkout: "frozen"` checks immutable Git objects for a preserved historical run,
without asserting that today's worktree is the historical execution environment.
Record source/native/config identities and worker outcomes at execution time;
do not retroactively invent missing provenance. Hashing a binary proves byte
identity, not that it was built from the claimed source or loaded by the process.
Likewise, worker records are attestations, not independently authenticated process
telemetry. Reviewers must inspect build/execution provenance.

## Files and formats

Keep the evidence manifest, policy, plan, and review receipts outside the frozen
member inventory. Existing active outputs can be used as read-only members;
adaptations should be made in a separate directory and preserve originals.
All member paths use canonical relative POSIX paths. Symlinks, hard-link aliases,
parent traversal, missing files, extra/missing members, and roles that alias the
original baseline, process records, or tables are rejected. Native/config files
may be shared by multiple runs using the same path.

The version-1 policy has exactly these fields (replace explanatory placeholders
with real, independently approved values):

```json
{
  "schema_version": 1,
  "lane": "my-lane",
  "baseline_domain": "public-edf7299",
  "runs": {
    "baseline": {
      "source": {
        "commit": "FULL_40_CHARACTER_COMMIT",
        "tree": "FULL_40_CHARACTER_TREE",
        "files": {"src/chronicler/simulation.py": "SHA256_OF_COMMITTED_BYTES"},
        "checkout": "frozen"
      },
      "native_sha256": "SHA256_OF_NATIVE_BINARY",
      "config_sha256": "SHA256_OF_EFFECTIVE_CONFIG",
      "seeds": [7, 8],
      "checkpoints": [10, 20],
      "table": {
        "columns": ["seed", "turn", "alive", "births", "exposure", "rate"],
        "counts": ["alive", "births", "exposure"],
        "ratios": [{"column": "rate", "numerator": "births", "denominator": "exposure", "absolute_tolerance": "0"}]
      }
    }
  },
  "original_baseline": {"run": "baseline", "sha256": "SHA256_OF_PRESERVED_ORIGINAL_CSV"},
  "review_tiers": ["tier1", "tier2"]
}
```

Add one `runs` entry for each candidate/arm. Each run may have its own identities,
grid, and table schema. Seed and turn form a unique row key: repeat measurements
or determinism replicates belong in separate run IDs. CSV headers must match
exactly, including order. All metric cells are explicit finite numbers. Seed/turn
cells are canonical nonnegative integers. Count columns are nonnegative integral
numbers. Every seed must have every checkpoint; there is no seed intersection or
silent missing-row filter. Include the true terminal turn as the maximum policy
checkpoint. Integers and schema versions reject booleans.

Ratio checks require an explicit nonzero denominator, even when the numerator
is zero. They compare decimal cross-products to the **policy's** absolute
tolerance. Undefined ratios never become zero or a pass. No tolerance is inferred
from observed data. Numeric size is limited to 4096 significant digits and an
absolute decimal exponent of 4096; oversized input fails with a structured
rejection. The original CSV has an independently pinned raw-byte hash, and its
rows must exactly equal the baseline run's decimal values at every key. Row order
and decimal spelling may differ; numerical differences have zero tolerance.

Every run has a JSON process record with exactly these fields:

```json
{
  "run_id": "baseline",
  "status": "complete",
  "returncode": 0,
  "seeds": [7, 8],
  "turns": 20,
  "source": {"commit": "FULL_COMMIT", "tree": "FULL_TREE", "files": {"src/chronicler/simulation.py": "SHA256"}, "checkout": "frozen"},
  "native_sha256": "SHA256_OF_NATIVE_BINARY",
  "config_sha256": "SHA256_OF_EFFECTIVE_CONFIG",
  "executions": [
    {"seed": 7, "status": "complete", "returncode": 0, "terminal_turn": 20},
    {"seed": 8, "status": "complete", "returncode": 0, "terminal_turn": 20}
  ]
}
```

The parent and every unique seed execution must succeed and reach the requested
terminal turn. A zero parent exit cannot hide a failed worker, timeout, missing
seed record, or short run. Source, binary, and config attestations must equal the
independently pinned run identities. Preserve actual failures as evidence.

## Seal once, then review

Write a plan with exactly the manifest fields, leaving `members` empty:

```json
{
  "schema_version": 1,
  "lane": "my-lane",
  "baseline_domain": "public-edf7299",
  "policy_sha256": "INDEPENDENTLY_APPROVED_POLICY_SHA256",
  "members": {},
  "runs": {
    "baseline": {
      "source": {"commit": "FULL_COMMIT", "tree": "FULL_TREE", "files": {"src/chronicler/simulation.py": "SHA256"}, "checkout": "frozen"},
      "native": "native/chronicler_agents.so",
      "config": "config.json",
      "process": "baseline-process.json",
      "table": "baseline.csv"
    }
  },
  "original_baseline": "preserved-original.csv"
}
```

The following uses shell variables whose values must come from the independently
approved policy and actual source repository:

```bash
python scripts/admit_experiment.py seal \
  --root /path/to/read-only-evidence \
  --policy /path/to/approved-policy.json --policy-sha256 "$approved_policy_sha256" \
  --source-repo baseline=/path/to/source-repository \
  --plan /path/to/plan.json --manifest /path/to/new-frozen-manifest.json
```

`seal` computes member hashes, validates the full package, and exclusively creates
the new manifest. It refuses to overwrite an existing manifest. Its JSON output
contains the exact manifest SHA-256 and `READY_FOR_REVIEW`. It never creates
approvals. Add `--source-repo candidate=/path/to/candidate-repository` for another
run. `--source-repo` must cover every run exactly once.

Before review, check readiness without writing:

```bash
python scripts/admit_experiment.py validate \
  --root /path/to/read-only-evidence \
  --policy /path/to/approved-policy.json --policy-sha256 "$approved_policy_sha256" \
  --source-repo baseline=/path/to/source-repository \
  --manifest /path/to/new-frozen-manifest.json --evidence-only
```

For final admission omit `--evidence-only` and supply one `--receipt` per tier.
Without receipts the result is `REVIEW_REQUIRED`, exit 3. Each final receipt has
exactly these fields:

```json
{
  "schema_version": 1,
  "tier": "tier1",
  "reviewer": "fresh-reviewer-a",
  "status": "approved",
  "evidence_sha256": "SHA256_OF_FROZEN_MANIFEST_BYTES",
  "policy_sha256": "INDEPENDENTLY_APPROVED_POLICY_SHA256",
  "dependencies": {}
}
```

Tier 2 has a different reviewer and `dependencies: {"tier1": "SHA256_OF_FINAL_TIER1_RECEIPT_BYTES"}`.
Any later tier must bind **all** preceding final receipts. CLI receipt argument
order is irrelevant; policy tier order determines dependency order. Receipt bytes,
including formatting, are frozen after completion. Review statuses other than
`approved`, stale/missing hashes, duplicate tiers/reviewers, missing upstream
dependencies, and self/cyclic references fail closed.

This ordering avoids the provisional-receipt hash trap: finish tier 1 first,
then let tier 2 hash those final bytes. If tier 1 changes, tier 2 must actually
review the revised dependency and issue a new final receipt. The tool never
updates receipt hashes, accepts provisional receipts, or hashes a manifest that
contains its own receipt. Changing manifest bytes requires every tier to repeat.

Receipts provide integrity/dependency binding, **not signatures or reviewer
authentication**. Distinct reviewer strings alone cannot prove independent humans
or agents reviewed a package. Use receipts issued through a trusted review channel
and retain that channel's provenance. This CLI does not authorize publication,
merge, default promotion, or external sharing.

## Results, API, and regression checks

All validation output is JSON on stdout. Exit 0 means `READY_FOR_REVIEW` in seal or
evidence-only mode, or `ADMITTED` when all final receipts pass. Exit 2 means
`REJECTED`; exit 3 means valid evidence still needs reviews. CLI usage errors use
argparse's normal exit 2 and stderr. Validation never writes inputs; sealing only
creates the requested new manifest. Freeze inputs while validation/review runs;
this is a local snapshot check, not a transactional filesystem lock.

Reusable Python entrypoints are `validate_policy`, `validate_source`,
`validate_identity` (binary/config), `validate_table`, `validate_evidence`, and
`validate_receipts`. They raise `AdmissionError` for contract violations. Callers
of `validate_evidence` must independently verify the raw policy hash; the CLI
does this before parsing. Callers must treat returned readiness separately from
receipt admission and scientific gates.

```bash
python -m unittest discover -s tests -p test_evidence_admission.py -v
```

The suite uses literal authored CSV/process fixtures and temporary Git commits.
It exercises rehashed bad evidence, omitted/duplicate rows, counts, undefined and
rounded ratios, altered originals, stale identities, failed/short workers, hidden
index flags, path aliases, strict JSON, and the two-phase CLI/review lifecycle.
It performs no scientific cohort run and makes no cross-baseline scientific claim.
