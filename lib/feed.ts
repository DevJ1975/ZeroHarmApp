import { api, isConfigured } from './config';
import { getDb } from './db';
import { savedFirst } from './saved-first';

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

const ordered = (items: FeedItem[]) =>
  [...items].sort((a, b) => Number(b.featured) - Number(a.featured) || b.published_at.localeCompare(a.published_at));

/**
 * Regulatory alerts and free resources published from GoHighLevel. The saved copy comes back right away; `onFresh`
 * gets the server's list when the background refresh lands.
 */
export async function listFeed(kinds: FeedKind[], onFresh?: (items: FeedItem[]) => void): Promise<FeedItem[]> {
  const marks = kinds.map(() => '?').join(',');
  const { value } = await savedFirst<FeedItem[]>(
    `feed-${[...kinds].sort().join(',')}`,
    async () => {
      const db = await getDb();
      const rows = await db.getAllAsync<{ json: string }>(`SELECT json FROM feed_cache WHERE kind IN (${marks})`, ...kinds);
      return rows.length ? ordered(rows.map((r) => JSON.parse(r.json) as FeedItem)) : null;
    },
    async () => {
      if (!isConfigured()) throw new Error('API not configured');
      const { items } = await api<{ items: FeedItem[] }>(`/feed/?kind=${kinds.join(',')}`);
      const db = await getDb();
      await db.withTransactionAsync(async () => {
        await db.runAsync(`DELETE FROM feed_cache WHERE kind IN (${marks})`, ...kinds);
        for (const i of items) {
          await db.runAsync('INSERT OR REPLACE INTO feed_cache (id, kind, json) VALUES (?, ?, ?)', i.id, i.kind, JSON.stringify(i));
        }
      });
      return ordered(items);
    },
    { onFresh },
  );
  return value ?? [];
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
