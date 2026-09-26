'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  Compass,
  Eye,
  LayoutDashboard,
  Loader2,
  LogOut,
  MapPin,
  Menu,
  Settings2,
  ShieldCheck,
  X,
} from 'lucide-react';
import { Brand } from '@/components/Brand';
import { LoginForm } from '@/components/LoginForm';
import { OverviewPanel } from '@/components/OverviewPanel';
import { DiscoverPanel, DiscoverFilters } from '@/components/DiscoverPanel';
import { ProfilePanel } from '@/components/ProfilePanel';
import { IngestionPanel } from '@/components/IngestionPanel';
import { TrainingDetail } from '@/components/TrainingDetail';
import {
  api,
  Candidate,
  Course,
  emptyRecord,
  Job,
  Progress,
  RecordData,
  User,
  WorkspaceTab,
} from '@/lib/portal';

const initialFilters: DiscoverFilters = {
  q: '',
  city: '',
  state: '',
  mode: '',
  difficulty: '',
  maxFee: '',
  minPoints: '',
  period: 'upcoming',
  dateFrom: '',
  dateTo: '',
  includeUnknown: false,
  radius: '25',
  location: null,
  page: 1,
};

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);
  const [demo, setDemo] = useState(false);
  const [signup, setSignup] = useState(false);
  const [tab, setTab] = useState<WorkspaceTab>('Overview');
  const [navOpen, setNavOpen] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [courses, setCourses] = useState<Course[]>([]);
  const [records, setRecords] = useState<Course[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<DiscoverFilters>(initialFilters);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Course | null>(null);
  const [edit, setEdit] = useState<RecordData>(emptyRecord);
  const [saving, setSaving] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [jobQuery, setJobQuery] = useState('GP CPD courses Kuala Lumpur');
  const [submitting, setSubmitting] = useState(false);
  const jobKey = useRef('');

  useEffect(() => {
    Promise.all([
      api('/config').then((c) => {
        setDemo(c.demo);
        setSignup(c.signup_enabled);
      }),
      api('/me').then(setUser).catch(() => {}),
    ]).finally(() => setBooting(false));
  }, []);

  const refreshRecords = useCallback(async () => {
    const [r, p] = await Promise.all([api('/me/trainings'), api('/me/progress')]);
    setRecords(r.items);
    setProgress(p);
  }, []);

  const loadCourses = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        q: filters.q,
        city: filters.city,
        state: filters.state,
        mode: filters.mode,
        difficulty: filters.difficulty,
        period: filters.period,
        page: String(filters.page),
        page_size: '9',
        include_unknown: String(filters.includeUnknown),
      });
      if (filters.maxFee) params.set('max_fee_myr', filters.maxFee);
      if (filters.minPoints) params.set('min_points', filters.minPoints);
      if (filters.dateFrom) params.set('date_from', filters.dateFrom);
      if (filters.dateTo) params.set('date_to', filters.dateTo);
      if (filters.location) {
        params.set('latitude', String(filters.location.latitude));
        params.set('longitude', String(filters.location.longitude));
        params.set('radius_km', filters.radius);
      }
      const data = await api('/trainings?' + params);
      setCourses(data.items);
      setTotal(data.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    if (user) refreshRecords().catch((e) => setError(e.message));
  }, [user, refreshRecords]);

  useEffect(() => {
    if (!user) return;
    const timer = setTimeout(loadCourses, 250);
    return () => clearTimeout(timer);
  }, [user, loadCourses]);

  const refreshOperator = useCallback(async () => {
    const [j, c] = await Promise.all([api('/admin/ingestion-jobs'), api('/admin/candidates')]);
    setJobs(j.items);
    setCandidates(c.items);
  }, []);

  useEffect(() => {
    if (user?.role !== 'operator' || tab !== 'Ingestion') return;
    refreshOperator().catch((e) => setError(e.message));
    const timer = setInterval(() => refreshOperator().catch(() => {}), 5000);
    return () => clearInterval(timer);
  }, [user, tab, refreshOperator]);

  useEffect(() => {
    if (!selected) return;
    const previous = document.activeElement as HTMLElement;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelected(null);
        return;
      }
      if (e.key === 'Tab') {
        const items = Array.from(
          document.querySelectorAll<HTMLElement>(
            '.modal button:not(:disabled),.modal a,.modal input,.modal textarea,.modal select',
          ),
        );
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus();
    };
  }, [selected]);

  function navigate(next: WorkspaceTab) {
    setTab(next);
    setNavOpen(false);
    setError('');
    setNotice('');
  }

  async function openCourse(course: Course) {
    try {
      const current = await api('/trainings/' + course.id);
      setSelected(current);
      setEdit({ ...emptyRecord, ...current.record });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveRecord(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setSaving(true);
    setError('');
    try {
      await api('/me/trainings/' + selected.id, { method: 'PUT', body: JSON.stringify(edit) });
      await refreshRecords();
      await loadCourses();
      setSelected(null);
      setNotice('Training record saved.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    if (!user) return;
    setSaving(true);
    try {
      const saved = await api('/me', {
        method: 'PATCH',
        body: JSON.stringify({
          name: user.name,
          city: user.city,
          bio: user.bio,
          public_enabled: user.public_enabled,
        }),
      });
      setUser(saved);
      setNotice('Profile settings saved.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function locate() {
    if (!navigator.geolocation) {
      setError('Location is unavailable. Choose your city instead.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setFilters((f) => ({
          ...f,
          location: { latitude: p.coords.latitude, longitude: p.coords.longitude },
          page: 1,
        }));
      },
      () => setError('Location was not available. You can still search by city.'),
      { timeout: 10000 },
    );
  }

  async function newJob(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      if (!jobKey.current) jobKey.current = crypto.randomUUID();
      await api('/admin/ingestion-jobs', {
        method: 'POST',
        headers: { 'Idempotency-Key': jobKey.current },
        body: JSON.stringify({ query: jobQuery }),
      });
      jobKey.current = '';
      await refreshOperator();
      setNotice('Job queued. The scraper will process it when running.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function review(id: string, action: string, reason = '') {
    setSaving(true);
    try {
      await api('/admin/candidates/' + id + '/review', {
        method: 'POST',
        body: JSON.stringify({ action, reason }),
      });
      await refreshOperator();
      await loadCourses();
      setNotice(
        action === 'publish'
          ? 'Training published with source evidence.'
          : action === 'hold'
            ? 'Candidate held for later review.'
            : 'Candidate rejected.',
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function retryJob(id: string) {
    setSaving(true);
    setError('');
    try {
      await api('/admin/ingestion-jobs/' + id + '/retry', { method: 'POST' });
      await refreshOperator();
      setNotice('Interrupted job queued again. Paid calls will not repeat until the scraper claims it.');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (booting) {
    return (
      <div className="boot">
        <Brand />
        <Loader2 className="spin" />
        <p>Opening your workspace…</p>
      </div>
    );
  }
  if (!user) return <LoginForm demo={demo} signup={signup} onLogin={setUser} />;

  const nav = [
    [LayoutDashboard, 'Overview'],
    [Compass, 'Discover training'],
    [BookOpen, 'My learning'],
    [Eye, 'Public profile'],
  ] as const;

  return (
    <div className="app-shell">
      {navOpen && <button className="nav-shade" aria-label="Close navigation" onClick={() => setNavOpen(false)} />}
      <aside className={'sidebar ' + (navOpen ? 'is-open' : '')}>
        <Brand />
        <p className="nav-label">YOUR WORKSPACE</p>
        <nav>
          {nav.map(([Icon, label]) => (
            <button
              key={label}
              className={'nav-item ' + (tab === label ? 'active' : '')}
              onClick={() => navigate(label)}
            >
              <Icon size={19} />
              {label}
            </button>
          ))}
        </nav>
        {user.role === 'operator' && (
          <>
            <p className="nav-label">MANAGE</p>
            <button
              className={'nav-item ' + (tab === 'Ingestion' ? 'active' : '')}
              onClick={() => navigate('Ingestion')}
            >
              <Settings2 size={19} />
              Training sources
            </button>
          </>
        )}
        <div className="sidebar-note">
          <ShieldCheck size={23} />
          <strong>Your learning. Your choice.</strong>
          <p>Your records stay private until you choose to share them.</p>
        </div>
        <div className="account">
          <span className="avatar">{user.name.replace('Dr ', '').slice(0, 1)}</span>
          <div>
            <strong>{user.name}</strong>
            <small>General practitioner</small>
          </div>
          <button
            className="icon-btn"
            aria-label="Sign out"
            onClick={async () => {
              await api('/auth/logout', { method: 'POST' });
              setUser(null);
            }}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <button className="mobile-menu icon-btn" aria-label="Open navigation" onClick={() => setNavOpen(!navOpen)}>
            <Menu />
          </button>
          <div className="breadcrumbs">
            Workspace <ChevronRight size={14} /> <strong>{tab}</strong>
          </div>
          <span className="region">
            <MapPin size={14} /> Malaysia
          </span>
        </header>
        <div className="content">
          {demo && (
            <div className="demo-banner">
              <span className="badge">DEMO</span> Example courses are fictional. Live discovery needs configured Tavily
              and model credentials.
            </div>
          )}
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button className="icon-btn" aria-label="Dismiss error" onClick={() => setError('')}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              <CheckCircle2 size={18} />
              {notice}
              <button className="icon-btn" aria-label="Dismiss notification" onClick={() => setNotice('')}>
                <X size={16} />
              </button>
            </div>
          )}
          {tab === 'Overview' && (
            <OverviewPanel
              progress={progress}
              courses={courses}
              loading={loading}
              onDiscover={() => navigate('Discover training')}
              onLearning={() => navigate('My learning')}
              onOpen={openCourse}
            />
          )}
          {(tab === 'Discover training' || tab === 'My learning') && (
            <DiscoverPanel
              tab={tab}
              filters={filters}
              courses={courses}
              records={records}
              total={total}
              loading={loading}
              onFilters={(patch) => setFilters((f) => ({ ...f, ...patch }))}
              onLocate={locate}
              onDiscover={() => navigate('Discover training')}
              onOpen={openCourse}
            />
          )}
          {tab === 'Public profile' && (
            <ProfilePanel user={user} saving={saving} onUser={setUser} onSave={saveProfile} />
          )}
          {tab === 'Ingestion' && (
            <IngestionPanel
              jobQuery={jobQuery}
              jobs={jobs}
              candidates={candidates}
              submitting={submitting}
              saving={saving}
              jobKey={jobKey}
              onJobQuery={setJobQuery}
              onSubmit={newJob}
              onRefresh={() => refreshOperator().catch((e) => setError(e.message))}
              onRetry={retryJob}
              onReview={review}
            />
          )}
          <footer>
            CareCredits <span>Built around your professional growth.</span>
            <small>Training and points are not independently accredited by CareCredits.</small>
          </footer>
        </div>
      </main>
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
