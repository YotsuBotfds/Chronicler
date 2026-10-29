# Deployment diagnostic: unprivileged PID1 namespace read denied

The single diagnostic completed successfully and its small artifact was
independently verified. In this current runner, reading PID1's cgroup
namespace returned `EACCES` (`errno 13`) on both attempts. Namespace equality
remains unknown. The result is observation-only and grants no deployment,
audit, baseline reuse or candidate-world admission.

| Evidence | Exact identity |
| --- | --- |
| Prepared source | `13491af1af0990927597ace596e605a4dc10d880` |
| Activation source | `cc2fea8042bf8dd4a61cdbe0235aa3831cba6382` |
| Run / attempt | [40817163080 / 1](https://github.com/YotsuBotfds/Chronicler/actions/runs/40817163080) |
| Job | `123260833950`, Deployment-only observation |
| Official job timestamps | 2026-10-29 04:20:12–04:20:21 UTC, nine seconds |
| Published artifact | `12872628853`, 1,014 bytes; expires 2026-11-28 04:20:17 UTC |
| ZIP SHA-256, independently matched to API | `86402cfac5fbd9945a376be0fcc5846dee042142e7dab65b57a8cad2710a9df0` |
| Typed member | `wealth-floor-deployment-diagnostic.json`, 1,915 bytes |
| Member SHA-256 | `e9f241c95a474a420e3233ba5682c8973858dfd185fe99921157c4563d9bd9c6` |

| Current observation | Result |
| --- | --- |
| Runner flags | `GITHUB_ACTIONS=true`, `RUNNER_ENVIRONMENT=github-hosted` |
| PID1 comm | `systemd`, valid shape and stable reread |
| Self cgroup namespace | Valid format and stable reread |
| PID1 cgroup namespace | Initial and repeated readlink denied, `errno 13` |
| Namespace equality | Unknown |
| First predicate evidenced by this diagnostic | `initial_read_unavailable` |
| Visible memory observation | 3 visible ancestors; no finite cap observed in their returned limit rows |
| Host/visible available bytes | 15,788,949,504; invisible provider limits remain unobservable |
| Observed metadata | 7,003 bytes within the 65,536-byte cap |
| CPU policy | One process pinned to CPU 0; affinity count and thread caps one |

The shared helper's ordered predicate model cannot establish its required
cross-PID namespace identity from these observations. All reads used ordinary
unprivileged access, and denied reads were recorded without elevation. Any
future admission design must explicitly retain that unavailable fact and its
VM/provider scope; this readout changes no assumption or guard.

The earlier `9aae9ab1` audit/run `40815630794` retains its original broad
`deployment_refused` result and unknown failed predicate. This fresh runner's
observations do not retroactively establish that older job's cause. Both
shared helpers remain byte-identical; no same-source rerun was launched.

Before this activation, the actual workflow copy passed all 88 guarded cases
in 0.19 seconds, unfiltered actionlint, diff checks, exact template equality
and unchanged source/helper hashes. Independent artifact review matched the
complete ZIP bytes to the official digest, checked its single safe member's
CRC/size/EOF, parsed strict typed JSON and matched the member bytes exactly to
the official decoded job log. The observation's approximately 0.00205-second
wall sample precedes output; it is not a closed job or CPU measurement.

The failed byte-audit activation, diagnostic activation and prepared sources
remain frozen. This result is published on a separate docs branch. The
diagnostic had no token, HTTP, historical archive, build, native, world or
privilege-elevation path. No real host probe ran locally. The small output
artifact was downloaded only for the authorized independent review. Main,
the original comparator, held native correction and historical kin-root
causal failures are unchanged.

The external verification receipt is SHA-256
`9f853a881dd61a9a7a24f072a33a7d360129a488e27be26c809bfd7946838fc0`.
It preserves official run/job/artifact JSON, decoded logs, the original ZIP,
typed member and their hashes. Original expiry and observation-only standing
remain explicit.
