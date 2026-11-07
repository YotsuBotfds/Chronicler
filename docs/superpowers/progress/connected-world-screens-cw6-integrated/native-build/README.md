# Native artifact used for CW6 preflight

The release artifact was built from native source commit `9e001701` in the dedicated evidence environment. The build owner independently checked all 56 Rust/build inputs in the evidence, lead and CW6 worktrees against that commit, retaining the aggregate path-and-content digest and actual build log in `receipt.json`. The compiled extension SHA-256 is `59f536b8f4a6c2bc82c51eeaec55f3aff6b0a1c5c8f1a324049ad15b42c51617`.

This proves which native source/artifact the early schema and serialization checks used. It does not establish final Python-source validation, scientific qualification or any held-screen result. Verify the unchanged native input tree and this artifact identity again at the final pilot/held source freeze. The temporary wheel path in the historical log is preserved as recorded; no binary is committed.
