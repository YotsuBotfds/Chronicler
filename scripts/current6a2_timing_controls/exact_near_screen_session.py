"""Selected original27f private-session primitives, never a simulator driver.

Original source27f0f3d11a1a171e1539353eb2c3a0fb896f0939, exact retained blob
05917006880c46a8f8b7ee4345293de61abb3a17 at1900bfadcbe34ed719f90d67affff4f7902529b4;
SHA256 e4ca3f0c3732e4b5536a88a6284ab44b173e2165fafb59586be02fbd1d015932.
Only the allowlisted definitions/methods below are retained verbatim. No probes,
worlds, old resource resolver, driver, CLI or original command launcher is kept.
"""
from __future__ import annotations
import os
from pathlib import Path
import signal

class Refusal(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def process_stat(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": int(pid), "state": fields[0], "pgrp": int(fields[2]),
                "session": int(fields[3]), "birth": int(fields[19])}
    except (FileNotFoundError, ProcessLookupError):
        return None


def session_live(sid):
    rows = []
    for path in Path("/proc").iterdir():
        if path.name.isdecimal():
            row = process_stat(path.name)
            if row and row["session"] == sid and row["state"] not in ("Z", "X"):
                rows.append(row)
    return rows


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text()


class Supervisor:
    def __init__(self, root, deadline, *, budget_label="80-minute"):
        self.root, self.deadline = root, deadline
        self.budget_label = budget_label
        self.cleanup_complete = True
        self.children = []

    def signal_session(self, child, owner, boot, sig):
        require(boot_id() == boot, "boot identity changed; cleanup ownership uncertain")
        leader = process_stat(child.pid)
        require(leader and leader["session"] == child.pid and leader["pgrp"] == child.pid,
                "unreaped private-session leader unavailable")
        if owner is not None:
            require(leader["birth"] == owner["birth"], "private-session leader birth changed")
        # A verified same-session member can use another process group.
        # pidfds prevent reuse between the membership/birth checks and signal.
        for member in session_live(child.pid):
            try:
                descriptor = os.pidfd_open(member["pid"])
            except ProcessLookupError:
                continue
            try:
                current = process_stat(member["pid"])
                if current is None:
                    continue
                require(current["birth"] == member["birth"] and current["session"] == child.pid,
                        "session-member identity changed before signal")
                try:
                    signal.pidfd_send_signal(descriptor, sig)
                except ProcessLookupError:
                    pass
            finally:
                os.close(descriptor)
