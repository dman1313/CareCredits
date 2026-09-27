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
import { LiveIngestion } from '@/components/LiveIngestion';
import { api, Course, emptyRecord, formatDate, Progress, RecordData, User } from '@/lib/portal';

const nav = [
  [LayoutDashboard, 'Overview'],
  [BookOpen, 'My Credits'],
  [Compass, 'Discover'],
  [CalendarDays, 'Events'],
  [FileText, 'Certificates'],
  [ShieldCheck, 'About credits'],
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
  const [oauth, setOauth] = useState(false);
  const [history, setHistory] = useState<{ at: number }[]>([]);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'register' | 'signin'>('register');
  const [tab, setTab] = useState<(typeof nav)[number][1]>('Discover');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('');
  const [deliveryMode, setDeliveryMode] = useState('');
  const [period, setPeriod] = useState('all');
  const [difficulty, setDifficulty] = useState('');
  const [maxFee, setMaxFee] = useState('');
  const [minPoints, setMinPoints] = useState('');
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [courses, setCourses] = useState<Course[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Course | null>(null);
  const [edit, setEdit] = useState<RecordData>(emptyRecord);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [digestOptIn, setDigestOptIn] = useState(false);
  const [suggestions, setSuggestions] = useState<
    { id: string; title: string; provider?: string; start_date?: string | null; city?: string | null; reason?: string; points?: number | null }[]
  >([]);
  const [certBusy, setCertBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locationBusy, setLocationBusy] = useState(false);
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    Promise.all([
      api('/config').then((c) => {
        setSignup(c.signup_enabled);
        setOauth(!!c.oauth_google);
      }),
      api('/me')
        .then(setUser)
        .catch(() => {}),
    ]).finally(() => setBooting(false));
  }, []);

  async function search(
    nextQuery = query,
    nextCity = city,
    nextMode = deliveryMode,
    nextPeriod = period,
    nextDifficulty = difficulty,
    nextMaxFee = maxFee,
    nextMinPoints = minPoints,
  ) {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        q: nextQuery,
        city: nextCity,
        period: nextPeriod,
        page: '1',
        page_size: '12',
        include_unknown: 'true',
      });
      if (nextMode) params.set('mode', nextMode);
      if (nextDifficulty) params.set('difficulty', nextDifficulty);
      if (nextMaxFee) params.set('max_fee_myr', nextMaxFee);
      if (nextMinPoints) params.set('min_points', nextMinPoints);
      const data = await api('/trainings?' + params);
      setCourses(data.items);
      setTotal(data.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadWorkspace(nextCity = city) {
    await search(query, nextCity, deliveryMode, period, difficulty, maxFee, minPoints);
    try {
      const [nextProgress, digest, nextSuggestions] = await Promise.all([
        api('/me/progress?year=' + year),
        api('/me/digest'),
        api('/me/suggestions'),
      ]);
      setProgress(nextProgress);
      setDigestOptIn(!!digest.opted_in);
      setSuggestions(nextSuggestions.items || []);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function clearFilters() {
    setQuery('');
    setCity(user?.city || '');
    setDeliveryMode('');
    setPeriod('all');
    setDifficulty('');
    setMaxFee('');
    setMinPoints('');
    search('', user?.city || '', '', 'all', '', '', '');
  }

  async function saveLocation(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    setLocationBusy(true);
    setError('');
    try {
      const saved = await api('/me', {
        method: 'PATCH',
        body: JSON.stringify({
          name: user.name,
          city: user.city || '',
          state: user.state || '',
          bio: user.bio || '',
          public_enabled: user.public_enabled,
          latitude: user.latitude ?? null,
          longitude: user.longitude ?? null,
        }),
      });
      setUser(saved);
      setCity(saved.city || '');
      await loadWorkspace(saved.city || '');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLocationBusy(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    const nextCity = city || user.city || '';
    if (!city && user.city) setCity(user.city);
    loadWorkspace(nextCity).catch(() => {});
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
        body: JSON.stringify({ year }),
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
      await loadWorkspace(city || user?.city || '');
      setProgress(await api('/me/progress?year=' + year));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function openCourse(course: Course) {
    setError('');
    setOpening(true);
    setSelected(course);
    setEdit({ ...emptyRecord, ...(course.record || {}) });
    try {
      const current = await api('/trainings/' + course.id);
      setSelected(current);
      setEdit({ ...emptyRecord, ...(current.record || {}) });
      const hist = await api('/me/trainings/' + course.id + '/history').catch(() => ({ items: [] }));
      setHistory(hist.items || []);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setOpening(false);
    }
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
          <a className="skip-link" href="#live-sign-in">
            Skip to sign in
          </a>
          <form id="live-sign-in" className="gate-card" onSubmit={submitAccount} aria-busy={busy}>
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
              <input required type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label>
              Password
              <input
                required
                type="password"
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
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
            {oauth && (
              <a className="secondary" href="/api/v1/auth/oauth/google">
                Continue with Google
              </a>
            )}
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
      <a className="skip-link" href="#live-main">
        Skip to content
      </a>
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
        <main className="main" id="live-main">
          <header className="topbar">
            <button className="menu-button" onClick={() => setOpen(true)} aria-label="Open navigation">
              <Menu />
            </button>
            <form
              id="live-filters"
              onSubmit={(event) => {
                event.preventDefault();
                setTab('Discover');
                search();
              }}
            >
              <label className="search">
                <Search aria-hidden="true" />
                <input
                  aria-label="Search training"
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
              <label className="city-search">
                <select
                  aria-label="Delivery mode"
                  value={deliveryMode}
                  onChange={(e) => setDeliveryMode(e.target.value)}
                >
                  <option value="">Any mode</option>
                  <option value="online">Online</option>
                  <option value="in_person">In person</option>
                  <option value="hybrid">Hybrid</option>
                </select>
              </label>
              <label className="city-search">
                <select aria-label="Period" value={period} onChange={(e) => setPeriod(e.target.value)}>
                  <option value="all">All dates</option>
                  <option value="upcoming">Upcoming</option>
                  <option value="past">Past</option>
                </select>
              </label>
              <label className="city-search">
                <select aria-label="Difficulty" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                  <option value="">Any level</option>
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </select>
              </label>
              <input
                className="city-search"
                type="number"
                min="0"
                step="1"
                value={maxFee}
                onChange={(e) => setMaxFee(e.target.value)}
                placeholder="Max fee MYR"
                aria-label="Maximum fee in MYR"
              />
              <input
                className="city-search"
                type="number"
                min="0"
                step="0.1"
                value={minPoints}
                onChange={(e) => setMinPoints(e.target.value)}
                placeholder="Min points"
                aria-label="Minimum advertised points"
              />
              <button className="search-btn" disabled={loading}>
                {loading ? <Loader2 className="spin" size={16} /> : 'Search'}
              </button>
              <button className="text-link" type="button" onClick={clearFilters}>
                Clear filters
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
                {error}{' '}
                <button className="text-link" type="button" onClick={() => loadWorkspace()}>
                  Retry
                </button>
              </p>
            )}
            {opening && (
              <p className="alert" role="status" aria-busy="true">
                Opening training details…
              </p>
            )}
            {tab === 'Overview' && (
              <>
                <section className="hero">
                  <div className="hero-copy">
                    <span className="eyebrow">MALAYSIA CPD</span>
                    <h1>Your learning, in one place</h1>
                    <p>Search the owned Malaysia CPD catalogue, keep a personal record, and open the provider page when you are ready.</p>
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
                      Find catalogue events <ChevronRight />
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
                {user.role === 'operator' && (
                  <LiveIngestion
                    onPublished={async () => {
                      await loadWorkspace(city || user.city || '');
                    }}
                  />
                )}
                <section className="card" id="live-location">
                  <div className="card-heading">
                    <div>
                      <span className="heading-icon">⌖</span>
                      <h2>Malaysia location</h2>
                    </div>
                  </div>
                  <p className="empty-copy">
                    Save city and state on your profile. Catalogue search uses that city. Skipping location does not
                    block the rest of the demo.
                  </p>
                  <form onSubmit={saveLocation}>
                    <label>
                      City
                      <input
                        aria-label="Profile city"
                        value={user.city || ''}
                        onChange={(e) => setUser({ ...user, city: e.target.value })}
                        placeholder="Kuala Lumpur"
                      />
                    </label>
                    <label>
                      State
                      <input
                        aria-label="Profile state"
                        value={user.state || ''}
                        onChange={(e) => setUser({ ...user, state: e.target.value })}
                        placeholder="Optional, e.g. Selangor"
                      />
                    </label>
                    <button className="secondary" disabled={locationBusy}>
                      {locationBusy ? 'Saving…' : 'Save location and search'}
                    </button>
                  </form>
                </section>
                <section className="card" id="live-suggestions" data-testid="live-suggestions">
                  <div className="card-heading">
                    <div>
                      <span className="heading-icon">✦</span>
                      <h2>Consider next</h2>
                    </div>
                  </div>
                  <p className="empty-copy">
                    Advisory catalogue matches by city and recent learning mode. CareCredits does not decide MMC, MOH, or APC compliance.
                  </p>
                  {suggestions.length ? (
                    suggestions.slice(0, 5).map((item, index) => (
                      <article key={item.id} className="recommendation">
                        <div className={`rec-photo ${index % 2 ? 'speaker' : 'doctor'}`} />
                        <div>
                          <h3>{item.title}</h3>
                          <p>{item.provider || 'Catalogue listing'}</p>
                          <small>
                            {formatDate(item.start_date || null)} · {item.city || 'Online'}
                            {item.reason ? ` — ${item.reason}` : ''}
                            {item.points != null ? ` · ${item.points} points` : ''}
                          </small>
                        </div>
                        <button
                          className="more"
                          onClick={() => openCourse({ id: item.id } as Course)}
                          aria-label={'Open ' + item.title}
                        >
                          ⋮
                        </button>
                      </article>
                    ))
                  ) : (
                    <p className="empty-copy">No upcoming catalogue suggestions yet. Save a city or browse Discover.</p>
                  )}
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
                      <label>
                        Year{' '}
                        <select
                          aria-label="Progress year"
                          value={year}
                          onChange={async (e) => {
                            const next = Number(e.target.value);
                            setYear(next);
                            try {
                              setProgress(await api('/me/progress?year=' + next));
                            } catch (err) {
                              setError((err as Error).message);
                            }
                          }}
                        >
                          {[0, 1, 2, 3, 4].map((offset) => {
                            const value = new Date().getFullYear() - offset;
                            return (
                              <option key={value} value={value}>
                                {value}
                              </option>
                            );
                          })}
                        </select>
                      </label>
                      <p className="missing">{progress?.excluded ? `${progress.excluded} records excluded from the CPD total` : 'Opening a source does not register you with the provider.'}</p>
                      <a className="text-link" href="/">
                        Open full workspace <ChevronRight />
                      </a>
                    </div>
                  </div>
                </section>
                {tab === 'About credits' && (
                  <section className="card">
                    <div className="card-heading">
                      <div>
                        <span className="heading-icon">▣</span>
                        <h2>About recorded credits</h2>
                      </div>
                    </div>
                    <p className="empty-copy">
                      CareCredits does not decide APC, MMC, or licence renewal. Points you record here are
                      self-reported and are not independently accredited.
                    </p>
                  </section>
                )}
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
                {tab === 'My Credits' && (
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
          history={history}
          onClose={() => setSelected(null)}
          onEdit={setEdit}
          onSave={saveRecord}
        />
      )}
    </div>
  );
}
