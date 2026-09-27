'use client';

import { FormEvent, MutableRefObject, useEffect, useState } from 'react';
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
  const [integrations, setIntegrations] = useState<{
    model_id: string | null;
    model_weights_url: string | null;
    model_license_url: string | null;
    model_open_weight_confirmed: boolean;
    model_caps_configured: boolean;
    model_key_configured: boolean;
    typesafe_configured: boolean;
    scraper_token_configured: boolean;
  } | null>(null);
  useEffect(() => {
    fetch('/api/v1/admin/integrations', { credentials: 'include', headers: { 'X-Care-Client': '1' } })
      .then((response) => (response.ok ? response.json() : null))
      .then(setIntegrations)
      .catch(() => setIntegrations(null));
  }, []);
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
        {integrations ? (
          <p className="small-note" data-testid="integration-status">
            Model {integrations.model_id || 'not selected'}
            {integrations.model_open_weight_confirmed ? ' · open-weight confirmed' : ' · open-weight not confirmed'}
            {integrations.model_key_configured ? ' · key present' : ' · key missing'}
            {integrations.model_caps_configured ? ' · caps set' : ' · caps missing'}
            {integrations.typesafe_configured ? ' · Jev ready' : ' · Jev key missing'}
            {integrations.scraper_token_configured ? ' · scraper token set' : ' · scraper token missing'}.
            {integrations.model_weights_url ? (
              <>
                {' '}
                <a href={integrations.model_weights_url} target="_blank" rel="noreferrer">
                  Weights
                </a>
              </>
            ) : null}
            {integrations.model_license_url ? (
              <>
                {' '}
                <a href={integrations.model_license_url} target="_blank" rel="noreferrer">
                  Licence
                </a>
              </>
            ) : null}{' '}
            Secrets stay on the server.
          </p>
        ) : null}
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
  const [edits, setEdits] = useState<Record<string, string>>({
    title: candidate.data.title || '',
    provider: candidate.data.provider || '',
    start_date: candidate.data.start_date || '',
    venue: candidate.data.venue || '',
    city: candidate.data.city || '',
    fee: candidate.data.fee == null ? '' : String(candidate.data.fee),
    points: candidate.data.points == null ? '' : String(candidate.data.points),
  });
  const [excerpts, setExcerpts] = useState<Record<string, string>>({
    title: candidate.data.evidence?.title || '',
    provider: candidate.data.evidence?.provider || '',
    start_date: candidate.data.evidence?.start_date || '',
    venue: candidate.data.evidence?.venue || '',
    city: candidate.data.evidence?.city || '',
    fee: candidate.data.evidence?.fee || '',
    points: candidate.data.evidence?.points || '',
  });
  const original: Record<string, string> = {
    title: candidate.data.title || '',
    provider: candidate.data.provider || '',
    start_date: candidate.data.start_date || '',
    venue: candidate.data.venue || '',
    city: candidate.data.city || '',
    fee: candidate.data.fee == null ? '' : String(candidate.data.fee),
    points: candidate.data.points == null ? '' : String(candidate.data.points),
  };
  function publishPayload() {
    const corrections: Record<string, string> = {};
    const evidence: Record<string, string> = {};
    for (const field of Object.keys(edits)) {
      if ((edits[field] || '') !== (original[field] || '')) {
        corrections[field] = edits[field];
        evidence[field] = excerpts[field] || '';
      }
    }
    return { corrections, evidence };
  }
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
      {candidate.data._refresh_diff?.length ? (
        <div className="refresh-diff" data-testid="refresh-diff">
          <p className="small-note">Proposed changes versus the published session. Review before overwriting.</p>
          <dl className="evidence">
            {candidate.data._refresh_diff.map((change) => (
              <div key={change.field}>
                <dt>{change.field.replaceAll('_', ' ')}</dt>
                <dd>
                  Published: {change.published == null || change.published === '' ? 'Unknown' : String(change.published)}
                  {' → '}
                  Proposed: {change.proposed == null || change.proposed === '' ? 'Unknown' : String(change.proposed)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
      <dl className="evidence">
        {Object.entries(candidate.data.evidence).map(([k, v]) => (
          <div key={k}>
            <dt>{k.replaceAll('_', ' ')}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {(
        [
          ['title', 'Corrected title'],
          ['provider', 'Corrected provider'],
          ['start_date', 'Corrected start date'],
          ['venue', 'Corrected venue'],
          ['city', 'Corrected city'],
          ['fee', 'Corrected fee'],
          ['points', 'Corrected points'],
        ] as const
      ).map(([field, label]) => (
        <div key={field}>
          <label>
            {label}
            <input
              value={edits[field]}
              onChange={(e) => setEdits({ ...edits, [field]: e.target.value })}
            />
          </label>
          {edits[field] !== original[field] ? (
            <label>
              {label.replace('Corrected ', '')} evidence excerpt
              <textarea
                rows={2}
                value={excerpts[field]}
                onChange={(e) => setExcerpts({ ...excerpts, [field]: e.target.value })}
                placeholder="Verbatim source sentence that supports this correction"
              />
            </label>
          ) : null}
        </div>
      ))}
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
          onClick={() => {
            const payload = publishPayload();
            onReview(candidate.id, 'publish', reason, candidate.version, payload.corrections, payload.evidence);
          }}
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
