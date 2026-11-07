# Downstream C2 exposure regression

Reviewed runtime base: `2ec3f31069221748b84176226ebde909dfae9169`.
No production, native, registry or manifest change is made here. The existing
`test_residence_exposure.py` module gains two integration cases, running the
real `epidemiology.tick_epidemics`, `_introduce` and `_step` implementations.
Wrappers record their inputs and call the original functions; disease cases
and mortality still use the existing regional epidemic authority.

The constructed comparison moves the same 130 stable identities from Avalon
to Brook, once with a recorded hunger driver and once with an unknown reason.
Final residence/population, carrying capacity, food shortfall, urban share,
initial plague/flux fractions, prior sanitation and prior C2 capacity are
identical. Constructed capacity is a test input, not evidence of paid carers.
The X1 frame, sanitation and care capacity are all dated T−1; the real guarded
reader and capacity consumer run at T. No same-turn frame is read.

In corrected `density_only` mode, introduction susceptibility is **1.75** in
both worlds. The actual SEIRS step receives identical plague/flux inputs and
produces identical positive case counts. Hunger, population/capacity and urban
susceptibility remain non-neutral. Care capacity is consumed exactly once and
reduces the independently composed fatality factor to **0.77** in both worlds;
flux additionally retains the separately modeled sanitation reduction. The
explicit `legacy_displacement` case retains **2.1875 versus 1.75** introduction
susceptibility and higher plague and flux cases for the known-reason cohort.
This is a one-tick regression, not a population-health or mortality evaluation.

A failing-old-code check substituted only the real `environment_factors`
implementation from main `2726bf449d0e4d581a72034000ee0861a58ee439`, retaining
all current epidemic and care code. The density-only regression failed at the
downstream introduction-input equality:

```text
assert (2.1875, 0.77, True) == (1.75, 0.77, True)
1 failed, 40 deselected in 0.19s
```

That old reader's complete source SHA256 is
`5e68aec3104902baf012e20225bd5801f60dd63333f59375a1224a60ebc71ea8`.
The historical substitution does not implement a toy alternative or patch
physical moves, disease dynamics, care or mortality.

Current focused result: **41 passed in 0.33s**, including the two new cases.
Commands used `PYTHONPATH=/workspace/cwr-c2-trace/src` and the separate
no-native Python environment; no simulation screen, browser, native build,
held seed, qualification gate or paid call was used. External raw receipt,
old-reader pytest adapter and output are retained under
`/workspace/evidence/cwr-c2-trace/`; their persistence after container recovery
is not promised.

Reproduce the current regression from this source with:

```sh
PYTHONPATH=src python -m pytest -q tests/test_residence_exposure.py
```

For the failing-old-reader check, a pytest plugin can load
`git show 2726bf449d0e4d581a72034000ee0861a58ee439:src/chronicler/public_health.py`
into a separate module and monkeypatch only
`chronicler.public_health.environment_factors` to that module's function in an
autouse fixture. Run the density-only parameter of
`test_move_reason_traces_through_real_epidemic_introduction_and_case_dynamics`.
The retained adapter performs precisely this substitution; the old reader
ignores the new configuration field, reproducing the original coupling.
