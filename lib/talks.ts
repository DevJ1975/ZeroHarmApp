import { api, isConfigured } from './config';
import { getDb } from './db';
import { noteStaleContent } from './live';

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
  /** Approved Spanish version, or null when there isn't one yet. */
  es?: TalkText | null;
};

/** The number printed on the issue (#01), falling back to the app's id. */
export const issueNumber = (t: Talk) => t.number ?? t.issue;

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
      noteStaleContent(); // a content change seen now is retried on the next check
      // no signal or server unreachable: fall through to the copy on this phone
    }
  }
  return { talks: await readCache(), offline: true };
}

export async function getTalk(issue: number): Promise<Talk | null> {
  const { talks } = await listTalks();
  return talks.find((t) => t.issue === issue) ?? null;
}
