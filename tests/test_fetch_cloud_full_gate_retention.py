"""Bounded artifact-list collection; all network responses are synthetic."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
import urllib.error

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fetch_cloud_full_gate_retention.py"
spec = importlib.util.spec_from_file_location("fetch_cloud_full_gate_retention", SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class Response(io.BytesIO):
    status = 200


def environment():
    return {collector.TOKEN_ENV: "unit-token", "GITHUB_REPOSITORY": collector.REPOSITORY,
            "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40,
            "COHORT_JOB_RESULT": "success"}


class RetentionCollectionContracts(unittest.TestCase):
    def test_exact_one_read_only_request_removes_token_and_retains_exact_response(self):
        env, calls = environment(), []
        raw = b'{"total_count": 1, "artifacts": [{"id": 1, "name": "example"}]}\n'

        def opener(request, timeout):
            self.assertNotIn(collector.TOKEN_ENV, env)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("Authorization"), "Bearer unit-token")
            self.assertEqual(timeout, 30)
            calls.append(request.full_url)
            return Response(raw)

        result = collector.collect(env, opener=opener)
        self.assertEqual(calls, ["https://api.github.com/repos/YotsuBotfds/Chronicler/actions/runs/123/artifacts?per_page=100"])
        self.assertTrue(result["complete"])
        self.assertEqual(result["raw_response"], raw.decode())
        self.assertEqual(result["raw_response_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(json.loads(result["raw_response"])["artifacts"], result["artifacts"])
        self.assertNotIn("unit-token", collector.encode(result).decode())

    def test_known_empty_collection_stays_complete_for_reader_missing_raw_adjudication(self):
        result = collector.collect(environment(), opener=lambda *a, **k: Response(b'{"total_count":0,"artifacts":[]}'))
        self.assertTrue(result["complete"])
        self.assertEqual(result["artifacts"], [])

    def test_oversized_paginated_truncated_ambiguous_or_nonfinite_response_is_not_complete(self):
        samples = [
            b"x" * (collector.MAX_RESPONSE_BYTES + 1),
            b'{"total_count":101,"artifacts":[]}',
            b'{"total_count":1,"artifacts":[]}',
            b'{"total_count":false,"artifacts":[]}',
            b'{"total_count":0,"total_count":0,"artifacts":[]}',
            b'{"total_count":0,"artifacts":[],"bad":1e9999}',
        ]
        for raw in samples:
            with self.subTest(size=len(raw)):
                calls = []
                def opener(*args, **kwargs):
                    calls.append(1)
                    return Response(raw)
                result = collector.collect(environment(), opener=opener)
                self.assertFalse(result["complete"])
                self.assertEqual(len(calls), 1)

    def test_http_error_does_not_retry_or_disclose_token_or_response_body(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            raise urllib.error.HTTPError(request.full_url, 403, "unit-token", {}, io.BytesIO(b"unit-token"))
        result = collector.collect(environment(), opener=opener)
        self.assertFalse(result["complete"])
        self.assertEqual(result["error"]["http_status"], 403)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("unit-token", collector.encode(result).decode())

    def test_missing_token_or_wrong_run_identity_never_calls_api(self):
        for key, value in ((collector.TOKEN_ENV, None), ("GITHUB_REPOSITORY", "Other/Repo"),
                           ("GITHUB_RUN_ID", "../123"), ("GITHUB_SHA", "wrong"),
                           ("COHORT_JOB_RESULT", "unknown")):
            env, calls = environment(), []
            if value is None:
                env.pop(key)
            else:
                env[key] = value
            result = collector.collect(env, opener=lambda *a, **k: calls.append(1))
            self.assertFalse(result["complete"])
            self.assertEqual(calls, [])
            self.assertNotIn(collector.TOKEN_ENV, env)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(collector.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.invalid"))


if __name__ == "__main__":
    unittest.main()
