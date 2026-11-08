"""Offline contract/behavior checks; synthetic fixtures are not captured product output."""

import contextlib
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import event_investigation as example


class FakeAPI:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class CollectorTests(unittest.TestCase):
    def test_collects_sources_without_inventing_connections(self):
        api = FakeAPI([
            {"results": [{"url": "https://example.org/report", "publishedAt": "2026-11-05T12:00:00Z"}]},
            {"results": [{"url": "https://example.org/report", "truncated": True, "source": "cache"}]},
            {"places": [{"id": "synthetic-place-a"}, {"id": "synthetic-place-b"}]},
            {"results": [{"accession": "synthetic-accession", "filedAt": "2026-11-03T00:00:00Z"}]},
            {"markdown": "Synthetic filing text", "truncated": True},
        ])
        args = example.parse_args(["sample event", "--place", "a place", "--ticker", "TEST",
                                   "--filing-query", "sample operation"])
        packet = example.collect(args, api)
        self.assertEqual(packet["status"], "collected")
        self.assertEqual([t for t, _ in api.calls], list(example.ROUTES))
        self.assertEqual(packet["calls"][0]["response"]["results"][0]["publishedAt"], "2026-11-05T12:00:00Z")
        self.assertEqual(len(packet["calls"][2]["response"]["places"]), 2)
        self.assertIn("not verified", packet["calls"][4]["selection"])
        self.assertTrue(packet["calls"][1]["response"]["results"][0]["truncated"])
        self.assertEqual(api.calls[1][1]["maxAgeSeconds"], "86400")

    def test_empty_news_does_not_widen_query_or_fetch(self):
        api = FakeAPI([{"results": []}])
        packet = example.collect(example.parse_args(["no matching event", "--recency", "day"]), api)
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(api.calls[0][1]["recency"], "RECENCY_DAY")
        self.assertIn("not broadened", packet["warnings"][-1])

    def test_explicit_news_bounds_are_preserved(self):
        args = example.parse_args(["event", "--after", "2026-11-01T00:00:00Z",
                                   "--before", "2026-11-08T20:16:00Z"])
        api = FakeAPI([{"results": []}])
        example.collect(args, api)
        self.assertNotIn("recency", api.calls[0][1])
        self.assertEqual(api.calls[0][1]["publishedBefore"], args.before)

    def test_error_preserves_earlier_calls_and_stops(self):
        api = FakeAPI([{"results": [{"url": "https://example.org/report"}]}, RuntimeError("HTTP 429.")])
        packet = example.collect(example.parse_args(["event", "--place", "place"]), api)
        self.assertEqual(packet["status"], "failed")
        self.assertEqual(len(api.calls), 2)
        self.assertIn("response", packet["calls"][0])
        self.assertEqual(packet["calls"][1]["error"], "HTTP 429.")

    def test_rejects_ambiguous_input_before_any_http(self):
        for argv in (["event", "--ticker", "TEST"], ["event", "--after", "2026-11-01"],
                     ["event", "--after", "2026-11-01", "--before", "2026-11-02"],
                     ["event", "--recency", "day", "--after", "2026-11-01T00:00:00Z",
                      "--before", "2026-11-02T00:00:00Z"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    example.parse_args(argv)


class HTTPTests(unittest.TestCase):
    def test_posts_json_to_fixed_data_endpoint(self):
        api = example.API("synthetic-test-key")
        response = Mock()
        response.read.return_value = b'{"results": []}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        api.opener.open = Mock(return_value=response)
        self.assertEqual(api.call("news_search", {"query": "test"}), {"results": []})
        request = api.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deep.navy/deepnavy.news.v1.NewsService/SearchNews")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"query": "test"})
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-test-key")

    def test_http_error_does_not_print_response_body(self):
        api = example.API("synthetic-test-key")
        api.opener.open = Mock(side_effect=urllib.error.HTTPError(
            "https://api.deep.navy/", 401, "unauthorized", {}, io.BytesIO(b"private body")))
        with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
            api.call("news_search", {"query": "test"})
        self.assertNotIn("private body", str(caught.exception))
        self.assertNotIn("synthetic-test-key", str(caught.exception))

    def test_does_not_forward_credentials_on_redirect(self):
        self.assertIsNone(example.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org"))


if __name__ == "__main__":
    unittest.main()
