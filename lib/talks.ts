import { api, isConfigured } from './config';
import { getDb } from './db';
import { noteStaleContent } from './live';
import { savedFirst } from './saved-first';

export type TalkText = { title: string; story_title: string; crew_question: string; body_md: string };

export type Talk = {
  issue: number;
  number?: number;
  issue_date: string;
  month_theme: string;
  title: string;
  story_title: string;
  crew_question: string;
  body_md: string | null;
  hero_url: string | null;
  pdf_url: string | null;
  /** The Sunday newsletter send time (UTC). */
  send_at?: string;
  /** True when the talk is ready in the app before its Sunday newsletter goes out. */
  early?: boolean;
  /** Approved Spanish version, or null when there isn't one yet. */
  es?: TalkText | null;
};

/** The number printed on the issue (#01), falling back to the app's id. */
export const issueNumber = (t: Talk) => t.number ?? t.issue;

/** "Sunday, January 3": when the newsletter for this talk goes out, in the phone's time zone. */
export const sendDay = (t: Talk, locale?: string) =>
  t.send_at ? new Date(t.send_at).toLocaleDateString(locale, { weekday: 'long', month: 'long', day: 'numeric' }) : '';

/**
 * Splits the talks the app has into this week's talk, past talks (newest first) and talks ready early (soonest first).
 * This week's talk is the newest one already sent; before the first Sunday, it's the first talk that's ready early.
 */
/** "Ready early" only until the newsletter's send time. A copy saved on Friday must not still say early on Monday. */
export function isEarly(t: Talk, now = new Date()) {
  return Boolean(t.early) && (!t.send_at || new Date(t.send_at) > now);
}

export function arrangeTalks(talks: Talk[], now = new Date()) {
  const byDate = (a: Talk, b: Talk) => a.issue_date.localeCompare(b.issue_date);
  const released = talks.filter((t) => !isEarly(t, now)).sort((a, b) => byDate(b, a));
  const early = talks.filter((t) => isEarly(t, now)).sort(byDate);
  const current = released[0] ?? early[0] ?? null;
  return {
    current,
    past: released.filter((t) => t !== current),
    early: early.filter((t) => t !== current),
  };
}

/**
 * Make the phone copy match the server list, so a pulled talk does not come back offline.
 * No transaction: the app shares one connection, and the feed loader's transaction running
 * at the same time would collide with ours and roll both back.
 */
async function cache(talks: Talk[]) {
  // Check the whole reply before touching the copy, so a bad reply leaves it as it was.
  if (!Array.isArray(talks) || !talks.every((t) => Number.isInteger(t?.issue))) {
    throw new Error('talks reply is malformed');
  }
  const db = await getDb();
  for (const t of talks) {
    await db.runAsync('INSERT OR REPLACE INTO talks_cache (issue, json) VALUES (?, ?)', t.issue, JSON.stringify(t));
  }
  // Add first, then drop the rest: the copy is never empty in between. An empty list clears it.
  const ids = JSON.stringify(talks.map((t) => t.issue));
  await db.runAsync('DELETE FROM talks_cache WHERE issue NOT IN (SELECT value FROM json_each(?))', ids);
}

async function readCache(): Promise<Talk[]> {
  const db = await getDb();
  const rows = await db.getAllAsync<{ json: string }>('SELECT json FROM talks_cache ORDER BY issue DESC');
  return rows.map((r) => JSON.parse(r.json) as Talk);
}

const notConfigured = () => Promise.reject(new Error('API not configured'));

async function fetchTalks(): Promise<Talk[]> {
  if (!isConfigured()) return notConfigured();
  const { talks } = await api<{ talks: Talk[] }>('/talks/');
  await cache(talks); // cache() drops the talks the server no longer returns, so a pulled talk leaves the copy
  return talks;
}

export type TalkList = { talks: Talk[]; offline: boolean };

/**
 * Talks the app shows, newest first. The saved copy comes back right away; a background refresh calls `onFresh` with
 * the server's list, or `onFresh` with `offline: true` when there's no signal.
 */
export async function listTalks(onFresh?: (list: TalkList) => void): Promise<TalkList> {
  const { value, fromSaved } = await savedFirst<Talk[]>(
    'talks',
    async () => {
      const saved = await readCache();
      return saved.length ? saved : null;
    },
    fetchTalks,
    {
      onFresh: (talks) => onFresh?.({ talks, offline: false }),
      onOffline: () => {
        noteStaleContent(); // a content change seen now is retried on the next check
        return readCache().then((talks) => onFresh?.({ talks, offline: true }));
      },
    },
  );
  return { talks: value ?? [], offline: value === null && !fromSaved && isConfigured() };
}

export async function getTalk(issue: number, onFresh?: (talk: Talk | null) => void): Promise<Talk | null> {
  const find = (list: Talk[]) => list.find((t) => t.issue === issue) ?? null;
  const { talks } = await listTalks(onFresh && ((r) => !r.offline && onFresh(find(r.talks))));
  return find(talks);
}
