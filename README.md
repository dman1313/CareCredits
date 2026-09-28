# CareCredits

A hackathon application being developed to help Malaysian doctors discover CPD trainings and track sign-ups, attendance and learning progress. The confirmed design uses **three application services: a Python backend, a JavaScript-based frontend, and a separate Python scraper**, with PostgreSQL owned by the backend.

The project requires **real Tavily Search and Extract API usage** and **open-weight models for application AI**. Official hackathon rules still need to be linked and checked. The portal, owned catalogue, operator review, and engagement features exist on this branch. Live Tavily + open-weight DEMO-01 still needs owner model keys.

## Target product

- Doctor sign-in and a personal dashboard.
- Malaysia-only discovery by city/state or optional nearby distance.
- Training details: CPD points, prerequisites, beginner/intermediate/advanced difficulty, and fees, with unknown values explicit.
- Records of courses signed up for and attended, with personal progress. The SDD proposes external registration and self-reported attendance for MVP.
- Source-backed ingestion using Tavily and an open-weight model to produce structured candidates for review.

[The SDD](docs/SDD.md) defines the full MVP, data model, service contracts, acceptance tests and build sequence. Proposed defaults and unresolved decisions are labelled. User-facing credits are called CPDs; original source labels are retained without assuming CE/CME equivalence.

## Tavily's role in the current code

1. An operator queues a bounded Malaysia training job on the backend.
2. The scraper claims the job, calls Tavily Search, then Extract for up to five unique URLs.
3. Successful page text is sent to the configured open-weight model for structured candidates with field evidence.
4. The backend stores candidates for operator review. Doctor search reads PostgreSQL, not Tavily.

Tavily and model keys belong only to the scraper. Results are **unverified sources**, not confirmed accredited events. Missing details must not be invented, and finding an event does not prove attendance or earn credits.

Official API references: [Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) and [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract).

## Current status

- Three Compose services: backend (FastAPI + PostgreSQL), scraper (Tavily + model worker), frontend (Next.js portal).
- Doctor **register** (when `ALLOW_SIGNUP=true` / `--demo`) and catalogue **search** against the owned database.
- **Daily scrape** (OPS-02): curated topics in `config/scrape_topics.json` enqueue once per `Asia/Kuala_Lumpur` day; operator can also `POST /api/v1/admin/daily-scrape`.
- Catalogue **connect / lookup / decide / save** APIs (`/internal/v1/catalogue/*`) with exact `source_key` short-circuit and **Jev** (TypeSafe System One SDK) existence judgments when `TYPESAFE_API_KEY` or `~/.typesafe/key` is set (near matches stay `uncertain` without it).
- Daily scrape uses Tavily Search/Extract plus Firehose (`FIREHOSE_MGMT_KEY`) when configured; doctors still only search the owned catalogue.
- Doctor sign-in uses httponly email/password sessions. Optional Google OAuth when `GOOGLE_CLIENT_*` are set.
- Malaysia catalogue filters, nearby distance when coordinates exist, personal sign-up/attendance, year progress, and an optional public profile are implemented.
- Operator ingestion uses leased jobs and an explicit retry for interrupted work.
- Demo fixtures load only with `DEMO_MODE=true` outside production and are labelled fictional.
- Live UI: http://127.0.0.1:3000/live — DEMO_MODE prefills `demo@carecredits.local`, labels fictional courses/candidates, and shows a fixture review queue separate from live Tavily discovery; operators can show service/integration status (with retry), start a bounded ingestion job, and review/publish or reject candidates; doctors can save city/state, apply FIND-01 filters, browse PROG-02 suggestions, see PROG-01 excluded-credit reasons, use My learning lists, select a progress year, and record sign-up/attendance from the same shell.
- Digests, suggestions, and printable certificates (DEC-10) are in the main workspace and `/live` (`MAIL_PROVIDER=log` by default).
- API errors use `{error:{code,message,request_id}}`. Personal records have `signup_status` including cancelled, plus attendance change history.
- Optional Google OAuth when `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` are set; email/password remains for local demo.
- Live TypeSafe Jev is configured when `TYPESAFE_API_KEY` or `~/.typesafe/key` is present.
- Not yet done: open-weight model live DEMO-01, official hackathon-rule check.

Read [the SDD](docs/SDD.md) and [the coding-agent handoff](docs/CODING_AGENT_HANDOFF.md).

## Configure secrets

Use Python 3.11+ and Docker Compose. From the repository root:

```sh
python3 scripts/setup_integrations.py
```

The script asks privately for the Tavily key, model identity, weights/licence URLs, I/O caps, and open-weight confirmation, writes the ignored `.env`, and generates `SCRAPER_SERVICE_TOKEN` / `POSTGRES_PASSWORD` if missing. Never put secrets in frontend code, `NEXT_PUBLIC_*` variables, chat, screenshots, or Git.

```sh
docker compose up --build
```

- Frontend: http://127.0.0.1:3000
- Backend API docs: http://127.0.0.1:8000/docs

Local three-service development without Compose:

```sh
python3 scripts/dev.py --demo
```

`scripts/dev.py` binds the next free local ports when 8000 or 3000 are already taken, or you can pass `--backend-port` / `--frontend-port`. A second Next.js instance uses its own `NEXT_DIST_DIR` under `frontend/.data/` (Turbopack will not use a dist dir outside the frontend app). It points the backend at scraper `/health/ready` and copies model identity (not `MODEL_API_KEY`) so `/live` can show DEMO-01 service/integration status. Demo sign-in is `demo@carecredits.local` / `CareCredits-demo-2026`. That path uses labelled fictional courses and does not call Tavily.

## Try live ingestion

Sign in as an operator, open **Training sources**, and start a bounded Malaysia topic. The scraper must have `TAVILY_API_KEY`, `MODEL_API_KEY`, `MODEL_ID`, weights/licence URLs, and `MODEL_OPEN_WEIGHT_CONFIRMED=true`. Missing configuration fails explicitly; it never returns demo results as live success.

Each job makes one Search call and, if URLs are returned, one Extract call for up to five pages. Those Tavily sources are stored on the job. Structured candidates need the model settings above; missing model configuration no longer blocks Tavily. Interrupted jobs stay interrupted until you retry them.

## Verification

With backend dependencies installed:

```sh
PYTHONPATH=.:backend python -m unittest discover -s backend/tests -v
```

Tests mock Tavily and the model and do not spend credits. `python3 scripts/happy_path_review.py` walks reject → hold → publish on labelled candidates without API credits. `.venv/bin/python scripts/demo_readiness.py` reports which DEMO-01 live prerequisites are set without printing secrets or calling APIs. A live API call, full Docker startup, and browser portal flow must be verified separately.
