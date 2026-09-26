'use client';

import { FormEvent, useEffect, useState } from 'react';
import {
  Bell,
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  Compass,
  FileText,
  GraduationCap,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  MessageSquare,
  Search,
  Settings,
  ShieldCheck,
  X,
} from 'lucide-react';
import { TrainingDetail } from '@/components/TrainingDetail';
import { api, Course, emptyRecord, formatDate, Progress, RecordData, User } from '@/lib/portal';

const nav = [
  [LayoutDashboard, 'Overview'],
  [BookOpen, 'My Credits'],
  [Compass, 'Discover'],
  [CalendarDays, 'Events'],
  [FileText, 'Certificates'],
  [ShieldCheck, 'APC Status'],
] as const;

const workspace = [
  [GraduationCap, 'Learning Hub'],
  [MessageSquare, 'Messages'],
  [Settings, 'Settings'],
] as const;

const tones = ['sky', 'mint', 'coral'] as const;

function Mark() {
  return (
    <span className="care-mark">
      <i />
      <b />
    </span>
  );
}

function initials(name: string) {
  return name
    .replace(/^Dr\.?\s+/i, '')
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || '')
    .join('');
}

export default function LiveSearch() {
  const [user, setUser] = useState<User | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [booting, setBooting] = useState(true);
  const [signup, setSignup] = useState(false);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'register' | 'signin'>('register');
  const [tab, setTab] = useState<(typeof nav)[number][1]>('Discover');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('');
  const [courses, setCourses] = useState<Course[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Course | null>(null);
  const [edit, setEdit] = useState<RecordData>(emptyRecord);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [digestOptIn, setDigestOptIn] = useState(false);
  const [suggestions, setSuggestions] = useState<{ id: string; title: string; start_date?: string | null; city?: string | null; reason?: string }[]>([]);
  const [certBusy, setCertBusy] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([
      api('/config').then((c) => setSignup(c.signup_enabled)),
      api('/me')
        .then(setUser)
        .catch(() => {}),
    ]).finally(() => setBooting(false));
  }, []);

  async function search(nextQuery = query, nextCity = city) {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        q: nextQuery,
        city: nextCity,
        period: 'all',
        page: '1',
        page_size: '12',
        include_unknown: 'true',
      });
      const data = await api('/trainings?' + params);
      setCourses(data.items);
      setTotal(data.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    search('', '').catch(() => {});
    api('/me/progress')
      .then(setProgress)
      .catch(() => {});
    api('/me/digest')
      .then((d) => setDigestOptIn(!!d.opted_in))
      .catch(() => {});
    api('/me/suggestions')
      .then((d) => setSuggestions(d.items || []))
      .catch(() => {});
  }, [user]);

  async function toggleDigest(next: boolean) {
    setError('');
    try {
      const d = await api('/me/digest', {
        method: 'PATCH',
        body: JSON.stringify({ opted_in: next, cadence_days: 14 }),
      });
      setDigestOptIn(!!d.opted_in);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function issueCertificate() {
    setCertBusy(true);
    setError('');
    try {
      const cert = await api('/me/certificates', {
        method: 'POST',
        body: JSON.stringify({ year: progress?.year || new Date().getFullYear() }),
      });
      window.open('/api/v1/me/certificates/' + cert.id, '_blank');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCertBusy(false);
    }
  }

  async function submitAccount(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = { email, password, name: name || 'Doctor' };
      if (mode === 'register') {
        if (!signup) throw new Error('Registration is disabled on this server.');
        await api('/auth/register', { method: 'POST', body: JSON.stringify(body) });
      }
      setUser(await api('/auth/login', { method: 'POST', body: JSON.stringify(body) }));
      setTab('Discover');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveRecord(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSaving(true);
    setError('');
    try {
      await api('/me/trainings/' + selected.id, { method: 'PUT', body: JSON.stringify(edit) });
      const current = await api('/trainings/' + selected.id);
      setSelected(current);
      setEdit(current.record || emptyRecord);
      await search();
      setProgress(await api('/me/progress'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function openCourse(course: Course) {
    setSelected(course);
    setEdit(course.record || emptyRecord);
  }

  if (booting) {
    return (
      <div className="dash">
        <div className="gate">
          <Loader2 className="spin" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="dash">
        <div className="gate">
          <form className="gate-card" onSubmit={submitAccount}>
            <div className="brand">
              <Mark />
              <div>
                <strong>Care Credits</strong>
                <small>Log points. Find training. Focus on patients.</small>
              </div>
            </div>
            <h1>{mode === 'register' ? 'Create your workspace' : 'Sign in to search'}</h1>
            <p>Register, then search Malaysian CPD courses from the original dashboard.</p>
            {mode === 'register' && (
              <label>
                Your name
                <input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
              </label>
            )}
            <label>
              Email address
              <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                minLength={12}
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && (
              <p role="alert" className="alert">
                {error}
              </p>
            )}
            <button className="primary" disabled={busy}>
              {busy ? 'Please wait…' : mode === 'register' ? 'Create account and search' : 'Sign in and search'}
              <ChevronRight />
            </button>
            <button
              type="button"
              className="text-link"
              onClick={() => {
                setMode(mode === 'register' ? 'signin' : 'register');
                setError('');
              }}
            >
              {mode === 'register' ? 'Already have an account? Sign in' : 'New here? Create an account'}
            </button>
          </form>
        </div>
      </div>
    );
  }

  const points = progress?.points ?? 0;
  const attended = progress?.attended ?? 0;
  const signed = progress?.signed_up ?? 0;

  return (
    <div className="dash">
      <div className="app-shell">
        <aside className={open ? 'sidebar sidebar-open' : 'sidebar'}>
          <div className="brand">
            <Mark />
            <div>
              <strong>Care Credits</strong>
              <small>Log points. Find training. Focus on patients.</small>
            </div>
            <button className="close-nav" onClick={() => setOpen(false)}>
              <X />
            </button>
          </div>
          <nav>
            {nav.map(([Icon, item]) => (
              <button
                key={item}
                className={item === tab ? 'nav-item active' : 'nav-item'}
                onClick={() => {
                  setTab(item);
                  setOpen(false);
                }}
              >
                <Icon />
                <span>{item}</span>
              </button>
            ))}
          </nav>
          <div className="nav-rule" />
          <p className="nav-heading">WORKSPACE</p>
          <nav>
            {workspace.map(([Icon, item]) => (
              <a key={item} className="nav-item" href="/">
                <Icon />
                <span>{item}</span>
              </a>
            ))}
          </nav>
          <div className="profile">
            <span className="avatar">{initials(user.name)}</span>
            <div>
              <strong>{user.name}</strong>
              <small>General Practice</small>
            </div>
            <button
              className="text-link"
              aria-label="Sign out"
              onClick={async () => {
                await api('/auth/logout', { method: 'POST' });
                setUser(null);
                setCourses([]);
                setSelected(null);
              }}
            >
              <LogOut />
            </button>
          </div>
        </aside>
        {open && <button className="veil" onClick={() => setOpen(false)} aria-label="Close navigation" />}
        <main className="main">
          <header className="topbar">
            <button className="menu-button" onClick={() => setOpen(true)} aria-label="Open navigation">
              <Menu />
            </button>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                setTab('Discover');
                search();
              }}
            >
              <label className="search">
                <Search />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search conferences, webinars, workshops..."
                />
              </label>
              <input
                className="city-search"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Kuala Lumpur"
                aria-label="City"
              />
              <button className="search-btn" disabled={loading}>
                {loading ? <Loader2 className="spin" size={16} /> : 'Search'}
              </button>
            </form>
            <div className="top-actions">
              <button className="icon-button" aria-label="Notifications">
                <Bell />
              </button>
              <span className="avatar">{initials(user.name)}</span>
              <ChevronDown className="chevron" />
            </div>
          </header>
          <div className="content">
            {error && (
              <p role="alert" className="alert">
                {error}
              </p>
            )}
            {tab === 'Overview' && (
              <>
                <section className="hero">
                  <div className="hero-copy">
                    <span className="eyebrow">MALAYSIA CPD</span>
                    <h1>Your learning, in one place</h1>
                    <p>Search accredited training, keep a personal record, and open the provider page when you are ready.</p>
                  </div>
                  <div className="progress-panel">
                    <div className="ring">
                      <span>{points}</span>
                    </div>
                    <div className="progress-copy">
                      <h2>
                        {points} <span>self-reported CPD points</span>
                      </h2>
                      <p>
                        <CalendarDays /> {progress?.year || new Date().getFullYear()} record
                        <br />
                        <strong>
                          {attended} attended · {signed} signed up
                        </strong>
                      </p>
                      <b className="warning">Self-reported totals are not a regulator credit.</b>
                    </div>
                    <button
                      className="primary"
                      onClick={() => {
                        setTab('Discover');
                        search();
                      }}
                    >
                      Find eligible events <ChevronRight />
                    </button>
                  </div>
                </section>
                <section className="metrics">
                  <article className="metric">
                    <span className="metric-icon green">★</span>
                    <div>
                      <p>Points recorded</p>
                      <strong className="metric-green">{points}</strong>
                    </div>
                  </article>
                  <article className="metric">
                    <span className="metric-icon orange">◎</span>
                    <div>
                      <p>Courses attended</p>
                      <strong>{attended}</strong>
                    </div>
                  </article>
                  <article className="metric">
                    <span className="metric-icon blue">♢</span>
                    <div>
                      <p>Signed up</p>
                      <strong>{signed}</strong>
                      {!!progress?.excluded && <small>{progress.excluded} excluded from the CPD total</small>}
                    </div>
                  </article>
                </section>
              </>
            )}
            <div className="dashboard-grid">
              <div className="left-column">
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <span className="heading-icon">▣</span>
                      <h2>{tab === 'Discover' ? 'Search results' : 'Upcoming and listed training'}</h2>
                    </div>
                    <p>{total} events</p>
                  </div>
                  {loading ? (
                    <p className="empty-copy">Finding your training…</p>
                  ) : courses.length ? (
                    courses.map((course, index) => (
                      <button key={course.id} className="event" onClick={() => openCourse(course)}>
                        <span className={`event-photo ${tones[index % tones.length]}`} />
                        <span className="event-name">
                          <strong>{course.title}</strong>
                          <small>
                            {formatDate(course.start_date)} · {course.city || 'Online'}
                          </small>
                        </span>
                        <span className="event-points">
                          {course.points != null ? `${course.points} ${course.credit_label || 'CPD'} points` : 'Points not listed'}
                        </span>
                        <ChevronRight />
                      </button>
                    ))
                  ) : (
                    <p className="empty-copy">No matching training. Try a broader topic or clear the city filter.</p>
                  )}
                </section>
              </div>
              <div className="right-column">
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <span className="heading-icon">✦</span>
                      <h2>Recommended for you</h2>
                    </div>
                  </div>
                  {courses.slice(0, 3).map((course, index) => (
                    <article key={course.id} className="recommendation">
                      <div className={`rec-photo ${index % 2 ? 'speaker' : 'doctor'}`} />
                      <div>
                        <h3>{course.title}</h3>
                        <p>{course.provider}</p>
                        <small>
                          ♢ {course.points != null ? `${course.points} points` : 'Points not listed'} ▣ {course.city || 'Online'}
                        </small>
                      </div>
                      <button className="more" onClick={() => openCourse(course)} aria-label={'Open ' + course.title}>
                        ⋮
                      </button>
                    </article>
                  ))}
                  {!courses.length && <p className="empty-copy">Search to see listed training here.</p>}
                </section>
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <span className="heading-icon">♧</span>
                      <h2>Learning record</h2>
                    </div>
                  </div>
                  <div className="assistant-content">
                    <div className="score">
                      <strong>{points}</strong>
                      <span>
                        CPD
                        <br />
                        recorded
                      </span>
                    </div>
                    <div>
                      <p>
                        Year <strong className="success">{progress?.year}</strong>
                      </p>
                      <p className="missing">{progress?.excluded ? `${progress.excluded} records excluded from the CPD total` : 'Opening a source does not register you with the provider.'}</p>
                      <a className="text-link" href="/">
                        Open full workspace <ChevronRight />
                      </a>
                    </div>
                  </div>
                </section>
                {tab === 'Certificates' && (
                  <section className="card">
                    <div className="card-heading">
                      <div>
                        <span className="heading-icon">▤</span>
                        <h2>Affiliation certificate</h2>
                      </div>
                    </div>
                    <p className="empty-copy">
                      Print a CareCredits affiliation record for {progress?.year || new Date().getFullYear()}. It is not an MMC, MOH, or APC certificate.
                    </p>
                    <button className="primary" disabled={certBusy} onClick={issueCertificate}>
                      {certBusy ? 'Preparing…' : 'Issue printable certificate'}
                    </button>
                  </section>
                )}
                {(tab === 'Settings' || tab === 'My Credits') && (
                  <section className="card">
                    <div className="card-heading">
                      <div>
                        <span className="heading-icon">✉</span>
                        <h2>Biweekly digest</h2>
                      </div>
                    </div>
                    <p className="empty-copy">
                      Opt in for a 14-day email with upcoming catalogue events, known prices, and your recorded CPD total.
                    </p>
                    <label className="empty-copy">
                      <input
                        type="checkbox"
                        checked={digestOptIn}
                        onChange={(e) => toggleDigest(e.target.checked)}
                      />{' '}
                      Email me the biweekly digest
                    </label>
                    {!!suggestions.length && (
                      <>
                        <h3 style={{ marginTop: 16 }}>Suggested next courses</h3>
                        <ul className="empty-copy">
                          {suggestions.slice(0, 5).map((item) => (
                            <li key={item.id}>
                              {item.start_date} · {item.title} ({item.city || 'Online'}) — {item.reason}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </section>
                )}
              </div>
            </div>
          </div>
        </main>
      </div>
      {selected && (
        <TrainingDetail
          course={selected}
          edit={edit}
          error={error}
          saving={saving}
          onClose={() => setSelected(null)}
          onEdit={setEdit}
          onSave={saveRecord}
        />
      )}
    </div>
  );
}
