'use client';

import { FormEvent } from 'react';
import { Check, ExternalLink, X } from 'lucide-react';
import {
  Course,
  RecordData,
  feeLabel,
  formatDate,
  modeName,
  todayLocal,
} from '@/lib/portal';

export function TrainingDetail({
  course,
  edit,
  error,
  saving,
  onClose,
  onEdit,
  onSave,
}: {
  course: Course;
  edit: RecordData;
  error: string;
  saving: boolean;
  onClose: () => void;
  onEdit: (next: RecordData) => void;
  onSave: (event: FormEvent) => void;
}) {
  return (
    <div className="modal-shade" onClick={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Training details"
        onClick={(e) => e.stopPropagation()}
      >
        <button autoFocus className="modal-close icon-btn" aria-label="Close training details" onClick={onClose}>
          <X />
        </button>
        <span className="pill">
          {modeName(course.mode)} {course.demo ? '· Demo course' : ''}
        </span>
        <h2>{course.title}</h2>
        <p className="muted">{course.provider}</p>
        <p>{course.description}</p>
        <div className="detail-grid">
          <div>
            <small>Date</small>
            <strong>{formatDate(course.start_date)}</strong>
          </div>
          <div>
            <small>Location</small>
            <strong>{course.city || 'Online'}</strong>
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
            <strong>{course.difficulty || 'Not specified'}</strong>
          </div>
          <div>
            <small>Prerequisites</small>
            <strong>{course.prerequisites || 'Not specified'}</strong>
          </div>
        </div>
        <div className="button-row">
          {course.registration_url && (
            <a className="secondary" href={course.registration_url} target="_blank" rel="noreferrer">
              Provider registration <ExternalLink size={14} />
            </a>
          )}
          <a className="text-btn" href={course.source_url} target="_blank" rel="noreferrer">
            View original source <ExternalLink size={14} />
          </a>
        </div>
        <p className="small-note">
          Confirm details and CPD eligibility with the provider. Opening a link does not register you.
        </p>
        <hr />
        <form onSubmit={onSave}>
          <h3>Your personal record</h3>
          {error && (
            <p className="alert error" role="alert">
              {error}
            </p>
          )}
          <label className="check-row">
            <input
              type="checkbox"
              checked={edit.signed_up}
              onChange={(e) => onEdit({ ...edit, signed_up: e.target.checked })}
            />
            I have signed up with the provider
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={edit.attended}
              onChange={(e) =>
                onEdit({
                  ...edit,
                  attended: e.target.checked,
                  attended_on: e.target.checked ? edit.attended_on || todayLocal() : null,
                  public: e.target.checked ? edit.public : false,
                })
              }
            />
            I attended this training
          </label>
          {edit.attended && (
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
        </form>
      </section>
    </div>
  );
}
