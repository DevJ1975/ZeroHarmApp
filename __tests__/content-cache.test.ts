/* eslint-disable @typescript-eslint/no-require-imports -- require() inside jest.isolateModules gives each test a fresh module instance */
/**
 * Content that must open with no signal on the dock: weekly talks (SQLite), the alerts/resources
 * feed (SQLite) and Zero Hour episodes (kv-store). Network success refreshes the phone's copy;
 * network failure falls back to it.
 */
import type { FeedItem } from '@/lib/feed';
import type { Talk } from '@/lib/talks';

// ---- boundaries ---------------------------------------------------------------------------

/** In-memory stand-in for the two SQLite mockTables these loaders touch. */
type Tables = { talks: Map<number, string>; feed: Map<number, { kind: string; json: string }> };
const mockTables: Tables = { talks: new Map(), feed: new Map() };

const mockDb = {
  async runAsync(sql: string, ...args: unknown[]) {
    if (sql.startsWith('INSERT OR REPLACE INTO talks_cache')) {
      mockTables.talks.set(args[0] as number, args[1] as string);
    } else if (sql.startsWith('INSERT OR REPLACE INTO feed_cache')) {
      mockTables.feed.set(args[0] as number, { kind: args[1] as string, json: args[2] as string });
    } else if (sql.startsWith('DELETE FROM feed_cache WHERE kind IN')) {
      for (const [id, row] of mockTables.feed) if (args.includes(row.kind)) mockTables.feed.delete(id);
    } else {
      throw new Error(`fake db: unexpected SQL ${sql}`);
    }
  },
  async getAllAsync(sql: string, ...args: unknown[]) {
    if (sql === 'SELECT json FROM talks_cache ORDER BY issue DESC') {
      return [...mockTables.talks.entries()].sort((a, b) => b[0] - a[0]).map(([, json]) => ({ json }));
    }
    if (sql.startsWith('SELECT json FROM feed_cache WHERE kind IN')) {
      // SQLite returns rows in rowid order, not by featured/date: the loader must sort.
      return [...mockTables.feed.entries()]
        .sort((a, b) => a[0] - b[0])
        .filter(([, r]) => args.includes(r.kind))
        .map(([, r]) => ({ json: r.json }));
    }
    throw new Error(`fake db: unexpected SQL ${sql}`);
  },
  async withTransactionAsync(fn: () => Promise<void>) {
    const snapshot = new Map(mockTables.feed);
    try {
      await fn();
    } catch (e) {
      mockTables.feed = snapshot;
      throw e;
    }
  },
};

jest.mock('@/lib/db', () => ({ getDb: async () => mockDb }));

const mockKv = new Map<string, string>();
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: async (k: string) => (mockKv.has(k) ? mockKv.get(k)! : null),
    setItem: async (k: string, v: string) => {
      mockKv.set(k, v);
    },
  },
}));

const fetchMock = jest.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: async () => body });
const noSignal = () => Promise.reject(new TypeError('Network request failed'));

// ---- helpers ------------------------------------------------------------------------------

function load(apiUrl = 'https://api.example.test') {
  process.env.EXPO_PUBLIC_API_URL = apiUrl;
  let mods!: {
    talks: typeof import('@/lib/talks');
    feed: typeof import('@/lib/feed');
    episodes: typeof import('@/lib/episodes');
    live: typeof import('@/lib/live');
  };
  jest.isolateModules(() => {
    mods = {
      talks: require('@/lib/talks'),
      feed: require('@/lib/feed'),
      episodes: require('@/lib/episodes'),
      live: require('@/lib/live'), // same instance the loaders report stale fallbacks to
    };
  });
  return mods;
}

const talk = (issue: number, title = `Talk ${issue}`): Talk => ({
  issue,
  issue_date: `2026-10-${String(issue).padStart(2, '0')}`,
  month_theme: 'Ladders',
  title,
  story_title: 's',
  crew_question: 'q',
  body_md: 'b',
  hero_url: null,
  pdf_url: null,
});

const item = (id: number, kind: FeedItem['kind'], published_at: string, featured = false): FeedItem => ({
  id,
  kind,
  title: `Item ${id}`,
  summary: '',
  body_md: null,
  link_url: null,
  image_url: null,
  jurisdiction: null,
  effective_date: null,
  published_at,
  featured,
});

beforeEach(() => {
  mockTables.talks = new Map();
  mockTables.feed = new Map();
  mockKv.clear();
  fetchMock.mockReset();
});

// ---- talks --------------------------------------------------------------------------------

describe('listTalks', () => {
  test('online: returns the server list and keeps a copy on the phone', async () => {
    const { talks } = load();
    fetchMock.mockReturnValueOnce(ok({ talks: [talk(2), talk(1)] }));

    const res = await talks.listTalks();

    expect(res.offline).toBe(false);
    expect(res.talks.map((t) => t.issue)).toEqual([2, 1]);
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.test/api/talks/');
    expect([...mockTables.talks.keys()].sort()).toEqual([1, 2]);
  });

  test('no signal: shows the copy saved last time, newest first, and says it is offline', async () => {
    const { talks } = load();
    fetchMock.mockReturnValueOnce(ok({ talks: [talk(1), talk(3, 'Fall protection')] }));
    await talks.listTalks();

    fetchMock.mockReturnValueOnce(noSignal());
    const res = await talks.listTalks();

    expect(res.offline).toBe(true);
    expect(res.talks.map((t) => t.issue)).toEqual([3, 1]);
    expect(res.talks[0].title).toBe('Fall protection');
  });

  test('a server error (500) also falls back to the phone copy', async () => {
    const { talks } = load();
    mockTables.talks.set(7, JSON.stringify(talk(7)));
    fetchMock.mockReturnValueOnce(Promise.resolve({ ok: false, status: 500, json: async () => ({}) }));

    const res = await talks.listTalks();
    expect(res).toEqual({ talks: [talk(7)], offline: true });
  });

  test('no signal and nothing saved yet: empty list, offline', async () => {
    const { talks } = load();
    fetchMock.mockReturnValueOnce(noSignal());
    expect(await talks.listTalks()).toEqual({ talks: [], offline: true });
  });

  test('a re-published talk replaces the saved copy instead of duplicating it', async () => {
    const { talks } = load();
    fetchMock.mockReturnValueOnce(ok({ talks: [talk(4, 'Old title')] }));
    await talks.listTalks();
    fetchMock.mockReturnValueOnce(ok({ talks: [talk(4, 'Fixed title')] }));
    await talks.listTalks();

    fetchMock.mockReturnValueOnce(noSignal());
    const { talks: offline } = await talks.listTalks();
    expect(offline.map((t) => t.title)).toEqual(['Fixed title']);
  });

  test('API not configured: never calls the network, reads the phone copy', async () => {
    const { talks } = load('');
    mockTables.talks.set(1, JSON.stringify(talk(1)));

    expect(await talks.listTalks()).toEqual({ talks: [talk(1)], offline: true });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // BUG: lib/talks.ts:25-30 cache() only INSERT OR REPLACEs, it never removes talks the server no longer
  // returns. The console can unpublish a talk or move its send_at later (TalkPatch.published / send_at in
  // console/src/api.ts) and lib/live.ts says content changes when something is "pulled", but a pulled talk
  // stays in talks_cache forever and reappears whenever the crew is offline. listFeed deletes pulled items;
  // listTalks should do the same.
  test.failing('BUG: a talk the server pulled still shows from the phone copy offline', async () => {
    const { talks } = load();
    fetchMock.mockReturnValueOnce(ok({ talks: [talk(2), talk(1)] }));
    await talks.listTalks();
    // issue 2 was unpublished on the server
    fetchMock.mockReturnValueOnce(ok({ talks: [talk(1)] }));
    await talks.listTalks();

    fetchMock.mockReturnValueOnce(noSignal());
    expect((await talks.listTalks()).talks.map((t) => t.issue)).toEqual([1]);
  });

  test('a malformed 200 reply falls back to the phone copy instead of throwing', async () => {
    const { talks } = load();
    mockTables.talks.set(5, JSON.stringify(talk(5)));
    fetchMock.mockReturnValueOnce(ok({}));
    expect(await talks.listTalks()).toEqual({ talks: [talk(5)], offline: true });
  });

  test('getTalk finds by issue id, null when missing', async () => {
    const { talks } = load();
    fetchMock.mockReturnValue(ok({ talks: [talk(2), talk(1)] }));
    expect((await talks.getTalk(1))?.issue).toBe(1);
    expect(await talks.getTalk(99)).toBeNull();
  });

  test('issueNumber prefers the printed number over the app id', () => {
    const { talks } = load();
    expect(talks.issueNumber({ ...talk(12), number: 3 })).toBe(3);
    expect(talks.issueNumber(talk(12))).toBe(12);
  });
});

// ---- feed ---------------------------------------------------------------------------------

describe('listFeed', () => {
  test('online: requests the kinds asked for and returns the server list', async () => {
    const { feed } = load();
    const items = [item(1, 'alert', '2026-11-01T00:00:00Z')];
    fetchMock.mockReturnValueOnce(ok({ items }));

    expect(await feed.listFeed(['alert'])).toEqual(items);
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.test/api/feed/?kind=alert');
  });

  test('offline: only the requested kinds, featured first, then newest first', async () => {
    const { feed } = load();
    fetchMock.mockReturnValueOnce(
      ok({
        items: [
          item(1, 'course', '2026-09-01T00:00:00Z'),
          item(2, 'tool', '2026-11-01T00:00:00Z'),
          item(3, 'course', '2026-08-01T00:00:00Z', true),
          item(4, 'video', '2026-10-01T00:00:00Z'),
        ],
      }),
    );
    await feed.listFeed(['course', 'tool', 'video']);
    fetchMock.mockReturnValueOnce(ok({ items: [item(9, 'alert', '2026-12-01T00:00:00Z', true)] }));
    await feed.listFeed(['alert']);

    fetchMock.mockReturnValueOnce(noSignal());
    const res = await feed.listFeed(['course', 'tool', 'video']);

    // the featured course leads even though it is the oldest; the alert is not a resource
    expect(res.map((i) => i.id)).toEqual([3, 2, 4, 1]);
  });

  test('refreshing one kind drops items the server pulled, and leaves other kinds alone', async () => {
    const { feed } = load();
    fetchMock.mockReturnValueOnce(
      ok({ items: [item(1, 'alert', '2026-10-01T00:00:00Z'), item(2, 'alert', '2026-10-02T00:00:00Z')] }),
    );
    await feed.listFeed(['alert']);
    fetchMock.mockReturnValueOnce(ok({ items: [item(5, 'course', '2026-10-03T00:00:00Z')] }));
    await feed.listFeed(['course']);

    // alert 1 was withdrawn on the server
    fetchMock.mockReturnValueOnce(ok({ items: [item(2, 'alert', '2026-10-02T00:00:00Z')] }));
    await feed.listFeed(['alert']);

    fetchMock.mockReturnValue(noSignal());
    expect((await feed.listFeed(['alert'])).map((i) => i.id)).toEqual([2]);
    expect((await feed.listFeed(['course'])).map((i) => i.id)).toEqual([5]);
  });

  test('a malformed 200 reply does not wipe the saved alerts (the delete is rolled back)', async () => {
    const { feed } = load();
    fetchMock.mockReturnValueOnce(ok({ items: [item(1, 'alert', '2026-10-01T00:00:00Z')] }));
    await feed.listFeed(['alert']);

    fetchMock.mockReturnValueOnce(ok({})); // no items array: inserting throws after the DELETE ran
    expect((await feed.listFeed(['alert'])).map((i) => i.id)).toEqual([1]);

    fetchMock.mockReturnValueOnce(noSignal());
    expect((await feed.listFeed(['alert'])).map((i) => i.id)).toEqual([1]);
  });

  test('API not configured: never calls the network, reads the phone copy', async () => {
    const { feed } = load('');
    mockTables.feed.set(3, { kind: 'tool', json: JSON.stringify(item(3, 'tool', '2026-10-01T00:00:00Z')) });
    expect((await feed.listFeed(['tool'])).map((i) => i.id)).toEqual([3]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('getFeedItem looks across alerts and every resource kind', async () => {
    const { feed } = load();
    fetchMock.mockReturnValueOnce(ok({ items: [item(8, 'newsletter', '2026-10-01T00:00:00Z')] }));

    expect((await feed.getFeedItem(8))?.kind).toBe('newsletter');
    expect(fetchMock.mock.calls[0][0]).toBe(
      'https://api.example.test/api/feed/?kind=alert,course,tool,video,newsletter',
    );
  });

  test('offline getFeedItem finds a saved item of any kind, null for an id that was never saved', async () => {
    const { feed } = load();
    fetchMock.mockReturnValueOnce(ok({ items: [item(6, 'video', '2026-10-01T00:00:00Z')] }));
    await feed.listFeed(['video']);

    fetchMock.mockReturnValue(noSignal());
    expect((await feed.getFeedItem(6))?.title).toBe('Item 6');
    expect(await feed.getFeedItem(123)).toBeNull();
  });
});

// ---- episodes -----------------------------------------------------------------------------

describe('listEpisodes', () => {
  const ep = (number: number) => ({ number, title: `Episode ${number}` });

  test('online: returns and saves the episodes; offline: the saved copy opens', async () => {
    const { episodes } = load();
    fetchMock.mockReturnValueOnce(ok({ episodes: [ep(2), ep(1)] }));
    expect((await episodes.listEpisodes()).map((e) => e.number)).toEqual([2, 1]);

    fetchMock.mockReturnValueOnce(noSignal());
    expect((await episodes.listEpisodes()).map((e) => e.number)).toEqual([2, 1]);
    expect(fetchMock.mock.calls[0][0]).toBe('https://api.example.test/api/episodes/');
  });

  test('offline with nothing saved: empty list, no throw', async () => {
    const { episodes } = load();
    fetchMock.mockReturnValueOnce(noSignal());
    expect(await episodes.listEpisodes()).toEqual([]);
  });

  test('API not configured: never calls the network, opens the saved copy', async () => {
    const { episodes } = load('');
    mockKv.set('zero_hour_cache', JSON.stringify([ep(5)]));
    expect((await episodes.listEpisodes()).map((e) => e.number)).toEqual([5]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test('getEpisode by number, null when missing', async () => {
    const { episodes } = load();
    fetchMock.mockReturnValue(ok({ episodes: [ep(3)] }));
    expect((await episodes.getEpisode(3))?.title).toBe('Episode 3');
    expect(await episodes.getEpisode(4)).toBeNull();
  });
});

// ---- live refresh -------------------------------------------------------------------------

/**
 * lib/live.ts only marks a new content version as seen when every reload really reached the server.
 * Each loader must report its offline fallback (noteStaleContent), or a change that arrives while the
 * signal drops is never shown until the next unrelated change.
 */
describe('content refresh after an offline fallback', () => {
  type Mods = ReturnType<typeof load>;
  const loaders: [string, (m: Mods) => Promise<unknown>][] = [
    ['listTalks', (m) => m.talks.listTalks()],
    ['listFeed', (m) => m.feed.listFeed(['alert'])],
    ['listEpisodes', (m) => m.episodes.listEpisodes()],
  ];

  /** The content-version endpoint answers; every content list fails or succeeds per `listsOnline`. */
  const route = (listsOnline: boolean) =>
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/content-version/')) return ok({ version: 'v2' });
      if (!listsOnline) return noSignal();
      if (url.includes('/talks/')) return ok({ talks: [] });
      if (url.includes('/feed/')) return ok({ items: [] });
      return ok({ episodes: [] });
    });

  test.each(loaders)('%s offline: the change stays unseen and the next check reloads again', async (_n, reload) => {
    const mods = load();
    const screen = jest.fn(() => reload(mods));
    mods.live.subscribeContent(screen);

    route(false);
    expect(await mods.live.refreshContent()).toBe(true);
    expect(mockKv.get('content_version')).toBeUndefined();

    route(true);
    expect(await mods.live.refreshContent()).toBe(true);
    expect(screen).toHaveBeenCalledTimes(2);
    expect(mockKv.get('content_version')).toBe('v2');
  });

  test.each(loaders)('%s online: the change is marked seen, so the next check does not reload', async (_n, reload) => {
    const mods = load();
    const screen = jest.fn(() => reload(mods));
    mods.live.subscribeContent(screen);

    route(true);
    expect(await mods.live.refreshContent()).toBe(true);
    expect(await mods.live.refreshContent()).toBe(false);
    expect(screen).toHaveBeenCalledTimes(1);
  });
});
