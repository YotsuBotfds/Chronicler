# One deployment-only diagnostic activation

Root cleared prepared source
`13491af1af0990927597ace596e605a4dc10d880` and authorized one observation on
the separate `lead/wealth-floor-deployment-diagnostic-activation-20261029`
branch. The dormant template is copied byte-for-byte to its registered active
workflow path. Scripts and both shared helpers remain unchanged.

Before one activation push, the full 88-case guarded selection, unfiltered
actionlint and diff checks must pass against the actual workflow copy, with
exact template equality and unchanged prepared-source hashes. No remote
outcome is claimed by this registration. The first result is retained without
a same-source rerun.

Final actual-copy checks passed: 88 guarded cases in 0.19 seconds, unfiltered
actionlint and diff checks, byte-identical template/body, and unchanged script
and helper hashes. The guard recorded no native activity, blocked IO or
runtime-factory calls.

The diagnostic observes only registered categorical runner/PID1/namespace
metadata and bounded shared memory observations. It grants no admission and
has no token, HTTP, archive, build, native, world or privileged-read path. It
does not retroactively assign a cause to the earlier `9aae9ab1` refusal.
The failed audit, prepared refs and main remain preserved. No real probe ran
locally.
