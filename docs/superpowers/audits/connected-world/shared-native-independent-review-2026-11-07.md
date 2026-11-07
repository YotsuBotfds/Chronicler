# Connected World shared native source review, 2026-11-07

Independent reviewer: B3 integration agent (author of none of the native or
wealth-accounting changes below). Reviewed actual commits, surrounding source,
specifications and tests in `/workspace/cw-evidence`, rather than a board summary.

Source approval covers `7009187c` (native wealth stages, army service and adaptive
inputs), `10dde332` (dated movement branch inputs), `7aed96dd` (dated individual
information), corrected by **`9e0017017245870affa0401714d14cddccf98ff7`**. The related
Python signed treasury seam correction **`2dcb2ce298d8f12902b9d711eaa8c6a47b2fa2d1`**
was separately reviewed and approved. This records source review, not completion
of integrated verification, main CI or qualification.

Reviewed contracts include exact native wealth stage operands and transfers;
army ration/civilian population/farm income separation; stable agent identities;
whole-batch FFI validation and stale-turn refusal; transient input consumption and
checkpoint omission; dated branch permission and current public boundary checks;
A6 own residence/prior bonds/unexpired packets, home-prior treatment of unknown
foreign regions; and independent primary movement/refusal receipts. D3's optional
suppression of the historical global soldier-at-war mortality multiplier is
explicitly active only on the opted-in D3 path. No silent default correction was
approved.

The initial A6 source attributed its personal score delta to packet news and
could label a changed target religious. This was a blocking review finding.
`9e001701` separates packet news before the adaptive delta and tests a no-packet,
no-faith target change with zero news and false threat/religion flags. Because
the legacy raw decision observer and migration driver budget have no independently
declared A6 term, active adaptive input now refuses them explicitly, in both FFI
configuration orders. Unknown information or selected personal effects are not
invented food/news/religion contributions. Empty record-only adaptive input retains
decisions, RNG and encoded legacy driver bytes.

The Python wealth package seam initially treated negative payer treasury units
as credits. `2dcb2ce2` corrects both closure and per-civilization charge signs;
the constructed regression uses a real negative treasury debit, accepted agent
credits and prepaid remainder.

No remaining source blocker was found on these exact corrections. The author
reported 774 Rust tests passing at the corrected native head and 30 wealth tests
passing at the signed-unit fix. Those are author-run checks, not independent
reruns. Native release/FFI checks and whole-program lifecycle, enabled exact
restore, feature-off identity, compatibility, declared-scale strict wealth
closure, provenance, browser and CI gates remain integration responsibilities.
The fixed absolute wealth closure tolerance particularly still needs exercised
at declared scale. This review consumes no held seeds and makes no efficacy or
qualification claim.
