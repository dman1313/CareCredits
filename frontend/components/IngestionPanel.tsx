'use client';

import { FormEvent, MutableRefObject, useState } from 'react';
import { Check, ExternalLink, Loader2, Pause, Sparkles } from 'lucide-react';
import { Candidate, Job, feeLabel, formatDate } from '@/lib/portal';
import { Empty } from '@/components/CourseList';

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
                  {j.result?.candidate_count ?? 0} candidates{' '}
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

function CandidateCard({
  candidate,
  saving,
  onReview,
}: {
  candidate: Candidate;
  saving: boolean;
  onReview: (
    id: string,
    action: string,
    reason: string,
    version?: number,
    corrections?: Record<string, string>,
    evidence?: Record<string, string>,
  ) => void;
}) {
  const [reason, setReason] = useState(candidate.reason || '');
  const [title, setTitle] = useState(candidate.data.title);
  const [excerpt, setExcerpt] = useState(candidate.data.evidence?.title || '');
  return (
    <section className="panel candidate">
      <div className="section-heading">
        <div>
          <h3>{candidate.data.title}</h3>
          <p>
            {candidate.data.provider} · {formatDate(candidate.data.start_date)} · {feeLabel(candidate.data)}
          {candidate.schema_version ? ` · schema ${candidate.schema_version}` : ''}
          </p>
        </div>
        <div className="button-row">
          <span className={'status ' + candidate.status}>{candidate.status}</span>
          <a href={candidate.data.source_url} target="_blank" rel="noreferrer" className="text-btn">
            Open source <ExternalLink size={14} />
          </a>
        </div>
      </div>
      <p>{candidate.data.description}</p>
      <dl className="evidence">
        {Object.entries(candidate.data.evidence).map(([k, v]) => (
          <div key={k}>
            <dt>{k.replaceAll('_', ' ')}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <label>
        Corrected title
        <input value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label>
        Title evidence excerpt
        <textarea
          rows={2}
          value={excerpt}
          onChange={(e) => setExcerpt(e.target.value)}
          placeholder="Verbatim source sentence that supports the corrected title"
        />
      </label>
      <label>
        Review reason
        <textarea
          maxLength={500}
          rows={2}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={candidate.status === 'held' ? 'Required to keep this on hold' : 'Required to hold; optional for publish or reject'}
        />
      </label>
      {candidate.reason ? <p className="small-note">Last reason: {candidate.reason}</p> : null}
      <p className="small-note">
        Confirm the extracted values match the source, including Malaysia eligibility. Publishing is not
        accreditation verification.
      </p>
      <div className="button-row">
        <button
          disabled={saving}
          className="primary"
          onClick={() =>
            onReview(
              candidate.id,
              'publish',
              reason,
              candidate.version,
              title !== candidate.data.title ? { title } : {},
              title !== candidate.data.title ? { title: excerpt } : {},
            )
          }
        >
          <Check size={16} /> Publish reviewed training
        </button>
        <button
          disabled={saving}
          className="secondary"
          onClick={() => onReview(candidate.id, 'hold', reason, candidate.version)}
        >
          <Pause size={16} /> Hold
        </button>
        <button
          disabled={saving}
          className="secondary"
          onClick={() => onReview(candidate.id, 'reject', reason, candidate.version)}
        >
          Reject
        </button>
      </div>
    </section>
  );
}
