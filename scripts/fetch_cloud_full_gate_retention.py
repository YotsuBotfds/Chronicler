#!/usr/bin/env python3
"""Collect one bounded current-run artifact index; never fetch raw archives."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

REPOSITORY = "YotsuBotfds/Chronicler"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ENVELOPE_BYTES = 3 * 1024 * 1024
MAX_ARTIFACTS = 100
TOKEN_ENV = "GH_ARTIFACT_READ_TOKEN"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


class CollectionRefusal(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise CollectionRefusal(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate API JSON key")
            result[key] = value
        return result

    def number(value):
        parsed = float(value)
        require(math.isfinite(parsed), "non-finite API JSON number")
        return parsed

    def constant(value):
        raise ValueError("non-finite API JSON constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def collect(environment, *, opener=None):
    # This collector imports only the standard library. Its token is removed
    # before any request and is never present in the later frozen-reader step.
    token = environment.pop(TOKEN_ENV, None)
    result = dict(schema_version=1, kind="chronicler-cloud-full-gate-retention-index",
        repo_full_name=environment.get("GITHUB_REPOSITORY"),
        github_run_id=environment.get("GITHUB_RUN_ID"),
        github_run_attempt=environment.get("GITHUB_RUN_ATTEMPT"),
        control_sha=environment.get("GITHUB_SHA"),
        cohort_job_result=environment.get("COHORT_JOB_RESULT"),
        observed_at=datetime.now(timezone.utc).isoformat(),
        complete=False, total_count=None, artifacts=[])
    try:
        require(result["repo_full_name"] == REPOSITORY, "unexpected repository")
        require(isinstance(result["github_run_id"], str) and
                re.fullmatch(r"[0-9]{1,20}", result["github_run_id"]), "invalid workflow run ID")
        require(isinstance(result["github_run_attempt"], str) and
                re.fullmatch(r"[0-9]{1,10}", result["github_run_attempt"]), "invalid workflow attempt")
        require(isinstance(result["control_sha"], str) and
                re.fullmatch(r"[0-9a-f]{40}", result["control_sha"]), "invalid control SHA")
        require(result["cohort_job_result"] in ("success", "failure", "cancelled", "skipped"),
                "workflow cohort result unavailable")
        require(isinstance(token, str) and bool(token), "artifact API token unavailable")
        url = ("https://api.github.com/repos/" + REPOSITORY + "/actions/runs/" +
               result["github_run_id"] + "/artifacts?per_page=100")
        result["api_url"] = url
        request = urllib.request.Request(url, method="GET", headers={
            "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "Chronicler-fixed-gate-retention"})
        open_request = opener or urllib.request.build_opener(NoRedirect()).open
        with open_request(request, timeout=30) as response:
            require(response.status == 200, "artifact API did not return HTTP 200")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        require(len(raw) <= MAX_RESPONSE_BYTES, "artifact API response exceeds byte cap")
        result["raw_response"] = raw.decode("utf-8", errors="strict")
        result["raw_response_sha256"] = hashlib.sha256(raw).hexdigest()
        parsed = strict_json(raw)
        require(isinstance(parsed, dict), "artifact API JSON must be an object")
        count, artifacts = parsed.get("total_count"), parsed.get("artifacts")
        require(type(count) is int and 0 <= count <= MAX_ARTIFACTS, "artifact API requires pagination or invalid count")
        require(isinstance(artifacts, list) and len(artifacts) == count and
                all(isinstance(item, dict) for item in artifacts), "artifact API collection incomplete")
        result.update(complete=True, total_count=count, artifacts=artifacts)
    except Exception as exc:
        # Do not print HTTP bodies, headers, tokens, or arbitrary server text.
        result["error"] = {"type": type(exc).__name__,
                           "reason": str(exc)[:256] if isinstance(exc, CollectionRefusal) else
                                     "bounded current-run artifact collection unavailable"}
        if isinstance(exc, urllib.error.HTTPError):
            result["error"]["http_status"] = exc.code
    return result


def encode(result):
    raw = (json.dumps(result, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    require(len(raw) <= MAX_ENVELOPE_BYTES, "retention envelope exceeds byte cap")
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = collect(os.environ)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as stream:
            stream.write(encode(result))
    except (OSError, ValueError):
        sys.stderr.write("Retention index could not be retained.\n")
        return 1
    print(json.dumps({key: result.get(key) for key in (
        "kind", "complete", "total_count", "github_run_id", "github_run_attempt",
        "control_sha", "cohort_job_result", "raw_response_sha256", "error")}), flush=True)
    # Observation failure is data for the reader, not permission to omit science.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
