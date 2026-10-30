"""Passive, bounded Python-frame evidence for one historical Native fixture.

No product import, object formatting, getter, mutation, or Native call occurs here.
"""
from __future__ import annotations
import ast
import hashlib
import json
import math
from pathlib import Path
import sys
import threading
import types

TRACE_MAX = 64 * 1024
FOOTER_RESERVE = 4096
TICK_NAME = "tick_grain_reserves"

class Refused(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Refused(message)

def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def primitive_copy(value, depth=0, remaining=None):
    """Copy exact builtin data only; never ask a product object to represent itself."""
    if remaining is None:
        remaining = [256]
    remaining[0] -= 1
    if remaining[0] < 0 or depth > 4:
        raise Refused("primitive snapshot bound")
    kind = type(value)
    if value is None or kind is bool:
        return value
    if kind is int:
        require(value.bit_length() <= 128, "integer snapshot bound")
        return value
    if kind is float:
        require(math.isfinite(value), "nonfinite primitive")
        return value
    if kind is str:
        require(len(value.encode("utf-8")) <= 256, "string snapshot bound")
        return value
    if kind in (list, tuple):
        require(len(value) <= 64, "sequence snapshot bound")
        return [primitive_copy(x, depth + 1, remaining) for x in value]
    if kind is dict:
        require(len(value) <= 64, "mapping snapshot bound")
        result = []
        # Preserve actual insertion order; no repr or cross-type key comparison.
        for key, item in value.items():
            require(type(key) in (str, int), "nonprimitive mapping key")
            result.append([primitive_copy(key, depth + 1, remaining),
                           primitive_copy(item, depth + 1, remaining)])
        return {"ordered_items": result}
    return {"opaque": True}

def ast_shape(value):
    """Version-stable fields (including empty lists), no source execution."""
    if isinstance(value, ast.AST):
        return {"node": type(value).__name__, "fields": {key: ast_shape(item) for key, item in ast.iter_fields(value)}}
    if type(value) is list:
        return [ast_shape(x) for x in value]
    return value

def _target_name(node):
    if isinstance(node, ast.Name):
        return node.id
    return None

def source_points(source):
    """Find exact statements in the immutable production AST, without importing it."""
    module = ast.parse(source)
    functions = [x for x in module.body if isinstance(x, ast.FunctionDef) and x.name == TICK_NAME]
    require(len(functions) == 1, "unique tick function")
    fn = functions[0]
    points = {}
    def add(name, matches, fields, scope="buyer"):
        require(len(matches) == 1, "unique point " + name)
        node = matches[0]
        require(str(node.lineno) not in points, "point line collision")
        points[str(node.lineno)] = {"point": name, "line": node.lineno,
            "statement_sha256": sha(encode(ast_shape(node))),
            "fields": list(fields), "scope": scope}
    nodes = list(ast.walk(fn))
    assignments = lambda name: [n for n in nodes if (
        isinstance(n, ast.Assign) and any(_target_name(t) == name for t in n.targets)
        or isinstance(n, ast.AnnAssign) and _target_name(n.target) == name)]
    observes = [n for n in fn.body if isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name) and n.value.func.id == "_observe"]
    require(len(observes) == 1, "unique observe")
    index = fn.body.index(observes[0])
    add("AFTER_OBSERVE", [fn.body[index + 1]], ("demand", "price"), "all")
    add("INPUTS_READY", assignments("foreign_bought"),
        ("demand", "price", "surplus", "projected", "budget", "graph"), "all")
    budget_checks = [n for n in nodes if isinstance(n, ast.If)
                     and ast.dump(n.test, include_attributes=False) ==
                     ast.dump(ast.parse("budget[ci] <= 0", mode="eval").body, include_attributes=False)]
    add("CIV_BUDGET", budget_checks, ("foreign", "ci", "budget", "surplus"), "transition")
    add("TARGETS_READY", [n for n in nodes if isinstance(n, ast.For)
        and isinstance(n.target, ast.Name) and n.target.id == "rid"
        and isinstance(n.iter, ast.Name) and n.iter.id == "targets"],
        ("foreign", "ci", "targets", "budget", "surplus"))
    add("SOURCES_READY", [n for n in nodes if isinstance(n, ast.For)
        and isinstance(n.target, ast.Name) and n.target.id == "src"
        and isinstance(n.iter, ast.Name) and n.iter.id == "sources"],
        ("foreign", "ci", "rid", "sources", "hops", "steps"))
    expressions = {
        "BUDGET_DEFICIT": ("budget[ci] <= 0 or deficit <= EPS",
            ("foreign", "ci", "rid", "src", "deficit", "budget")),
        "ONE_HOP": ("foreign and shipments is not None and shipments.accept_orders and steps[src] != 1",
            ("foreign", "ci", "rid", "src", "steps")),
        "SURPLUS_PRICE": ("surplus[src] <= EPS or p <= 0",
            ("foreign", "ci", "rid", "src", "surplus", "p")),
        "INTEGER_COST": ("cost < 1",
            ("foreign", "ci", "rid", "src", "deficit", "keep", "want", "p", "cost", "budget", "surplus")),
        "DISPATCH_RETURN": ("event is None",
            ("foreign", "ci", "rid", "src", "seller", "sent", "received", "cost", "budget", "surplus")),
    }
    for name, (expression, fields) in expressions.items():
        expected = ast.dump(ast.parse(expression, mode="eval").body, include_attributes=False)
        add(name, [n for n in nodes if isinstance(n, ast.If)
                   and ast.dump(n.test, include_attributes=False) == expected], fields)
    return {"first_line": fn.lineno, "function_ast_sha256": sha(encode(ast_shape(fn))), "points": points}

class TraceBuffer:
    def __init__(self, header, limit=TRACE_MAX):
        require(type(limit) is int and FOOTER_RESERVE < limit <= TRACE_MAX, "trace limit")
        self.limit = limit
        self.records = [encode({"kind": "HEADER", **header})]
        self.bytes = len(self.records[0])
        require(self.bytes < limit - FOOTER_RESERVE, "header bound")
        self.attempted = 0
        self.dropped = 0
        self.truncated = False
        self.errors = []
    def error(self, label):
        if label not in self.errors and len(self.errors) < 16:
            self.errors.append(label)
    def append(self, value):
        self.attempted += 1
        if self.truncated or self.errors:
            self.dropped += 1
            return
        try:
            body = encode(value)
            if self.bytes + len(body) > self.limit - FOOTER_RESERVE:
                self.truncated = True
                self.dropped += 1
                return
            self.records.append(body)
            self.bytes += len(body)
        except BaseException as error:
            self.error(type(error).__name__)
            self.dropped += 1
    def finish(self, closure):
        complete = not self.truncated and not self.errors and closure["hooks_restored"] and closure["active_frames"] == 0 and closure["calls"] > 0
        footer = encode({"kind": "CLOSURE", **closure, "complete": complete,
            "truncated": self.truncated, "observer_errors": self.errors,
            "attempted_records": self.attempted, "dropped_records": self.dropped})
        require(len(footer) <= FOOTER_RESERVE and self.bytes + len(footer) <= self.limit, "closure bound")
        return b"".join(self.records) + footer, complete

class PassiveTrace:
    def __init__(self, source_path, expected_source_sha256, expected_points,
                 output_path, filters, header, module_name="chronicler.grain_reserves"):
        self.source_path = Path(source_path).resolve(strict=True)
        data = self.source_path.read_bytes()
        require(sha(data) == expected_source_sha256, "pinned production source")
        self.source_sha256 = expected_source_sha256
        self.schema = source_points(data.decode("utf-8"))
        compiled = compile(data, str(self.source_path), "exec", dont_inherit=True, optimize=0)
        codes = [x for x in compiled.co_consts if type(x) is types.CodeType and x.co_name == TICK_NAME]
        require(len(codes) == 1, "one compiled source tick")
        self.expected_code = codes[0]
        require(self.schema == expected_points, "pinned AST point schema")
        self.output_path = Path(output_path)
        require(not self.output_path.exists(), "fresh trace")
        self.module_name = module_name
        self.filters = filters
        self.buffer = TraceBuffer(header)
        self.code = None
        self.calls = 0
        self.frames = {}
        self.bound_code = None
        self.hooks_restored = False
        self.installed = False
        self.closed = False
        self.restoration_error = None
        self.complete = False
    def _admit_hooks(self):
        require(sys.version_info >= (3, 13), "Python3.13 trace APIs")
        require(sys.gettrace() is None and threading.gettrace() is None, "source-owned None trace context")
        for frame in sys._current_frames().values():
            while frame is not None:
                require(frame.f_trace is None, "pre-existing frame trace")
                frame = frame.f_back
    def install(self):
        self._admit_hooks()
        self.initial_threads = {x.ident for x in threading.enumerate()}
        self.global_hook, self.local_hook = self._global, self._local
        self.installed = True
        threading.settrace_all_threads(self.global_hook)
        threading.settrace(self.global_hook)
        sys.settrace(self.global_hook)
    def _bind(self, code):
        module = sys.modules.get(self.module_name)
        require(type(module) is types.ModuleType, "already loaded product module")
        function = vars(module).get(TICK_NAME)
        require(type(function) is types.FunctionType and function.__code__ is code, "exact live code object")
        require(code.co_filename == str(self.source_path) and code.co_firstlineno == self.schema["first_line"], "code path/first line")
        require(code == self.expected_code, "actual tick matches pinned compiled source")
        if self.code is None:
            self.code = code
            self.bound_code = {"bytecode_sha256": sha(code.co_code),
                "line_table_sha256": sha(code.co_linetable), "first_line": code.co_firstlineno}
        else:
            require(self.code is code, "code identity changed during test")
    def _global(self, frame, event, arg):
        # Constant-string filter first: no filesystem resolution on ordinary calls.
        code = frame.f_code
        if code.co_name != TICK_NAME or code.co_filename != str(self.source_path):
            return None
        try:
            self._bind(code)
            if event == "call":
                self.calls += 1
                self.frames[id(frame)] = {"call": self.calls, "thread": threading.get_ident(), "pending": None}
            return self._local(frame, event, arg)
        except BaseException as error:
            self.buffer.error(type(error).__name__)
            return None
    def _wanted(self, point, values):
        scope = point["scope"]
        if scope == "all":
            return True
        if scope == "transition":
            # All-civ domestic→foreign state: retain first-civ boundary and buyer.
            return values.get("ci") in (0, self.filters["buyer"])
        if values.get("ci") != self.filters["buyer"]:
            return False
        if point["point"] not in ("TARGETS_READY",):
            if "rid" in values and values["rid"] not in self.filters["destinations"]:
                return False
        if point["point"] in ("BUDGET_DEFICIT", "ONE_HOP", "SURPLUS_PRICE", "INTEGER_COST", "DISPATCH_RETURN"):
            return values.get("src") in self.filters["sources"]
        return True
    def _flush(self, state, next_event, next_line):
        pending = state["pending"]
        if pending is not None:
            pending["following_event"] = next_event
            pending["following_line"] = next_line
            self.buffer.append(pending)
            state["pending"] = None
    def _local(self, frame, event, arg):
        try:
            state = self.frames.get(id(frame))
            if state is None:
                self.buffer.error("UNREGISTERED_TARGET_FRAME")
                return None
            self._flush(state, event, frame.f_lineno)
            if event == "line" and str(frame.f_lineno) in self.schema["points"] and not self.buffer.truncated and not self.buffer.errors:
                point = self.schema["points"][str(frame.f_lineno)]
                values = frame.f_locals
                if self._wanted(point, values):
                    copied = {}
                    for key in point["fields"]:
                        copied[key] = {"present": key in values}
                        if key in values:
                            copied[key]["value"] = primitive_copy(values[key])
                    if point["point"] == "DISPATCH_RETURN":
                        copied["event"] = {"present": "event" in values,
                            "is_none": values.get("event") is None}
                    state["pending"] = {"kind": "POINT", "call_ordinal": state["call"],
                        "thread": state["thread"], "point": point["point"],
                        "source_line": point["line"], "locals": copied}
            elif event == "exception":
                # Never format exception objects or retain tracebacks.
                self.buffer.append({"kind": "EXCEPTION", "call_ordinal": state["call"],
                    "thread": state["thread"], "source_line": frame.f_lineno,
                    "type": arg[0].__name__ if type(arg) is tuple and isinstance(arg[0], type) else "OPAQUE"})
            elif event == "return":
                self.buffer.append({"kind": "RETURN", "call_ordinal": state["call"],
                    "thread": state["thread"], "source_line": frame.f_lineno,
                    "is_none": arg is None})
                self.frames.pop(id(frame), None)
        except BaseException as error:
            # An observer failure must never become a producer exception.
            self.buffer.error(type(error).__name__)
        return self.local_hook
    def close(self):
        require(not self.closed, "trace closes once")
        self.closed = True
        if self.installed:
            try:
                threading.settrace_all_threads(None)
                threading.settrace(None)
                sys.settrace(None)
                frames_clear = True
                for current in sys._current_frames().values():
                    while current is not None:
                        if current.f_trace is self.global_hook or current.f_trace is self.local_hook:
                            current.f_trace = None
                        if current.f_trace is not None:
                            frames_clear = False
                        current = current.f_back
                self.hooks_restored = sys.gettrace() is None and threading.gettrace() is None and frames_clear
                if not frames_clear:
                    self.buffer.error("UNEXPECTED_FRAME_TRACE_AT_CLOSE")
            except BaseException as error:
                self.restoration_error = type(error).__name__
                self.buffer.error("RESTORE_" + self.restoration_error)
        else:
            self.buffer.error("NOT_INSTALLED")
        new_alive = [x.ident for x in threading.enumerate()
                     if x.ident not in getattr(self, "initial_threads", set())]
        if new_alive:
            self.buffer.error("OWNED_THREADS_NOT_QUIESCENT")
        try:
            if sha(self.source_path.read_bytes()) != self.source_sha256:
                self.buffer.error("PRODUCTION_SOURCE_CHANGED")
        except BaseException as error:
            self.buffer.error("SOURCE_RECHECK_" + type(error).__name__)
        body, self.complete = self.buffer.finish({"hooks_restored": self.hooks_restored,
            "active_frames": len(self.frames), "calls": self.calls,
            "code": self.bound_code, "new_alive_threads": new_alive})
        with self.output_path.open("xb") as stream:
            stream.write(body)
        return self.complete

def pytest_plugin(trace, target):
    import pytest
    class Plugin:
        def __init__(self):
            self.case_reports = []
            self.collection = []
            self.calls = 0
            self.trace_close_error = None
        def pytest_collection_modifyitems(self, items):
            self.collection = [x.nodeid for x in items]
            require(self.collection == [target], "one fixed original case")
        @pytest.hookimpl(hookwrapper=True, tryfirst=True)
        def pytest_runtest_call(self, item):
            require(item.nodeid == target and self.calls == 0, "single selected call")
            self.calls += 1
            try:
                trace.install()
                yield
            finally:
                try:
                    trace.close()
                except BaseException as error:
                    self.trace_close_error = type(error).__name__
        def pytest_runtest_logreport(self, report):
            if report.nodeid == target:
                self.case_reports.append({"when": report.when, "outcome": report.outcome})
    return Plugin()
