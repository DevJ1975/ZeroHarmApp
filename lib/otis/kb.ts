import Storage from 'expo-sqlite/kv-store';

import { api, apiFetch, isConfigured } from '../config';
import { noteStaleContent } from '../live';
import { kbVersionKey } from './manifest';

/**
 * One searchable passage: a KB entry or one section of a released talk. `kind: 'support'` marks a tech-support entry
 * about the app itself. Those are shown word for word and never reach the safety answers; everything else has no kind.
 */
export type KbItem = { id: string; title: string; text: string; source: string; lang: 'en' | 'es'; issue: number | null; episode?: number; tags?: string; kind?: 'support' };

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

/** True for a tech-support entry about the app (how to fix a stuck download, say). Never mixed into safety answers. */
export const isSupport = (d: KbItem) => d.kind === 'support';

type Scope = 'safety' | 'support';

/**
 * Words that say "something is wrong with the app" but not what, and words that say nothing about which entry fits
 * (the phone's name, "has", "open", "play"). They would match every support entry, or the wrong one ("the video is
 * not playing" is not about Google Play), so they are left out.
 */
const VAGUE = new Set(
  ('am im ive app apps application aplicacion zero harm please help ayuda problem problems problema problemas issue issues not no wont won cant cannot ' +
    'doesnt doesn isnt isn didnt didn keep keeps kept just still really por favor ' +
    'iphone ipad android phone phones tablet telefono celular cel has have had our mi play playing plays open opens opening abre abrir ' +
    'get gets got getting going went goes needed out up off tap taps tapped tapping toque toco work works worked working want wants need needs quiero quisiera necesito puedo pude').split(' '),
);

/** "crashing", "crashed" and "crashes" all become "crash", and "close" and "closes" both "clos", so a support entry is found however the person says it. */
function stem(w: string): string {
  if (w.length < 4 || /\d/.test(w)) return w;
  const cut = w.replace(/(ing|ed|es|s|e)$/, '');
  return cut.length >= 3 ? cut : w;
}

type Prepared = {
  docs: KbItem[];
  toks: string[][];
  avg: number;
  df: Map<string, number>;
  /** Support only: the words that pick an entry on their own, and every word of its title and tags. */
  keys: { title: Set<string>; tag: Set<string> }[];
  heads: string[][];
};
const prepared = new WeakMap<KbItem[], Map<string, Prepared>>();

/** The words of a phrase that carry meaning for the support search, stemmed. "won't open" has none; "no llegan" has "llegan". */
const meaningful = (s: string) => words(s).filter((w) => !VAGUE.has(w)).map(stem);

/** Every word, small ones too, stemmed: for telling apart entries that fit a one-word question equally well. */
const allWords = (s: string) =>
  s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .split(/[^a-z0-9]+/)
    .filter(Boolean)
    .map(stem);

/**
 * How much of the question an entry's title and tags say, word for word: the words of the question covered by a
 * title or tag that is wholly in the question. "What is otis" is a tag of "What OTIS is" and covers all three words;
 * the tag "otis" on the other OTIS entries covers one. "Report an issue" is covered twice by "How to report a problem"
 * (tags "report" and "issue") and once by "What a crash report sends" (tag "reportes").
 */
function phraseFit(d: KbItem, query: Set<string>): number {
  const covered = new Set<string>();
  for (const phrase of [d.title, ...(d.tags ?? '').split(',')]) {
    const w = allWords(phrase);
    if (w.length && w.every((x) => query.has(x))) w.forEach((x) => covered.add(x));
  }
  return covered.size;
}

/**
 * The words that can pick a support entry on their own: a word of its title, or a tag that comes down to one word
 * ("notification", "not working" as "working", "no abre" as "abre"). One stray word of the body text never can.
 */
function keysOf(d: KbItem) {
  const tag = new Set<string>();
  for (const t of (d.tags ?? '').split(',')) {
    const left = meaningful(t);
    if (left.length === 1) tag.add(left[0]);
  }
  return { title: new Set(meaningful(d.title)), tag };
}

/**
 * Tokenizes the knowledge base once per language and scope, not on every question: it holds regulation text now, so
 * it's bigger. Safety and support passages are split here, before any scoring, so one kind can never take a place
 * among the other's results or change how its words are weighed.
 */
function prepare(kb: KbItem[], lang: 'en' | 'es', scope: Scope): Prepared {
  let byKey = prepared.get(kb);
  if (!byKey) prepared.set(kb, (byKey = new Map()));
  const key = `${scope}:${lang}`;
  const hit = byKey.get(key);
  if (hit) return hit;
  const docs = kb.filter((d) => isSupport(d) === (scope === 'support') && (d.lang === lang || d.lang === 'en'));
  const toks = docs.map((d) => {
    const t = words(`${d.title} ${d.title} ${d.tags ?? ''} ${d.text}`);
    return scope === 'support' ? t.map(stem) : t;
  });
  const avg = toks.reduce((n, t) => n + t.length, 0) / Math.max(1, toks.length);
  const df = new Map<string, number>();
  for (const t of toks) for (const w of new Set(t)) df.set(w, (df.get(w) ?? 0) + 1);
  const support = scope === 'support';
  const p = { docs, toks, avg, df, keys: support ? docs.map(keysOf) : [], heads: support ? docs.map((d) => words(`${d.title} ${d.tags ?? ''}`).map(stem)) : [] };
  byKey.set(key, p);
  return p;
}

/** The same word, allowing for an ending: "crash" finds "crashing". Numbers and standards (1910.147) must match exactly. */
const same = (x: string, w: string) => x === w || (w.length > 4 && !/\d/.test(w) && x.startsWith(w.slice(0, -1)));

/**
 * BM25 keyword ranking of one scope's passages against the query words. `hits` is how many of the query words the
 * passage holds; `named` how many of those are in a support entry's title or tags (not just its steps).
 */
function rank(kb: KbItem[], q: string[], lang: 'en' | 'es', scope: Scope) {
  const { docs, toks, avg, df, heads } = prepare(kb, lang, scope);
  return docs.map((d, i) => {
    const t = toks[i];
    let score = 0;
    let hits = 0;
    let named = 0;
    for (const w of q) {
      const tf = t.filter((x) => same(x, w)).length;
      if (!tf) continue;
      hits++;
      if (heads[i]?.some((x) => same(x, w))) named++;
      const idf = Math.log(1 + (docs.length - (df.get(w) ?? 0) + 0.5) / ((df.get(w) ?? 0) + 0.5));
      score += (idf * tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (t.length / avg)));
    }
    if (d.lang === lang) score *= 1.15; // prefer the reader's language when both exist
    if (isRegulation(d)) score *= 0.85; // explain in plain words first, quote the rule second
    return { d, score, hits, named };
  });
}

/**
 * BM25 keyword ranking over the safety passages. Small enough to run instantly on the phone with no extra model.
 * Plain-language entries and talks rank ahead of raw regulation text on a near tie, so OTIS explains first and
 * quotes the rule as backup. At most two regulation passages come back, so they never crowd out the explanation.
 * Tech-support entries are never searched here: use searchSupport for those.
 */
export function search(kb: KbItem[], query: string, lang: 'en' | 'es', k = 4): KbItem[] {
  const q = [...new Set(words(query))];
  if (!q.length) return [];
  let regs = 0;
  return rank(kb, q, lang, 'safety')
    .filter((s) => s.score > 0.5)
    .sort((a, b) => b.score - a.score)
    .filter((s) => !isRegulation(s.d) || ++regs <= 2)
    .slice(0, k)
    .map((s) => s.d);
}

/** An entry about OTIS ("OTIS is slow ..."). "The app is slow" names the app, not OTIS, so it is not for that. */
const aboutOtis = (d: KbItem) => /\botis\b/i.test(d.title);
const namesAppNotOtis = (query: string) => /\b(apps?|aplicaci[oó]n)\b/i.test(query) && !/\botis\b/i.test(query);

/**
 * One meaningful word left: the entry that has it as a title word or a whole tag (a tag beats a title word). With two
 * that fit, the one whose title or a tag says the question best, if just one does. The shortest entry never wins.
 */
function byOneWord(docs: KbItem[], keys: Prepared['keys'], w: string, query: string): KbItem[] {
  const has = (set: Set<string>) => [...set].some((x) => same(x, w));
  const byTag = docs.filter((_, i) => has(keys[i].tag));
  const fit = byTag.length ? byTag : docs.filter((_, i) => has(keys[i].title));
  if (fit.length < 2) return fit;
  const asked = new Set(allWords(query));
  const fits = fit.map((d) => phraseFit(d, asked));
  const top = Math.max(...fits);
  return fits.filter((n) => n === top).length === 1 ? [fit[fits.indexOf(top)]] : [];
}

/**
 * Finds tech-support entries only ("the app keeps crashing", "OTIS download is stuck"). Never returns a safety passage.
 * These entries are shown word for word, so a weak match is worse than none. First the words that carry no meaning
 * here are left out ("app", "problem", "not", "iphone", "tap"), and an entry about OTIS is not for a question that
 * names the app and not OTIS. Then:
 *   - one word left: it must be a word of an entry's title or a whole tag, and only one entry may have it that way.
 *   - more words: an entry must hold at least two and at least half of them. With `strict` (the person did not name
 *     the app) more than half of them, and at least two, must be in the entry's title or tags: its steps do not count.
 *   - when no entry holds two, one word may still pick an entry the way a single word would, if that entry also
 *     holds half of the words (more than half with `strict`).
 */
export function searchSupport(kb: KbItem[], query: string, lang: 'en' | 'es', k = 2, strict = false): KbItem[] {
  const q = [...new Set(meaningful(query))];
  if (!q.length) return [];
  const prep = prepare(kb, lang, 'support');
  const otis = !namesAppNotOtis(query);
  const docs = prep.docs.filter((d) => otis || !aboutOtis(d));
  const keys = prep.keys.filter((_, i) => otis || !aboutOtis(prep.docs[i]));
  if (q.length === 1) return byOneWord(docs, keys, q[0], query);
  const ranked = rank(kb, q, lang, 'support')
    .filter((s) => (otis || !aboutOtis(s.d)) && s.score > 0.5)
    .sort((a, b) => b.score - a.score);
  const enough = ranked.filter((s) => (strict ? s.named >= 2 && s.named * 2 > q.length : s.hits >= 2 && s.hits * 2 >= q.length));
  if (enough.length) return enough.slice(0, k).map((s) => s.d);
  // No entry holds two of the words. One word may still pick an entry the way a single word would ("didn't get the
  // monday notification": "notification" is a whole tag of one entry), never the length of the entry.
  const picks = [...new Set(q.flatMap((w) => byOneWord(docs, keys, w, query)))];
  const asked = new Set(allWords(query));
  const fits = picks.map((d) => phraseFit(d, asked));
  const top = Math.max(0, ...fits);
  const pick = picks.length === 1 ? picks[0] : fits.filter((n) => n === top).length === 1 ? picks[fits.indexOf(top)] : null;
  const held = pick ? ranked.find((s) => s.d === pick) : undefined;
  if (!held) return [];
  return (strict ? held.hits >= 2 && held.hits * 2 > q.length : held.hits * 2 >= q.length) ? [pick as KbItem] : [];
}
