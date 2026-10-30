# Integrated web deployment

`web/` imports the deployed Care Credits application from
`nahiphog/care-credits` commit `27350e560aad4923379f79843a8dc018f05091ea`.
It contains the Next.js dashboard, FastAPI backend, scraper, tests, and Vercel
configuration used by https://care-credits-hackathon.vercel.app/.

This is a staged consolidation, not a replacement of the root application.
The repositories have unrelated Git histories. The root backend has since been
refactored into routers, repositories and services, while the deployed backend
includes serverless execution, production origin handling and discovery fixes.
Keeping this deployment self-contained preserves both implementations for review.
The root application's newer architecture is **not** used by this deployment yet.

## What this brings into the shared repository

- The dashboard at `/`, with old layout versions archived and legacy URLs redirected.
- Account sessions, published catalogue search, personal learning records and operator review.
- Responsive filter dialog, no default city/date filters, and structured discovery results.
- Request-based discovery for Vercel with persisted jobs and truthful completion status.
- Configurable NVIDIA/Nebius model integration, Tavily discovery and extraction receipts.
- Vercel Services configuration and Neon Postgres connectivity; no embedded credentials.

## Local verification

Run commands from `deployments/web`, not the repository root:

```sh
npm ci
npm run build:demo
python -m pip install -r requirements.txt
PYTHONPATH=.:backend python -m unittest backend.tests.test_extraction backend.tests.test_serverless -v
```

See `web/docs/VERCEL.md` for environment names and operational constraints.
Never copy production environment files into Git. No database migration or seeding
is necessary for this source-repository transfer.

## Production handover after review and merge

1. Keep the existing Vercel project `daily-gattai/care-credits`, its domains,
   environment variables and existing Neon integration.
2. Connect that project to `dman1313/CareCredits` and select the agreed production
   branch. Set Root Directory to `deployments/web`.
3. Build a staged production deployment using the existing project settings.
   Verify login, catalogue search, saved records and operator review before promotion.
4. Promote the verified build. The existing `care-credits-hackathon.vercel.app`
   URL stays attached to the project; no new project or paid plan is needed.
5. Roll back to the previous deployment if verification fails.

Opening this PR does not switch the live deployment's source. That switch should
follow review/merge, so unreviewed changes do not replace the working site.

## Follow-up consolidation

Port the deployment-specific fixes and regression tests onto the root's refactored
backend, then point this frontend at that implementation and verify database/API
compatibility. Remove the duplicate backend only after parity is demonstrated.
Until then, treat `deployments/web` as the production application and the root
implementation as the ongoing refactor; avoid assuming edits automatically sync.
