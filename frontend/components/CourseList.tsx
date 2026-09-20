'use client';

import { ArrowRight, BookOpen, CalendarDays, Check, GraduationCap, Loader2, MapPin } from 'lucide-react';
import { Course, feeLabel, formatDate, modeName } from '@/lib/portal';

export function CourseCard({ course: c, onOpen }: { course: Course; onOpen: () => void }) {
  return (
    <article className="course-card">
      <div className={'course-cover ' + (c.mode === 'online' ? 'peach' : c.difficulty === 'beginner' ? 'blue' : 'green')}>
        <span className="cover-label">
          <GraduationCap size={15} />
          {modeName(c.mode)}
        </span>
        <span className="cover-art" aria-hidden="true">
          {c.mode === 'online' ? '◉' : '✳'}
        </span>
        <span className="point-badge">
          {c.points !== null ? `${c.points} ${c.credit_label || 'credits'}` : 'Points not listed'}
        </span>
      </div>
      <div className="course-body">
        <div className="course-tags">
          {c.demo && <span className="tag">Demo</span>}
          <span>{c.difficulty || 'Level not listed'}</span>
          {c.record?.attended ? (
            <span className="record-status">
              <Check size={13} /> Attended
            </span>
          ) : (
            c.record?.signed_up && <span className="record-status">Signed up</span>
          )}
        </div>
        <h3>
          <button onClick={onOpen}>{c.title}</button>
        </h3>
        <p className="provider">{c.provider}</p>
        <div className="course-meta">
          <span>
            <CalendarDays size={15} />
            {formatDate(c.start_date)}
          </span>
          <span>
            <MapPin size={15} />
            {c.city || 'Online'}
            {c.distance_km != null ? ` · ~${c.distance_km} km` : ''}
          </span>
        </div>
        <div className="card-bottom">
          <strong>{feeLabel(c)}</strong>
          <button aria-label={'View ' + c.title} className="text-btn" onClick={onOpen}>
            View details <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </article>
  );
}

export function Empty({ title, text, action }: { title: string; text: string; action?: () => void }) {
  return (
    <div className="empty-state">
      <BookOpen size={30} />
      <h3>{title}</h3>
      <p>{text}</p>
      {action && (
        <button className="secondary" onClick={action}>
          Explore training <ArrowRight size={16} />
        </button>
      )}
    </div>
  );
}

export function Loading() {
  return (
    <div className="empty-state" role="status">
      <Loader2 className="spin" />
      <p>Finding your training…</p>
    </div>
  );
}
