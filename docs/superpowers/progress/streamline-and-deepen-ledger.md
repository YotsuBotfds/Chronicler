# Streamline and deepen — integration ledger

The lead session's dated record of what was integrated on `claude/exciting-mayer-nolksw`, how each piece was reviewed, and which gates ran. Nothing here is merged to `main`. Opening PRs is the owner's call. Decisions are in [streamline-and-deepen-decisions.md](streamline-and-deepen-decisions.md) and statuses in [streamline-and-deepen.json](streamline-and-deepen.json).

**Process for every task**
- An implementer works on its own branch `sd/<task>` from the roadmap plan block, in an isolated worktree.
- An independent reviewer then re-runs the checks. Corrections and the pin transition get two reviewers, one for scope and behaviour and one for repository contracts.
- Up to two fix and re-review rounds follow.
- The lead merges only approved branches, with `--no-ff`, so each reviewed head stays in history. The lead then runs the gates below on the merged head.

**Shared identity baseline.** All nine `scripts/turn_speed_identity.py` cases were run from `4e8e76b7`, with the native extension built from that tree (SHA-256 `2125dfd7b5f9e2091ac70fad5f08709c14d2e553ab65691f7638d219e9c22641`). The run used Linux and the cloud container's Python 3.13.18.

## 2026-11-09 — integration 1 (R1/R2, first batch)

Merged, each approved by an independent reviewer with no blocker or major findings:

| Task | Reviewed head | Class | Notes |
|---|---|---|---|
| HYG-2 | `a00ada41` | config | `.gitignore` additions; `git ls-files -ci --exclude-standard` is empty |
| DEAD-3 | `48108143` | removal | Dead Rust helpers removed; five test-only functions put under `cfg(test)`; `cargo check` gives 0 warnings |
| FIX-6, FIX-13 | `a4e37a63` | fix | `settle_food_purchases` returns `Err` before any pool write; `+0.0`-normalised `total_cmp` comparators at the six sort and argmax sites |
| DEAD-2a | `a457aab5` | removal | Dead Python leaf helpers removed from 10 modules, with their tests |
| FIX-4, FIX-5, FIX-12, FIX-2 | `e54095ca` | fix + test | M53 record YAMLs moved to `docs/validation/m53/`, with a clean-load test; historiography and languages sidecars made atomic; FIX-2's audit claim was not reproduced (`CAPTURED` moves ownership, not stock), and a test pins the residual |
| FIX-9 | `686c1224` | fix | LLM client timeout (120 s), truncation counts, token and call budgets, batch poll deadline; narration only |

Gates on the merged head `e4557096`:
- `scripts/refactor_preflight.py --git-diff 4e8e76b`: no content pin and no recorded digest touched. The only `enforced` items are native-shard and oracle-chunk ownership of eight test modules that were edited in place, which is allowed.
- `scripts/run_python_oracle_checks.py --jobs 2`: PASS in 237.4 s. 76 chunks; 8,139 passed, 69 skipped, 0 failed. The 110 s limit is unchanged.
- `cargo test --locked`: every test binary passed (library 779 passed).
- The native extension was built fresh from `e4557096`. Its SHA-256, `97049985efadbee551631cb3166267f8c8cc403eb1c418b80db8ecafd2e7c6f8`, matches the FIX-6 implementer's independent build. `check_python_env.py --expect native` passes.
- `turn_speed_identity.py`, all 9 cases against the baseline: **399 files compared, 0 differences**. This covers the cases the FIX-6 review noted as unrun (off_s7, proc48_off_s7, scaled22k_s42 and scaled52k_s7).

Not run: viewer lanes (no viewer change in this batch), the 200-seed gate (no outcome change intended), and GitHub CI (no PR).

Integration notes:
- A disk-full error during workflow A stopped worktree creation for HYG-1/HYG-3, HYG-5/HYG-6, DEAD-2b, DEP-7 and the FIX-7 review. They were relaunched, and those agents now remove their venvs when they finish.
- FIX-7 is held back for the scope ruling recorded in the decision record.
