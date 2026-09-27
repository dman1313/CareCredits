export type User = {
  id: string;
  name: string;
  email: string;
  city: string;
  state: string;
  bio: string;
  role: string;
  public_enabled: boolean;
  public_slug: string;
};

export type Suggestion = {
  id: string;
  title: string;
  provider?: string;
  start_date?: string | null;
  city?: string | null;
  mode?: string;
  fee?: number | null;
  currency?: string | null;
  reason?: string;
};

export type SignupStatus = 'not_recorded' | 'signed_up' | 'cancelled';

export type RecordData = {
  signed_up: boolean;
  signup_status: SignupStatus;
  attended: boolean;
  attended_on: string | null;
  points: number | null;
  credit_label: string;
  notes: string;
  public: boolean;
  version: number;
  signed_up_at?: number | null;
  points_origin?: string;
};

export type RecordHistoryItem = {
  at: number;
  signup_status?: SignupStatus;
  attended?: boolean;
  attended_on?: string | null;
  points?: number | null;
  credit_label?: string;
};

export type Course = {
  id: string;
  title: string;
  provider: string;
  description: string;
  start_date: string | null;
  city: string | null;
  state?: string | null;
  mode: string;
  fee: number | null;
  currency: string | null;
  points: number | null;
  credit_label: string | null;
  difficulty: string | null;
  prerequisites: string | null;
  registration_url: string | null;
  source_url: string;
  evidence: Record<string, string>;
  distance_km?: number | null;
  demo: boolean;
  verification_status?: string;
  reviewed_at?: number | null;
  record: RecordData | null;
};

export type Progress = {
  year: number;
  signed_up: number;
  attended: number;
  points: number;
  excluded: number;
};

export type TavilySource = {
  url: string;
  title: string;
  snippet: string;
  extraction_status: string;
  verification_status: string;
};

export type Job = {
  id: string;
  query: string;
  status: string;
  max_results?: number;
  result: { warnings?: string[]; candidate_count?: number; sources?: TavilySource[] } | null;
};

export type Candidate = { id: string; data: Course; status: string; reason?: string; version?: number };

export type WorkspaceTab =
  | 'Overview'
  | 'Discover training'
  | 'My learning'
  | 'Public profile'
  | 'Ingestion';

export const emptyRecord: RecordData = {
  signed_up: false,
  signup_status: 'not_recorded',
  attended: false,
  attended_on: null,
  points: null,
  credit_label: 'CPD',
  notes: '',
  public: false,
  version: 0,
};

export function formatDate(value: string | null) {
  return value
    ? new Date(value + 'T12:00:00').toLocaleDateString('en-MY', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : 'Date to be confirmed';
}

export function feeLabel(c: Course) {
  if (c.fee === null) return 'Fee not listed';
  if (c.fee === 0) return 'Free';
  return `${c.currency} ${c.fee.toLocaleString()}`;
}

export function modeName(value: string) {
  return ({ in_person: 'In person', online: 'Online', hybrid: 'Hybrid' }[value] || value);
}

export function locationLabel(course: { mode: string; city: string | null; state?: string | null }) {
  if (course.city) {
    return course.state ? `${course.city}, ${course.state}` : course.city;
  }
  return course.mode === 'online' ? 'Online' : 'Location not listed';
}

export function distanceLabel(course: { distance_km?: number | null; mode: string }, nearby = false) {
  if (course.distance_km != null) return ` · ~${course.distance_km} km`;
  if (nearby && course.mode !== 'online') return ' · distance unavailable';
  return '';
}

export function todayLocal() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kuala_Lumpur' }).format(new Date());
}

export async function api(path: string, options: RequestInit = {}) {
  const response = await fetch('/api/v1' + path, {
    ...options,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      'X-Care-Client': '1',
      ...options.headers,
    },
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message = data?.error?.message || (typeof data.detail === 'string' ? data.detail : '');
    throw new Error(message || 'Please check your entries and try again.');
  }
  return response.json();
}
