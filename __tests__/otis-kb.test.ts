/* eslint-disable @typescript-eslint/no-require-imports -- require() inside jest.isolateModules gives each test a fresh module instance */
import type { KbItem } from '../lib/otis/kb';

// ---- boundaries: backend config/api and on-phone kv-store ----
const mockStore = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: jest.fn(async (k: string) => (mockStore.has(k) ? mockStore.get(k)! : null)),
    setItem: jest.fn(async (k: string, v: string) => {
      mockStore.set(k, v);
    }),
  },
}));

// lib/live keeps a counter of reloads that fell back to the phone copy, so the content version is
// retried later. It is module state, so it is mocked to observe the contract.
const mockNoteStale = jest.fn();
jest.mock('../lib/live', () => ({ noteStaleContent: () => mockNoteStale() }));

const mockConfig = { configured: true, api: jest.fn(), apiFetch: jest.fn() };
jest.mock('../lib/config', () => ({
  isConfigured: () => mockConfig.configured,
  api: (...args: unknown[]) => mockConfig.api(...args),
  apiFetch: (...args: unknown[]) => mockConfig.apiFetch(...args),
}));

// kb.ts reads the saved-KB-version key from lib/otis/manifest, which pulls in the on-device model
// library. That library has no native side under Jest, so it is stubbed here instead of the
// manifest module: the test then uses the real key, and a rename there cannot leave it passing
// against a key the app no longer writes.
jest.mock('react-native-executorch', () => ({ getRegisteredBackends: () => [], models: { llm: {} } }));
const versionKey: string = jest.requireActual('../lib/otis/manifest').kbVersionKey;

let item = 0;
const doc = (p: Partial<KbItem>): KbItem => ({
  id: p.id ?? `d${++item}`,
  title: p.title ?? 'Untitled',
  text: p.text ?? '',
  source: p.source ?? 'test',
  lang: p.lang ?? 'en',
  issue: p.issue ?? null,
  tags: p.tags,
});

// Filler passages so idf behaves like a real KB (a term in every passage carries no signal).
const filler = [
  doc({ id: 'f1', title: 'Heat stress', text: 'Drink water every fifteen minutes and rest in shade during hot shifts.' }),
  doc({ id: 'f2', title: 'Housekeeping', text: 'Keep walkways clear of cords, pallets and spilled oil.' }),
  doc({ id: 'f3', title: 'Hearing protection', text: 'Wear earplugs above eighty five decibels near compressors.' }),
  doc({ id: 'f4', title: 'Eye wash', text: 'Flush eyes for fifteen minutes at the nearest station.' }),
];

const ids = (r: KbItem[]) => r.map((d) => d.id);

describe('search', () => {
  let search: typeof import('../lib/otis/kb').search;
  beforeAll(() => {
    search = require('../lib/otis/kb').search;
  });

  test('empty or stop-word-only query returns nothing', () => {
    const kb = [...filler, doc({ id: 'x', title: 'What is the rule', text: 'what is the rule' })];
    expect(search(kb, '', 'en')).toEqual([]);
    expect(search(kb, '   ?!  ', 'en')).toEqual([]);
    expect(search(kb, 'what is the', 'en')).toEqual([]);
    expect(search(kb, 'qué es el que', 'es')).toEqual([]);
  });

  test('finds the passage that matches and ignores ones that do not', () => {
    const kb = [...filler, doc({ id: 'ladder', title: 'Ladder safety', text: 'Keep three points of contact on a ladder.' })];
    expect(ids(search(kb, 'How do I climb a ladder?', 'en'))).toEqual(['ladder']);
    expect(search(kb, 'forklift', 'en')).toEqual([]);
  });

  test('title match ranks above a passing mention in the body', () => {
    const kb = [
      ...filler,
      doc({ id: 'mention', title: 'Roof work', text: 'Tie off before you step off the ladder onto the roof edge today.' }),
      doc({ id: 'titled', title: 'Ladder inspection', text: 'Check rungs, feet and rails before each use.' }),
    ];
    expect(ids(search(kb, 'ladder', 'en'))).toEqual(['titled', 'mention']);
  });

  test('a rarer query term outweighs a common one', () => {
    // "a" and "b" are the same length and each hold one query word once, so only idf can separate
    // them. "b" is listed first so a tie (e.g. idf ignored) would put it on top.
    const kb = [
      doc({ id: 'b', title: 'Gate rules', text: 'operator signs in' }),
      doc({ id: 'a', title: 'Lift plan', text: 'crane signs in' }),
      doc({ id: 'c', title: 'Forklift', text: 'operator drives slowly' }),
      doc({ id: 'd', title: 'Shift start', text: 'operator reads board' }),
    ];
    expect(ids(search(kb, 'crane operator', 'en'))[0]).toBe('a');
  });

  test('tags are searchable', () => {
    const kb = [...filler, doc({ id: 'loto', title: 'Energy control', tags: 'lockout tagout', text: 'Isolate every source.' })];
    expect(ids(search(kb, 'tagout', 'en'))).toEqual(['loto']);
  });

  test('accents are stripped on both sides (é -> e)', () => {
    const kb = [
      ...filler,
      doc({ id: 'es', lang: 'es', title: 'Protección auditiva', text: 'Use tapones cerca del compresor.' }),
    ];
    expect(ids(search(kb, 'proteccion auditiva', 'es'))).toEqual(['es']);
    expect(ids(search(kb, 'PROTECCIÓN', 'es'))).toEqual(['es']);
  });

  test('word-ending variants match by prefix for longer words (harness -> harnesses)', () => {
    const kb = [...filler, doc({ id: 'fall', title: 'Fall arrest', text: 'Inspect harnesses and lanyards daily.' })];
    expect(ids(search(kb, 'harness', 'en'))).toEqual(['fall']);
  });

  test('English reader never gets Spanish passages', () => {
    const kb = [
      ...filler,
      doc({ id: 'es', lang: 'es', title: 'Escaleras LOTO', text: 'LOTO escaleras' }),
      doc({ id: 'en', lang: 'en', title: 'Ladders LOTO', text: 'LOTO ladders' }),
    ];
    expect(ids(search(kb, 'LOTO', 'en'))).toEqual(['en']);
  });

  test('Spanish reader gets the Spanish passage first, English as fallback', () => {
    const kb = [
      ...filler,
      doc({ id: 'en', lang: 'en', title: 'LOTO procedure', text: 'LOTO steps for the mixer.' }),
      doc({ id: 'es', lang: 'es', title: 'LOTO procedimiento', text: 'LOTO pasos para la mezcladora.' }),
    ];
    expect(ids(search(kb, 'LOTO', 'es'))).toEqual(['es', 'en']);
    // Only English exists for this topic: fall back to it.
    const enOnly = [...filler, doc({ id: 'en2', lang: 'en', title: 'Silica dust', text: 'Use wet cutting for silica.' })];
    expect(ids(search(enOnly, 'silica', 'es'))).toEqual(['en2']);
  });

  // Merged architecture tokenizes each KB once and caches it. The cache is per language, so the
  // same array asked in both languages must not serve the first language's passages twice.
  test('the same KB asked in English then Spanish answers for each language', () => {
    const kb = [
      ...filler,
      doc({ id: 'en', lang: 'en', title: 'LOTO procedure', text: 'LOTO steps for the mixer.' }),
      doc({ id: 'es', lang: 'es', title: 'LOTO procedimiento', text: 'LOTO pasos para la mezcladora.' }),
    ];
    expect(ids(search(kb, 'LOTO', 'en'))).toEqual(['en']);
    expect(ids(search(kb, 'LOTO', 'es'))).toEqual(['es', 'en']);
  });

  test('returns at most k results, default 4, best first', () => {
    const kb = [
      ...filler,
      ...filler.map((f) => doc({ ...f, id: `${f.id}b` })),
      ...[1, 2, 3, 4, 5, 6].map((n) => doc({ id: `s${n}`, title: `Scaffold ${n}`, text: 'scaffold '.repeat(n) })),
    ];
    // More mentions of the word = stronger match, so s6 is best and s1 weakest.
    expect(ids(search(kb, 'scaffold', 'en'))).toEqual(['s6', 's5', 's4', 's3']);
    expect(ids(search(kb, 'scaffold', 'en', 2))).toEqual(['s6', 's5']);
    expect(ids(search(kb, 'scaffold', 'en', 10))).toEqual(['s6', 's5', 's4', 's3', 's2', 's1']);
  });

  // Merged architecture: ids starting with "r" are raw regulation text, so OSHA passages are
  // de-ranked on a near tie and capped, letting the plain-language answer come first.
  test('a plain-language entry outranks the regulation passage on a tie', () => {
    const kb = [
      ...filler,
      doc({ id: 'r-loto', title: 'Lockout rule', text: 'energy control procedures' }),
      doc({ id: 'plain', title: 'Lockout rule', text: 'energy control procedures' }),
    ];
    // Identical passages, regulation listed first, so a tie would leave it on top.
    expect(ids(search(kb, 'lockout', 'en'))).toEqual(['plain', 'r-loto']);
  });

  test('at most two regulation passages come back, so they never crowd out the explanation', () => {
    const kb = [
      ...filler,
      ...[1, 2, 3, 4].map((n) => doc({ id: `r${n}`, title: `Scaffold rule ${n}`, text: 'scaffold '.repeat(6) })),
      doc({ id: 'plain', title: 'Scaffold basics', text: 'scaffold scaffold scaffold' }),
    ];
    const out = ids(search(kb, 'scaffold', 'en', 10));
    expect(out.filter((id) => id.startsWith('r'))).toHaveLength(2);
    expect(out).toContain('plain');
  });

  test('a term found in every passage is below the score cutoff', () => {
    const kb = filler.map((f) => doc({ ...f, text: `${f.text} safety` }));
    expect(search(kb, 'safety', 'en')).toEqual([]);
  });

  // Fixed: the tokenizer drops periods that are not inside a number, so "lock." matches "lock".
  test('a sentence-final short word still matches without its period', () => {
    const kb = [...filler, doc({ id: 'loto', title: 'Energy isolation', text: 'Before you reach in, apply your lock.' })];
    expect(ids(search(kb, 'Where does my lock go?', 'en'))).toEqual(['loto']);
  });

  // Fixed: tokens with a digit skip the prefix rule, so "1910.147" matches only itself.
  test('"1910.147" does not match 1910.146 / 1910.141 passages', () => {
    const kb = [
      ...filler,
      doc({ id: 'cs', title: 'Confined spaces', text: 'Permit spaces are covered by 1910.146 requirements' }),
      doc({ id: 'san', title: 'Sanitation', text: 'Toilets and washing facilities per 1910.141 rules' }),
    ];
    expect(search(kb, '1910.147', 'en')).toEqual([]);
  });

  test('exact standard number still finds its own passage', () => {
    const kb = [...filler, doc({ id: 'loto', title: 'Lockout standard', text: 'The rule is 1910.147 for energy control' })];
    expect(ids(search(kb, '1910.147', 'en'))).toEqual(['loto']);
  });

  test('a standard number at the end of a sentence still matches', () => {
    const kb = [...filler, doc({ id: 'loto', title: 'Lockout standard', text: 'Energy control is covered by 1910.147.' })];
    expect(ids(search(kb, 'What does 1910.147. say?', 'en'))).toEqual(['loto']);
  });

  // Fixed: a period is only kept between digits, so a missing space after "lock." no longer hides the word.
  test('a period with no space after it does not glue two words together', () => {
    const kb = [...filler, doc({ id: 'loto', title: 'Energy isolation', text: 'Apply your lock.Then test the machine' })];
    expect(ids(search(kb, 'lock', 'en'))).toEqual(['loto']);
  });

  // The period rule has two halves: this covers the other one, a period that sits before a digit.
  test('a word that runs straight into a standard number is split from it', () => {
    const kb = [...filler, doc({ id: 'loto', title: 'Energy isolation', text: 'Apply your lock.1910.147 covers the rest' })];
    expect(ids(search(kb, 'lock', 'en'))).toEqual(['loto']);
    expect(ids(search(kb, '1910.147', 'en'))).toEqual(['loto']);
  });

  test('word queries still use the prefix rule after the digit check', () => {
    const kb = [...filler, doc({ id: 'h', title: 'Fall gear', text: 'Inspect harnesses daily' })];
    expect(ids(search(kb, 'harness', 'en'))).toEqual(['h']);
  });
});

describe('loadKb', () => {
  const remote = [doc({ id: 'k1', title: 'Remote passage', text: 'from the server' })];

  // What apiFetch hands back for /v2/otis/kb: only the bits loadKb reads.
  const sent = (items: KbItem[], version = 'v9') => ({ ok: true, status: 200, json: async () => ({ version, items }) });
  const unchanged = () => ({ ok: false, status: 304 });
  const noV2 = () => ({ ok: false, status: 404 }); // older server: loadKb retries the v1 endpoint

  let loadKb: typeof import('../lib/otis/kb').loadKb;
  beforeEach(() => {
    mockStore.clear();
    mockConfig.configured = true;
    mockConfig.api.mockReset();
    mockConfig.apiFetch.mockReset();
    mockNoteStale.mockReset();
    jest.resetModules(); // fresh in-memory cache per test
    loadKb = require('../lib/otis/kb').loadKb;
  });

  test('network success returns items and saves a copy and its version on the phone', async () => {
    mockConfig.apiFetch.mockResolvedValue(sent(remote));
    await expect(loadKb()).resolves.toEqual(remote);
    expect(JSON.parse(mockStore.get('otis_kb')!)).toEqual(remote);
    expect(mockStore.get(versionKey)).toBe('v9');
  });

  test('with a saved copy, the saved version goes out so the server can answer 304', async () => {
    mockStore.set('otis_kb', JSON.stringify(remote));
    mockStore.set(versionKey, 'v9');
    mockConfig.apiFetch.mockResolvedValue(unchanged());
    await expect(loadKb()).resolves.toEqual(remote);
    expect(mockConfig.apiFetch).toHaveBeenCalledWith('/v2/otis/kb', { headers: { 'If-None-Match': '"v9"' } });
  });

  test('no saved copy: no version header, and nothing is sent until there is one', async () => {
    mockConfig.apiFetch.mockResolvedValue(sent(remote));
    await loadKb();
    expect(mockConfig.apiFetch).toHaveBeenCalledWith('/v2/otis/kb', { headers: {} });
  });

  test('older server without v2 falls back to the v1 endpoint', async () => {
    mockConfig.apiFetch.mockResolvedValue(noV2());
    mockConfig.api.mockResolvedValue({ items: remote, version: '3' });
    await expect(loadKb()).resolves.toEqual(remote);
    expect(mockConfig.api).toHaveBeenCalledWith('/otis/kb/');
    expect(mockStore.get(versionKey)).toBe('v1-3');
  });

  test('network failure falls back to the saved copy', async () => {
    const saved = [doc({ id: 's1', title: 'Saved', text: 'offline copy' })];
    mockStore.set('otis_kb', JSON.stringify(saved));
    mockConfig.apiFetch.mockRejectedValue(new Error('offline'));
    await expect(loadKb()).resolves.toEqual(saved);
    // The reload served old content, so the content-version check must try again later.
    expect(mockNoteStale).toHaveBeenCalledTimes(1);
  });

  test('a successful fetch does not flag the content as stale', async () => {
    mockConfig.apiFetch.mockResolvedValue(sent(remote));
    await loadKb();
    expect(mockNoteStale).not.toHaveBeenCalled();
  });

  test('network failure with no saved copy gives an empty KB', async () => {
    mockConfig.apiFetch.mockRejectedValue(new Error('offline'));
    await expect(loadKb()).resolves.toEqual([]);
  });

  test('not configured: reads the saved copy without calling the backend', async () => {
    mockConfig.configured = false;
    const saved = [doc({ id: 's2', title: 'Saved', text: 'copy' })];
    mockStore.set('otis_kb', JSON.stringify(saved));
    await expect(loadKb()).resolves.toEqual(saved);
    expect(mockConfig.apiFetch).not.toHaveBeenCalled();
    expect(mockConfig.api).not.toHaveBeenCalled();
  });

  test('after one good fetch, a later outage serves the in-memory copy', async () => {
    mockConfig.apiFetch.mockResolvedValueOnce(sent(remote)).mockRejectedValueOnce(new Error('offline'));
    await loadKb();
    mockStore.clear(); // even if storage is gone, the cached list survives
    await expect(loadKb()).resolves.toEqual(remote);
  });

  test('a fresh fetch replaces the previous copy', async () => {
    const newer = [doc({ id: 'k2', title: 'Newer', text: 'v2' })];
    mockConfig.apiFetch.mockResolvedValueOnce(sent(remote)).mockResolvedValueOnce(sent(newer, 'v10'));
    await loadKb();
    await expect(loadKb()).resolves.toEqual(newer);
    expect(JSON.parse(mockStore.get('otis_kb')!)).toEqual(newer);
  });

  // Fixed: the save to the phone has its own try, so a failed write still returns the fetched items.
  test('a failed save to the phone still returns the items just fetched', async () => {
    const Storage = require('expo-sqlite/kv-store').default;
    Storage.setItem.mockRejectedValueOnce(new Error('disk full'));
    mockConfig.apiFetch.mockResolvedValue(sent(remote));
    await expect(loadKb()).resolves.toEqual(remote);
  });

  test('a failed save does not flag stale content and the fetched copy survives a later outage', async () => {
    const Storage = require('expo-sqlite/kv-store').default;
    Storage.setItem.mockRejectedValueOnce(new Error('disk full'));
    mockConfig.apiFetch.mockResolvedValueOnce(sent(remote)).mockRejectedValueOnce(new Error('offline'));
    await loadKb();
    expect(mockNoteStale).not.toHaveBeenCalled();
    await expect(loadKb()).resolves.toEqual(remote);
  });
});
