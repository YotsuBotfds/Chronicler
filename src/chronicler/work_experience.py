"""Optional A6 planner adapters; no decision or accounting authority here.

Keep fully observed personal money separate from group receipts. Unknown
counterfactual titles and combined paid-work shares remain unknown.
"""
from __future__ import annotations


def _module(world):
    state = getattr(getattr(world, "livelihoods", None), "adaptive_livelihoods", None)
    if state is None or not state.enabled:
        return None
    from chronicler import adaptive_livelihoods
    return adaptive_livelihoods


def active(world):
    return _module(world) is not None


def accepts_offer(world, agent_id, kind):
    module = _module(world)
    return module.accepts_offer(world, agent_id, kind) if module is not None else True


def record(world, agent_id, kind, *, paid_milli, receipt, share, region, occupation=None, source):
    module = _module(world)
    if module is None:
        return
    observed = receipt.get(agent_id) if receipt is not None else None
    withheld = round(observed[2] * 1000) if observed is not None and abs(observed[0]-share) <= 1e-6 else None
    title = module.forgone_title(world, region, occupation=occupation) if occupation is not None else None
    module.note_work(world, agent_id, kind, paid_milli=paid_milli, withheld_milli=withheld,
                     title_forgone_milli=title, source=source)


def occupations(snapshot):
    from chronicler.columnar import batch_arrays
    arrays = batch_arrays(snapshot, ("id", "occupation"))
    return dict(zip(map(int, arrays[0]), map(int, arrays[1]), strict=True)) if arrays is not None else {}
