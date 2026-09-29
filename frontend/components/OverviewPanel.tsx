'use client';

import { ArrowRight, GraduationCap } from 'lucide-react';
import { AuditItem, Course, Progress, Suggestion, formatDate } from '@/lib/portal';
import { CourseCard, Empty, Loading } from '@/components/CourseList';

export function OverviewPanel({
  progress,
  year,
  courses,
  suggestions,
  digestOptIn,
  digestBusy,
  digestFailed = false,
  certBusy,
  loading,
  coursesLoading = false,
  suggestionsFailed = false,
  auditFailed = false,
  audits = [],
  onDiscover,
  onLearning,
  onOpen,
  onToggleDigest,
  onIssueCertificate,
  onYear,
  onRetrySuggestions,
  onRetryAudit,
  onRetryDigest,
}: {
  progress: Progress | null;
  year: number;
  courses: Course[];
  suggestions: Suggestion[];
  digestOptIn: boolean;
  digestBusy: boolean;
  digestFailed?: boolean;
  certBusy: boolean;
  loading: boolean;
  coursesLoading?: boolean;
  suggestionsFailed?: boolean;
  auditFailed?: boolean;
  audits?: AuditItem[];
  onDiscover: () => void;
  onLearning: () => void;
  onOpen: (course: Course) => void;
  onToggleDigest: (next: boolean) => void;
  onIssueCertificate: () => void;
  onYear?: (year: number) => void;
  onRetrySuggestions?: () => void;
  onRetryAudit?: () => void;
  onRetryDigest?: () => void;
}) {
  const progressBusy = loading || !progress || progress.year !== year;
  const points = progressBusy ? '…' : progress.points ?? 0;
  const attended = progressBusy ? '…' : progress.attended ?? 0;
  const signed = progressBusy ? '…' : progress.signed_up ?? 0;
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">MAKE ROOM FOR LEARNING</p>
          <h1>Your next step starts here.</h1>
          <p>Less time searching. More time growing your practice.</p>
        </div>
        <button className="primary" onClick={onDiscover}>
          Find training <ArrowRight size={17} />
        </button>
      </div>
      <div className="overview-grid">
        <section className="learning-hero">
          <div>
            <span className="pill">
              <GraduationCap size={15} /> Your learning record · {year}
            </span>
            <h2>
              Good care starts
              <br />
              with staying curious.
            </h2>
            <p>
              Bring your courses and CPD records together.
              <br />
              At your pace, in one place.
            </p>
            <button className="light-btn" onClick={onLearning}>
              Open my learning <ArrowRight size={16} />
            </button>
          </div>
        </section>
        <section className="summary-card">
          <span className="section-kicker">YOUR YEAR SO FAR</span>
          {onYear && (
            <label>
              Year
              <select
                aria-label="Progress year"
                value={year}
                onChange={(e) => onYear(Number(e.target.value))}
              >
                {[0, 1, 2].map((offset) => {
                  const optionYear = new Date().getFullYear() - offset;
                  return (
                    <option key={optionYear} value={optionYear}>
                      {optionYear}
                    </option>
                  );
                })}
              </select>
            </label>
          )}
          <div className="points-total">
            {points}
            <span>CPDs recorded</span>
          </div>
          <p className="muted">Self-reported learning points</p>
          <div className="mini-stats">
            <div>
              <strong>{attended}</strong>
              <span>Courses attended</span>
            </div>
            <div>
              <strong>{signed}</strong>
              <span>Signed up</span>
            </div>
          </div>
          {!progressBusy && !!progress.excluded && (
            <small>
              {progress.excluded} attended record(s) excluded
              {progress.excluded_reasons?.length
                ? ': ' +
                  progress.excluded_reasons
                    .map((item) =>
                      item.reason === 'unknown_points' ? 'unknown points' : item.credit_label || 'other credit type',
                    )
                    .join(', ')
                : ' (unknown or other credit types)'}
              .
            </small>
          )}
        </section>
      </div>
      <div className="overview-grid engagement-grid">
        <section className="panel">
          <span className="section-kicker">CONSIDER NEXT</span>
          <h2>Suggested upcoming courses</h2>
          <p className="muted">Advisory catalogue matches by city and date. CareCredits does not decide MMC, MOH, or APC compliance.</p>
          {loading && !suggestions.length ? (
            <p className="small-note" role="status" aria-busy="true">
              Loading suggestions…
            </p>
          ) : suggestions.length ? (
            <ul className="source-list">
              {suggestions.slice(0, 5).map((item) => (
                <li key={item.id}>
                  <button className="text-btn" type="button" onClick={() => onOpen({ id: item.id } as Course)}>
                    {formatDate(item.start_date || null)} · {item.title}
                  </button>
                  <small>
                    {' '}
                    {item.city || 'Online'} — {item.reason}
                  </small>
                </li>
              ))}
            </ul>
          ) : (
            <p className="small-note">
              {suggestionsFailed
                ? "Couldn't load suggestions. Check your connection, then try again."
                : 'No upcoming catalogue suggestions yet. Discover training to browse the owned catalogue.'}
              {onRetrySuggestions ? (
                <>
                  {' '}
                  <button className="text-btn" type="button" onClick={onRetrySuggestions}>
                    Retry
                  </button>
                </>
              ) : null}
            </p>
          )}
        </section>
        <section className="panel">
          <span className="section-kicker">STAY INFORMED</span>
          <h2>Digest and certificate</h2>
          {digestFailed ? (
            <p className="small-note">
              Couldn't load digest preference. Check your connection, then try again.
              {onRetryDigest ? (
                <>
                  {' '}
                  <button className="text-btn" type="button" onClick={onRetryDigest}>
                    Retry
                  </button>
                </>
              ) : null}
            </p>
          ) : (
            <label className="check-row">
              <input
                type="checkbox"
                checked={digestOptIn}
                disabled={digestBusy}
                onChange={(e) => onToggleDigest(e.target.checked)}
              />
              <span>
                <strong>Email me the biweekly digest</strong>
                <small>Upcoming catalogue events, known prices, and your recorded CPD total. Unsubscribe from any email.</small>
              </span>
            </label>
          )}
          <p className="small-note">
            Print a CareCredits affiliation statement for {year}. It is not an MMC, MOH, or APC certificate.
          </p>
          <button className="secondary" type="button" disabled={certBusy} onClick={onIssueCertificate}>
            {certBusy ? 'Preparing…' : 'Issue printable certificate'}
          </button>
        </section>
        <section className="panel" id="owner-audit">
          <span className="section-kicker">YOUR ACTIVITY</span>
          <h2>Recent account actions</h2>
          <p className="muted">Your own audit trail. Personal notes and secrets are never shown here.</p>
          {loading && !audits.length ? (
            <p className="small-note" role="status" aria-busy="true">
              Loading your activity…
            </p>
          ) : audits.length ? (
            <ul className="source-list">
              {audits.slice(0, 8).map((item) => (
                <li key={item.id}>
                  {item.action} · {item.entity_id}
                  {item.at ? ` · ${new Date(item.at * 1000).toLocaleString('en-MY')}` : ''}
                </li>
              ))}
            </ul>
          ) : (
            <p className="small-note">
              {auditFailed
                ? "Couldn't load your activity. Check your connection, then try again."
                : 'Sign-up, attendance, and profile saves will appear here.'}
              {auditFailed && onRetryAudit ? (
                <>
                  {' '}
                  <button className="text-btn" type="button" onClick={onRetryAudit}>
                    Retry
                  </button>
                </>
              ) : null}
            </p>
          )}
        </section>
      </div>
      <div className="section-heading">
        <div>
          <p className="section-kicker">KEEP MOVING FORWARD</p>
          <h2>Explore your next opportunity</h2>
        </div>
        <button className="text-btn" onClick={onDiscover}>
          View all training <ArrowRight size={16} />
        </button>
      </div>
      {coursesLoading ? (
        <Loading />
      ) : courses.length ? (
        <div className="course-grid">
          {courses.slice(0, 3).map((c) => (
            <CourseCard key={c.id} course={c} onOpen={() => onOpen(c)} />
          ))}
        </div>
      ) : (
        <Empty
          title="Your catalogue is ready to grow"
          text="An operator can add training through the source discovery workflow."
        />
      )}
    </>
  );
}
