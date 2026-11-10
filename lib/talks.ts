import { api, isConfigured } from './config';
import { getDb } from './db';

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
export function arrangeTalks(talks: Talk[]) {
  const byDate = (a: Talk, b: Talk) => a.issue_date.localeCompare(b.issue_date);
  const released = talks.filter((t) => !t.early).sort((a, b) => byDate(b, a));
  const early = talks.filter((t) => t.early).sort(byDate);
  const current = released[0] ?? early[0] ?? null;
  return {
    current,
    past: released.filter((t) => t !== current),
    early: early.filter((t) => t !== current),
  };
}

async function cache(talks: Talk[]) {
  const db = await getDb();
  for (const t of talks) {
    await db.runAsync('INSERT OR REPLACE INTO talks_cache (issue, json) VALUES (?, ?)', t.issue, JSON.stringify(t));
  }
}

async function readCache(): Promise<Talk[]> {
  const db = await getDb();
  const rows = await db.getAllAsync<{ json: string }>('SELECT json FROM talks_cache ORDER BY issue DESC');
  return rows.map((r) => JSON.parse(r.json) as Talk);
}

/**
 * Released talks, newest first. The Django API only returns talks whose Sunday send time
 * has passed, so the app never shows next week's talk early.
 * Falls back to the on-device copy when there is no signal.
 */
export async function listTalks(): Promise<{ talks: Talk[]; offline: boolean }> {
  if (isConfigured()) {
    try {
      const { talks } = await api<{ talks: Talk[] }>('/talks/');
      await cache(talks);
      return { talks, offline: false };
    } catch {
      // no signal or server unreachable: fall through to the copy on this phone
    }
  }
  return { talks: await readCache(), offline: true };
}

export async function getTalk(issue: number): Promise<Talk | null> {
  const { talks } = await listTalks();
  return talks.find((t) => t.issue === issue) ?? null;
}
