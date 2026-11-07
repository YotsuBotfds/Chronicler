# Independent pre-held freeze review

Concrete freeze `d791dc2e` with provenance correction `20722d5e` is approved.
The protocol is SHA256 `51b8a336969f48b4beb6f5b3e543062eda71822b98513b337ceb2d010e6efe7a`.
The [receipt](rework-pre-held-freeze-review-2026-11-07.json) records exact
pilot/runtime identities. This review ran no simulation or held seed.

The actual protocol diff changes only DRAFT to FROZEN and appends the reviewed
runtime/pilot receipt. Runtime 8792be88 is unchanged in production/native/scripts.
All twelve controls, three primaries, all-world enrollment, 120-turn horizon,
fresh 4101–4106/4201–4206 cohorts, default-off behavior, two-hour cap and fixed
1.5 margin remain unchanged. No outcome-dependent adjustment was introduced.
The earlier 52-reference reservation check remains the source of cohort freshness.

The pilot contains exactly 24 distinct successful arm/world rows. Metrics and
report hashes match the frozen receipt. Independent timing recomputation gives
484.7 simulation + 68.5 extraction = 553.2 seconds; six held worlds per stratum
project 0.922 core-hours, or 1.383 with the fixed 1.5 margin, below 2.0. The
independent stdlib checker was rerun against the actual pilot and exact frozen
protocol: PASS, 24 rows, no errors in 0.56s. It checks controls, rates/nulls,
contrast arithmetic and report rows without Chronicler/native imports.

The original launch receipt's null report hash remains truthful and preserved.
Successful report stdout was published byte for byte, with a separate copy/hash
receipt. One provenance overclaim was caught: the pilot requested no private
checkpoints and actually has zero .ckpt files. The corrected README now names
bundles, Arrow event sidecars and JSON world states for all 24 cases and assigns
private-state evidence to the separate profile/resume gates. This changed no
model, output, source, control or budget.

The complete-window viewer follow-up also has delegated independent approval.
Its corrected counter is **2,163 = 2,142 + 21**, with 3,808 independent adjacent-
snapshot comparisons. The original 2,392 was inflated by 229 because a complete
sparse empty current region became null while its prior equivalent became zero.
Correction 1168a2e1 applies consistent empty-region semantics and checks the
next saved PH frame. The invalid receipt is preserved byte for byte. All 3,840
prior-frame assertions and 372 browser assertions remain unchanged. Six initial
history-navigation harness failures remain retained; no UI/model change or new
simulation was used for the corrected evidence.

The lead must integrate the arithmetic checker, freeze and provenance documents
and run the final live source/native/registry/pilot compatibility preflight
before the bounded 144-run held screen. Actual enabled resume execution, held
outcomes and final reviewed-head/main CI remain separate gates. This approval
neither runs the restricted qualifications nor promotes defaults.
