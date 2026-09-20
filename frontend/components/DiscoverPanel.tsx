'use client';

import { ArrowDownToLine, ChevronLeft, ChevronRight, FileText, MapPin, Search } from 'lucide-react';
import { Course } from '@/lib/portal';
import { CourseCard, Empty, Loading } from '@/components/CourseList';

export type DiscoverFilters = {
  q: string;
  city: string;
  state: string;
  mode: string;
  difficulty: string;
  maxFee: string;
  minPoints: string;
  period: string;
  dateFrom: string;
  dateTo: string;
  includeUnknown: boolean;
  radius: string;
  location: { latitude: number; longitude: number } | null;
  page: number;
};

export function DiscoverPanel({
  tab,
  filters,
  courses,
  records,
  total,
  loading,
  onFilters,
  onLocate,
  onDiscover,
  onOpen,
}: {
  tab: 'Discover training' | 'My learning';
  filters: DiscoverFilters;
  courses: Course[];
  records: Course[];
  total: number;
  loading: boolean;
  onFilters: (patch: Partial<DiscoverFilters>) => void;
  onLocate: () => void;
  onDiscover: () => void;
  onOpen: (course: Course) => void;
}) {
  const list = tab === 'My learning' ? records : courses;
  const {
    q,
    city,
    state,
    mode,
    difficulty,
    maxFee,
    minPoints,
    period,
    dateFrom,
    dateTo,
    includeUnknown,
    radius,
    location,
    page,
  } = filters;

  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">{tab === 'My learning' ? 'YOUR PERSONAL RECORD' : 'OPPORTUNITIES NEAR YOU'}</p>
          <h1>{tab === 'My learning' ? 'A little learning. Lasting impact.' : 'Find your next CPD training.'}</h1>
          <p>
            {tab === 'My learning'
              ? 'Keep sign-ups, attendance and notes together.'
              : 'Compare practical details before making time in your calendar.'}
          </p>
        </div>
        {tab === 'My learning' && (
          <div className="button-row">
            <a className="secondary" href="/api/v1/me/export/csv">
              <ArrowDownToLine size={16} /> Spreadsheet
            </a>
            <a className="secondary" href="/api/v1/me/export/eml">
              <FileText size={16} /> Email draft
            </a>
          </div>
        )}
      </div>
      {tab === 'Discover training' && (
        <section className="filter-panel">
          <div className="search-line">
            <label className="search-box">
              <Search size={19} />
              <input
                aria-label="Search training"
                placeholder="Search a topic, course or provider…"
                value={q}
                onChange={(e) => onFilters({ q: e.target.value, page: 1 })}
              />
            </label>
            <button className={'secondary ' + (location ? 'chosen' : '')} onClick={onLocate}>
              <MapPin size={16} />
              {location ? 'Location selected' : 'Near me'}
            </button>
            {location && (
              <button className="text-btn" onClick={() => onFilters({ location: null })}>
                Clear location
              </button>
            )}
          </div>
          <div className="filters">
            <label>
              City
              <input
                placeholder="City, e.g. Kuala Lumpur"
                value={city}
                onChange={(e) => onFilters({ city: e.target.value, page: 1 })}
              />
            </label>
            <label>
              State
              <input
                placeholder="State, e.g. Selangor"
                value={state}
                onChange={(e) => onFilters({ state: e.target.value, page: 1 })}
              />
            </label>
            {location && (
              <label>
                Radius
                <select value={radius} onChange={(e) => onFilters({ radius: e.target.value })}>
                  {[10, 25, 50, 100].map((n) => (
                    <option key={n} value={n}>
                      {n} km
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Format
              <select value={mode} onChange={(e) => onFilters({ mode: e.target.value, page: 1 })}>
                <option value="">Any format</option>
                <option value="in_person">In person</option>
                <option value="online">Online</option>
                <option value="hybrid">Hybrid</option>
              </select>
            </label>
            <label>
              Level
              <select value={difficulty} onChange={(e) => onFilters({ difficulty: e.target.value, page: 1 })}>
                <option value="">Any level</option>
                {['beginner', 'intermediate', 'advanced'].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              Max fee (MYR)
              <input
                type="number"
                min="0"
                placeholder="Any price"
                value={maxFee}
                onChange={(e) => onFilters({ maxFee: e.target.value, page: 1 })}
              />
            </label>
            <label>
              Min points
              <input
                type="number"
                min="0"
                placeholder="Any points"
                value={minPoints}
                onChange={(e) => onFilters({ minPoints: e.target.value, page: 1 })}
              />
            </label>
            <label>
              When
              <select value={period} onChange={(e) => onFilters({ period: e.target.value, page: 1 })}>
                <option value="upcoming">Upcoming</option>
                <option value="past">Past courses</option>
                <option value="all">All dates</option>
              </select>
            </label>
            <label>
              From
              <input type="date" value={dateFrom} onChange={(e) => onFilters({ dateFrom: e.target.value, page: 1 })} />
            </label>
            <label>
              To
              <input type="date" value={dateTo} onChange={(e) => onFilters({ dateTo: e.target.value, page: 1 })} />
            </label>
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={includeUnknown}
              onChange={(e) => onFilters({ includeUnknown: e.target.checked, page: 1 })}
            />
            <span>Include date not confirmed and unknown fees or points</span>
          </label>
          {location && (
            <p className="filter-note">
              Approximate straight-line distance, not travel time. Courses without venue coordinates stay visible when
              they match city or state, with distance unavailable. Online courses appear when Online, Hybrid or Any
              format is selected.
            </p>
          )}
        </section>
      )}
      <div className="results-heading">
        <span>
          {tab === 'My learning' ? records.length : total}{' '}
          {tab === 'My learning' ? 'saved records' : 'training opportunities'}
        </span>
        <span>Source-linked · Details may change</span>
      </div>
      {loading && tab !== 'My learning' ? (
        <Loading />
      ) : list.length ? (
        <div className="course-grid">
          {list.map((c) => (
            <CourseCard key={c.id} course={c} onOpen={() => onOpen(c)} />
          ))}
        </div>
      ) : (
        <Empty
          title={tab === 'My learning' ? 'Your learning story starts here' : 'No matching training yet'}
          text={
            tab === 'My learning'
              ? 'Open a course to record your sign-up or attendance.'
              : 'Try another city or fewer filters. The catalogue may need more sources.'
          }
          action={onDiscover}
        />
      )}
      {tab === 'Discover training' && total > 9 && (
        <div className="pagination">
          <button className="secondary" disabled={page === 1} onClick={() => onFilters({ page: page - 1 })}>
            <ChevronLeft size={16} /> Previous
          </button>
          <span>
            Page {page} of {Math.ceil(total / 9)}
          </span>
          <button className="secondary" disabled={page * 9 >= total} onClick={() => onFilters({ page: page + 1 })}>
            Next <ChevronRight size={16} />
          </button>
        </div>
      )}
    </>
  );
}
