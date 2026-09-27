'use client';

import { FormEvent, MutableRefObject } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { Candidate, Job } from '@/lib/portal';
import { Empty } from '@/components/CourseList';
import { IntegrationStatus } from '@/components/IntegrationStatus';
import { CandidateCard } from '@/components/CandidateCard';

export function IngestionPanel({
  jobQuery,
  jobMaxResults,
  jobs,
  candidates,
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
}: {
  jobQuery: string;
  jobMaxResults: number;
  jobs: Job[];
  candidates: Candidate[];
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
}) {
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">OPERATOR WORKSPACE</p>
          <h1>Bring useful training into view.</h1>
          <p>Tavily finds sources. An open-weight model extracts details. You review the evidence.</p>
        </div>
      </div>
      <form className="panel ingestion-form" onSubmit={onSubmit}>
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
          <button className="primary" disabled={submitting}>
            {submitting ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />} Start discovery
          </button>
          {onDailyScrape && (
            <button className="secondary" type="button" disabled={saving || submitting} onClick={onDailyScrape}>
              Queue daily scrape
            </button>
          )}
        </div>
        <p className="small-note">
          A live run uses Tavily Search and Extract for up to five sources. Missing Tavily credentials fail honestly.
          Structured candidates still need a configured open-weight model.
        </p>
        <IntegrationStatus />
      </form>
      <div className="section-heading">
        <h2>Discovery jobs</h2>
        <button className="text-btn" onClick={onRefresh}>
          Refresh
        </button>
      </div>
      <div className="job-list">
        {jobs.length ? (
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
                    {j.result.sources.map((source) => (
                      <li key={source.url}>
                        <a href={source.url} target="_blank" rel="noreferrer">
                          {source.title || source.url}
                        </a>
                        {source.snippet ? <span> — {source.snippet}</span> : null}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
              <div className="button-row">
                <span className={'status ' + j.status}>{j.status}</span>
                {j.status === 'interrupted' && (
                  <button className="secondary" disabled={saving} onClick={() => onRetry(j.id)}>
                    Retry job
                  </button>
                )}
              </div>
            </article>
          ))
        ) : (
          <Empty title="No discovery jobs yet" text="Start a search above to populate the review queue." />
        )}
      </div>
      <div className="section-heading">
        <h2>Review candidates</h2>
        <span>{candidateTotal ?? candidates.length} awaiting review</span>
      </div>
      {candidates.length ? (
        candidates.map((c) => <CandidateCard key={c.id} candidate={c} saving={saving} onReview={onReview} />)
      ) : (
        <Empty title="No candidates awaiting review" text="Queued jobs will appear here after the scraper finishes." />
      )}
    </>
  );
}
