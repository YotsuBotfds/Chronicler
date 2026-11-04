# Source-scoped CI and arc qualification — 2026-10-29

All six standard CI lanes passed at each of the four exact sources below.
The separate arc export study also completed its registered matrix. This pack
records those completed checks and official artifact publication metadata.

The [JSON companion](ci-arc-qualification-2026-10-29.json) retains full source,
control, run/job IDs, selected step timestamps, reported test clocks, archive
sizes/digests and expiry dates. Counts come from completed job-log summaries;
timestamps and artifact metadata come from the GitHub Actions API. Raw logs,
generated worlds, private paths and signed download URLs are not committed.

## Exact sources

- Recovered integration 49b: source and workflow control `49b2a35b0a1f4aae4d965d517df604880ea7546b`; [run 40792298299](https://github.com/YotsuBotfds/Chronicler/actions/runs/40792298299). Recovered finite research, reviewed cloud fixes, arc projection and viewer repairs.
- Recovered integration c76: source and workflow control `c76efe8552b4c6c288ebb1f813e2c0a58e5957b1`; [run 40793639813](https://github.com/YotsuBotfds/Chronicler/actions/runs/40793639813). 49b plus strict composition-proof observer/tests and deterministic opt-in relationship-statistics key ordering.
- Household wealth-floor correction 503: source and workflow control `503070175e3e78d9014add158ead8f16ce940843`; [run 40794594072](https://github.com/YotsuBotfds/Chronicler/actions/runs/40794594072). d028-based isolated intentional Rust behavior correction; no recovered research integration.
- Arc projection 249a: source and workflow control `249a4e1879cf5fbbb070de11f478f19825f51419`; [run 40791763886](https://github.com/YotsuBotfds/Chronicler/actions/runs/40791763886). d028-based arc event-type projection and frozen-source classifier parity tests.

Arc export study: simulation baseline
`d0281e5f57c508f27cea1676f36e0e6ed1225c9d`, candidate
`249a4e1879cf5fbbb070de11f478f19825f51419`; workflow control
`9e800f812dc884d70e16f49103e1542f6aface91`,
[run 40793636869](https://github.com/YotsuBotfds/Chronicler/actions/runs/40793636869).
The workflow control is distinct from both simulation checkouts.

This documentation branch starts at c76 and changes documentation only.
Availability on a review branch does not promote a default or approve a merge.

## Completed CI counts

Each Python cell is **parent tests passed / successful subtests / skipped**.
Offline cells are **chunks; passed / skipped**. Rust cells are full-suite
**passed / ignored**; viewer cells are **tests / files**. All viewer rows also
passed lint and production build; both upstream native jobs satisfied the
combined native requirement. No browser-session QA is included here. Counts are not summed across overlapping lanes
or different sources.

| Source | Native Python | No-Rust Python | Bounded offline | Rust | Viewer |
| --- | ---: | ---: | ---: | ---: | ---: |
| `49b2a35b` | 8,006 / 526 / 6 | 7,692 / 526 / 306 | 31; 3,898 / 65 | 1,088 / 2 | 743 / 69 |
| `c76efe85` | 8,023 / 526 / 6 | 7,709 / 526 / 306 | 31; 3,898 / 65 | 1,088 / 2 | 743 / 69 |
| `50307017` | 7,800 / 526 / 6 | 7,486 / 526 / 306 | 29; 3,697 / 65 | 1,092 / 2 | 703 / 67 |
| `249a4e18` | 7,808 / 526 / 6 | 7,494 / 526 / 306 | 30; 3,705 / 65 | 1,088 / 2 | 703 / 67 |

Wealth source 503 first passed four focused Rust regressions, then the full
Rust suite with 1,092 passes and two ignored cases. Those four focused tests are
already included in the full suite, rather than four additional unique tests.
The new correction addresses near-zero pooled wealth amplifying migration;
these CI passes do not establish its migration balance or full-population
outcome qualification.

## Observed clocks

All values below are wall seconds from this single run of each source.
A GitHub job includes setup/build/reporting; an enclosing test step also
includes interpreter/import and reporting overhead absent from pytest's own
clock. Queue time from run creation to first job start was only 2–3 seconds.

| Source | Native job | Wheel step | Native test step | Native pytest | No-Rust job | No-Rust test step | No-Rust pytest |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `49b2a35b` | 901 | 197 | 671 | 666.92 | 423 | 410 | 406.12 |
| `c76efe85` | 883 | 167 | 691 | 687.12 | 351 | 338 | 333.53 |
| `50307017` | 585 | 110 | 458 | 454.18 | 502 | 489 | 485.63 |
| `249a4e18` | 670 | 140 | 510 | 505.97 | 444 | 429 | 423.98 |

| Source | Offline job | Guarded runner step | Sum of printed chunk times | Slowest printed chunk |
| --- | ---: | ---: | ---: | --- |
| `49b2a35b` | 239 | 222 | 222.5 | systems-2: 37.4 / 110 |
| `c76efe85` | 230 | 213 | 212.4 | systems-2: 35.9 / 110 |
| `50307017` | 202 | 185 | 184.8 | systems-2: 32.2 / 110 |
| `249a4e18` | 221 | 206 | 206.7 | systems-2: 36.1 / 110 |

Chunk times are printed rounded values, so their sum need not equal the
enclosing step's whole-second timestamp difference. The per-chunk limit remains
110 seconds in every run. Other job/step timestamps are retained in JSON.

For c76 versus 49b, the native test step was 20 seconds longer, while its wheel
step was 30 seconds shorter; the complete native job was 883 versus 901 seconds.
This does not show a test hang or a controlled performance change. Different
sources, cache state and hosted-runner variability prevent using this table
as a speed benchmark.

## Fixed arc export identity

The producer passed **22 unittest contracts**, then completed all **18 simulations
and 3,200 actual physics ticks**: nine fixed cases at each frozen source. Cases
cover two off-mode 300-turn runs; three hybrid 200-turn runs; 48-region/10-civ
hybrid 150-turn and off-mode 200-turn runs; and 12-region/4-civ scaled runs of
30 and 20 turns. The latter's registered targets are 18,800 and 43,700; their
22k/52k case labels are not observed population counts.

One fresh wheel was shared between the sources. The producer checked actual
compiled classes/schema identities, source bytes/modes and clean standing,
case outputs/horizons, the frozen comparator, and final raw/audit/native/wheel
integrity. All cases completed and the producer's final qualification was true.
The sole normalized output field was `metadata.generated_at`; logs and
`run_manifest.json` were excluded by the existing comparator and retained
in raw evidence.

| Receipt | SHA-256 |
| --- | --- |
| Loaded native module | `06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6` |
| Shared wheel | `54616417b94036ec91a40b69b94ad2b608d3b66666c93dd2b20e05af176cc58f` |
| Payload inventory | `a64b3f4b3d208c6adcb78500e508eb1058cdc2fa5c261e50c3ab53bc89cfcb31` |

The helper reported 548.139856 seconds including build/probes/worlds/audits/final
checks; its enclosing step took 549 seconds and job 588 seconds. This is exported
file identity for the registered matrix in one environment. It establishes no
arc whole-workload speedup, cross-source complete checkpoint/RNG-state equality,
large-scale scientific outcome or natural optional-system efficacy.

## Published artifacts

All archives below were nonexpired and bound to the exact producing run/source
when this pack was prepared. Digests are **GitHub-reported ZIP digests**. This
pack did not download or independently rehash those archives. The arc producer's
own final payload audit is separate from an independent archive reinspection.

CI artifacts expire on 2026-11-12; the arc archive expires on 2026-11-28.
Exact publication/expiry timestamps and full names are in JSON.

| Evidence | Artifact ID | ZIP bytes | GitHub SHA-256 |
| --- | ---: | ---: | --- |
| 49b2a35b native | [12862592362](https://github.com/YotsuBotfds/Chronicler/actions/runs/40792298299/artifacts/12862592362) | 137,879 | `ef2ffa9f5183a85c03972129cae74aea4da4d6c08c8bbf2436e32efc010400a9` |
| 49b2a35b no-Rust | [12862517051](https://github.com/YotsuBotfds/Chronicler/actions/runs/40792298299/artifacts/12862517051) | 139,521 | `1540bb82e127a53d671f0e5f80e418e8354ca75e4c4e6f239daacb307e95aa55` |
| 49b2a35b offline | [12861673725](https://github.com/YotsuBotfds/Chronicler/actions/runs/40792298299/artifacts/12861673725) | 40,812 | `c84413bb54df618dcf79abd7981d25813d389d7bdc08ea69407fe93fcd454e43` |
| 49b2a35b Rust | [12861349842](https://github.com/YotsuBotfds/Chronicler/actions/runs/40792298299/artifacts/12861349842) | 516 | `c16a29a77b758227588200953388c13b4378f38a6e9cd277055de81a6dc50d50` |
| c76efe85 native | [12863811132](https://github.com/YotsuBotfds/Chronicler/actions/runs/40793639813/artifacts/12863811132) | 138,303 | `a78effb9fd321a29c24df0cd4f83c30ebe2658726284164042d4165955610a13` |
| c76efe85 offline | [12863400679](https://github.com/YotsuBotfds/Chronicler/actions/runs/40793639813/artifacts/12863400679) | 40,824 | `a1fdb97a0905a5cceb75ff89303d4b01a7524951bccfd83009ca14dd28764af7` |
| c76efe85 no-Rust | [12862703241](https://github.com/YotsuBotfds/Chronicler/actions/runs/40793639813/artifacts/12862703241) | 139,092 | `343735d74cb8e26461199432083bd4b521f01cb6d7b3e1554736182d55648b03` |
| c76efe85 Rust | [12862259474](https://github.com/YotsuBotfds/Chronicler/actions/runs/40793639813/artifacts/12862259474) | 517 | `18e4afbbfc8a3d218221da213f381f73878442ed3c4275caa56d714c74757248` |
| 50307017 offline | [12863930445](https://github.com/YotsuBotfds/Chronicler/actions/runs/40794594072/artifacts/12863930445) | 38,849 | `c82d06d03236435d584f45c73c33acee9fc960e09ad08dedc1724d104cdc4611` |
| 50307017 no-Rust | [12863846594](https://github.com/YotsuBotfds/Chronicler/actions/runs/40794594072/artifacts/12863846594) | 135,908 | `0808db17e8d5482b13da6d65b2654a6632c6ca4cf066b0d7d715775cc2804f1d` |
| 50307017 Rust | [12863556247](https://github.com/YotsuBotfds/Chronicler/actions/runs/40794594072/artifacts/12863556247) | 3,714 | `6769be9da66ae979055782a5a1c6af91d7477edcf272b5c584cd2a0660a97036` |
| 50307017 native | [12863004197](https://github.com/YotsuBotfds/Chronicler/actions/runs/40794594072/artifacts/12863004197) | 132,807 | `bc502444e929671c58b881265f3420668ee3003fa6c20062e776e43443c85ac2` |
| 249a4e18 no-Rust | [12862600651](https://github.com/YotsuBotfds/Chronicler/actions/runs/40791763886/artifacts/12862600651) | 135,830 | `66e1d78755ec6db4bbea915011528ac976270c9eaeadd4054be2bc19b122e5ed` |
| 249a4e18 Rust | [12862276355](https://github.com/YotsuBotfds/Chronicler/actions/runs/40791763886/artifacts/12862276355) | 522 | `779329ac50d889909eade426872e103f4050bd05fd733572fb4a3c5b47c1f79a` |
| 249a4e18 native | [12861993770](https://github.com/YotsuBotfds/Chronicler/actions/runs/40791763886/artifacts/12861993770) | 133,483 | `6d62891f91236eff3f3ad77d882b32bb253440aae1dcde753dbbf7e6f3f364ce` |
| 249a4e18 offline | [12861473849](https://github.com/YotsuBotfds/Chronicler/actions/runs/40791763886/artifacts/12861473849) | 39,584 | `2b4b8a84349ff63bb639cd906652ae8ff468aaf9ee953728eb4ce766182eb0e7` |
| arc identity | [12863585862](https://github.com/YotsuBotfds/Chronicler/actions/runs/40793636869/artifacts/12863585862) | 54,791,602 | `bfaa8fc0b7ae44fd9074c6ebad446706c8d0d95e62afdb09a1c8fb5654542d4c` |

## Qualification boundaries

The separate registered full-gate run 40791402289 freezes 2f9d618b versus d0281e5f.
Its result is not included here and does not qualify c76 or 503. The separate
c76 default-output identity run 40796958774 also has no result included in this
pack. Forkserver timing has its own source, experiment and readout. No artifact
or test result from one of those studies is substituted for another.

Main and every producer source branch remain unchanged by this documentation.
