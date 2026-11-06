import { isConfigured } from './config';
import { getDb } from './db';
import { supabase } from './supabase';

export type Talk = {
  issue: number;
  issue_date: string;
  month_theme: string;
  title: string;
  story_title: string;
  crew_question: string;
  body_md: string | null;
  hero_url: string | null;
  pdf_url: string | null;
};

const COLUMNS = 'issue, issue_date, month_theme, title, story_title, crew_question, body_md, hero_url, pdf_url';

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
 * Released talks, newest first. Row-level security in Supabase only returns talks whose
 * Sunday send time has passed, so the app never shows next week's talk early.
 * Falls back to the on-device copy when there is no signal.
 */
export async function listTalks(): Promise<{ talks: Talk[]; offline: boolean }> {
  if (isConfigured()) {
    const { data, error } = await supabase
      .from('toolbox_talks')
      .select(COLUMNS)
      .order('issue', { ascending: false });
    if (!error && data) {
      await cache(data as Talk[]);
      return { talks: data as Talk[], offline: false };
    }
  }
  return { talks: await readCache(), offline: true };
}

export async function getTalk(issue: number): Promise<Talk | null> {
  const { talks } = await listTalks();
  return talks.find((t) => t.issue === issue) ?? null;
}
