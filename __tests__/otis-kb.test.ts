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

const mockConfig = { configured: true, api: jest.fn() };
jest.mock('../lib/config', () => ({
  isConfigured: () => mockConfig.configured,
  api: (...args: unknown[]) => mockConfig.api(...args),
}));

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

  test('a term found in every passage is below the score cutoff', () => {
    const kb = filler.map((f) => doc({ ...f, text: `${f.text} safety` }));
    expect(search(kb, 'safety', 'en')).toEqual([]);
  });

  // BUG: lib/otis/kb.ts:41 splits on /[^a-z0-9.]+/, so the period is kept as part of a word.
  // "...apply your lock." tokenizes to "lock." which never equals "lock", and "lock" is too short
  // (<=4 chars) for the prefix rule at kb.ts:57 to rescue it. Any short word that ends a sentence
  // in a passage (lock, tag, fall, oil, fire...) is invisible to search.
  test.failing('BUG: sentence-final short word keeps its period and never matches', () => {
    const kb = [...filler, doc({ id: 'loto', title: 'Energy isolation', text: 'Before you reach in, apply your lock.' })];
    expect(ids(search(kb, 'Where does my lock go?', 'en'))).toEqual(['loto']);
  });

  // BUG: lib/otis/kb.ts:57 prefix rule matches any token starting with w.slice(0, -1). For the
  // OSHA standard "1910.147" (lockout/tagout) the prefix is "1910.14", so 1910.146 (confined spaces)
  // and 1910.141 (sanitation) match too. A worker asking about LOTO gets confined-space guidance.
  test.failing('BUG: "1910.147" matches 1910.146 / 1910.141 passages', () => {
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
});

describe('loadKb', () => {
  const remote = [doc({ id: 'r1', title: 'Remote passage', text: 'from the server' })];

  let loadKb: typeof import('../lib/otis/kb').loadKb;
  beforeEach(() => {
    mockStore.clear();
    mockConfig.configured = true;
    mockConfig.api.mockReset();
    mockNoteStale.mockReset();
    jest.resetModules(); // fresh in-memory cache per test
    loadKb = require('../lib/otis/kb').loadKb;
  });

  test('network success returns items and saves a copy on the phone', async () => {
    mockConfig.api.mockResolvedValue({ items: remote });
    await expect(loadKb()).resolves.toEqual(remote);
    expect(JSON.parse(mockStore.get('otis_kb')!)).toEqual(remote);
  });

  test('network failure falls back to the saved copy', async () => {
    const saved = [doc({ id: 's1', title: 'Saved', text: 'offline copy' })];
    mockStore.set('otis_kb', JSON.stringify(saved));
    mockConfig.api.mockRejectedValue(new Error('offline'));
    await expect(loadKb()).resolves.toEqual(saved);
    // The reload served old content, so the content-version check must try again later.
    expect(mockNoteStale).toHaveBeenCalledTimes(1);
  });

  test('a successful fetch does not flag the content as stale', async () => {
    mockConfig.api.mockResolvedValue({ items: remote });
    await loadKb();
    expect(mockNoteStale).not.toHaveBeenCalled();
  });

  test('network failure with no saved copy gives an empty KB', async () => {
    mockConfig.api.mockRejectedValue(new Error('offline'));
    await expect(loadKb()).resolves.toEqual([]);
  });

  test('not configured: reads the saved copy without calling the backend', async () => {
    mockConfig.configured = false;
    const saved = [doc({ id: 's2', title: 'Saved', text: 'copy' })];
    mockStore.set('otis_kb', JSON.stringify(saved));
    await expect(loadKb()).resolves.toEqual(saved);
    expect(mockConfig.api).not.toHaveBeenCalled();
  });

  test('after one good fetch, a later outage serves the in-memory copy', async () => {
    mockConfig.api.mockResolvedValueOnce({ items: remote }).mockRejectedValueOnce(new Error('offline'));
    await loadKb();
    mockStore.clear(); // even if storage is gone, the cached list survives
    await expect(loadKb()).resolves.toEqual(remote);
  });

  test('a fresh fetch replaces the previous copy', async () => {
    const newer = [doc({ id: 'r2', title: 'Newer', text: 'v2' })];
    mockConfig.api.mockResolvedValueOnce({ items: remote }).mockResolvedValueOnce({ items: newer });
    await loadKb();
    await expect(loadKb()).resolves.toEqual(newer);
    expect(JSON.parse(mockStore.get('otis_kb')!)).toEqual(newer);
  });

  // BUG: lib/otis/kb.ts:17 saves to the phone inside the same try as the fetch. If the kv-store
  // write fails (disk full, storage error) the catch at kb.ts:20 throws the fresh items away and
  // serves the old memory/saved copy - on a first launch that is [] even though the network worked.
  // OTIS would then answer with no knowledge base at all.
  test.failing('BUG: a failed save to the phone discards the items just fetched', async () => {
    const Storage = require('expo-sqlite/kv-store').default;
    Storage.setItem.mockRejectedValueOnce(new Error('disk full'));
    mockConfig.api.mockResolvedValue({ items: remote });
    await expect(loadKb()).resolves.toEqual(remote);
  });
});
