"""Run lane chunks N at a time, in order, starting nothing new after a failure.

Used by ``scripts/run_python_oracle_checks.py --jobs N`` (N > 1). Each item runs
in a worker thread. A typical ``run`` starts a guarded pytest child process and
waits for it, so the threads only wait.

The items that run always form a prefix of ``items``:
- items start in order;
- once a result fails, nothing new starts;
- items already running finish.

The results come back in item order, so a receipt reads the same at any N.

Results are also published into ``results``, a dict the caller owns, as each item
finishes. On an exceptional exit (Ctrl-C, or an exception from ``run`` or
``passed``) the executor first lets the running items finish. Every item that
finished normally is then published before the exception propagates, so a caller
that writes its receipt in ``finally`` keeps them.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable, Sequence, TypeVar

Item = TypeVar("Item")
Result = TypeVar("Result")


def run_in_order(items: Sequence[Item], run: Callable[[Item], Result],
                 passed: Callable[[Result], bool], jobs: int,
                 results: dict[int, Result] | None = None) -> list[Result]:
    """Results of ``run`` for a prefix of ``items``, in item order."""
    if not isinstance(jobs, int) or isinstance(jobs, bool) or jobs < 1:
        raise ValueError(f"jobs must be a positive integer, not {jobs!r}")
    results = {} if results is None else results
    pending = iter(enumerate(items))
    running: dict = {}
    failed = False
    try:
        with ThreadPoolExecutor(max_workers=jobs) as pool:

            def start_next() -> bool:
                for index, item in pending:
                    running[pool.submit(run, item)] = index
                    return True
                return False

            while len(running) < jobs and start_next():
                pass
            while running:
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    index = running.pop(future)
                    results[index] = future.result()
                    failed = failed or not passed(results[index])
                while not failed and len(running) < jobs and start_next():
                    pass
    finally:
        # Normal exit: nothing is left here. Exceptional exit: leaving the ``with``
        # block waited for the running items, so publish those that finished normally.
        for future, index in running.items():
            if future.done() and not future.cancelled() and future.exception() is None:
                results.setdefault(index, future.result())
    return [results[index] for index in sorted(results)]
