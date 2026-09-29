'use client';

import { FormEvent, MutableRefObject, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { AuditItem, Candidate, Job, publicWebUrl } from '@/lib/portal';
import { Empty, Loading } from '@/components/CourseList';
import { IntegrationStatus } from '@/components/IntegrationStatus';
import { CandidateCard } from '@/components/CandidateCard';

export function IngestionPanel({
  jobQuery,
  jobMaxResults,
  jobs,
  candidates,
  candidatePage = 1,
  candidateTotal,
  submitting,
  saving,
  jobKey,
  onJobQuery,
  onJobMaxResults,
  onSubmit,
  onRefresh,
  onRetry,
  onReview,
  onDailyScrape,
  onCandidatePage,
  loading = false,
  failed = false,
  auditFailed = false,
  topics = [],
  ceiling = null,
  scrapeDay = '',
  forceScrape = false,
  onForceScrape,
  scrapeResult,
  onRunDigests,
  digestResult,
  audits = [],
}: {
  jobQuery: string;
  jobMaxResults: number;
  jobs: Job[];
  candidates: Candidate[];
  candidatePage?: number;
  candidateTotal?: number;
  submitting: boolean;
  saving: boolean;
  jobKey: MutableRefObject<string>;
  onJobQuery: (value: string) => void;
  onJobMaxResults: (value: number) => void;
  onSubmit: (event: FormEvent) => void;
  onRefresh: () => void;
  onRetry: (id: string) => void;
  onReview: (
    id: string,
    action: string,
    reason: string,
    version?: number,
    corrections?: Record<string, string>,
    evidence?: Record<string, string>,
  ) => void;
  onDailyScrape?: () => void;
  onCandidatePage?: (page: number) => void;
  loading?: boolean;
  failed?: boolean;
  auditFailed?: boolean;
  topics?: { query: string; max_results: number }[];
  ceiling?: number | null;
  scrapeDay?: string;
  forceScrape?: boolean;
  onForceScrape?: (next: boolean) => void;
  scrapeResult?: { enqueued: number; skipped: number; day: string; ceiling: number; topics: number } | null;
  onRunDigests?: () => void;
  digestResult?: { sent: number; failed: number; day: string } | null;
  audits?: AuditItem[];
}) {
  const [liveReady, setLiveReady] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const paidBlocked = !liveReady || statusLoading;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (paidBlocked) return;
    onSubmit(event);
  }

  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">OPERATOR WORKSPACE</p>
          <h1>Bring useful training into view.</h1>
          <p>Tavily finds sources. An open-weight model extracts details. You review the evidence.</p>
        </div>
      </div>
      <form className="panel ingestion-form" onSubmit={handleSubmit}>
        <label>
          Malaysia training topic
          <input
            required
            minLength={3}
            maxLength={300}
            value={jobQuery}
            onChange={(e) => {
              onJobQuery(e.target.value);
              jobKey.current = '';
            }}
          />
        </label>
        <label>
          Source pages
          <select
            aria-label="Maximum source pages"
            value={jobMaxResults}
            onChange={(e) => {
              onJobMaxResults(Number(e.target.value));
              jobKey.current = '';
            }}
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="button-row">
          <button className="primary" disabled={submitting || paidBlocked}>
            {submitting ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />} Start discovery
          </button>
          {onDailyScrape && (
            <button
              className="secondary"
              type="button"
              disabled={saving || submitting || paidBlocked}
              onClick={() => {
                if (paidBlocked) return;
                onDailyScrape();
              }}
            >
              Queue daily scrape
            </button>
          )}
          {onRunDigests && (
            <button className="secondary" type="button" disabled={saving || submitting} onClick={onRunDigests}>
              Send due digests
            </button>
          )}
        </div>
        {onDailyScrape && onForceScrape ? (
          <label className="check-row">
            <input type="checkbox" checked={forceScrape} onChange={(e) => onForceScrape(e.target.checked)} />
            <span>Re-queue idle jobs (force)</span>
          </label>
        ) : null}
        {scrapeResult ? (
          <p className="small-note">
            Daily scrape {scrapeResult.day}: {scrapeResult.enqueued} queued, {scrapeResult.skipped} skipped, ceiling{' '}
            {scrapeResult.ceiling}, {scrapeResult.topics} topics.
          </p>
        ) : null}
        {digestResult ? (
          <p className="small-note">
            Digest {digestResult.day}: {digestResult.sent} sent, {digestResult.failed} failed. Catalogue and progress
            only — no Tavily call.
          </p>
        ) : null}
        {topics.length ? (
          <div className="small-note">
            <p>
              Curated daily topics ({topics.length}
              {ceiling != null ? ` · ceiling ${ceiling}` : ''}
              {scrapeDay ? ` · ${scrapeDay}` : ''}). Edit config/scrape_topics.json to change the list.
            </p>
            <ul className="source-list">
              {topics.map((topic) => (
                <li key={topic.query}>
                  {topic.query} · up to {topic.max_results}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <p className="small-note">
          {liveReady
            ? 'A live run uses Tavily Search and Extract for up to five sources. Missing Tavily credentials fail honestly. Structured candidates still need a configured open-weight model.'
            : 'Live discovery stays off until Tavily and the open-weight model are ready. Review the fixture queue without spending credits.'}
        </p>
        <IntegrationStatus
          onLiveReady={(ready, loading) => {
            setLiveReady(ready);
            setStatusLoading(loading);
          }}
        />
      </form>
      <div className="section-heading">
        <h2>Discovery jobs</h2>
        <button className="text-btn" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      <div className="job-list">
        {loading && !jobs.length ? (
          <Loading text="Loading discovery jobs…" />
        ) : jobs.length ? (
          jobs.map((j) => (
            <article className="job-row" key={j.id}>
              <div>
                <strong>{j.query}</strong>
                <small>
                  Up to {j.max_results ?? 5} pages · {j.result?.sources?.length ?? 0} Tavily sources ·{' '}
                  {j.result?.candidate_count ?? 0} candidates
                  {j.result?.usage?.tavily_credits != null
                    ? ` · ${j.result.usage.tavily_credits} reported Tavily credits`
                    : ''}
                  {j.result?.usage?.model_tokens != null
                    ? ` · ${j.result.usage.model_tokens} reported model tokens`
                    : ''}{' '}
                  {j.result?.warnings?.map((w, i) => (
                    <span className="job-warning" key={i}>
                      {w}
                    </span>
                  ))}
                </small>
                {j.result?.sources?.length ? (
                  <ul className="source-list">
                    {j.result.sources.map((source, index) => {
                      const href = publicWebUrl(source.url);
                      return (
                        <li key={source.url || source.title || index}>
                          {href ? (
                            <a href={href} target="_blank" rel="noreferrer">
                              {source.title || source.url}
                            </a>
                          ) : (
                            <span>{source.title || 'Source URL is not available'}</span>
                          )}
                          {source.snippet ? <span> — {source.snippet}</span> : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </div>
              <div className="button-row">
                <span className={'status ' + j.status}>{j.status}</span>
                {j.status === 'interrupted' && (
                  <button
                    className="secondary"
                    disabled={saving || paidBlocked}
                    onClick={() => {
                      if (paidBlocked) return;
                      onRetry(j.id);
                    }}
                  >
                    Retry job
                  </button>
                )}
              </div>
            </article>
          ))
        ) : (
          <Empty
            title={failed ? "Couldn't load discovery jobs" : 'No discovery jobs yet'}
            text={
              failed
                ? 'Check your connection, then try again.'
                : 'Start a search above to populate the review queue.'
            }
            action={onRefresh}
            actionLabel="Retry"
          />
        )}
      </div>
      <div className="section-heading">
        <h2>Review candidates</h2>
        <span>
          {loading && !candidates.length
            ? 'Loading…'
            : failed
              ? "Couldn't load…"
              : `${candidateTotal ?? candidates.length} awaiting review`}
        </span>
      </div>
      {loading && !candidates.length ? (
        <Loading text="Loading review candidates…" />
      ) : candidates.length ? (
        <>
          {candidates.map((c) => <CandidateCard key={c.id} candidate={c} saving={saving} onReview={onReview} />)}
          {onCandidatePage && (candidateTotal ?? 0) > 20 && (
            <div className="pagination">
              <button
                className="secondary"
                type="button"
                disabled={candidatePage <= 1 || saving}
                onClick={() => onCandidatePage(candidatePage - 1)}
              >
                Previous
              </button>
              <span>
                Page {candidatePage} of {Math.max(1, Math.ceil((candidateTotal || 0) / 20))}
              </span>
              <button
                className="secondary"
                type="button"
                disabled={candidatePage * 20 >= (candidateTotal || 0) || saving}
                onClick={() => onCandidatePage(candidatePage + 1)}
              >
                Next
              </button>
            </div>
          )}
        </>
      ) : (
        <Empty
          title={failed ? "Couldn't load review candidates" : 'No candidates awaiting review'}
          text={
            failed
              ? 'Check your connection, then try again.'
              : 'Queued jobs will appear here after the scraper finishes.'
          }
          action={onRefresh}
          actionLabel="Retry"
        />
      )}
      <div className="section-heading">
        <h2>Operator audit</h2>
        <span>
          {loading && !audits.length
            ? 'Loading…'
            : auditFailed && !audits.length
              ? "Couldn't load…"
              : `${audits.length} recent`}
        </span>
      </div>
      {loading && !audits.length ? (
        <p className="small-note" role="status" aria-busy="true">
          Loading operator activity…
        </p>
      ) : audits.length ? (
        <ul className="source-list">
          {audits.map((item) => (
            <li key={item.id}>
              {item.action} · {item.entity_id}
              {item.at ? ` · ${new Date(item.at * 1000).toLocaleString('en-MY')}` : ''}
            </li>
          ))}
        </ul>
      ) : (
        <p className="small-note">
          {auditFailed
            ? "Couldn't load operator activity. Check your connection, then try again."
            : 'Review and profile actions appear here. Personal notes are never stored on this list.'}
          {auditFailed ? (
            <>
              {' '}
              <button className="text-btn" type="button" onClick={onRefresh}>
                Retry
              </button>
            </>
          ) : null}
        </p>
      )}
    </>
  );
}
