'use client';

import { FormEvent, useEffect, useRef } from 'react';
import { Check, ExternalLink, X } from 'lucide-react';
import {
  Course,
  RecordData,
  RecordHistoryItem,
  feeLabel,
  formatDate,
  locationLabel,
  modeName,
  todayLocal,
} from '@/lib/portal';

export function TrainingDetail({
  course,
  edit,
  error,
  saving,
  history = [],
  onClose,
  onEdit,
  onSave,
  canCancel = false,
  onCancel,
}: {
  course: Course;
  edit: RecordData;
  error: string;
  saving: boolean;
  history?: RecordHistoryItem[];
  onClose: () => void;
  onEdit: (next: RecordData) => void;
  onSave: (event: FormEvent) => void;
  canCancel?: boolean;
  onCancel?: () => void;
}) {
  const attendable = !course.start_date || course.start_date <= todayLocal();
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const items = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>('button:not(:disabled),a,input,textarea,select'),
      );
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus();
    };
  }, [onClose]);
  return (
    <div className="modal-shade" onClick={onClose}>
      <section
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="training-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <button autoFocus className="modal-close icon-btn" aria-label="Close training details" onClick={onClose}>
          <X />
        </button>
        <span className="pill">
          {modeName(course.mode)} {course.demo ? '· Demo course' : ''}
          {course.verification_status === 'source_reviewed' ? ' · Source reviewed' : ' · Unverified claims'}
        </span>
        <h2 id="training-title">{course.title}</h2>
        <p className="muted">{course.provider}</p>
        <p>{course.description}</p>
        <div className="detail-grid">
          <div>
            <small>Date</small>
            <strong>
              {formatDate(course.start_date)}
              {course.end_date ? ` – ${formatDate(course.end_date)}` : ''}
              {course.timezone ? ` · ${course.timezone}` : ''}
            </strong>
          </div>
          <div>
            <small>Location</small>
            <strong>{locationLabel(course)}</strong>
          </div>
          <div>
            <small>Fee</small>
            <strong>{feeLabel(course)}</strong>
          </div>
          <div>
            <small>Advertised credits</small>
            <strong>
              {course.points ?? 'Not listed'} {course.credit_label || ''}
            </strong>
          </div>
          <div>
            <small>Level</small>
            <strong>{course.difficulty || 'Not listed'}</strong>
          </div>
          <div>
            <small>Prerequisites</small>
            <strong>
              {course.prerequisites || 'Unknown — source does not establish prerequisites'}
            </strong>
          </div>
        </div>
        {(course.field_evidence?.length || Object.keys(course.evidence || {}).length) ? (
          <dl className="evidence">
            {(course.field_evidence?.length
              ? course.field_evidence.map((row) => [row.field_name, row.excerpt] as const)
              : Object.entries(course.evidence)
            ).map(([field, excerpt]) => (
              <div key={field}>
                <dt>{field.replaceAll('_', ' ')}</dt>
                <dd>{excerpt}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <div className="button-row">
          {course.registration_url && (
            <a className="secondary" href={course.registration_url} target="_blank" rel="noreferrer">
              Provider registration <ExternalLink size={14} />
            </a>
          )}
          <a className="text-btn" href={course.source_url} target="_blank" rel="noreferrer">
            View original source <ExternalLink size={14} />
          </a>
          {canCancel && onCancel && course.publication_status !== 'cancelled' ? (
            <button type="button" className="text-btn" disabled={saving} onClick={onCancel}>
              Cancel published session
            </button>
          ) : null}
          {course.publication_status === 'cancelled' ? <span className="small-note">Session cancelled; personal records are kept.</span> : null}
        </div>
        <p className="small-note">
          Confirm details and CPD eligibility with the provider. Opening a link does not register you.
          Attendance you record here is self-reported and is not MMC, MOH, or APC proof.
        </p>
        <hr />
        <form onSubmit={onSave}>
          <h3>Your personal record</h3>
          {error && (
            <p className="alert error" role="alert">
              {error}
            </p>
          )}
          <label>
            Provider sign-up
            <select
              value={edit.signup_status || (edit.signed_up ? 'signed_up' : 'not_recorded')}
              onChange={(e) =>
                onEdit({
                  ...edit,
                  signup_status: e.target.value as RecordData['signup_status'],
                  signed_up: e.target.value === 'signed_up',
                })
              }
            >
              <option value="not_recorded">Not recorded</option>
              <option value="signed_up">Signed up with the provider</option>
              <option value="cancelled">Cancelled sign-up</option>
            </select>
          </label>
          <label>
            Attendance
            <select
              aria-label="Attendance status"
              value={edit.attendance_status || (edit.attended ? 'attended' : 'not_recorded')}
              disabled={!attendable && !edit.attended}
              onChange={(e) => {
                const attendance_status = e.target.value as RecordData['attendance_status'];
                const attended = attendance_status === 'attended';
                onEdit({
                  ...edit,
                  attendance_status,
                  attended,
                  attended_on: attended ? edit.attended_on || todayLocal() : null,
                  public: attended ? edit.public : false,
                });
              }}
            >
              <option value="not_recorded">Not recorded</option>
              <option value="attended">Attended</option>
            </select>
            {!attendable && !edit.attended && (
              <small> Attendance can be recorded after the session date ({formatDate(course.start_date)}).</small>
            )}
          </label>
          {(edit.attendance_status === 'attended' || edit.attended) && (
            <>
              <div className="form-grid">
                <label>
                  Completion date
                  <input
                    required
                    type="date"
                    max={todayLocal()}
                    value={edit.attended_on || ''}
                    onChange={(e) => onEdit({ ...edit, attended_on: e.target.value })}
                  />
                </label>
                <label>
                  Points I recorded
                  <input
                    type="number"
                    min="0"
                    max="10000"
                    step="0.1"
                    placeholder="Unknown"
                    value={edit.points ?? ''}
                    onChange={(e) =>
                      onEdit({
                        ...edit,
                        points: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                  />
                </label>
                <label>
                  Original credit label
                  <input
                    required
                    maxLength={30}
                    value={edit.credit_label}
                    onChange={(e) => onEdit({ ...edit, credit_label: e.target.value })}
                  />
                </label>
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={edit.public}
                  onChange={(e) => onEdit({ ...edit, public: e.target.checked })}
                />
                <span>
                  Show on my public profile
                  <small>Visible only when your profile is also public. Labelled self-reported.</small>
                </span>
              </label>
            </>
          )}
          <label>
            Private learning notes
            <textarea
              placeholder="What did you learn? Where is your certificate stored?"
              value={edit.notes}
              maxLength={5000}
              onChange={(e) => onEdit({ ...edit, notes: e.target.value })}
            />
          </label>
          <button className="primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save my record'} <Check size={16} />
          </button>
          {history.length > 0 && (
            <div className="small-note">
              <p>Correction history. Cancelling sign-up does not erase attendance.</p>
              <ol className="source-list">
                {history.map((item, index) => (
                  <li key={`${item.at}-${index}`}>
                    {item.at ? new Date(item.at * 1000).toLocaleString('en-MY') : 'Earlier'}
                    {item.signup_status ? ` · sign-up ${item.signup_status.replace('_', ' ')}` : ''}
                    {item.attended != null ? ` · ${item.attended ? 'attended' : 'not attended'}` : ''}
                    {item.attended_on ? ` · ${item.attended_on}` : ''}
                    {item.points != null ? ` · ${item.points} ${item.credit_label || ''}`.trim() : ''}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </form>
      </section>
    </div>
  );
}
