/**
 * Typed client for the Zero Harm content console API (/api/console/ on the Django backend).
 * Requests go to the local console server, which adds the console key before forwarding.
 */

// ---------- Shared types ----------

export type SpanishStatus = 'none' | 'draft' | 'approved';
export type FeedKind = 'alert' | 'course' | 'tool' | 'video' | 'newsletter';
export type Jurisdiction = '' | 'federal' | 'nevada' | 'las_vegas';
export type Audience = 'weekly_talk' | 'alerts' | 'zero_hour' | 'offers';
export type SuggestionStatus = 'new' | 'planned' | 'used' | 'declined';
export type UpcomingType = 'talk' | 'feed' | 'episode';

export interface Counts {
  talks: number;
  talks_released: number;
  talks_needing_review: number;
  feed_live: number;
  episodes_released: number;
  kb_entries: number;
  suggestions_new: number;
  sheets_failed: number;
}

export interface UpcomingItem {
  type: UpcomingType;
  id: number | string;
  title: string;
  at: string;
  push: boolean;
}

export interface RecentPush {
  type: UpcomingType | 'broadcast';
  id: number | string;
  title: string;
  at: string;
}

export interface Overview {
  counts: Counts;
  upcoming: UpcomingItem[];
  recent_pushes: RecentPush[];
  onesignal_configured: boolean;
  anthropic_configured: boolean;
  content_version: string;
}

export interface TalkSpanish {
  title: string;
  story_title: string;
  crew_question: string;
  body_md: string;
}

/** ToolboxTalk.as_api() plus the fields only the console sees. */
export interface TalkAdmin {
  issue: number;
  number: number;
  issue_date: string;
  month_theme: string;
  title: string;
  story_title: string;
  crew_question: string;
  body_md: string | null;
  hero_url: string | null;
  pdf_url: string | null;
  es: TalkSpanish | null;
  send_at: string;
  published: boolean;
  needs_review: boolean;
  review_flags: string;
  spanish_status: SpanishStatus;
  title_es: string;
  story_title_es: string;
  crew_question_es: string;
  body_md_es: string;
  push_sent_at: string | null;
  released: boolean;
  updated_at: string;
}

export interface TalkPatch {
  title?: string;
  story_title?: string;
  crew_question?: string;
  body_md?: string;
  month_theme?: string;
  hero_url?: string;
  pdf_url?: string;
  /** ISO. A time without an offset is read as America/Los_Angeles. */
  send_at?: string;
  published?: boolean;
  needs_review?: boolean;
  title_es?: string;
  story_title_es?: string;
  crew_question_es?: string;
  body_md_es?: string;
  spanish_status?: SpanishStatus;
}

/** FeedItem.as_api() plus the fields only the console sees. */
export interface FeedAdmin {
  id: number;
  kind: FeedKind;
  title: string;
  summary: string;
  body_md: string | null;
  /** The tracked link the app opens (src=zero-harm-app added). */
  link_url: string | null;
  image_url: string | null;
  /** Display name from as_api(), e.g. "Federal OSHA". Use jurisdictionCode() to get the stored value. */
  jurisdiction: string | null;
  effective_date: string | null;
  published_at: string;
  featured: boolean;
  external_id: string;
  publish_at: string;
  expires_at: string | null;
  published: boolean;
  send_push: boolean;
  push_sent_at: string | null;
  live: boolean;
  /** The link exactly as stored, without tracking. */
  link_url_raw: string;
}

export interface FeedInput {
  kind?: FeedKind;
  title?: string;
  summary?: string;
  body_md?: string;
  link_url?: string;
  image_url?: string;
  jurisdiction?: Jurisdiction;
  effective_date?: string | null;
  publish_at?: string;
  expires_at?: string | null;
  send_push?: boolean;
  featured?: boolean;
  published?: boolean;
}

/** Episode.as_api() plus the fields only the console sees. */
export interface EpisodeAdmin {
  number: number;
  title: string;
  hazard: string;
  story: string;
  zero_hour: string;
  chain: string[];
  checks_label: string;
  checks: string[];
  stop_when: string;
  emergency_label: string;
  emergency: string;
  questions: string[];
  references: string[];
  video_url: string | null;
  thumbnail_url: string | null;
  card_pdf_url: string | null;
  released_at: string;
  release_at?: string;
  published?: boolean;
  needs_details?: boolean;
  send_push?: boolean;
  push_sent_at?: string | null;
  released?: boolean;
  updated_at?: string;
}

export interface EpisodePatch {
  title?: string;
  hazard?: string;
  story?: string;
  zero_hour?: string;
  chain?: string[];
  checks_label?: string;
  checks?: string[];
  stop_when?: string;
  emergency_label?: string;
  emergency?: string;
  questions?: string[];
  references?: string[];
  video_url?: string;
  thumbnail_url?: string;
  card_pdf_url?: string;
  release_at?: string;
  published?: boolean;
  needs_details?: boolean;
  send_push?: boolean;
}

export interface KbEntry {
  id: number;
  title: string;
  body: string;
  source: string;
  tags: string;
  published: boolean;
  updated_at?: string;
}

export interface KbInput {
  title?: string;
  body?: string;
  source?: string;
  tags?: string;
  published?: boolean;
}

export interface Suggestion {
  id: number;
  topic: string;
  details: string;
  month_theme: string;
  name: string;
  email: string;
  company: string;
  may_contact: boolean;
  status: SuggestionStatus;
  used_in_issue: number | null;
  created_at: string;
}

export interface SuggestionPatch {
  status?: SuggestionStatus;
  used_in_issue?: number | null;
}

/** A push the API handled. ok is false when OneSignal refused it; detail then says why. */
export interface PushResult {
  ok: boolean;
  detail: unknown;
}

export interface BroadcastInput {
  audience: Audience;
  heading: string;
  message: string;
  route?: string;
  dry_run: boolean;
}

// ---------- Connection status ----------

export interface Connection {
  ok: boolean;
  status: number;
  error: string;
}

type ConnectionListener = (c: Connection) => void;
const listeners = new Set<ConnectionListener>();

/** The app shows a banner while the API is unreachable or the key is wrong. */
export function onConnection(listener: ConnectionListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function report(c: Connection) {
  listeners.forEach((l) => l(c));
}

// Statuses that mean the console can't work at all, as opposed to a bad field in one form.
const CONNECTION_STATUSES = [0, 401, 403, 429, 502, 503, 504];

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// ---------- Request helper ----------

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-ZeroHarm-Console': '1' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    const error = 'The console server is not running. Start it with npm run dev in the console folder.';
    report({ ok: false, status: 0, error });
    throw new ApiError(0, error);
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const fromServer = data && typeof data === 'object' && 'error' in data ? String((data as { error: unknown }).error) : '';
    const error = fromServer || `The API answered ${res.status} ${res.statusText}.`;
    if (CONNECTION_STATUSES.includes(res.status)) report({ ok: false, status: res.status, error });
    throw new ApiError(res.status, error);
  }
  report({ ok: true, status: res.status, error: '' });
  return data as T;
}

const enc = encodeURIComponent;

// ---------- Endpoints ----------

export const api = {
  overview: () => request<Overview>('GET', '/console/overview/'),
  contentVersion: () => request<{ version: string }>('GET', '/content-version/'),

  talks: () => request<{ talks: TalkAdmin[] }>('GET', '/console/talks/').then((d) => d.talks),
  talk: (issue: number) => request<TalkAdmin>('GET', `/console/talks/${issue}/`),
  updateTalk: (issue: number, patch: TalkPatch) => request<TalkAdmin>('PATCH', `/console/talks/${issue}/`, patch),
  pushTalk: (issue: number, force = false) => request<PushResult>('POST', `/console/talks/${issue}/push/`, force ? { force: true } : {}),
  draftSpanish: (issue: number) => request<TalkAdmin>('POST', `/console/talks/${issue}/spanish-draft/`, {}),

  feed: () => request<{ items: FeedAdmin[] }>('GET', '/console/feed/').then((d) => d.items),
  createFeed: (input: FeedInput) => request<FeedAdmin>('POST', '/console/feed/', input),
  updateFeed: (id: number, patch: FeedInput) => request<FeedAdmin>('PATCH', `/console/feed/${id}/`, patch),
  unpublishFeed: (id: number) => request<FeedAdmin>('DELETE', `/console/feed/${id}/`),
  feedItem: (id: number) => request<FeedAdmin>('GET', `/console/feed/${id}/`),
  pushFeed: (id: number, force = false) => request<PushResult>('POST', `/console/feed/${id}/push/`, force ? { force: true } : {}),

  episodes: () => request<{ episodes: EpisodeAdmin[] }>('GET', '/console/episodes/').then((d) => d.episodes),
  episode: (n: number) => request<EpisodeAdmin>('GET', `/console/episodes/${n}/`),
  updateEpisode: (n: number, patch: EpisodePatch) => request<EpisodeAdmin>('PATCH', `/console/episodes/${n}/`, patch),
  pushEpisode: (n: number, force = false) => request<PushResult>('POST', `/console/episodes/${n}/push/`, force ? { force: true } : {}),

  kb: () => request<{ entries: KbEntry[] }>('GET', '/console/kb/').then((d) => d.entries),
  createKb: (input: KbInput) => request<KbEntry>('POST', '/console/kb/', input),
  updateKb: (id: number, patch: KbInput) => request<KbEntry>('PATCH', `/console/kb/${enc(String(id))}/`, patch),
  unpublishKb: (id: number) => request<KbEntry>('DELETE', `/console/kb/${enc(String(id))}/`),

  suggestions: () => request<{ suggestions: Suggestion[] }>('GET', '/console/suggestions/').then((d) => d.suggestions),
  updateSuggestion: (id: number, patch: SuggestionPatch) => request<Suggestion>('PATCH', `/console/suggestions/${id}/`, patch),

  broadcast: (input: BroadcastInput) => request<PushResult>('POST', '/console/broadcast/', input),
};

// ---------- Small helpers shared by screens ----------

const JURISDICTION_NAMES: Record<Exclude<Jurisdiction, ''>, string> = {
  federal: 'Federal OSHA',
  nevada: 'Nevada',
  las_vegas: 'Las Vegas',
};

export const JURISDICTIONS: { value: Jurisdiction; label: string }[] = [
  { value: '', label: 'None' },
  { value: 'federal', label: JURISDICTION_NAMES.federal },
  { value: 'nevada', label: JURISDICTION_NAMES.nevada },
  { value: 'las_vegas', label: JURISDICTION_NAMES.las_vegas },
];

/** as_api() sends the display name; the editor needs the stored code. Accepts either. */
export function jurisdictionCode(value: string | null): Jurisdiction {
  if (!value) return '';
  const hit = JURISDICTIONS.find((j) => j.value === value || j.label === value);
  return hit ? hit.value : '';
}

/** Push results carry whatever OneSignal said. Turn it into one readable line. */
export function detailText(detail: unknown): string {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

/** Routes the app accepts in a notification's data.route. */
export const ROUTE_PREFIXES = ['/talk/', '/alert/', '/zero-hour/', '/monday/', '/learn', '/otis', '/archive'];
