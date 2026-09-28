'use client';

import { FormEvent, useEffect, useState } from 'react';
import {
  BookOpen,
  CalendarDays,
  ChevronRight,
  Compass,
  FileText,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Search,
  Settings,
  ShieldCheck,
  X,
} from 'lucide-react';
import { TrainingDetail } from '@/components/TrainingDetail';
import { LiveIngestion } from '@/components/LiveIngestion';
import { api, AuditItem, Course, distanceLabel, emptyRecord, formatDate, Progress, RecordData, RecordHistoryItem, User } from '@/lib/portal';

const PAGE_SIZE = 12;

function excludedCopy(progress: Progress | null) {
  if (!progress?.excluded) return '';
  const reasons = progress.excluded_reasons?.length
    ? ': ' +
      progress.excluded_reasons
        .map((item) => (item.reason === 'unknown_points' ? 'unknown points' : item.credit_label || 'other credit type'))
        .join(', ')
    : ' (unknown or other credit types)';
  return `${progress.excluded} attended record(s) excluded${reasons}.`;
}

const nav = [
  [LayoutDashboard, 'Overview'],
  [BookOpen, 'My Credits'],
  [Compass, 'Discover'],
  [CalendarDays, 'Events'],
  [FileText, 'Certificates'],
  [ShieldCheck, 'About credits'],
] as const;

function DateChip({ value }: { value?: string | null }) {
  if (!value) {
    return (
      <span className="event-date">
        <strong>—</strong>
        <small>TBC</small>
      </span>
    );
  }
  const date = new Date(value + 'T00:00:00+08:00');
  return (
    <span className="event-date">
      <strong>
        {date.toLocaleDateString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', day: 'numeric' })}
      </strong>
      <small>
        {date.toLocaleDateString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', month: 'short' })}
      </small>
    </span>
  );
}

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
  const [demo, setDemo] = useState(false);
  const [history, setHistory] = useState<RecordHistoryItem[]>([]);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'register' | 'signin'>('register');
  const [tab, setTab] = useState<(typeof nav)[number][1]>('Discover');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [deliveryMode, setDeliveryMode] = useState('');
  const [period, setPeriod] = useState('upcoming');
  const [difficulty, setDifficulty] = useState('');
  const [maxFee, setMaxFee] = useState('');
  const [minPoints, setMinPoints] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [includeUnknown, setIncludeUnknown] = useState(false);
  const [radius, setRadius] = useState('25');
  const [page, setPage] = useState(1);
  const [nearby, setNearby] = useState<{ latitude: number; longitude: number } | null>(null);
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
  const [digestBusy, setDigestBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locationBusy, setLocationBusy] = useState(false);
  const [opening, setOpening] = useState(false);
  const [records, setRecords] = useState<Course[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [learningFilter, setLearningFilter] = useState<'all' | 'signed_up' | 'attended'>('all');
  const [learningPage, setLearningPage] = useState(1);
  const [learningBusy, setLearningBusy] = useState(false);
  const [audits, setAudits] = useState<AuditItem[]>([]);

  useEffect(() => {
    Promise.all([
      api('/config').then((c) => {
        setSignup(c.signup_enabled);
        setOauth(!!c.oauth_google);
        setDemo(!!c.demo);
        if (c.demo) {
          setEmail((current) => current || 'demo@carecredits.local');
          setPassword((current) => current || 'CareCredits-demo-2026');
          setMode('signin');
        }
      }),
      api('/me')
        .then(setUser)
        .catch(() => {}),
    ]).finally(() => setBooting(false));
  }, []);

  async function search(overrides: {
    query?: string;
    city?: string;
    state?: string;
    mode?: string;
    period?: string;
    difficulty?: string;
    maxFee?: string;
    minPoints?: string;
    dateFrom?: string;
    dateTo?: string;
    includeUnknown?: boolean;
    radius?: string;
    page?: number;
    nearby?: { latitude: number; longitude: number } | null;
  } = {}) {
    const nextQuery = overrides.query ?? query;
    const nextCity = overrides.city ?? city;
    const nextState = overrides.state ?? state;
    const nextMode = overrides.mode ?? deliveryMode;
    const nextPeriod = overrides.period ?? period;
    const nextDifficulty = overrides.difficulty ?? difficulty;
    const nextMaxFee = overrides.maxFee ?? maxFee;
    const nextMinPoints = overrides.minPoints ?? minPoints;
    const nextDateFrom = overrides.dateFrom ?? dateFrom;
    const nextDateTo = overrides.dateTo ?? dateTo;
    const nextIncludeUnknown = overrides.includeUnknown ?? includeUnknown;
    const nextRadius = overrides.radius ?? radius;
    const nextPage = overrides.page ?? page;
    const nextNearby = overrides.nearby === undefined ? nearby : overrides.nearby;
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        q: nextQuery,
        city: nextCity,
        state: nextState,
        period: nextPeriod,
        page: String(nextPage),
        page_size: String(PAGE_SIZE),
        include_unknown: String(nextIncludeUnknown),
      });
      if (nextMode) params.set('mode', nextMode);
      if (nextDifficulty) params.set('difficulty', nextDifficulty);
      if (nextMaxFee) params.set('max_fee_myr', nextMaxFee);
      if (nextMinPoints) params.set('min_points', nextMinPoints);
      if (nextDateFrom) params.set('date_from', nextDateFrom);
      if (nextDateTo) params.set('date_to', nextDateTo);
      if (nextNearby) {
        params.set('latitude', String(nextNearby.latitude));
        params.set('longitude', String(nextNearby.longitude));
        params.set('radius_km', nextRadius);
      }
      const data = await api('/trainings?' + params);
      setCourses(data.items);
      setTotal(data.total);
      setPage(nextPage);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function loadLearning(
    filter: 'all' | 'signed_up' | 'attended' = learningFilter,
    nextPage = filter === learningFilter ? learningPage : 1,
  ) {
    setLearningBusy(true);
    try {
      const params = new URLSearchParams({ page: String(nextPage), page_size: '12' });
      if (filter === 'signed_up') params.set('signup_status', 'signed_up');
      if (filter === 'attended') params.set('attendance_status', 'attended');
      const data = await api('/me/trainings?' + params);
      const total = data.total || 0;
      const pageCount = Math.max(1, Math.ceil(total / 12));
      if (nextPage > pageCount) {
        await loadLearning(filter, pageCount);
        return;
      }
      setRecords(data.items || []);
      setRecordsTotal(total);
      setLearningFilter(filter);
      setLearningPage(nextPage);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLearningBusy(false);
    }
  }

  async function loadWorkspace(nextCity = city, nextState = state) {
    await search({ city: nextCity, state: nextState, page: 1 });
    try {
      const [nextProgress, digest, nextSuggestions, mine] = await Promise.all([
        api('/me/progress?year=' + year),
        api('/me/digest'),
        api('/me/suggestions'),
        api('/me/audit?page=1&page_size=8').catch(() => null),
      ]);
      setProgress(nextProgress);
      setDigestOptIn(!!digest.opted_in);
      setSuggestions(nextSuggestions.items || []);
      if (mine) setAudits(mine.items || []);
      await loadLearning(learningFilter);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function clearFilters() {
    const nextCity = user?.city || '';
    const nextState = user?.state || '';
    setQuery('');
    setCity(nextCity);
    setState(nextState);
    setDeliveryMode('');
    setPeriod('upcoming');
    setDifficulty('');
    setMaxFee('');
    setMinPoints('');
    setDateFrom('');
    setDateTo('');
    setIncludeUnknown(false);
    setRadius('25');
    setNearby(null);
    setPage(1);
    search({
      query: '',
      city: nextCity,
      state: nextState,
      mode: '',
      period: 'upcoming',
      difficulty: '',
      maxFee: '',
      minPoints: '',
      dateFrom: '',
      dateTo: '',
      includeUnknown: false,
      radius: '25',
      page: 1,
      nearby: null,
    });
  }

  function locateNearby() {
    if (!navigator.geolocation) {
      setError('Location is unavailable. Choose your city instead.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const next = { latitude: position.coords.latitude, longitude: position.coords.longitude };
        setNearby(next);
        setPage(1);
        search({ nearby: next, page: 1 });
      },
      () => setError('Location was not available. You can still search by city or state.'),
      { timeout: 10000 },
    );
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
      setState(saved.state || '');
      await loadWorkspace(saved.city || '', saved.state || '');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLocationBusy(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    const nextCity = city || user.city || '';
    const nextState = state || user.state || '';
    if (!city && user.city) setCity(user.city);
    if (!state && user.state) setState(user.state);
    loadWorkspace(nextCity, nextState).catch(() => {});
  }, [user]);

  async function toggleDigest(next: boolean) {
    setError('');
    setDigestBusy(true);
    try {
      const d = await api('/me/digest', {
        method: 'PATCH',
        body: JSON.stringify({ opted_in: next, cadence_days: 14 }),
      });
      setDigestOptIn(!!d.opted_in);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDigestBusy(false);
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
      window.open('/api/v1/me/certificates/' + cert.id, '_blank', 'noopener');
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
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        <div className="gate" id="main-content">
          <Loader2 className="spin" />
          <p>Opening CareCredits…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="dash">
        <div className="gate">
          <a className="skip-link" href="#main-content">
            Skip to sign in
          </a>
          <form id="main-content" className="gate-card" onSubmit={submitAccount} aria-busy={busy}>
            <div className="brand">
              <Mark />
              <div>
                <strong>Care Credits</strong>
                <small>Log points. Find training. Focus on patients.</small>
              </div>
            </div>
            <h1>{mode === 'register' ? 'Create your workspace' : 'Sign in to search'}</h1>
            <p>
              {demo
                ? 'Demo mode: sign in as demo@carecredits.local to review fixtures and personal tracking. Live Tavily/model discovery needs configured credentials.'
                : 'Register, then search Malaysian CPD courses from the original dashboard.'}
            </p>
            {demo && (
              <p className="demo-banner">
                <span className="badge">DEMO</span> Example courses and review candidates are fictional. Use doctor@carecredits.local for a pure doctor login.
              </p>
            )}
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
      <a className="skip-link" href="#main-content">
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
                  if (item === 'Events' || item === 'Discover') {
                    setPeriod('upcoming');
                    void search({ period: 'upcoming', page: 1 });
                  }
                }}
              >
                <Icon />
                <span>{item}</span>
              </button>
            ))}
          </nav>
          <div className="nav-rule" />
          <p className="nav-heading">FULL WORKSPACE</p>
          <nav>
            <a className="nav-item" href="/" aria-label="Open full CareCredits workspace">
              <Settings />
              <span>Operator and doctor workspace</span>
            </a>
          </nav>
          <div className="profile">
            <span className="avatar">{initials(user.name)}</span>
            <div>
              <strong>{user.name}</strong>
              <small>{user.role === 'operator' ? 'Operator' : user.city || 'Malaysia'}</small>
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
        <main className="main" id="main-content">
          <header className="topbar">
            <button className="menu-button" onClick={() => setOpen(true)} aria-label="Open navigation">
              <Menu />
            </button>
            <form
              id="live-filters"
              onSubmit={(event) => {
                event.preventDefault();
                setTab('Discover');
                search({ page: 1 });
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
              <input
                className="city-search"
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder="Selangor"
                aria-label="State"
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
                  <option value="upcoming">Upcoming</option>
                  <option value="all">All dates</option>
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
              <input
                className="city-search"
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                aria-label="From date"
              />
              <input
                className="city-search"
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                aria-label="To date"
              />
              <label className="city-search">
                <select aria-label="Search radius" value={radius} onChange={(e) => setRadius(e.target.value)}>
                  {[10, 25, 50, 100].map((km) => (
                    <option key={km} value={km}>
                      {km} km
                    </option>
                  ))}
                </select>
              </label>
              <label className="city-search check-row">
                <input
                  type="checkbox"
                  checked={includeUnknown}
                  onChange={(e) => setIncludeUnknown(e.target.checked)}
                  aria-label="Include date not confirmed and unknown fees or points"
                />
                <span>Include date not confirmed and unknown fees or points</span>
              </label>
              <button className="search-btn" disabled={loading}>
                {loading ? <Loader2 className="spin" size={16} /> : 'Search'}
              </button>
              <button
                className="text-link"
                type="button"
                onClick={() => {
                  setTab('Discover');
                  locateNearby();
                }}
              >
                Near me
              </button>
              <button className="text-link" type="button" onClick={clearFilters}>
                Clear filters
              </button>
            </form>
            <div className="top-actions">
              <span className="avatar" title={user.name} aria-label={user.name}>
                {initials(user.name)}
              </span>
            </div>
          </header>
          <div className="content">
            {demo && (
              <p className="demo-banner">
                <span className="badge">DEMO</span> Example courses and review candidates are fictional. Live discovery
                needs configured Tavily and model credentials.
              </p>
            )}
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
                        search({ page: 1 });
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
                      {!!progress?.excluded && <small>{excludedCopy(progress)}</small>}
                    </div>
                  </article>
                </section>
                <section className="card" id="live-audit">
                  <div className="card-heading">
                    <div>
                      <span className="heading-icon">▤</span>
                      <h2>Your activity</h2>
                    </div>
                  </div>
                  <p className="empty-copy">Your own audit trail. Personal notes and secrets are never shown here.</p>
                  {audits.length ? (
                    <ul className="source-list">
                      {audits.slice(0, 8).map((item) => (
                        <li key={item.id}>
                          {item.action} · {item.entity_id}
                          {item.at ? ` · ${new Date(item.at * 1000).toLocaleString('en-MY')}` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="empty-copy">Sign-up, attendance, and profile saves will appear here.</p>
                  )}
                </section>
              </>
            )}
            <div className="dashboard-grid">
              {(tab === 'Discover' || tab === 'Events' || tab === 'Overview') && (
              <div className="left-column">
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <span className="heading-icon">▣</span>
                      <h2>
                        {tab === 'Discover'
                          ? 'Search results'
                          : tab === 'Events'
                            ? 'Upcoming training'
                            : 'Listed training'}
                      </h2>
                    </div>
                    <p>{total} events</p>
                  </div>
                  {loading ? (
                    <p className="empty-copy">Finding your training…</p>
                  ) : courses.length ? (
                    <>
                      {courses.map((course) => (
                        <button key={course.id} className="event" onClick={() => openCourse(course)}>
                          <DateChip value={course.start_date} />
                          <span className="event-name">
                            <strong>
                              {course.title}
                              {course.demo ? ' · Demo course' : ''}
                            </strong>
                            <small>
                              {formatDate(course.start_date)} · {course.city || 'Online'}
                              {distanceLabel(course, !!nearby)}
                            </small>
                          </span>
                          <span className="event-points">
                            {course.points != null ? `${course.points} ${course.credit_label || 'CPD'} points` : 'Points not listed'}
                          </span>
                          <ChevronRight />
                        </button>
                      ))}
                      {total > PAGE_SIZE && (
                        <div className="pager">
                          <button
                            className="text-link"
                            type="button"
                            disabled={page <= 1 || loading}
                            onClick={() => search({ page: page - 1 })}
                          >
                            Previous
                          </button>
                          <span>
                            Page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
                          </span>
                          <button
                            className="text-link"
                            type="button"
                            disabled={page * PAGE_SIZE >= total || loading}
                            onClick={() => search({ page: page + 1 })}
                          >
                            Next
                          </button>
                        </div>
                      )}
                      {nearby && (
                        <p className="empty-copy">
                          Approximate straight-line distance when venue coordinates exist; otherwise distance unavailable.
                          Online sessions still appear for Online, Hybrid, or Any mode.
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="empty-copy">No matching training. Try a broader topic or clear filters.</p>
                  )}
                </section>
              </div>
              )}
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
                    Save city and state on your profile. Catalogue search uses those fields, or Near me with a radius when
                    you share coordinates. Skipping location does not block the rest of the demo.
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
                    <label>
                      Public profile bio
                      <textarea
                        aria-label="Public profile bio"
                        value={user.bio || ''}
                        onChange={(e) => setUser({ ...user, bio: e.target.value })}
                        rows={2}
                      />
                    </label>
                    <label className="empty-copy">
                      <input
                        type="checkbox"
                        checked={!!user.public_enabled}
                        onChange={(e) => setUser({ ...user, public_enabled: e.target.checked })}
                      />{' '}
                      Show selected attended learning on a public profile
                    </label>
                    {user.public_slug ? (
                      <p className="empty-copy">
                        <a href={'/p/' + user.public_slug} target="_blank" rel="noreferrer">
                          Open public profile
                        </a>
                        {user.public_enabled ? '' : ' (private until you enable sharing)'}
                      </p>
                    ) : null}
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
                    suggestions.slice(0, 5).map((item) => (
                      <button
                        key={item.id}
                        className="recommendation"
                        type="button"
                        onClick={() => openCourse({ id: item.id } as Course)}
                      >
                        <DateChip value={item.start_date} />
                        <div>
                          <h3>{item.title}</h3>
                          <p>{item.provider || 'Catalogue listing'}</p>
                          <small>
                            {formatDate(item.start_date || null)} · {item.city || 'Online'}
                            {item.reason ? ` — ${item.reason}` : ''}
                            {item.points != null ? ` · ${item.points} points` : ''}
                          </small>
                        </div>
                        <ChevronRight />
                      </button>
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
                      <p className="missing">
                        {progress?.excluded
                          ? excludedCopy(progress)
                          : 'Opening a source does not register you with the provider.'}
                      </p>
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
                  <section className="card" id="live-learning" data-testid="live-learning">
                    <div className="card-heading">
                      <div>
                        <span className="heading-icon">▣</span>
                        <h2>My learning</h2>
                      </div>
                      <p>{recordsTotal} saved records</p>
                    </div>
                    <p className="empty-copy">
                      Signed-up and attended lists from your personal record. Opening a provider link does not create a
                      sign-up.
                    </p>
                    <div className="button-row">
                      {(
                        [
                          ['all', 'All'],
                          ['signed_up', 'Signed up'],
                          ['attended', 'Attended'],
                        ] as const
                      ).map(([value, label]) => (
                        <button
                          key={value}
                          className={learningFilter === value ? 'secondary chosen' : 'secondary'}
                          type="button"
                          aria-pressed={learningFilter === value}
                          onClick={() => loadLearning(value)}
                        >
                          {label}
                        </button>
                      ))}
                      <button className="text-link" type="button" onClick={() => loadLearning(learningFilter)}>
                        Retry
                      </button>
                      <a className="text-link" href="/api/v1/me/export/csv">
                        Export CSV
                      </a>
                      <a className="text-link" href="/api/v1/me/export/eml">
                        Email draft
                      </a>
                    </div>
                    {learningBusy ? (
                      <p className="empty-copy" role="status" aria-busy="true">
                        Loading your learning record…
                      </p>
                    ) : records.length ? (
                      <>
                        {records.map((course) => (
                          <button key={course.id} className="event" type="button" onClick={() => openCourse(course)}>
                            <DateChip value={course.start_date} />
                            <span className="event-name">
                              <strong>{course.title}</strong>
                              <small>
                                {formatDate(course.start_date)} ·{' '}
                                {course.record?.attendance_status === 'attended'
                                  ? 'Attended'
                                  : course.record?.signup_status === 'signed_up'
                                    ? 'Signed up'
                                    : course.record?.signup_status === 'cancelled'
                                      ? 'Sign-up cancelled'
                                      : 'Saved'}
                              </small>
                            </span>
                            <ChevronRight />
                          </button>
                        ))}
                        {recordsTotal > 12 && (
                          <div className="pager" data-testid="live-learning-pager">
                            <button
                              className="text-link"
                              type="button"
                              disabled={learningPage <= 1 || learningBusy}
                              onClick={() => loadLearning(learningFilter, learningPage - 1)}
                            >
                              Previous
                            </button>
                            <span>
                              Page {learningPage} of {Math.max(1, Math.ceil(recordsTotal / 12))}
                            </span>
                            <button
                              className="text-link"
                              type="button"
                              disabled={learningPage * 12 >= recordsTotal || learningBusy}
                              onClick={() => loadLearning(learningFilter, learningPage + 1)}
                            >
                              Next
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="empty-copy">
                        Your learning story starts here. Open a catalogue course to record sign-up or attendance.
                      </p>
                    )}
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
                        disabled={digestBusy}
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
          canCancel={user?.role === 'operator'}
          onCancel={async () => {
            setSaving(true);
            try {
              await api('/admin/trainings/' + selected.id + '/cancel', { method: 'POST' });
              await search({ page: 1 });
              setSelected(null);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setSaving(false);
            }
          }}
        />
      )}
    </div>
  );
}
