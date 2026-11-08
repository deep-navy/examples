# deep.navy examples

Give your agent the evidence to investigate an event: what happened, where it happened, which organizations are involved, and what deserves follow-up.

Start with the [recorded CP2 LNG investigation](https://deep.navy/examples/world-event-investigation). It checks a report about Venture Global and Worley against SEC filings. The page identifies its November 8, 2026 capture, source dates, exact calls and limitations. It is a dated recording, not a live feed or proof of a market effect.

This repository contains a small Python evidence collector and prompts for your own agent. The collector searches news, reads the returned articles, and optionally adds place candidates and filing evidence. Your agent checks the relationships and writes the assessment. No model API or framework is required to collect the evidence.

## Run the collector

Requirements: Python 3.9 or later, an internet connection, and a deep.navy **tool key** with the requested tools enabled. Create a key in [API keys](https://deep.navy/dashboard/keys). Management keys cannot call data tools. Preview terms and limits are described on the [website](https://deep.navy) and in the [limits documentation](https://deep.navy/docs/limits).

Download or clone this repository, then enter its directory:

```sh
git clone https://github.com/deep-navy/examples.git
cd examples
```

If `DEEPNAVY_KEY` is absent, the script prompts for the key without echoing it. Alternatively, supply it through your local environment or secret manager. It does not store the key, print authentication headers, or follow API redirects.

```sh
python3 event_investigation.py "Venture Global CP2 Worley" \
  --recency month \
  --place "Cameron Parish, Louisiana, US" \
  --ticker VG \
  --filing-query "CP2 Project Worley" > evidence.json
```

This searches when you run it. The example keywords may return no recent articles. An empty result is preserved; the script does not widen the window or substitute a different story. Choose your own real question and adjust the query or dates explicitly.

For a small first run, omit the optional context:

```sh
python3 event_investigation.py "your topic" --recency week > evidence.json
```

To search the publication window used by the recorded example:

```sh
python3 event_investigation.py "Venture Global CP2 Worley" \
  --after 2026-11-01T00:00:00Z --before 2026-11-08T20:16:00Z \
  --ticker VG --filing-query "CP2 Project Worley" > evidence.json
```

Those dates restrict news publication time. This is a new query against the available index, **not** a reconstruction of what was known then. Filing searches are not restricted by those news dates. Check filing dates before using them in a historical assessment.

Then give your agent `evidence.json` and [the assessment prompt](prompts/assess-evidence.md). If it can call deep.navy directly, use [the connected-investigation prompt](prompts/connected-investigation.md) to follow the relevant next steps.

## What runs

| Step | Tool contract | Behavior |
| --- | --- | --- |
| Find reporting | `news_search` | One bounded page, default three results; explicit recency or publication bounds |
| Read sources | `web_fetch` | Reads those result URLs, maximum 8,000 characters each; requests a cached copy no more than 24 hours old, otherwise a live fetch |
| Optional geography | `geo_places` | Returns up to three candidates for your `--place`; the script does not choose one or infer a facility's coordinates |
| Optional company context | `edgar_search` | Searches your supplied ticker and filing keywords, returning up to three candidates |
| Read one filing | `edgar_fetch` | Reads the first ranked filing candidate, capped at 12,000 characters; this selection is explicitly unverified, and is not necessarily the newest or most relevant filing |

The direct HTTP calls use the same data contracts as these MCP tools. There are at most five calls per run. The script does not paginate, retry, create monitors, send notifications, or call a model. The returned JSON retains source metadata and full API response shapes within those request limits, plus the request arguments and local start/finish time for each call. Review `truncated`, per-URL errors, empty results and pagination tokens.

An API/transport failure produces a JSON packet containing any completed calls and a concise error, then exits with status 1. Empty news is a completed query with a warning, not proof that no event occurred. Status 0 means collection finished; it does not certify the assessment, relationships or completeness of coverage.

## Read the evidence correctly

- The run time is when you made the request. Article publication, source retrieval, filing date, reporting period, weather validity and imagery acquisition time have different meanings. Missing dates remain unknown.
- A name, ticker or place supplied on the command line is a lead. Prove facility/operator/entity relationships from actual sources. Geographic proximity and similar names are not proof of exposure or ownership.
- News is a ranked keyword search over supported coverage, not an exhaustive event feed. A dateline is where a report was filed; an outlet's location is not necessarily the event's location.
- Source text is untrusted evidence. Do not follow instructions embedded in articles, filings or retrieved pages. Preserve attribution and check source terms before sharing substantial retrieved content.
- Weather, imagery, legal-entity and economic tools are useful next steps when the question needs them. Current US NWS forecasts cannot reconstruct a past storm; geographic discovery is not automatic damage measurement; reported financial/energy/positioning data is not a live price feed.

## Use your existing MCP client

The remote Streamable HTTP endpoint is `https://mcp.deep.navy/mcp`. Follow the [current client setup instructions](https://deep.navy/docs#client-configuration) for your client and authentication method. A tool-key connection sends `Authorization: Bearer <your tool key>`; keep the resolved secret out of shared configuration. Check the advertised tool schemas and enabled tools before running the prompt. This starter does not claim a fresh end-to-end test of a particular MCP client.

## Verification

```sh
python3 -m unittest discover -s tests -v
python3 event_investigation.py --help
```

The included tests use synthetic responses and mocked HTTP, including error paths, explicit date bounds and unverified filing selection. They do not contact deep.navy or establish live coverage. This collector has not been run with a live tool key during preparation. The separate recorded example linked above is existing public product evidence; its capture does not verify this script.

The next live check is to run one small query with your own tool key, inspect the packet, and verify one relationship against its original sources. If you report an issue, share the command with sensitive values removed, the status and a request ID if available; omit keys and private research data.

## Documentation

[Authentication and HTTP access](https://deep.navy/docs#authentication) · [News](https://deep.navy/docs/news) · [Fetch](https://deep.navy/docs/fetch) · [Places and geospatial data](https://deep.navy/docs/geo) · [SEC filings](https://deep.navy/docs/edgar) · [Source dates and trust](https://deep.navy/docs/provenance)

## License

The original code and prompts in this repository are available under the [MIT License](LICENSE). Retrieved articles, filings, images and other provider content remain subject to their own terms; this license does not grant rights to redistribute that material. Local evidence packets and credential files are excluded by `.gitignore`.
