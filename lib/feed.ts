import { api, isConfigured } from './config';
import { getDb } from './db';

export type FeedKind = 'alert' | 'course' | 'tool' | 'video' | 'newsletter';

export type FeedItem = {
  id: number;
  kind: FeedKind;
  title: string;
  summary: string;
  body_md: string | null;
  link_url: string | null;
  image_url: string | null;
  jurisdiction: string | null;
  effective_date: string | null;
  published_at: string;
  featured: boolean;
};

export const RESOURCE_KINDS: FeedKind[] = ['course', 'tool', 'video', 'newsletter'];

/** Regulatory alerts and free resources that Jamil publishes from GoHighLevel. Cached for use with no signal. */
export async function listFeed(kinds: FeedKind[]): Promise<FeedItem[]> {
  const db = await getDb();
  if (isConfigured()) {
    try {
      const { items } = await api<{ items: FeedItem[] }>(`/feed/?kind=${kinds.join(',')}`);
      await db.withTransactionAsync(async () => {
        await db.runAsync(`DELETE FROM feed_cache WHERE kind IN (${kinds.map(() => '?').join(',')})`, ...kinds);
        for (const i of items) {
          await db.runAsync('INSERT OR REPLACE INTO feed_cache (id, kind, json) VALUES (?, ?, ?)', i.id, i.kind, JSON.stringify(i));
        }
      });
      return items;
    } catch {
      // no signal: fall back to the copy on this phone
    }
  }
  const rows = await db.getAllAsync<{ json: string }>(
    `SELECT json FROM feed_cache WHERE kind IN (${kinds.map(() => '?').join(',')})`,
    ...kinds,
  );
  return rows
    .map((r) => JSON.parse(r.json) as FeedItem)
    .sort((a, b) => Number(b.featured) - Number(a.featured) || b.published_at.localeCompare(a.published_at));
}

export async function getFeedItem(id: number): Promise<FeedItem | null> {
  const all = await listFeed(['alert', ...RESOURCE_KINDS]);
  return all.find((i) => i.id === id) ?? null;
}

export const KIND_LABEL: Record<FeedKind, string> = {
  alert: 'Regulatory alert',
  course: 'Free course',
  tool: 'Free tool',
  video: 'Video',
  newsletter: 'Newsletter',
};
