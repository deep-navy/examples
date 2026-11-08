#!/usr/bin/env python3
"""Collect bounded event evidence from deep.navy; no model, dependencies or auto-joins."""

import argparse
import datetime as dt
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = "https://api.deep.navy/"
ROUTES = {
    "news_search": "deepnavy.news.v1.NewsService/SearchNews",
    "web_fetch": "deepnavy.contents.v1.ContentsService/GetContents",
    "geo_places": "deepnavy.geo.v1.GeoService/SearchPlaces",
    "edgar_search": "deepnavy.edgar.v1.EdgarService/SearchFilings",
    "edgar_fetch": "deepnavy.edgar.v1.EdgarService/FetchFiling",
}
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, key):
        self.key = key
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, tool, arguments):
        request = urllib.request.Request(
            BASE_URL + ROUTES[tool],
            data=json.dumps(arguments).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.key,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Connect-Protocol-Version": "1",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("API response exceeded this example's 4 MiB limit.")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise RuntimeError("Expected a JSON object from the API.")
                return result
        except urllib.error.HTTPError as error:
            hints = {
                401: "Check that your key is an active tool key.",
                403: "Check tool access and enabled tools.",
                429: "A rate or usage limit was reached; check the limits documentation.",
            }
            raise RuntimeError(
                "HTTP %s. %s" % (error.code, hints.get(error.code, "The API request failed."))
            ) from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError("The API could not be reached or the request timed out.") from None
        except (ValueError, UnicodeError):
            raise RuntimeError("The API response was not valid JSON.") from None


def collect(args, api):
    packet = {
        "schemaVersion": 1,
        "startedAt": now(),
        "status": "collecting",
        "leads": {"query": args.query, "place": args.place, "ticker": args.ticker},
        "calls": [],
        "warnings": [
            "User-supplied places and companies are unverified leads, not established relationships.",
            "Request times are not source publication, observation or reporting-period times.",
            "This packet contains retrieved evidence, not a generated or verified assessment.",
        ],
    }

    def run(tool, arguments, selection=None):
        call = {"tool": tool, "arguments": arguments, "startedAt": now()}
        if selection:
            call["selection"] = selection
        packet["calls"].append(call)
        try:
            call["response"] = api.call(tool, arguments)
        except RuntimeError as error:
            call["error"] = str(error)
            raise
        finally:
            call["finishedAt"] = now()
        return call["response"]

    try:
        search = {"query": args.query, "numResults": args.limit}
        if args.after:
            search.update(publishedAfter=args.after, publishedBefore=args.before)
        else:
            search["recency"] = "RECENCY_" + (args.recency or "week").upper()
        news = run("news_search", search)
        urls = list(dict.fromkeys(
            row["url"] for row in news.get("results", [])[:args.limit]
            if isinstance(row, dict) and row.get("url")
        ))
        if urls:
            run("web_fetch", {
                "urls": urls, "formats": ["FORMAT_MARKDOWN"],
                "maxCharacters": 8000, "maxAgeSeconds": "86400",
            })
        else:
            packet["warnings"].append("No news URLs returned. The query/window was not broadened.")
        if args.place:
            run("geo_places", {"query": args.place, "limit": 3})
        if args.ticker:
            filings = run("edgar_search", {
                "ticker": args.ticker, "query": args.filing_query, "numResults": 3,
            })
            rows = filings.get("results", [])
            if rows and rows[0].get("accession"):
                run("edgar_fetch", {"accession": rows[0]["accession"], "maxCharacters": 12000},
                    selection="First ranked candidate; relevance and relationship not verified by script.")
            else:
                packet["warnings"].append("No filing candidate with an accession returned.")
        packet["status"] = "collected"
    except RuntimeError:
        packet["status"] = "failed"
        packet["warnings"].append("Collection stopped on an API error; earlier evidence is retained.")
    packet["finishedAt"] = now()
    return packet


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="News keywords; use the sources your actual question needs.")
    parser.add_argument("--recency", choices=["hour", "day", "week", "month", "year"],
                        help="News recency; defaults to week. Cannot combine with --after/--before.")
    parser.add_argument("--after", help="Inclusive news publication bound, RFC 3339 with timezone.")
    parser.add_argument("--before", help="Inclusive news publication bound, RFC 3339 with timezone.")
    parser.add_argument("--limit", type=int, choices=range(1, 6), default=3,
                        help="News results to request and read: 1–5, default 3.")
    parser.add_argument("--place", help="Optional qualified place name to look up; not an automatic join.")
    parser.add_argument("--ticker", help="Optional SEC company ticker to investigate.")
    parser.add_argument("--filing-query", help="Required with --ticker: keywords for relevant filings.")
    args = parser.parse_args(argv)
    if not args.query.strip():
        parser.error("query must not be blank")
    if bool(args.after) != bool(args.before):
        parser.error("provide both --after and --before")
    if args.after and args.recency:
        parser.error("use --recency or publication bounds, not both")
    if bool(args.ticker) != bool(args.filing_query):
        parser.error("provide --ticker and --filing-query together")
    if args.after:
        try:
            bounds = [dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                      for value in (args.after, args.before)]
            if any(value.tzinfo is None for value in bounds) or bounds[0] > bounds[1]:
                raise ValueError()
        except ValueError:
            parser.error("publication bounds must include a timezone and after must be <= before")
    return args


def main():
    args = parse_args()
    key = os.environ.get("DEEPNAVY_KEY", "").strip()
    if not key:
        if not sys.stdin.isatty():
            print("Set DEEPNAVY_KEY to a tool key, or run interactively for a hidden prompt.", file=sys.stderr)
            return 2
        key = getpass.getpass("deep.navy tool key (hidden): ").strip()
    if not key:
        print("A tool key is required. See https://deep.navy/dashboard/keys.", file=sys.stderr)
        return 2
    packet = collect(args, API(key))
    # Never emit this process's credential even if a response happens to echo it.
    print(json.dumps(packet, indent=2, ensure_ascii=False).replace(key, "[REDACTED]"))
    return 1 if packet["status"] == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
