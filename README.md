# CareCredits

A hackathon application being developed to help Malaysian doctors discover CPD trainings and track sign-ups, attendance and learning progress. The confirmed design uses **three application services: a Python backend, a JavaScript-based frontend, and a separate Python scraper**, with PostgreSQL owned by the backend.

The project requires **real Tavily Search and Extract API usage** and **open-weight models for application AI**. Official hackathon rules still need to be linked and checked. The current code is a foundation, not the complete implementation.

## Target product

- Doctor sign-in and a personal dashboard.
- Malaysia-only discovery by city/state or optional nearby distance.
- Training details: CPD points, prerequisites, beginner/intermediate/advanced difficulty, and fees, with unknown values explicit.
- Records of courses signed up for and attended, with personal progress. The SDD proposes external registration and self-reported attendance for MVP.
- Source-backed ingestion using Tavily and an open-weight model to produce structured candidates for review.

[SDD v0.3](docs/SDD.md) defines the full MVP, data model, service contracts, acceptance tests and build sequence. Proposed defaults and unresolved decisions are labelled. User-facing credits are called CPDs; original source labels are retained without assuming CE/CME equivalence.

## Tavily's role in the current code

1. An operator queues a bounded Malaysia training job on the backend.
2. The scraper claims the job, calls Tavily Search, then Extract for up to five unique URLs.
3. Successful page text is sent to the configured open-weight model for structured candidates with field evidence.
4. The backend stores candidates for operator review. Doctor search reads PostgreSQL, not Tavily.

Tavily and model keys belong only to the scraper. Results are **unverified sources**, not confirmed accredited events. Missing details must not be invented, and finding an event does not prove attendance or earn credits.

Official API references: [Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) and [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract).

## Current status

- Three Compose services: backend (FastAPI + PostgreSQL), scraper (Tavily + model worker), frontend (Next.js portal).
- Doctor sign-in uses httponly email/password sessions. Third-party OAuth is still an open decision.
- Malaysia catalogue filters, nearby distance when coordinates exist, personal sign-up/attendance, year progress, and an optional public profile are implemented.
- Operator ingestion uses leased jobs and an explicit retry for interrupted work. The old `POST /discovery/search` endpoint was removed after the adapter moved to the scraper.
- Demo fixtures load only with `DEMO_MODE=true` outside production and are labelled fictional.
- Not yet done: official hackathon-rule check, selected open-weight model evidence, live Tavily/model demonstration, OAuth, candidate hold, cancelled sign-up status, and the target error envelope.
- Nebius remains an unresolved hosting/inference choice; `MODEL_BASE_URL` defaults to Token Factory but is not a completed integration.

Read [the SDD](docs/SDD.md) and [the coding-agent handoff](docs/CODING_AGENT_HANDOFF.md).

## Configure secrets

Use Python 3.11+ and Docker Compose. From the repository root:

```sh
python3 scripts/setup_integrations.py
```

The script asks privately for the Tavily key and model settings, writes the ignored `.env`, and generates `SCRAPER_SERVICE_TOKEN` / `POSTGRES_PASSWORD` if missing. Never put secrets in frontend code, `NEXT_PUBLIC_*` variables, chat, screenshots, or Git.

```sh
docker compose up --build
```

- Frontend: http://127.0.0.1:3000
- Backend API docs: http://127.0.0.1:8000/docs

Local three-service development without Compose:

```sh
python3 scripts/dev.py --demo
```

Demo sign-in is `demo@carecredits.local` / `CareCredits-demo-2026`. That path uses labelled fictional courses and does not call Tavily.

## Try live ingestion

Sign in as an operator, open **Training sources**, and start a bounded Malaysia topic. The scraper must have `TAVILY_API_KEY`, `MODEL_API_KEY`, `MODEL_ID`, weights/licence URLs, and `MODEL_OPEN_WEIGHT_CONFIRMED=true`. Missing configuration fails explicitly; it never returns demo results as live success.

Each job makes one Search call and, if URLs are returned, one Extract call for up to five pages, then one model request per extracted page. This consumes credits. Interrupted jobs stay interrupted until you retry them.

## Verification

With backend dependencies installed:

```sh
PYTHONPATH=.:backend python -m unittest discover -s backend/tests -v
```

Tests mock Tavily and the model and do not spend credits. A live API call, full Docker startup, and browser portal flow must be verified separately.
