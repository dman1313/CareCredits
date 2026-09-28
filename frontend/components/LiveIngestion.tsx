'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { CandidateCard } from '@/components/CandidateCard';
import { IntegrationStatus } from '@/components/IntegrationStatus';
import { api, Candidate, Job } from '@/lib/portal';

type Topic = { query: string; max_results: number };
type ScrapeResult = { enqueued: number; skipped: number; day: string; ceiling: number; topics: number };

const TERMINAL = new Set(['succeeded', 'partial', 'failed']);

function isFixtureJob(job: Job | null) {
  if (!job) return false;
  return (
    job.result?.extraction_status === 'fixture' ||
    (job.query || '').toLowerCase().includes('fictional fixtures') ||
    (job.result?.warnings || []).some((warning) => warning.toUpperCase().includes('FIXTURE'))
  );
}

export function LiveIngestion({ onPublished }: { onPublished?: () => void }) {
  const [query, setQuery] = useState('GP CPD courses Kuala Lumpur');
  const [maxResults, setMaxResults] = useState(3);
  const [job, setJob] = useState<Job | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidatePage, setCandidatePage] = useState(1);
  const [candidateTotal, setCandidateTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [liveReady, setLiveReady] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [ceiling, setCeiling] = useState<number | null>(null);
  const [scrapeDay, setScrapeDay] = useState('');
  const [forceScrape, setForceScrape] = useState(false);
  const [scrapeBusy, setScrapeBusy] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<ScrapeResult | null>(null);
  const keyRef = useRef('');
  const CANDIDATE_PAGE = 20;

  async function loadCandidates(page = candidatePage) {
    try {
      const data = await api('/admin/candidates?page=' + page + '&page_size=' + CANDIDATE_PAGE);
      const total = data.total || 0;
      const pageCount = Math.max(1, Math.ceil(total / CANDIDATE_PAGE));
      if (page > pageCount) {
        await loadCandidates(pageCount);
        return;
      }
      setCandidates(data.items || []);
      setCandidateTotal(total);
      setCandidatePage(page);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    Promise.all([
      api('/admin/ingestion-jobs'),
      loadCandidates(),
      api('/admin/scrape-topics').catch(() => null),
    ])
      .then(([jobList, _candidates, topicPayload]) => {
        const items: Job[] = jobList.items || [];
        setJobs(items);
        const fixture = items.find((item) => isFixtureJob(item));
        if (fixture) setJob(fixture);
        if (topicPayload) {
          setTopics(topicPayload.topics || []);
          setCeiling(topicPayload.ceiling ?? null);
          setScrapeDay(topicPayload.day || '');
        }
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  useEffect(() => {
    if (!job?.id || TERMINAL.has(job.status) || job.status === 'interrupted') {
      if (job?.id && TERMINAL.has(job.status)) loadCandidates();
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const current = await api('/admin/ingestion-jobs/' + job.id);
        setJob(current);
        if (TERMINAL.has(current.status)) loadCandidates();
      } catch {
        /* keep last known status */
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  async function queueDaily() {
    if (!liveReady) {
      setError('Live discovery stays off until Tavily and the open-weight model are ready.');
      return;
    }
    setScrapeBusy(true);
    setError('');
    try {
      const result = await api('/admin/daily-scrape?force=' + String(forceScrape), { method: 'POST' });
      setScrapeResult(result);
      const jobList = await api('/admin/ingestion-jobs');
      setJobs(jobList.items || []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScrapeBusy(false);
    }
  }

  async function start(event: FormEvent) {
    event.preventDefault();
    if (!liveReady) {
      setError('Live discovery stays off until Tavily and the open-weight model are ready.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      if (!keyRef.current) keyRef.current = crypto.randomUUID();
      const created = await api('/admin/ingestion-jobs', {
        method: 'POST',
        headers: { 'Idempotency-Key': keyRef.current },
        body: JSON.stringify({ query, max_results: maxResults }),
      });
      keyRef.current = '';
      setJob(created);
      await loadCandidates(1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function retry() {
    if (!job?.id) return;
    setBusy(true);
    setError('');
    try {
      setJob(await api('/admin/ingestion-jobs/' + job.id + '/retry', { method: 'POST' }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const sources = job?.result?.sources || [];
  const warnings = job?.result?.warnings || [];
  const fixtureJob = isFixtureJob(job);
  const fixtureCandidates = candidates.some(
    (item) => item.data._fixture || (item.data.source_url || '').includes('carecredits-demo-candidate'),
  );

  return (
    <section className="card">
      <div className="card-heading">
        <div>
          <span className="heading-icon">▣</span>
          <h2>{fixtureJob || fixtureCandidates ? 'Fixture review queue' : 'Live ingestion'}</h2>
        </div>
      </div>
      <IntegrationStatus
        className="empty-copy"
        onLiveReady={(ready, loading) => {
          setLiveReady(ready);
          setStatusLoading(loading);
        }}
      />
      {(fixtureJob || fixtureCandidates) && (
        <p className="empty-copy" data-testid="fixture-review-banner">
          <span className="badge">FIXTURE</span> Pending candidates below are fictional demo fixtures for offline
          review. They are not a live Tavily Search/Extract or model run. Start a bounded discovery below only when
          live credentials are configured.
        </p>
      )}
      {topics.length ? (
        <div className="empty-copy" data-testid="live-scrape-topics">
          <p>
            Curated daily topics ({topics.length}
            {ceiling != null ? ` · ceiling ${ceiling}` : ''}
            {scrapeDay ? ` · ${scrapeDay}` : ''}). Edit config/scrape_topics.json to change the list.
          </p>
          <ul>
            {topics.map((topic) => (
              <li key={topic.query}>
                {topic.query} · up to {topic.max_results}
              </li>
            ))}
          </ul>
          <label>
            <input type="checkbox" checked={forceScrape} onChange={(e) => setForceScrape(e.target.checked)} />{' '}
            Re-queue idle jobs (force)
          </label>{' '}
          <button className="secondary" type="button" disabled={scrapeBusy || !liveReady || statusLoading} onClick={queueDaily}>
            {scrapeBusy ? 'Queuing…' : 'Queue daily scrape'}
          </button>
          {scrapeResult ? (
            <p>
              Daily scrape {scrapeResult.day}: {scrapeResult.enqueued} queued, {scrapeResult.skipped} skipped, ceiling{' '}
              {scrapeResult.ceiling}, {scrapeResult.topics} topics.
            </p>
          ) : null}
        </div>
      ) : null}
      {jobs.length ? (
        <div className="empty-copy" data-testid="live-job-list">
          <p>Recent jobs</p>
          <ul>
            {jobs.slice(0, 8).map((item) => (
              <li key={item.id}>
                {item.status} · {item.query}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <form className="empty-copy" onSubmit={start}>
        <label>
          Malaysia training topic
          <input
            required
            minLength={3}
            maxLength={300}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              keyRef.current = '';
            }}
          />
        </label>
        <label>
          Source pages
          <select
            aria-label="Maximum source pages"
            value={maxResults}
            onChange={(e) => {
              setMaxResults(Number(e.target.value));
              keyRef.current = '';
            }}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button className="primary" disabled={busy || !liveReady || statusLoading}>
          {busy ? <Loader2 className="spin" size={16} /> : null}
          {busy ? 'Queuing…' : 'Start bounded discovery'}
        </button>
      </form>
      <p className="empty-copy">
        {liveReady
          ? 'One Search and, if URLs return, one Extract for up to five pages. Doctor search never calls Tavily. Live jobs spend operator credits; fixture queue items do not.'
          : 'Live discovery stays off until Tavily and the open-weight model are ready. Review the fixture queue without spending credits.'}
      </p>
      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}
      {job && (
        <div className="empty-copy" data-testid="live-job-status">
          <p>
            {fixtureJob ? 'Fixture job' : 'Job'} {job.status}
            {job.result?.usage?.tavily_credits != null ? ` · ${job.result.usage.tavily_credits} reported Tavily credits` : ''}
            {job.result?.usage?.model_tokens != null ? ` · ${job.result.usage.model_tokens} reported model tokens` : ''}
          </p>
          {sources.length ? (
            <ul>
              {sources.map((source) => (
                <li key={source.url}>
                  {source.extraction_status}: {source.url}
                </li>
              ))}
            </ul>
          ) : (
            <p>{fixtureJob ? 'Fixture sources are labelled below. No Tavily URLs were fetched.' : 'No Tavily source URLs yet.'}</p>
          )}
          {warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
          {job.status === 'interrupted' && (
            <button className="secondary" type="button" disabled={busy} onClick={retry}>
              Retry interrupted job
            </button>
          )}
        </div>
      )}
      <div data-testid="live-review-queue">
        <h3 className="empty-copy">Review candidates</h3>
        {candidates.length ? (
          <>
            {candidates.map((item) => (
              <CandidateCard
                key={item.id}
                candidate={item}
                saving={saving}
                onReview={async (id, action, reason, version, corrections, evidence) => {
                  setSaving(true);
                  setError('');
                  try {
                    await api('/admin/candidates/' + id + '/review', {
                      method: 'POST',
                      body: JSON.stringify({ action, reason, version, corrections, evidence }),
                    });
                    await loadCandidates(candidatePage);
                    if (action === 'publish') onPublished?.();
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setSaving(false);
                  }
                }}
              />
            ))}
            {candidateTotal > CANDIDATE_PAGE && (
              <div className="pager" data-testid="live-candidate-pager">
                <button
                  className="text-link"
                  type="button"
                  disabled={candidatePage <= 1 || saving}
                  onClick={() => loadCandidates(candidatePage - 1)}
                >
                  Previous
                </button>
                <span>
                  Page {candidatePage} of {Math.max(1, Math.ceil(candidateTotal / CANDIDATE_PAGE))}
                </span>
                <button
                  className="text-link"
                  type="button"
                  disabled={candidatePage * CANDIDATE_PAGE >= candidateTotal || saving}
                  onClick={() => loadCandidates(candidatePage + 1)}
                >
                  Next
                </button>
              </div>
            )}
          </>
        ) : (
          <p className="empty-copy">No candidates awaiting review.</p>
        )}
      </div>
    </section>
  );
}
