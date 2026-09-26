'use client';

import { FormEvent, MutableRefObject, useState } from 'react';
import { Check, ExternalLink, Loader2, Pause, Sparkles } from 'lucide-react';
import { Candidate, Job, feeLabel, formatDate } from '@/lib/portal';
import { Empty } from '@/components/CourseList';

export function IngestionPanel({
  jobQuery,
  jobs,
  candidates,
  submitting,
  saving,
  jobKey,
  onJobQuery,
  onSubmit,
  onRefresh,
  onRetry,
  onReview,
}: {
  jobQuery: string;
  jobs: Job[];
  candidates: Candidate[];
  submitting: boolean;
  saving: boolean;
  jobKey: MutableRefObject<string>;
  onJobQuery: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onRefresh: () => void;
  onRetry: (id: string) => void;
  onReview: (id: string, action: string, reason: string) => void;
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
        <button className="primary" disabled={submitting}>
          {submitting ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />} Start discovery
        </button>
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
                  {j.result?.sources?.length ?? 0} Tavily sources · {j.result?.candidate_count ?? 0} candidates{' '}
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
        <span>{candidates.length} awaiting review</span>
      </div>
      {candidates.map((c) => (
        <CandidateCard key={c.id} candidate={c} saving={saving} onReview={onReview} />
      ))}
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
  onReview: (id: string, action: string, reason: string) => void;
}) {
  const [reason, setReason] = useState(candidate.reason || '');
  return (
    <section className="panel candidate">
      <div className="section-heading">
        <div>
          <h3>{candidate.data.title}</h3>
          <p>
            {candidate.data.provider} · {formatDate(candidate.data.start_date)} · {feeLabel(candidate.data)}
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
        <button disabled={saving} className="primary" onClick={() => onReview(candidate.id, 'publish', reason)}>
          <Check size={16} /> Publish reviewed training
        </button>
        <button disabled={saving} className="secondary" onClick={() => onReview(candidate.id, 'hold', reason)}>
          <Pause size={16} /> Hold
        </button>
        <button disabled={saving} className="secondary" onClick={() => onReview(candidate.id, 'reject', reason)}>
          Reject
        </button>
      </div>
    </section>
  );
}
