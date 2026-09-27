'use client';

import { ArrowRight, BookOpen, GraduationCap } from 'lucide-react';
import { Course, Progress, Suggestion, formatDate } from '@/lib/portal';
import { CourseCard, Empty, Loading } from '@/components/CourseList';

export function OverviewPanel({
  progress,
  courses,
  suggestions,
  digestOptIn,
  digestBusy,
  certBusy,
  loading,
  onDiscover,
  onLearning,
  onOpen,
  onToggleDigest,
  onIssueCertificate,
  onYear,
}: {
  progress: Progress | null;
  courses: Course[];
  suggestions: Suggestion[];
  digestOptIn: boolean;
  digestBusy: boolean;
  certBusy: boolean;
  loading: boolean;
  onDiscover: () => void;
  onLearning: () => void;
  onOpen: (course: Course) => void;
  onToggleDigest: (next: boolean) => void;
  onIssueCertificate: () => void;
  onYear?: (year: number) => void;
}) {
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
              <GraduationCap size={15} /> Your learning record · {progress?.year}
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
          <div className="hero-art" aria-hidden="true">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <BookOpen strokeWidth={1} size={78} />
            <span className="art-spark">✦</span>
            <span className="art-plus">+</span>
          </div>
        </section>
        <section className="summary-card">
          <span className="section-kicker">YOUR YEAR SO FAR</span>
          {onYear && (
            <label>
              Year
              <select
                aria-label="Progress year"
                value={progress?.year || new Date().getFullYear()}
                onChange={(e) => onYear(Number(e.target.value))}
              >
                {[0, 1, 2].map((offset) => {
                  const year = new Date().getFullYear() - offset;
                  return (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  );
                })}
              </select>
            </label>
          )}
          <div className="points-total">
            {progress?.points ?? 0}
            <span>CPDs recorded</span>
          </div>
          <p className="muted">Self-reported learning points</p>
          <div className="mini-stats">
            <div>
              <strong>{progress?.attended ?? 0}</strong>
              <span>Courses attended</span>
            </div>
            <div>
              <strong>{progress?.signed_up ?? 0}</strong>
              <span>Signed up</span>
            </div>
          </div>
          {!!progress?.excluded && (
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
          {suggestions.length ? (
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
            <p className="small-note">No upcoming catalogue suggestions yet. Discover training to browse the owned catalogue.</p>
          )}
        </section>
        <section className="panel">
          <span className="section-kicker">STAY INFORMED</span>
          <h2>Digest and certificate</h2>
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
          <p className="small-note">
            Print a CareCredits affiliation statement for {progress?.year || new Date().getFullYear()}. It is not an MMC,
            MOH, or APC certificate.
          </p>
          <button className="secondary" type="button" disabled={certBusy} onClick={onIssueCertificate}>
            {certBusy ? 'Preparing…' : 'Issue printable certificate'}
          </button>
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
      {loading ? (
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
