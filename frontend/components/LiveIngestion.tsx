'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { CandidateCard } from '@/components/CandidateCard';
import { IntegrationStatus } from '@/components/IntegrationStatus';
import { api, Candidate, Job } from '@/lib/portal';

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
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const keyRef = useRef('');

  async function loadCandidates() {
    try {
      const data = await api('/admin/candidates?page=1&page_size=5');
      setCandidates(data.items || []);
    } catch {
      setCandidates([]);
    }
  }

  useEffect(() => {
    Promise.all([api('/admin/ingestion-jobs'), loadCandidates()])
      .then(([jobs]) => {
        const items: Job[] = jobs.items || [];
        const fixture = items.find((item) => isFixtureJob(item));
        if (fixture) setJob(fixture);
      })
      .catch(() => {});
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

  async function start(event: FormEvent) {
    event.preventDefault();
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
      await loadCandidates();
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
      <IntegrationStatus className="empty-copy" />
      {(fixtureJob || fixtureCandidates) && (
        <p className="empty-copy" data-testid="fixture-review-banner">
          <span className="badge">FIXTURE</span> Pending candidates below are fictional demo fixtures for offline
          review. They are not a live Tavily Search/Extract or model run. Start a bounded discovery below only when
          live credentials are configured.
        </p>
      )}
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
        <button className="primary" disabled={busy}>
          {busy ? <Loader2 className="spin" size={16} /> : null}
          {busy ? 'Queuing…' : 'Start bounded discovery'}
        </button>
      </form>
      <p className="empty-copy">
        One Search and, if URLs return, one Extract for up to five pages. Doctor search never calls Tavily. Live jobs
        spend operator credits; fixture queue items do not.
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
          candidates.map((item) => (
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
                  await loadCandidates();
                  if (action === 'publish') onPublished?.();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setSaving(false);
                }
              }}
            />
          ))
        ) : (
          <p className="empty-copy">No candidates awaiting review.</p>
        )}
      </div>
    </section>
  );
}
