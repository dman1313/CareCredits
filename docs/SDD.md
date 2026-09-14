# CareCredits: spec-driven development document

Status: initial specification, 2026-09-15. No earlier SDD existed on main when this document was created.

## Problem and scope

Working hypothesis: Malaysian doctors need an easier way to discover relevant CPD activities across fragmented sources and track learning. Validate this with doctors and authoritative sources; the repository contains no user-research evidence.

The first deliverable is course discovery with traceable sources. Registration and CPD tracking remain the wider vision. The dashboard is a visual prototype: its dates, points, categories, and compliance scores are not regulatory facts.

## Hackathon constraints

- HACK-01: The owner states this is a Tavily hackathon project. Real Tavily Search and Extract calls are mandatory for the project. A static dataset alone does not satisfy this requirement.
- HACK-02: Obtain the official hackathon URL, rules, judging criteria, deadline, and submission requirements before claiming compliance.
- HACK-03: Earlier planning mentioned Nebius. Confirm whether it is additionally required and what service it should provide; do not silently replace that requirement.

## Architecture

Implemented: authorized operator → FastAPI `/discovery/search` → Tavily Search → deduplicate source URLs → Tavily Extract → source response.

Planned: authenticated doctor → dashboard → application backend → cached, structured event records with evidence. Protected ingestion refreshes records through the existing Tavily adapter.

Keep calls and keys server-side. The operator supplies `TAVILY_API_KEY`; end users do not. Local setup prompts via `scripts/setup_tavily.py`; deployment uses server-side secrets. A separate `DISCOVERY_API_TOKEN` protects the operator endpoint. This is not finished end-user authentication.

Tavily provides discovery and page extraction. Event parsing, cross-page deduplication, storage, accreditation checks, and CPD accounting remain application responsibilities. External text is untrusted data: future AI processing must not execute instructions found in sources.

## Requirements and acceptance criteria

| ID | Requirement and acceptance criterion | Status |
| --- | --- | --- |
| DISC-01 | Valid authorized query calls real Tavily Search with Malaysian medical CPD context | Implemented; live test pending |
| DISC-02 | Extract up to five unique web URLs returned by Search; skip extraction on empty results | Implemented; live test pending |
| DISC-03 | Return URL, title, snippet, extraction status, unverified label and UTC retrieval time | Implemented |
| DISC-04 | Extraction failure retains snippets with warnings; search failure is an error, never fabricated data | Implemented |
| DISC-05 | Trimmed query 3–300 characters, 1–5 results, 30-second timeout per upstream call, no automatic retries | Implemented |
| SEC-01 | Hidden-input setup saves ignored `.env` with owner-only permissions; never print secrets | Implemented |
| SEC-02 | Missing operator token disables endpoint; invalid bearer token blocks calls before Tavily | Implemented |
| EVT-01 | Parse event name, organizer, date/time/timezone, location/online mode, fee/currency, advertised CPD points and registration link; preserve source URL, retrieval time and supporting excerpts; unavailable fields are null | Planned |
| EVT-02 | Re-import updates the same source/event; distinct events on a page remain separate; ambiguous cross-site duplicates require review | Planned |
| EVT-03 | Separate advertised points from verified eligibility; verification records authoritative evidence and review time | Planned |
| UI-01 | Authenticated user can search, see loading/empty/error states, open sources and see unverified labels; no secrets reach browser | Planned |
| OPS-01 | Add per-user throttling, bounded concurrency, caching and a documented refresh/credit budget before public access | Planned |
| DEMO-01 | Record successful live query, source links, extraction outcome and matching Tavily dashboard usage without credentials | Pending key and live test |

## Implemented API contract

`POST /discovery/search`, `Authorization: Bearer <DISCOVERY_API_TOKEN>`.

Request: `{"query":"cardiology workshops Kuala Lumpur 2026","max_results":5}`.

Response:

- `provider`: `tavily`.
- `query`: trimmed user query; backend adds Malaysian medical CPD context upstream.
- `retrieved_at`: UTC ISO retrieval timestamp, not the event date.
- `sources`: objects containing `url`, `title`, `snippet`, nullable `raw_content`, `extraction_status` (`success` or `failed`), and `verification_status` (`unverified`).
- `warnings`: sanitized extraction failure information, without provider bodies or credentials.

No matches returns 200 with an empty list. Invalid input returns 422; missing/invalid caller authorization 401; unconfigured integration/rejected Tavily key 503; upstream limits 429; other upstream failures 502; network/timeout errors 504. If Search succeeds but Extract fails, return 200 with snippets and warnings.

URL filtering removes fragments and rejects non-web links, embedded credentials, literal IPs and obvious local hosts. It is not a general crawler security boundary. Only Tavily retrieves the source pages.

## Implementation sequence

1. Foundation: adapter, operator endpoint, local setup and mocked tests (DISC-01–05, SEC-01–02).
2. Configure a real key locally; run the smoke test and verify actual usage (DEMO-01).
3. Define event schema and implement parsing with evidence and unknown values. If using AI, choose its provider after resolving HACK-03 and validate structured output (EVT-01).
4. Persist records, implement source-aware updates, duplicate review and accreditation review (EVT-02–03).
5. Add end-user access controls, rate limits and caching; connect UI to application backend, not directly to Tavily (OPS-01, UI-01).
6. Replace or label fixtures; verify Malaysian CPD requirements before implementing compliance calculations.

## Verification and demo

Automated tests cover Search → Extract sequencing, deduplication, URL filtering, empty results, partial failure, missing configuration, authorization, validation bounds, sanitized provider errors and setup-file behavior. Mocks prove adapter behavior, not live connectivity or search completeness.

Live demo: configure the key privately, start the API, authorize locally, submit a query, inspect sources and extracted text, and confirm Tavily dashboard usage. Check event dates and points against sources. Disclose provider failures and label saved fixtures as prerecorded. Discovery does not prove accreditation or complete CPD tracking.

Open decisions: official event rules; Nebius role; source domains; specialties/geography; date window; structured extraction approach; CPD verification authority; retention; hosting and credit budget.

## References

- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Extract API](https://docs.tavily.com/documentation/api-reference/endpoint/extract)

API contracts checked 2026-09-15. Hackathon requirements are owner-supplied, not independently verified rules.
