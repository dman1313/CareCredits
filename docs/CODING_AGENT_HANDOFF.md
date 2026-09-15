# Coding-agent handoff — CareCredits full MVP

Use this prompt to implement the specification:

> Read `docs/SDD.md` v0.2, `README.md`, and the current code before editing. The owner's meeting decisions define the scope: Malaysia-only CPD discovery and personal sign-up/attendance/progress tracking, three application services, PostgreSQL, real Tavily usage, and open-weight application AI. Preserve the distinction between confirmed requirements, proposed defaults and unresolved decisions.
>
> **Architecture:** build a Python backend, a separate Python scraper, and a JavaScript-based frontend. Retain the existing TypeScript/Next.js frontend. The backend alone owns PostgreSQL access. The scraper owns Tavily Search/Extract and open-weight model calls, exchanging leased jobs and candidate results through authenticated internal backend APIs.
>
> The existing `backend/discovery.py` and `/discovery/search` are a synchronous foundation, not the target architecture. Reuse and move the adapter into the scraper service, retain its tested failure/provenance behavior, and implement the SDD job contracts. The earlier instruction to keep scraping inside FastAPI is superseded. Retire or disable the transitional operator endpoint before a public release rather than silently changing its response contract.
>
> **Credentials:** ask the developer to run `python3 scripts/setup_tavily.py` in their own terminal when live testing is needed. It prompts privately and saves the key in the ignored `.env`. Never ask for keys in chat. Update secret routing and the setup script as services split; prompt privately for the selected model provider's key when needed. Never expose Tavily/model keys, database credentials or service tokens in frontend code. Continue independent work while keys are unavailable; never fake live success.
>
> **Model requirement:** use an eligible open-weight model for structured event extraction with field-level source evidence and validated outputs. Record model/version, weights source and licence. Resolve the earlier Nebius requirement and official hackathon rules before final provider/model selection. No silent closed-weight fallback. Unknown fees, points, prerequisites or difficulty remain unknown rather than guessed.
>
> **Doctor experience:** implement real sign-in and ownership isolation before exposing personal records; existing user endpoints are unauthenticated. Build Malaysia location selection, nearby/date/fee/points/mode/difficulty filters, source-backed details, personal sign-up and attendance records, and the defined progress calculations. Follow the SDD's reversible state rules and idempotency/version contracts. Its default is external provider registration plus user-recorded sign-up; clicking a link must not register the doctor. Self-reported attendance is not verified credit or licence compliance.
>
> Follow BUILD-01 through BUILD-08 with their dependencies. Where a task is blocked by an unresolved external choice, continue independent tasks. Do not silently drop confirmed scope to fit a deadline. Include migrations, distinct containers, role-scoped secrets, durable jobs, review workflow and resource limits. Implement the SDD acceptance tests, not tests that merely reproduce code.
>
> Link changes to requirement and test IDs. Keep status claims current. Verify the three-service deployment, two-user isolation, failure states, nearby filters, tracking corrections and actual Tavily/model usage. Existing mocked tests do not establish live connectivity. Replace or label prototype fixtures; do not use sample compliance numbers as Malaysian rules. Report remaining gaps and provide redacted demo evidence without credentials.
