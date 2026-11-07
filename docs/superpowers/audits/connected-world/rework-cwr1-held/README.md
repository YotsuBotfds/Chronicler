# CWR1 bounded held screen: start receipt

The preregistered screen started **2026-11-07T22:41:33Z** at immutable source
`b45c1e99572d4d6a60fb01fbd75cb7688aa54e93`, with protocol SHA256
`51b8a336969f48b4beb6f5b3e543062eda71822b98513b337ceb2d010e6efe7a`
and receipt identity
`98c7bb2accb18b04e68f0585780ba58f85f03ece77c987d82ff67ceb7d9370a8`.
The reviewed source is production/scripts-equivalent to runtime `8792be88`.
The native artifact is `b1d3ea5…`, with the same 57-file `f55df55…` input
receipt and separately verified native crate pyproject.

This start is **not a result or completion receipt**. It records twelve fresh
worlds, all twelve arms, 120 turns each: 144 planned cases. Template seeds
4101–4106 and procedural seeds 4201–4206 were registered before the source-
bound pilot. The full matching 24-case pilot passed with a 1.383-core-hour
projection after its fixed 1.5 margin, below the unchanged two-hour cap.
No default was promoted and neither restricted qualification gate is run.

The [start record](start.json), [source snapshot](source-start.txt), actual
[launch arguments](launch.json) and independently reviewed
[wrapper](run-bounded-held.py) preserve the live execution boundary. The
generic runner owns its normal start ledger and budget enforcement. The
wrapper adds source/native/protocol and matrix checks, scoped CPU/wall/RSS
measurements, and captures report stdout directly as Markdown. It does not
edit or mark the seed registry.

All raw output and live metrics are under
`/workspace/evidence/cwr-evaluation/held-cwr1-b45c1e99-v1/`.
The frozen checkout is `/workspace/cwr-held-runtime`; its local generic ledger
is `output/held-runs/ledger.jsonl`. The integration owner is the sole registry
writer. From this start the reservation is potentially spent, including if
the process is interrupted. Preserve failures, nulls and unrun cases; do not
replace seeds, tune the model or increase the cap after starting.

For recovery, inspect the existing output and ledger, check the same
source/native/protocol identities, and resume that recorded run through the
unchanged generic runner if it is recoverable. Do not launch a new output
directory for the same cohort. If the environment is unavailable, the
integration owner must record the limitation and treat the started cohort
conservatively; this receipt does not promise automatic restart.

Complete results, independent arithmetic/raw review and the lead's final
`mark-run` disposition must be added after the actual process closes. No
fresh effect estimate is claimed by this start receipt.
