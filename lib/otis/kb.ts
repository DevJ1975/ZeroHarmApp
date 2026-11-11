import Storage from 'expo-sqlite/kv-store';

import { api, apiFetch, isConfigured } from '../config';
import { noteStaleContent } from '../live';
import { kbVersionKey } from './manifest';

/** One searchable passage: a KB entry or one section of a released talk. */
export type KbItem = { id: string; title: string; text: string; source: string; lang: 'en' | 'es'; issue: number | null; episode?: number; tags?: string };

const KEY = 'otis_kb';
let memo: KbItem[] | null = null;

async function saved(): Promise<KbItem[] | null> {
  if (memo) return memo;
  const raw = await Storage.getItem(KEY);
  memo = raw ? (JSON.parse(raw) as KbItem[]) : null;
  return memo;
}

async function keep(items: KbItem[], version: string) {
  memo = items; // hold them in memory first: a phone that can't save still gets this session's answers
  try {
    await Storage.setItem(KEY, JSON.stringify(items));
    await Storage.setItem(kbVersionKey, version);
  } catch {
    // couldn't save to the phone (disk full?): still use what we just fetched
  }
}

/**
 * Keeps the knowledge base on the phone so OTIS works on the dock with no signal. With signal, asks /api/v2/otis/kb
 * with the version already saved; the server answers 304 when nothing changed, so the phone downloads only real updates.
 */
export async function loadKb(): Promise<KbItem[]> {
  const copy = await saved();
  if (isConfigured()) {
    try {
      const version = copy ? await Storage.getItem(kbVersionKey) : null;
      const res = await apiFetch('/v2/otis/kb', { headers: version ? { 'If-None-Match': `"${version}"` } : {} });
      if (res.status === 304 && copy) return copy;
      if (res.ok) {
        const body = (await res.json()) as { version: string; items: KbItem[] };
        await keep(body.items, body.version);
        return body.items;
      }
      // Older server without v2: the original endpoint.
      const { items, version: v1 } = await api<{ items: KbItem[]; version: string }>('/otis/kb/');
      await keep(items, `v1-${v1}`);
      return items;
    } catch {
      noteStaleContent(); // a content change seen now is retried on the next check
      // no signal: use the saved copy
    }
  }
  return copy ?? [];
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
    .replace(/(^|\D)\.|\.(?!\d)/g, '$1 ') // a period only counts inside a number like 1910.147
    .split(/[^a-z0-9.]+/)
    .filter((w) => w.length > 1 && !STOP.has(w));

/** True for a passage of official OSHA regulation text (the server's regulation library), not a plain-language entry. */
export const isRegulation = (d: KbItem) => d.id.startsWith('r');

type Prepared = { docs: KbItem[]; toks: string[][]; avg: number; df: Map<string, number> };
const prepared = new WeakMap<KbItem[], Map<string, Prepared>>();

/** Tokenizes the knowledge base once per language, not on every question: it holds regulation text now, so it's bigger. */
function prepare(kb: KbItem[], lang: 'en' | 'es'): Prepared {
  let byLang = prepared.get(kb);
  if (!byLang) prepared.set(kb, (byLang = new Map()));
  const hit = byLang.get(lang);
  if (hit) return hit;
  const docs = kb.filter((d) => d.lang === lang || d.lang === 'en');
  const toks = docs.map((d) => words(`${d.title} ${d.title} ${d.tags ?? ''} ${d.text}`));
  const avg = toks.reduce((n, t) => n + t.length, 0) / Math.max(1, toks.length);
  const df = new Map<string, number>();
  for (const t of toks) for (const w of new Set(t)) df.set(w, (df.get(w) ?? 0) + 1);
  const p = { docs, toks, avg, df };
  byLang.set(lang, p);
  return p;
}

/**
 * BM25 keyword ranking over the passages. Small enough to run instantly on the phone with no extra model.
 * Plain-language entries and talks rank ahead of raw regulation text on a near tie, so OTIS explains first and
 * quotes the rule as backup. At most two regulation passages come back, so they never crowd out the explanation.
 */
export function search(kb: KbItem[], query: string, lang: 'en' | 'es', k = 4): KbItem[] {
  const q = [...new Set(words(query))];
  if (!q.length) return [];
  const { docs, toks, avg, df } = prepare(kb, lang);
  const scored = docs.map((d, i) => {
    const t = toks[i];
    let score = 0;
    for (const w of q) {
      const prefix = w.length > 4 && !/\d/.test(w); // numbers and standards (1910.147) must match exactly
      const tf = t.filter((x) => x === w || (prefix && x.startsWith(w.slice(0, -1)))).length;
      if (!tf) continue;
      const idf = Math.log(1 + (docs.length - (df.get(w) ?? 0) + 0.5) / ((df.get(w) ?? 0) + 0.5));
      score += (idf * tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (t.length / avg)));
    }
    if (d.lang === lang) score *= 1.15; // prefer the reader's language when both exist
    if (isRegulation(d)) score *= 0.85; // explain in plain words first, quote the rule second
    return { d, score };
  });
  let regs = 0;
  return scored
    .filter((s) => s.score > 0.5)
    .sort((a, b) => b.score - a.score)
    .filter((s) => !isRegulation(s.d) || ++regs <= 2)
    .slice(0, k)
    .map((s) => s.d);
}
