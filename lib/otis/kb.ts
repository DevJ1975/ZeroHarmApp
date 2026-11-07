import Storage from 'expo-sqlite/kv-store';

import { api, isConfigured } from '../config';

/** One searchable passage: a KB entry or one section of a released talk. */
export type KbItem = { id: string; title: string; text: string; source: string; lang: 'en' | 'es'; issue: number | null; tags?: string };

const KEY = 'otis_kb';
let memo: KbItem[] | null = null;

/** Fetches the knowledge base when there's signal and keeps a copy on the phone, so OTIS works on the dock with none. */
export async function loadKb(): Promise<KbItem[]> {
  if (isConfigured()) {
    try {
      const { items } = await api<{ items: KbItem[] }>('/otis/kb/');
      await Storage.setItem(KEY, JSON.stringify(items));
      memo = items;
      return items;
    } catch {
      // no signal: use the saved copy
    }
  }
  if (memo) return memo;
  const raw = await Storage.getItem(KEY);
  memo = raw ? (JSON.parse(raw) as KbItem[]) : [];
  return memo;
}

const STOP = new Set(
  ('a an and are as at be but by can do does for from how i if in is it its me my of on or should so that the their them there they this ' +
    'to was we what when where which who why will with you your el la los las un una y o de del que en es por para con se su sus lo al como').split(' '),
);

const words = (s: string) =>
  s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .split(/[^a-z0-9.]+/)
    .filter((w) => w.length > 1 && !STOP.has(w));

/** BM25 keyword ranking over the passages. Small enough to run instantly on the phone with no extra model. */
export function search(kb: KbItem[], query: string, lang: 'en' | 'es', k = 4): KbItem[] {
  const q = [...new Set(words(query))];
  if (!q.length) return [];
  const docs = kb.filter((d) => d.lang === lang || d.lang === 'en');
  const toks = docs.map((d) => words(`${d.title} ${d.title} ${d.tags ?? ''} ${d.text}`));
  const avg = toks.reduce((n, t) => n + t.length, 0) / Math.max(1, toks.length);
  const df = new Map<string, number>();
  for (const t of toks) for (const w of new Set(t)) df.set(w, (df.get(w) ?? 0) + 1);
  const scored = docs.map((d, i) => {
    const t = toks[i];
    let score = 0;
    for (const w of q) {
      const tf = t.filter((x) => x === w || (w.length > 4 && x.startsWith(w.slice(0, -1)))).length;
      if (!tf) continue;
      const idf = Math.log(1 + (docs.length - (df.get(w) ?? 0) + 0.5) / ((df.get(w) ?? 0) + 0.5));
      score += (idf * tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (t.length / avg)));
    }
    if (d.lang === lang) score *= 1.15; // prefer the reader's language when both exist
    return { d, score };
  });
  return scored
    .filter((s) => s.score > 0.5)
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((s) => s.d);
}
