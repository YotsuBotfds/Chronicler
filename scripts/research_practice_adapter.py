"""Caller-owned study bridge: actual prephysics counter, then one observer call."""
from __future__ import annotations

import os
from pathlib import Path

if __package__:
    from . import research_practice_recorder as R
else:
    import research_practice_recorder as R


class StudyPracticeOwner:
    def __init__(self, folder, *, seed, role, observer, expected_checkpoint_effort=None):
        R.require(type(seed) is int and seed in R.SEEDS and type(role) is str and role in R.ROLES,
                  "unregistered study owner")
        self.folder, self.seed, self.role, self.observer = Path(folder), seed, role, observer
        R.require(expected_checkpoint_effort is None or type(expected_checkpoint_effort) is int,
                  "checkpoint effort is not a typed integer")
        R.require(role == "parent" or expected_checkpoint_effort is not None,
                  "fork requires the actual restored checkpoint effort")
        self.expected = None if expected_checkpoint_effort is None else R.uint(expected_checkpoint_effort)
        self.start = 0 if role == "parent" else 60
        self.recorder, self.baseline, self.pending = None, None, None
        self.attempted, self.completed, self.failed, self.closed = 0, 0, False, False

    def run_turn_result(self, world, *args, **kwargs):
        try:
            R.require(not self.closed and not self.failed and self.pending is None,
                      "study owner cannot repeat or skip a turn")
            R.require(type(world.seed) is int and world.seed == self.seed, "study seed differs")
            source = R.uint(world.turn)
            R.require(source == self.start + self.completed < R.END, "study source clock differs")
            if self.recorder is None:
                # execute_run has generated/restored/configured this actual World.
                # No guessed fresh counter and no caller-supplied substitute.
                actual = R.uint(world.scientific_claims.effort_spent)
                R.require(self.expected is None or actual == self.expected, "checkpoint effort differs before physics")
                self.recorder = R.PracticeRecorder(self.folder, seed=self.seed, role=self.role,
                                                   initial_effort_spent=actual)
                self.baseline = dict(schema_version=1, seed=self.seed, role=self.role, source_turn=source,
                    initial_effort_spent=actual, expected_checkpoint_effort=self.expected,
                    clock="immediately before first actual observer/physics call")
                with (self.folder / "practice-counter-baseline.json").open("xb") as stream:
                    stream.write(R.encoded(self.baseline) + b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            self.attempted += 1
            result = self.observer.run_turn_result(world, *args, **kwargs)
            R.require(type(world.turn) is int and world.turn == source + 1 and
                      type(result.observation.source_turn) is int and
                      type(result.observation.completed_turn) is int and
                      result.observation.source_turn == source and result.observation.completed_turn == source + 1,
                      "observed result/world clock differs")
            self.completed += 1
            self.pending = source
            return result
        except BaseException:
            self.failed = True
            raise

    def record_turn_end(self, world):
        try:
            R.require(not self.closed and not self.failed and self.recorder is not None and
                      self.pending is not None and type(world.turn) is int and world.turn == self.pending + 1 and
                      type(world.seed) is int and world.seed == self.seed,
                      "completed study boundary differs")
            frame = self.observer.read_latest(expected_source_turn=self.pending)
            record = self.recorder.append(frame, source_turn=self.pending,
                                          effort_spent=world.scientific_claims.effort_spent)
            self.pending = None
            return record
        except BaseException:
            self.failed = True
            raise

    def finish(self):
        try:
            R.require(not self.closed and not self.failed and self.pending is None and
                      self.completed == R.END - self.start and self.recorder is not None,
                      "study owner did not finish its registered window")
            return self.recorder.finish()
        except BaseException:
            self.failed = True
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.observer.close()
            finally:
                if self.recorder is not None:
                    self.recorder.close()

    def __getstate__(self):
        raise TypeError("study practice owners are transient caller state")
