# First retained-baseline byte audit: deployment admission refused

The single authorized activation **failed deployment admission** before any
historical archive transfer or audit. No audit or baseline reuse is qualified.
The first failure is preserved; no same-source rerun was launched.

| Identity | Exact evidence |
| --- | --- |
| Prepared source | `0cd031093514106f910404a20e96a3df92993acf` |
| Activation source | `9aae9ab1ca5114b4ec4fd3bdb5348934dfc7b714` |
| Run / attempt | [40815630794 / 1](https://github.com/YotsuBotfds/Chronicler/actions/runs/40815630794) |
| Job | `123255889667`, Retained baseline byte audit |
| Official job timestamps | 2026-10-29 04:04:07–04:04:15 UTC, eight seconds |
| Explicit audit step | Failed at 04:04:12 UTC |
| Published artifacts | Zero |
| Job script SHA-256 | `58dda4aba3b79bae94f9e42a36cee6de06d1334db5459047830c87748d9e6589` |
| Active workflow/template SHA-256 | `d8db8801d30819bc24e34b46edc23ca2388c9e60192f93cdb60ae9aa95b7ae42` |

The official log emitted this bounded refusal:

```json
{"artifact_id":null,"candidate_worlds_enabled":false,"http_status":null,"kind":"wealth-floor-baseline-audit-refusal","reason":"deployment_refused","response_bytes_received":null,"schema_version":1,"stage":"admission","status":"refused"}
```

Checkout, CPython 3.13.17 setup and the inert default succeeded. The explicit
audit command then returned exit code one. Publication found no files, and the
official artifact API confirms an empty artifact list.

The exact frozen call order invokes the shared hosted-VM precondition before
controller source snapshots, the RAM/disk resource probe, client construction,
staging or HTTP requests. Its `DeploymentRefused` exception produces the
observed receipt. Thus this attempt downloaded zero historical archives,
prepared no historical plan and audited no raw payloads. It built no native
binary and ran no world.

The particular failed predicate is **unknown**. The broad category does not
distinguish runner environment, PID1 identity, namespace shape/match, read
failure or changing observations. It also does not establish which deployment
proc reads occurred. The eight-second job duration is the failed admission's
elapsed time; it is not archive throughput or an audit speed measurement.

Before the one push, all 207 guarded cases passed in 0.96 seconds against the
actual active workflow copy. Unfiltered actionlint, diff checks, exact
workflow/template equality and unchanged reviewed-source hashes passed. These
local pure checks qualify the control contracts; actual hosted deployment
compatibility remains unqualified. Candidate-world proof pins remain null.

Original source refs and the failed activation ref remain frozen. This readout
lives on a separate docs branch. Original D028 candidate roles, artifact IDs,
expiry, strict decisions and kin-root causal failures are unchanged; the
original comparator, held native correction and main are untouched.

The next useful diagnostic would be a separately reviewed deployment-only
control: categorized runner flags, bounded PID1 identity and self/PID1 cgroup
namespace observations with stability rereads. It would need no archive token,
archive transfer, build or world. No such diagnostic or guard change is
activated by this readout.

The external failure receipt is SHA-256
`36c73a8bf676b34267c1afb83e9cb9a814e813fecc00b16d46f970aac38d4826`.
Its retained official MCP-decoded UTF-8 job log is SHA-256
`486f9b0d2e01d7aa146345c3cb9d893be7d4bdac58fb46a606018de878e972eb`.
Official run/job/artifact JSON, original refusal and pre-push guard/lint/source
proofs remain external. No artifact ZIP was downloaded or independently
rehashed for this result because none was published.
