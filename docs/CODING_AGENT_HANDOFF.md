# Coding-agent handoff

Use this prompt to continue implementing CareCredits:

> Read `docs/SDD.md`, `README.md`, and the current code before editing. This is a Tavily hackathon project: actual Tavily Search and Extract usage is mandatory for discovery. Do not replace it with mocks or another search provider.
>
> The backend provides protected `POST /discovery/search`. Extend it rather than creating another scraper service. Run the tests and inspect the API contract first.
>
> For live testing, ask the developer to run `python3 scripts/setup_tavily.py` in their own terminal. It prompts for the API key without echoing it and saves it in the ignored `.env`. Never ask for the key in chat. Never put either the Tavily key or operator token in frontend code. Missing configuration must give a setup instruction, not fake success. Continue independent work while the key is unavailable.
>
> Implement planned SDD requirements in order: structured event parsing with evidence and nulls for missing fields; persistence and deduplication; accreditation review; authenticated, rate-limited dashboard access with caching. Preserve provenance and show partial failures and unverified labels. The existing operator token is not end-user authentication and must not ship to browsers.
>
> Resolve the earlier Nebius requirement before selecting an AI provider. Do not assume a search result is a verified course or that advertised points are approved for a particular doctor. Keep unrelated registration and CPD accounting outside the discovery milestone.
>
> Link changes and tests to SDD requirement IDs. Verify frontend loading, empty, success and failure states. Run a real Search and Extract smoke test only after credentials are configured locally; report exactly what was verified. Update the SDD status table and README to match the code. Capture source links and redacted evidence of Tavily usage for the hackathon, without credentials.
