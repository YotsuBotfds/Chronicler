#!/usr/bin/env python3
"""Read two fixed historical CI artifacts; never import or run the simulator."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, build_opener
import xml.etree.ElementTree as ET
import zipfile

sys.dont_write_bytecode = True
REPOSITORY = "YotsuBotfds/Chronicler"
SOURCE = "d0281e5f57c508f27cea1676f36e0e6ed1225c9d"
RUN = 40782783254
API = f"https://api.github.com/repos/{REPOSITORY}"
HELPER_SHA = "2bacde640402ce64ac52e284f3eb63d3462e1b00ec299ae8a21e1b6f065c649c"
JSON_LIMIT = 2 * 1024**2
LOG_LIMIT = 8 * 1024**2
XML_LIMIT = 16 * 1024**2
REPORT_LIMIT = 32 * 1024**2
PINS = {
    "native": dict(artifact=12858492130, archive_bytes=133807,
        archive_sha="e045c31693155bb32d38d4952d7b53ec9c529fd89421435d242c5a6f08bc820c",
        artifact_name=f"python-native-{SOURCE}", job=123148383504,
        job_name="Python native execution", xml="native.xml",
        members={"native.xml", "native-identity.json"}, passed=7800, skipped=6, subtests=526,
        test_step="Run Python tests with real native extension preloaded"),
    "no-rust": dict(artifact=12857957732, archive_bytes=135280,
        archive_sha="8e8d855f5b6dbd3d40cc8d194cd6bfd40b43cd80c7d71c5e0f49957f643dcb6d",
        artifact_name=f"python-no-rust-{SOURCE}", job=123148383879,
        job_name="Python no-Rust", xml="no-rust.xml", members={"no-rust.xml"},
        passed=7486, skipped=306, subtests=526,
        test_step="Run Python tests without Rust extension"),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _load_helper():
    path = Path(__file__).with_name("default_output_identity_reader.py")
    if sha(path.read_bytes()) != HELPER_SHA:
        raise ValueError("reviewed safety helper differs")
    spec = importlib.util.spec_from_file_location("_duration_audit_safety", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


safe = _load_helper()
Refusal, require = safe.Refusal, safe.require


def bounded_read(stream, limit):
    result = bytearray()
    while block := stream.read(min(65536, limit - len(result) + 1)):
        result.extend(block)
        require(len(result) <= limit, "input exceeds byte limit")
    return bytes(result)


def fetch_fixed(suffix, token, limit, redirect=False):
    """Only fixed repository endpoints; bearer credentials never leave api.github.com."""
    allowed = {f"/actions/runs/{RUN}", f"/actions/runs/{RUN}/artifacts?per_page=100",
               f"/actions/runs/{RUN}/jobs?per_page=100"}
    allowed |= {f"/actions/artifacts/{p['artifact']}/zip" for p in PINS.values()}
    allowed |= {f"/actions/jobs/{p['job']}/logs" for p in PINS.values()}
    require(suffix in allowed and type(token) is str and bool(token), "unregistered API request")
    require(redirect == (suffix.endswith("/zip") or suffix.endswith("/logs")),
            "unregistered redirect mode")
    opener = build_opener(safe.NoRedirect)
    request = Request(API + suffix, headers={"Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        try:
            response = opener.open(request, timeout=30)
        except HTTPError as error:
            try:
                require(redirect and error.code == 302, "fixed API request refused")
                location = safe._public_location(error.headers.get("Location"))
            finally:
                error.close()
        else:
            with response:
                require(not redirect and response.status == 200, "fixed API response differs")
                return bounded_read(response, limit)
        for _ in range(3):
            try:
                # Deliberately new Request: no API headers or token on public storage hops.
                response = opener.open(Request(location), timeout=60)
                with response:
                    require(response.status == 200, "storage response differs")
                    return bounded_read(response, limit)
            except HTTPError as error:
                try:
                    require(error.code in (301, 302, 303, 307, 308), "storage request refused")
                    location = safe._public_location(error.headers.get("Location"))
                finally:
                    error.close()
        raise Refusal("too many storage redirects")
    except Refusal:
        raise
    except Exception:
        # Exception text may expose signed storage URLs. Retain only fixed messages.
        raise Refusal("fixed historical evidence request failed") from None


def unpack(raw, pin):
    require(len(raw) == pin["archive_bytes"] and sha(raw) == pin["archive_sha"],
            "historical ZIP digest or size differs")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            rows = archive.infolist()
            require(len(rows) == len(pin["members"]) <= 2, "unexpected ZIP entry count")
            require(all(0 <= row.file_size <= XML_LIMIT for row in rows)
                    and sum(row.file_size for row in rows) <= 2 * XML_LIMIT, "ZIP bounds exceeded")
            files = safe.archive_members(archive)
            require(set(files) == pin["members"] and all("/" not in n for n in files),
                    "historical ZIP members differ")
            result = {}
            for name, member in files.items():
                with archive.open(member) as stream:
                    result[name] = bounded_read(stream, member.file_size)
                require(len(result[name]) == member.file_size, "ZIP member is incomplete")
            return result
    except Refusal:
        raise
    except Exception:
        raise Refusal("invalid historical ZIP") from None


def integer(value):
    require(type(value) is str and re.fullmatch(r"0|[1-9][0-9]{0,6}", value),
            "invalid JUnit count")
    return int(value)


def seconds(value):
    require(type(value) is str and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)
            and len(value) <= 32, "invalid duration")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise Refusal("invalid duration") from None
    require(result.is_finite() and 0 <= result <= 7200, "duration outside historical job bounds")
    return result


def terminal_summary(raw):
    require(len(raw) <= LOG_LIMIT, "job log exceeds byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise Refusal("job log must be UTF-8") from None
    summaries = []
    for line in text.splitlines():
        line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line)
        line = re.sub(r"^\d{4}-\d\d-\d\dT[0-9:.]+Z ", "", line).strip("= ")
        match = re.fullmatch(r"(.+) in ([0-9]+(?:\.[0-9]+)?)s(?: \([^()]+\))?", line)
        if match is None:
            continue
        counters = {}
        for token in match[1].split(", "):
            count = re.fullmatch(r"([0-9]+) (passed|skipped|subtests passed|warnings?)", token)
            require(count is not None and count[2] not in counters, "unsupported terminal pytest summary")
            counters[count[2]] = int(count[1])
        summaries.append({"passed": counters.get("passed", 0), "skipped": counters.get("skipped", 0),
            "subtests": counters.get("subtests passed", 0), "seconds": float(seconds(match[2]))})
    require(len(summaries) == 1, "expected one successful terminal pytest summary")
    return summaries[0]


def module_for(classname, modules):
    matches = [key for key in modules if classname == key or classname.startswith(key + ".")]
    return modules[max(matches, key=len)] if matches else None


def parse_junit(raw, summary, modules):
    require(type(raw) is bytes and 0 < len(raw) <= XML_LIMIT, "JUnit exceeds byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise Refusal("JUnit must be UTF-8") from None
    require("\x00" not in text and not re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I),
            "DTD, entities and NUL are forbidden in JUnit")
    declaration = re.match(r"\ufeff?\s*<\?xml\s+([^?]+)\?>", text)
    if declaration:
        encoding = re.search(r"encoding\s*=\s*['\"]([^'\"]+)['\"]", declaration[1], re.I)
        require(encoding is None or encoding[1].lower() in ("utf-8", "utf8", "us-ascii"),
                "unsupported JUnit encoding")
    depth, elements = 0, 0
    try:
        parser = ET.iterparse(io.BytesIO(raw), events=("start", "end"))
        for event, element in parser:
            if event == "start":
                depth += 1
                elements += 1
                require(depth <= 12 and elements <= 100000, "JUnit structure exceeds bounds")
                require(len(element.attrib) <= 24 and all(len(v) <= 65536 for v in element.attrib.values()),
                        "JUnit attribute exceeds bounds")
            else:
                depth -= 1
        root = parser.root
    except Refusal:
        raise
    except (ET.ParseError, ValueError):
        raise Refusal("invalid JUnit XML") from None
    require(root.tag in ("testsuites", "testsuite"), "invalid JUnit root")
    suites = list(root.iter("testsuite"))
    require(len(suites) == 1 and not suites[0].findall("testsuite"), "expected one flat pytest suite")
    suite = suites[0]
    require(root is suite or list(root) == [suite], "unexpected JUnit suite structure")
    cases = list(root.iter("testcase"))
    require(0 < len(cases) <= 20000 and cases == suite.findall("testcase"), "invalid JUnit testcase placement")
    counts = {key: integer(suite.get(key)) for key in ("tests", "failures", "errors", "skipped")}
    require(counts["failures"] == counts["errors"] == 0, "historical JUnit is not successful")
    rows, module_rows = [], {}
    total = Decimal(0)
    skipped = 0
    for ordinal, case in enumerate(cases):
        name, classname = case.get("name"), case.get("classname")
        require(type(name) is str and bool(name) and type(classname) is str and bool(classname),
                "testcase identity is missing")
        tags = [child.tag for child in case]
        require(all(tag in ("skipped", "system-out", "system-err", "properties") for tag in tags)
                and tags.count("skipped") <= 1, "unexpected successful testcase outcome")
        duration = seconds(case.get("time"))
        total += duration
        is_skipped = "skipped" in tags
        skipped += is_skipped
        module = module_for(classname, modules)
        node = None
        if module:
            prefix = module[:-3].replace("/", ".")
            tail = classname[len(prefix):].lstrip(".")
            node = module + "::" + ((tail.replace(".", "::") + "::") if tail else "") + name
        row = dict(xml_ordinal=ordinal, classname=classname, name=name, module=module,
                   derived_node_id=node, seconds=float(duration), skipped=is_skipped)
        rows.append(row)
        group = module_rows.setdefault(module or "<unattributed>",
            dict(module=module, testcases=0, skipped=0, seconds=Decimal(0)))
        group["testcases"] += 1
        group["skipped"] += is_skipped
        group["seconds"] += duration
    require(skipped == counts["skipped"] == summary["skipped"], "JUnit skipped count differs")
    require(len(cases) == summary["passed"] + summary["skipped"], "terminal parent count differs")
    require(counts["tests"] == len(cases) + summary["subtests"], "successful subtest count differs")
    groups = [{**row, "seconds": float(row["seconds"])} for row in module_rows.values()]
    return dict(serialized_testcases=len(cases), passed=len(cases) - skipped, skipped=skipped,
        successful_subtests_not_serialized=summary["subtests"], junit_declared_tests=counts["tests"],
        suite_seconds=float(seconds(suite.get("time"))), testcase_seconds=float(total),
        terminal_seconds=summary["seconds"], modules=sorted(groups, key=lambda r: (-r["seconds"], r["module"] or "")),
        testcases=sorted(rows, key=lambda r: (-r["seconds"], r["xml_ordinal"])),
        unattributed_testcases=sum(row["module"] is None for row in rows))


def timestamp(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value),
            "invalid GitHub timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def elapsed(row):
    value = (timestamp(row.get("completed_at")) - timestamp(row.get("started_at"))).total_seconds()
    require(0 <= value <= 7200, "invalid GitHub wall duration")
    return value


def validate_metadata(run, artifacts, jobs):
    require(run.get("id") == RUN and run.get("head_sha") == SOURCE and run.get("run_attempt") == 1
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and run.get("path") == ".github/workflows/tests.yml"
            and run.get("repository", {}).get("full_name") == REPOSITORY, "source run identity differs")
    require(type(artifacts.get("artifacts")) is list and type(artifacts.get("total_count")) is int
            and artifacts["total_count"] == len(artifacts["artifacts"]) <= 100, "artifact list incomplete")
    require(type(jobs.get("jobs")) is list and type(jobs.get("total_count")) is int
            and jobs["total_count"] == len(jobs["jobs"]) <= 100, "job list incomplete")
    result = {}
    for lane, pin in PINS.items():
        matches = [r for r in artifacts["artifacts"] if r.get("id") == pin["artifact"]]
        require(len(matches) == 1, "pinned artifact missing or duplicated")
        row = matches[0]
        origin = row.get("workflow_run", {})
        require(row.get("name") == pin["artifact_name"] and row.get("size_in_bytes") == pin["archive_bytes"]
                and row.get("digest") == "sha256:" + pin["archive_sha"] and row.get("expired") is False
                and origin.get("id") == RUN and origin.get("head_sha") == SOURCE,
                "pinned artifact metadata differs")
        require(timestamp(row.get("expires_at")) > datetime.now(timezone.utc), "pinned artifact expired")
        matches = [r for r in jobs["jobs"] if r.get("id") == pin["job"]]
        require(len(matches) == 1, "pinned producer job missing or duplicated")
        job = matches[0]
        require(job.get("name") == pin["job_name"] and job.get("run_id") == RUN
                and job.get("run_attempt") == 1 and job.get("head_sha") == SOURCE
                and job.get("status") == "completed" and job.get("conclusion") == "success",
                "pinned producer job identity differs")
        test_steps = [r for r in job.get("steps", []) if r.get("name") == pin["test_step"]]
        require(len(test_steps) == 1 and test_steps[0].get("conclusion") == "success", "pytest step differs")
        builds = [r for r in job["steps"] if r.get("name") == "Build Rust extension wheel"]
        require(len(builds) == (1 if lane == "native" else 0)
                and all(step.get("conclusion") == "success" for step in builds), "native build step differs")
        result[lane] = dict(job_seconds=elapsed(job), test_step_seconds=elapsed(test_steps[0]),
                            build_step_seconds=elapsed(builds[0]) if builds else 0)
    return result


def source_modules(root):
    require(not root.is_symlink(), "source checkout must not be a symlink")
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                           check=True, capture_output=True, text=True).stdout
    require(head == SOURCE and not dirty, "frozen source is not exact and clean")
    names = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "*.py"], check=True,
                           capture_output=True).stdout.decode().split("\x00")
    return {name[:-3].replace("/", "."): name for name in names if name and name.endswith(".py")}


def native_identity(raw):
    require(len(raw) <= 65536, "native identity exceeds bounds")
    row = safe.strict_json(raw)
    require(row.get("source_commit") == SOURCE
            and row.get("classes") == ["AgentSimulator", "EcologySimulator", "PoliticsSimulator"]
            and type(row.get("sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            and type(row.get("compiled_extension")) is str
            and row["compiled_extension"].endswith(".so")
            and type(row.get("python")) is str and row["python"].startswith("3.13."),
            "historical native identity differs")
    return row


def shard_model(groups, count):
    """Prospective file partition based only on serialized testcase attribution."""
    require(type(count) is int and count in (2, 3), "unregistered shard model")
    bins = [dict(attributed_seconds=0.0, modules=[]) for _ in range(count)]
    for row in groups:
        if row["module"] is None:
            continue
        target = min(range(count), key=lambda i: (bins[i]["attributed_seconds"], i))
        bins[target]["modules"].append(row["module"])
        bins[target]["attributed_seconds"] += row["seconds"]
    return bins


def markdown(result):
    lines = ["# Historical CI duration audit", "", f"Source `{SOURCE}`; run `{RUN}`. No tests or worlds were rerun.", "",
        "Times below describe one completed run. They are not a speedup measurement or a native-versus-Python benchmark.", "",
        "| Lane | Parent passes | Skips | Successful subtests | Case attribution (s) | Suite (s) | Terminal pytest (s) | Test step (s) | Job (s) | Build step (s) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for lane, row in result["lanes"].items():
        lines.append(f"| {lane} | {row['passed']} | {row['skipped']} | {row['successful_subtests_not_serialized']} | {row['testcase_seconds']:.3f} | {row['suite_seconds']:.3f} | {row['terminal_seconds']:.2f} | {row['test_step_seconds']:.0f} | {row['job_seconds']:.0f} | {row['build_step_seconds']:.0f} |")
        lines += ["", f"## {lane}: largest file totals", "", "| Module | Case seconds | Cases | Skips |", "| --- | ---: | ---: | ---: |"]
        for group in row["modules"][:15]:
            lines.append(f"| `{group['module'] or '<unattributed>'}` | {group['seconds']:.3f} | {group['testcases']} | {group['skipped']} |")
        lines += ["", "Largest reported testcases (XML ordinal disambiguates repeated identities):", ""]
        for case in row["testcases"][:15]:
            label = json.dumps(case["derived_node_id"] or (case["classname"] + "::" + case["name"]), ensure_ascii=True)
            label = label.replace("`", "\\u0060")
            lines.append(f"- {case['seconds']:.3f}s, XML #{case['xml_ordinal']}: `{label}`")
    lines += ["", "## Interpretation and next experiment", "",
        "Successful subtests are independently reconciled against the original terminal log. They enlarge the JUnit header but are not additional serialized testcase duration rows. Skipped rows remain included in attribution.", "",
        "Case times include pytest's recorded setup/call/teardown attribution. Shared fixtures, collection, interpreter startup, wheel build and Actions overhead do not form independent per-file costs. XML rounding can accumulate across thousands of rows; suite, terminal, step and job clocks are kept separate. API timestamps have one-second resolution. Repeated identities are retained, not deduplicated.", "",
        "The JSON includes deterministic two- and three-way file partitions using largest-first historical case totals. Their loads are attribution models only. Actual sharding would repeat environment setup, native installation and some fixtures, and may change contention or coverage. Test selection, count/subtest reconciliation, compiled identity and aggregate job success would need fresh verification before adoption. No workflow sharding is activated by this audit.", ""]
    return "\n".join(lines)


def main(argv=None):
    token = os.environ.pop("GH_ARTIFACT_READ_TOKEN", None)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root, output = args.source_root.resolve(), args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be fresh")
    require(not output.resolve().is_relative_to(root)
            and not output.resolve().is_relative_to(Path(__file__).resolve().parents[1]),
            "output must be outside source checkouts")
    output.mkdir(parents=False, exist_ok=False)
    receipt = dict(schema_version=1, kind="chronicler-fixed-ci-duration-audit", complete=False,
                   source_sha=SOURCE, source_run_id=RUN, reader_sha256=sha(Path(__file__).read_bytes()),
                   safety_helper_sha256=HELPER_SHA, inputs={})
    try:
        modules = source_modules(root)
        metadata = {}
        for key, suffix in (("run", f"/actions/runs/{RUN}"),
                ("artifacts", f"/actions/runs/{RUN}/artifacts?per_page=100"),
                ("jobs", f"/actions/runs/{RUN}/jobs?per_page=100")):
            raw = fetch_fixed(suffix, token, JSON_LIMIT)
            name = key + ".json"
            with (output / name).open("xb") as stream:
                stream.write(raw)
            receipt["inputs"][name] = dict(bytes=len(raw), sha256=sha(raw))
            metadata[key] = safe.strict_json(raw)
        clocks = validate_metadata(**metadata)
        result = dict(schema_version=1, source_sha=SOURCE, source_run_id=RUN, lanes={})
        for lane, pin in PINS.items():
            archive = fetch_fixed(f"/actions/artifacts/{pin['artifact']}/zip", token, pin["archive_bytes"], True)
            name = lane + ".zip"
            with (output / name).open("xb") as stream:
                stream.write(archive)
            receipt["inputs"][name] = dict(bytes=len(archive), sha256=sha(archive))
            payload = unpack(archive, pin)
            log = fetch_fixed(f"/actions/jobs/{pin['job']}/logs", token, LOG_LIMIT, True)
            name = lane + ".log"
            with (output / name).open("xb") as stream:
                stream.write(log)
            receipt["inputs"][name] = dict(bytes=len(log), sha256=sha(log))
            summary = terminal_summary(log)
            require(all(summary[key] == pin[key] for key in ("passed", "skipped", "subtests")),
                    "historical terminal counts differ")
            row = parse_junit(payload[pin["xml"]], summary, modules)
            row.update(clocks[lane])
            row["artifact_id"], row["job_id"] = pin["artifact"], pin["job"]
            row["members"] = {name: dict(bytes=len(raw), sha256=sha(raw)) for name, raw in payload.items()}
            row["native_identity"] = native_identity(payload["native-identity.json"]) if lane == "native" else None
            row["prospective_file_partitions"] = {str(n): shard_model(row["modules"], n) for n in (2, 3)}
            result["lanes"][lane] = row
        require(source_modules(root) == modules and sha(Path(safe.__file__).read_bytes()) == HELPER_SHA,
                "source or safety helper changed during audit")
        for name, raw in (("duration-report.json", json.dumps(result, indent=2, allow_nan=False) + "\n"),
                          ("duration-summary.md", markdown(result))):
            data = raw.encode()
            require(len(data) <= REPORT_LIMIT, "derived report exceeds byte limit")
            with (output / name).open("xb") as stream:
                stream.write(data)
            receipt.setdefault("outputs", {})[name] = dict(bytes=len(data), sha256=sha(data))
        receipt["complete"] = True
    except Refusal as error:
        receipt["error"] = str(error)
    except Exception:
        receipt["error"] = "historical audit failed; no duration result qualified"
    with (output / "audit-result.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if receipt["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
