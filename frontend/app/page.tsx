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
import { DiscoverPanel, DiscoverFilters, LearningFilters } from '@/components/DiscoverPanel';
import { ProfilePanel } from '@/components/ProfilePanel';
import { IngestionPanel } from '@/components/IngestionPanel';
import { TrainingDetail } from '@/components/TrainingDetail';
import {
  api,
  AuditItem,
  Candidate,
  Course,
  emptyRecord,
  Job,
  Progress,
  RecordData,
  Suggestion,
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
  const [oauth, setOauth] = useState(false);
  const [history, setHistory] = useState<import('@/lib/portal').RecordHistoryItem[]>([]);
  const [tab, setTab] = useState<WorkspaceTab>('Overview');
  const [navOpen, setNavOpen] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [courses, setCourses] = useState<Course[]>([]);
  const [records, setRecords] = useState<Course[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [operatorLoading, setOperatorLoading] = useState(false);
  const [filters, setFilters] = useState<DiscoverFilters>(initialFilters);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Course | null>(null);
  const [opening, setOpening] = useState(false);
  const [edit, setEdit] = useState<RecordData>(emptyRecord);
  const [saving, setSaving] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [jobQuery, setJobQuery] = useState('GP CPD courses Kuala Lumpur');
  const [submitting, setSubmitting] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [digestOptIn, setDigestOptIn] = useState(false);
  const [digestBusy, setDigestBusy] = useState(false);
  const [certBusy, setCertBusy] = useState(false);
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [jobMaxResults, setJobMaxResults] = useState(5);
  const [candidateTotal, setCandidateTotal] = useState(0);
  const [candidatePage, setCandidatePage] = useState(1);
  const [audits, setAudits] = useState<AuditItem[]>([]);
  const [operatorAudits, setOperatorAudits] = useState<AuditItem[]>([]);
  const [topics, setTopics] = useState<{ query: string; max_results: number }[]>([]);
  const [scrapeCeiling, setScrapeCeiling] = useState<number | null>(null);
  const [scrapeDay, setScrapeDay] = useState('');
  const [forceScrape, setForceScrape] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<{
    enqueued: number;
    skipped: number;
    day: string;
    ceiling: number;
    topics: number;
  } | null>(null);
  const [digestResult, setDigestResult] = useState<{ sent: number; failed: number; day: string } | null>(null);
  const [learning, setLearning] = useState<LearningFilters>({ signupStatus: '', attended: '', page: 1 });
  const [recordsTotal, setRecordsTotal] = useState(0);
  const jobKey = useRef('');
  const retryRef = useRef<() => void>(() => {});
  const operatorBoot = useRef(true);

  function fail(err: unknown, retry: () => void) {
    setError((err as Error).message);
    retryRef.current = retry;
  }

  useEffect(() => {
    Promise.all([
      api('/config').then((c) => {
        setDemo(c.demo);
        setSignup(c.signup_enabled);
        setOauth(!!c.oauth_google);
      }),
      api('/me').then(setUser).catch(() => {}),
    ]).finally(() => setBooting(false));
  }, []);

  const refreshRecords = useCallback(async () => {
    const params = new URLSearchParams({
      page: String(learning.page),
      page_size: '9',
    });
    if (learning.signupStatus) params.set('signup_status', learning.signupStatus);
    if (learning.attended) params.set('attendance_status', learning.attended);
    setRecordsLoading(true);
    try {
      const [r, p] = await Promise.all([api('/me/trainings?' + params), api('/me/progress?year=' + year)]);
      setRecords(r.items);
      setRecordsTotal(r.total || 0);
      setProgress(p);
      const [digest, next, mine] = await Promise.all([
        api('/me/digest'),
        api('/me/suggestions'),
        api('/me/audit?page=1&page_size=8').catch(() => null),
      ]);
      setDigestOptIn(!!digest.opted_in);
      setSuggestions(next.items || []);
      if (mine) setAudits(mine.items || []);
    } catch (e) {
      fail(e, () => {
        refreshRecords().catch((err) => fail(err, () => refreshRecords()));
      });
    } finally {
      setRecordsLoading(false);
    }
  }, [year, learning]);

  const loadCourses = useCallback(async () => {
    setCoursesLoading(true);
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
      fail(e, () => {
        loadCourses();
      });
    } finally {
      setCoursesLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    if (user) refreshRecords().catch((e) => fail(e, () => refreshRecords()));
  }, [user, refreshRecords]);

  useEffect(() => {
    if (!user) return;
    const timer = setTimeout(loadCourses, 250);
    return () => clearTimeout(timer);
  }, [user, loadCourses]);

  const refreshOperator = useCallback(async () => {
    if (operatorBoot.current) setOperatorLoading(true);
    try {
      const [j, c, topicPayload, auditPayload] = await Promise.all([
        api('/admin/ingestion-jobs'),
        api('/admin/candidates?page=' + candidatePage + '&page_size=20'),
        api('/admin/scrape-topics').catch(() => null),
        api('/admin/audit?page=1&page_size=10').catch(() => null),
      ]);
      if (topicPayload) {
        setTopics(topicPayload.topics || []);
        setScrapeCeiling(topicPayload.ceiling ?? null);
        setScrapeDay(topicPayload.day || '');
      }
      const total = c.total || c.items.length;
      const pageCount = Math.max(1, Math.ceil(total / 20));
      if (candidatePage > pageCount) {
        setCandidatePage(pageCount);
        return;
      }
      setJobs(j.items);
      setCandidates(c.items);
      setCandidateTotal(total);
      if (auditPayload) setOperatorAudits(auditPayload.items || []);
    } finally {
      operatorBoot.current = false;
      setOperatorLoading(false);
    }
  }, [candidatePage]);

  useEffect(() => {
    if (user?.role !== 'operator' || tab !== 'Ingestion') return;
    refreshOperator().catch((e) => fail(e, () => refreshOperator()));
    const timer = setInterval(() => refreshOperator().catch(() => {}), 5000);
    return () => clearInterval(timer);
  }, [user, tab, refreshOperator]);

  function navigate(next: WorkspaceTab) {
    setTab(next);
    setNavOpen(false);
    setError('');
    setNotice('');
  }

  async function openCourse(course: Course) {
    setOpening(true);
    setError('');
    try {
      const current = await api('/trainings/' + course.id);
      setSelected(current);
      setEdit({ ...emptyRecord, ...current.record });
      const hist = await api('/me/trainings/' + course.id + '/history').catch(() => ({ items: [] }));
      setHistory(hist.items || []);
    } catch (e) {
      fail(e, () => openCourse(course));
    } finally {
      setOpening(false);
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
      fail(e, () => saveRecord({ preventDefault() {} } as FormEvent));
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
          state: user.state || '',
          bio: user.bio,
          public_enabled: user.public_enabled,
          latitude: user.latitude ?? null,
          longitude: user.longitude ?? null,
        }),
      });
      setUser(saved);
      setNotice('Profile settings saved.');
    } catch (e) {
      fail(e, () => saveProfile({ preventDefault() {} } as FormEvent));
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
        body: JSON.stringify({ query: jobQuery, max_results: jobMaxResults }),
      });
      jobKey.current = '';
      setCandidatePage(1);
      await refreshOperator();
      setNotice('Job queued. The scraper will process it when running.');
    } catch (e) {
      fail(e, () => newJob({ preventDefault() {} } as FormEvent));
    } finally {
      setSubmitting(false);
    }
  }

  async function review(
    id: string,
    action: string,
    reason = '',
    version = 0,
    corrections: Record<string, string> = {},
    evidence: Record<string, string> = {},
  ) {
    setSaving(true);
    try {
      await api('/admin/candidates/' + id + '/review', {
        method: 'POST',
        body: JSON.stringify({ action, reason, version, corrections, evidence }),
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
      fail(e, () => review(id, action, reason, version, corrections, evidence));
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
      fail(e, () => retryJob(id));
    } finally {
      setSaving(false);
    }
  }

  if (booting) {
    return (
      <div className="boot">
        <a className="skip-link" href="#main-content">
          Skip to content
        </a>
        <Brand />
        <Loader2 className="spin" />
        <p id="main-content">Opening your workspace…</p>
      </div>
    );
  }
  if (!user) return <LoginForm demo={demo} signup={signup} oauth={oauth} onLogin={setUser} />;

  const nav = [
    [LayoutDashboard, 'Overview'],
    [Compass, 'Discover training'],
    [BookOpen, 'My learning'],
    [Eye, 'Public profile'],
  ] as const;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      {navOpen && <button className="nav-shade" aria-label="Close navigation" onClick={() => setNavOpen(false)} />}
      <aside className={'sidebar ' + (navOpen ? 'is-open' : '')}>
        <Brand />
        <p className="nav-label">YOUR WORKSPACE</p>
        <nav>
          {nav.map(([Icon, label]) => (
            <button
              key={label}
              className={'nav-item ' + (tab === label ? 'active' : '')}
              aria-current={tab === label ? 'page' : undefined}
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
              aria-current={tab === 'Ingestion' ? 'page' : undefined}
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
            <small>{user.role === 'operator' ? 'Operator' : user.city || 'Malaysia'}</small>
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
        <div className="content" id="main-content">
          {demo && (
            <div className="demo-banner">
              <span className="badge">DEMO</span> Example courses are fictional. Live discovery needs configured Tavily
              and model credentials.
            </div>
          )}
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button className="text-btn" type="button" onClick={() => retryRef.current()}>
                Retry
              </button>
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
          {opening && (
            <p className="alert" role="status" aria-busy="true">
              Opening training details…
            </p>
          )}
          {tab === 'Overview' && (
            <OverviewPanel
              progress={progress}
              courses={courses}
              suggestions={suggestions}
              digestOptIn={digestOptIn}
              digestBusy={digestBusy}
              certBusy={certBusy}
              loading={recordsLoading}
              audits={audits}
              onDiscover={() => navigate('Discover training')}
              onLearning={() => navigate('My learning')}
              onOpen={openCourse}
              onYear={setYear}
              onToggleDigest={async (next) => {
                setDigestBusy(true);
                setError('');
                try {
                  const d = await api('/me/digest', {
                    method: 'PATCH',
                    body: JSON.stringify({ opted_in: next, cadence_days: 14 }),
                  });
                  setDigestOptIn(!!d.opted_in);
                  setNotice(d.opted_in ? 'Biweekly digest enabled.' : 'Digest emails turned off.');
                } catch (e) {
                  fail(e, () => refreshRecords());
                } finally {
                  setDigestBusy(false);
                }
              }}
              onIssueCertificate={async () => {
                setCertBusy(true);
                setError('');
                try {
                  const cert = await api('/me/certificates', {
                    method: 'POST',
                    body: JSON.stringify({ year }),
                  });
                  window.open('/api/v1/me/certificates/' + cert.id, '_blank', 'noopener');
                  setNotice('Affiliation certificate ready to print. It is not a regulator document.');
                } catch (e) {
                  fail(e, () => refreshRecords());
                } finally {
                  setCertBusy(false);
                }
              }}
            />
          )}
          {(tab === 'Discover training' || tab === 'My learning') && (
            <DiscoverPanel
              tab={tab}
              filters={filters}
              courses={courses}
              records={records}
              total={total}
              loading={tab === 'My learning' ? recordsLoading : coursesLoading}
              learning={learning}
              recordsTotal={recordsTotal}
              onFilters={(patch) => setFilters((f) => ({ ...f, ...patch }))}
              onLocate={locate}
              onDiscover={() => navigate('Discover training')}
              onOpen={openCourse}
              onClearFilters={() => setFilters(initialFilters)}
              onLearningFilters={(patch) => setLearning((f) => ({ ...f, ...patch }))}
            />
          )}
          {tab === 'Public profile' && (
            <ProfilePanel
              user={user}
              saving={saving}
              onUser={setUser}
              onSave={saveProfile}
              onLocateError={(message) => fail(new Error(message), locate)}
            />
          )}
          {tab === 'Ingestion' && (
            <IngestionPanel
              jobQuery={jobQuery}
              jobMaxResults={jobMaxResults}
              jobs={jobs}
              candidates={candidates}
              candidatePage={candidatePage}
              candidateTotal={candidateTotal}
              submitting={submitting}
              saving={saving}
              jobKey={jobKey}
              onJobQuery={setJobQuery}
              onJobMaxResults={setJobMaxResults}
              onSubmit={newJob}
              onRefresh={() => refreshOperator().catch((e) => fail(e, () => refreshOperator()))}
              onRetry={retryJob}
              onReview={review}
              onCandidatePage={setCandidatePage}
              loading={operatorLoading}
              topics={topics}
              ceiling={scrapeCeiling}
              scrapeDay={scrapeDay}
              forceScrape={forceScrape}
              onForceScrape={setForceScrape}
              scrapeResult={scrapeResult}
              digestResult={digestResult}
              audits={operatorAudits}
              onDailyScrape={async () => {
                setSaving(true);
                setError('');
                try {
                  const result = await api('/admin/daily-scrape?force=' + String(forceScrape), { method: 'POST' });
                  setScrapeResult(result);
                  await refreshOperator();
                  setNotice(
                    `Daily scrape ${result.day}: ${result.enqueued} queued, ${result.skipped} skipped (ceiling ${result.ceiling}).`,
                  );
                } catch (e) {
                  fail(e, () => refreshOperator());
                } finally {
                  setSaving(false);
                }
              }}
              onRunDigests={async () => {
                setSaving(true);
                setError('');
                try {
                  const result = await api('/admin/digests/run', { method: 'POST' });
                  setDigestResult(result);
                  setNotice(
                    `Digest ${result.day}: ${result.sent} sent, ${result.failed} failed. No Tavily call.`,
                  );
                } catch (e) {
                  fail(e, () => refreshOperator());
                } finally {
                  setSaving(false);
                }
              }}
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
          history={history}
          onClose={() => setSelected(null)}
          onEdit={setEdit}
          onSave={saveRecord}
          canCancel={user?.role === 'operator'}
          onCancel={async () => {
            setSaving(true);
            try {
              await api('/admin/trainings/' + selected.id + '/cancel', { method: 'POST' });
              await loadCourses();
              setSelected(null);
              setNotice('Session cancelled. Personal records were kept.');
            } catch (e) {
              fail(e, () => {});
            } finally {
              setSaving(false);
            }
          }}
        />
      )}
    </div>
  );
}
