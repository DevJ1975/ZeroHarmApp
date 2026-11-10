import Storage from 'expo-sqlite/kv-store';
import { Platform } from 'react-native';

import { api, ApiError, isConfigured } from './config';
import { getDb } from './db';
import { installId } from './install';
import { savedFirst } from './saved-first';

/** Monday Minute: the weekly AI-written toolbox talk, separate from Zero Harm Weekly. */
export type Minute = {
  id: number;
  week: string;
  published_at: string;
  topic: string;
  category: string;
  title: string;
  intro: string;
  points: string[];
  story_title: string;
  story: string;
  crew_question: string;
  takeaway: string;
  references: string[];
  thumbs_up: number;
  thumbs_down: number;
  comment_count: number;
};

export type Comment = { id: number; display_name: string; body: string; created_at: string; author_key: string; replies: Comment[] };
export type Reason = 'unsafe' | 'not_my_site' | 'confusing' | 'too_long' | 'too_basic';
export const REASONS: { key: Reason; label: string }[] = [
  { key: 'unsafe', label: 'Something in it isn’t safe or isn’t right' },
  { key: 'not_my_site', label: 'Doesn’t fit my site' },
  { key: 'confusing', label: 'Confusing' },
  { key: 'too_long', label: 'Too long' },
  { key: 'too_basic', label: 'Too basic' },
];

export const weekLabel = (m: Pick<Minute, 'week'>) =>
  new Date(`${m.week}T12:00:00`).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });

async function cache(list: Minute[]) {
  const db = await getDb();
  for (const m of list) await db.runAsync('INSERT OR REPLACE INTO monday_cache (id, json) VALUES (?, ?)', m.id, JSON.stringify(m));
}

/** Makes the saved copy match the server's list, so a talk that was pulled doesn't live on in the phone's offline copy. */
async function replaceCache(list: Minute[]) {
  const db = await getDb();
  await db.runAsync('DELETE FROM monday_cache');
  await cache(list);
}

async function forget(id: number) {
  const db = await getDb();
  await db.runAsync('DELETE FROM monday_cache WHERE id = ?', id);
}

async function readCache(): Promise<Minute[]> {
  const db = await getDb();
  const rows = await db.getAllAsync<{ json: string }>('SELECT json FROM monday_cache ORDER BY id DESC');
  return rows.map((r) => JSON.parse(r.json) as Minute);
}

const byWeek = (list: Minute[]) => [...list].sort((a, b) => b.week.localeCompare(a.week));

async function fetchMinutes(): Promise<Minute[]> {
  if (!isConfigured()) throw new Error('API not configured');
  const { minutes } = await api<{ minutes: Minute[] }>('/v2/monday-minute');
  await replaceCache(minutes);
  return minutes;
}

/**
 * Published Monday Minutes, newest first. The saved copy comes back right away, so the first screen opens instantly on
 * a weak signal; `onFresh` gets the server's list when the background refresh lands.
 */
export async function listMinutes(onFresh?: (list: Minute[]) => void): Promise<Minute[]> {
  const { value } = await savedFirst<Minute[]>(
    'monday',
    async () => {
      const saved = await readCache();
      return saved.length ? byWeek(saved) : null;
    },
    fetchMinutes,
    { onFresh },
  );
  return value ?? [];
}

/** One Monday Minute: the saved copy first, then `onFresh` with the latest (or null if it was pulled). */
export async function getMinute(id: number, onFresh?: (m: Minute | null) => void): Promise<Minute | null> {
  const { value } = await savedFirst<Minute | null>(
    `monday-${id}`,
    async () => (await readCache()).find((m) => m.id === id) ?? null,
    async () => {
      if (!isConfigured()) throw new Error('API not configured');
      try {
        const m = await api<Minute>(`/v2/monday-minute/${id}`);
        await cache([m]);
        return m;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          await forget(id); // pulled or unpublished: don't keep showing the saved copy
          return null;
        }
        throw err;
      }
    },
    { onFresh },
  );
  return value;
}

// ---- Thumbs up / down ------------------------------------------------------------------------------

const VOTES = 'monday_votes';
type Vote = { helpful: boolean; reasons: Reason[] };

export async function myVote(id: number): Promise<Vote | null> {
  const raw = await Storage.getItem(VOTES);
  return raw ? ((JSON.parse(raw) as Record<string, Vote>)[id] ?? null) : null;
}

const OUTBOX = 'monday_vote_outbox';
type QueuedVote = { id: number; helpful: boolean; reasons: Reason[]; note: string };

async function sendVote(v: QueuedVote) {
  return api<{ thumbs_up: number; thumbs_down: number }>(`/v2/monday-minute/${v.id}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ install_id: await installId(), helpful: v.helpful, reasons: v.reasons, note: v.note.slice(0, 300), platform: Platform.OS === 'ios' ? 'ios' : 'android' }),
  });
}

/**
 * Saves the vote on the phone and sends it. With no signal it waits in an outbox and goes out later (flushVotes), so a
 * thumbs down in a dead spot on the floor is never lost. Returns the new counts, or null when it's waiting to send.
 */
export async function rate(id: number, helpful: boolean, reasons: Reason[] = [], note = '') {
  const raw = await Storage.getItem(VOTES);
  const all = raw ? (JSON.parse(raw) as Record<string, Vote>) : {};
  all[id] = { helpful, reasons };
  await Storage.setItem(VOTES, JSON.stringify(all));
  const vote: QueuedVote = { id, helpful, reasons, note };
  try {
    return await sendVote(vote);
  } catch {
    const queued = JSON.parse((await Storage.getItem(OUTBOX)) ?? '[]') as QueuedVote[];
    await Storage.setItem(OUTBOX, JSON.stringify([...queued.filter((q) => q.id !== id), vote]));
    return null;
  }
}

/** Sends votes that were made with no signal. Safe to call often. */
export async function flushVotes() {
  if (!isConfigured()) return;
  const queued = JSON.parse((await Storage.getItem(OUTBOX)) ?? '[]') as QueuedVote[];
  if (!queued.length) return;
  const left: QueuedVote[] = [];
  for (const v of queued) {
    try {
      await sendVote(v);
    } catch (err) {
      if (!(err instanceof ApiError && err.status >= 400 && err.status < 500)) left.push(v); // keep unless the server refused it for good
    }
  }
  await Storage.setItem(OUTBOX, JSON.stringify(left));
}

// ---- Comments ---------------------------------------------------------------------------------------

const BLOCKED = 'monday_blocked_authors';
const RULES_OK = 'monday_rules_ok';
const NAME = 'monday_display_name';

export async function listComments(id: number) {
  const data = await api<{ comments: Comment[]; rules: string[] }>(`/v2/monday-minute/${id}/comments`);
  const blocked = new Set(await blockedAuthors());
  const keep = (c: Comment) => !blocked.has(c.author_key);
  return { rules: data.rules, comments: data.comments.filter(keep).map((c) => ({ ...c, replies: c.replies.filter(keep) })) };
}

export async function postComment(id: number, body: string, displayName: string, parentId?: number) {
  await Storage.setItem(NAME, displayName);
  return api<{ status: 'visible' | 'pending' | 'rejected'; message: string; comment: Comment | null }>(
    `/v2/monday-minute/${id}/comments`,
    {
      method: 'POST',
      body: JSON.stringify({ install_id: await installId(), body, display_name: displayName, parent_id: parentId ?? null, accepted_rules: true }),
    },
    30000, // the comment is checked before it posts; give a weak signal time
  );
}

export async function reportComment(commentId: number, reason = '') {
  return api(`/v2/monday-minute/comments/${commentId}/report`, { method: 'POST', body: JSON.stringify({ install_id: await installId(), reason }) });
}

export async function blockedAuthors(): Promise<string[]> {
  const raw = await Storage.getItem(BLOCKED);
  return raw ? (JSON.parse(raw) as string[]) : [];
}

/** Hides everything from this commenter on this phone. */
export async function blockAuthor(key: string) {
  const list = new Set(await blockedAuthors());
  list.add(key);
  await Storage.setItem(BLOCKED, JSON.stringify([...list]));
}

export const rulesAccepted = async () => (await Storage.getItem(RULES_OK)) === 'yes';
export const acceptRules = () => Storage.setItem(RULES_OK, 'yes');
export const savedDisplayName = async () => (await Storage.getItem(NAME)) ?? '';
