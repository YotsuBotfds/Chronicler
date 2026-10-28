# Community minimum-size capacity diagnostic

Run the detached reader against an existing validation report:

```sh
python -m chronicler.community_admissibility path/to/validation_report.json
```

It caps input at 64 MiB, emits JSON on stdout with the input SHA-256, and
writes no files. It invokes neither simulation nor oracle detection.
The hash identifies the bytes read; it does not independently verify provenance.

Community method 2 requires at least five members and a community share
at most 5% of regional living agents. Five members require a regional
population of at least 100. The reader uses existing method-2 counters:

| Saved counter | Meaning |
| --- | --- |
| C: spec.communities | Detected community/snapshot observations |
| L: communities_in_regions_of_at_least.communities | Observations in regions with at least 100 living agents |
| A: region_share.communities_above | Observations exceeding the 5% share bound |

The output separates C−L structurally forced share failures, A−(C−L)
failures despite enough population for a group of five, and C−A observations
within the share bound. Counts must be nonnegative integers with consistent
totals and the expected saved population threshold. Boolean and floating
aliases, contradictory PASS/share counters, and malformed known structures fail.

The denominator is repeated detected-community/snapshot observations.
It is not independent communities, all regions, or all opportunities for
community formation. Regions without detected communities are absent.
A larger detected community can exceed 5% even in a region above 100.

Zero observations remain `no_observations`, with no estimated fraction.
Legacy, unsupported and skipped evidence remains unavailable. Existing report
and gate verdicts are untouched. An assessed diagnostic is not a qualification.

Minimum-size capacity is necessary, not sufficient, for satisfying the
share criterion. It says nothing about detection, shared memories, the
unscaled global count band of 3–15, or the other oracle criteria. Expanding
population does not predict a PASS. Any new higher-density validation
scenario needs prospective registration and its own qualification.

The population constraint was already documented in
[the spec-community record](spec-communities.md). This tool makes the existing
distinction reproducible from saved counters; it does not claim a new discovery.
