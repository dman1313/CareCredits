'use client';

import { FormEvent, MutableRefObject } from 'react';
import { Check, ExternalLink, Loader2, Sparkles } from 'lucide-react';
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
  onReview: (id: string, action: string) => void;
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
          A live run uses API credits and processes up to five sources. Missing credentials produce a setup error, never
          demo results.
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
                  {j.result?.candidate_count ?? 0} candidates{' '}
                  {j.result?.warnings?.map((w, i) => (
                    <span className="job-warning" key={i}>
                      {w}
                    </span>
                  ))}
                </small>
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
        <section key={c.id} className="panel candidate">
          <div className="section-heading">
            <div>
              <h3>{c.data.title}</h3>
              <p>
                {c.data.provider} · {formatDate(c.data.start_date)} · {feeLabel(c.data)}
              </p>
            </div>
            <a href={c.data.source_url} target="_blank" rel="noreferrer" className="text-btn">
              Open source <ExternalLink size={14} />
            </a>
          </div>
          <p>{c.data.description}</p>
          <dl className="evidence">
            {Object.entries(c.data.evidence).map(([k, v]) => (
              <div key={k}>
                <dt>{k.replaceAll('_', ' ')}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          <p className="small-note">
            Confirm the extracted values match the source, including Malaysia eligibility. Publishing is not
            accreditation verification.
          </p>
          <div className="button-row">
            <button disabled={saving} className="primary" onClick={() => onReview(c.id, 'publish')}>
              <Check size={16} /> Publish reviewed training
            </button>
            <button disabled={saving} className="secondary" onClick={() => onReview(c.id, 'reject')}>
              Reject
            </button>
          </div>
        </section>
      ))}
    </>
  );
}
