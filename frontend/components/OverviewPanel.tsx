'use client';

import { ArrowRight, BookOpen, GraduationCap } from 'lucide-react';
import { Course, Progress } from '@/lib/portal';
import { CourseCard, Empty, Loading } from '@/components/CourseList';

export function OverviewPanel({
  progress,
  courses,
  loading,
  onDiscover,
  onLearning,
  onOpen,
}: {
  progress: Progress | null;
  courses: Course[];
  loading: boolean;
  onDiscover: () => void;
  onLearning: () => void;
  onOpen: (course: Course) => void;
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
              {progress.excluded} attended record(s) have unknown or other credit types and are excluded.
            </small>
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
