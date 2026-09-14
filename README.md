# CareCredits

A hackathon prototype for helping Malaysian doctors discover CPD learning opportunities and, eventually, track their learning. The project owner specifies that this is a **Tavily hackathon project and must make real Tavily API calls**. The official event rules still need to be linked and checked.

## Tavily's role

1. FastAPI sends a course search to Tavily Search.
2. It deduplicates returned URLs and sends up to five to Tavily Extract.
3. It returns titles, source URLs, snippets, extracted text, retrieval time, and extraction status.
4. Later work will turn these sources into reviewed, structured event records for the dashboard.

This implements the previously proposed scraper inside FastAPI; there is no separate scraper microservice yet. Results are **unverified sources**, not confirmed accredited events. Missing details must not be invented, and finding an event does not prove attendance or earn credits.

Official API references: [Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) and [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract).

## Current status

- Next.js/React/Tailwind dashboard: prototype with hardcoded examples, including non-Malaysian events and illustrative compliance numbers. These are not validated Malaysian requirements.
- FastAPI/SQLAlchemy: basic user endpoints plus protected `POST /discovery/search` using Tavily Search and Extract.
- PostgreSQL: configured through Docker Compose; SQLite is the local backend fallback.
- Not yet implemented: dashboard connection to discovery, event parsing/persistence, accreditation verification, registrations, certificate processing, or real CPD accounting.
- Nebius was mentioned in earlier planning. Its required role is unresolved; no Nebius integration is claimed.

Read [the SDD](docs/SDD.md) and [the coding-agent handoff](docs/CODING_AGENT_HANDOFF.md).

## Configure the API key

Use Python 3.11+ and Docker Compose. From the repository root:

```sh
python3 scripts/setup_tavily.py
```

The script asks for your **Tavily API key with hidden input**, creates or updates the ignored root `.env`, and generates a separate `DISCOVERY_API_TOKEN` if missing. Obtain your key from the [Tavily dashboard](https://app.tavily.com/).

This is developer setup: doctors should not supply API keys. Never put either secret in frontend code, `NEXT_PUBLIC_*` variables, chat, screenshots, or Git. For deployment, use server-side secret settings. Configuration alone does not verify that a key works.

Before starting Docker, review the database and other placeholder credentials in `.env`. Keep POSTGRES_* and DB_* database values consistent; DB_PORT is the container's PostgreSQL port, normally 5432.

```sh
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend interactive API docs: http://localhost:8000/docs

Compose loads `.env` into the backend. For a direct Python launch, install `backend/requirements.txt` in a virtual environment and run from the root:

```sh
python -m uvicorn main:app --app-dir backend --env-file .env --port 8000
```

## Try real discovery

In the local API docs, click **Authorize** and enter the `DISCOVERY_API_TOKEN` from your local `.env` (not the Tavily key). Execute `POST /discovery/search`:

```json
{"query": "cardiology workshops Kuala Lumpur 2026", "max_results": 5}
```

Each request makes one basic Search call and, if suitable URLs are returned, one basic Extract call for up to five pages. This consumes Tavily credits; no automatic retries or background crawling are enabled.

Results contain `provider`, `query`, `retrieved_at`, `sources`, and `warnings`. Each source has `url`, `title`, `snippet`, `raw_content`, `extraction_status`, and `verification_status: "unverified"`. Extraction failures retain snippets and report warnings. An empty successful search returns an empty list; configuration/provider failures are explicit errors, never sample results.

The endpoint uses a separate bearer token and Compose exposes the backend only on loopback. Do not expose that token to a public browser; add authenticated user access and rate limits before connecting a public UI.

## Verification

With backend dependencies installed:

```sh
python -m unittest discover -s backend/tests -v
```

Tests mock Tavily and do not spend credits. A live API call, full Docker startup, and frontend discovery flow must be verified separately. Do not present mocks as evidence of live Tavily usage.
