/* eslint-disable @typescript-eslint/no-require-imports -- require() inside jest.isolateModules gives each test a fresh module instance */
/**
 * lib/live.ts: the "content version" check that tells open screens to reload.
 * Boundaries mocked: expo-sqlite/kv-store (storage), react-native AppState, ../lib/config (network).
 */

const mockStore = new Map<string, string>();
const mockStorage = {
  getItem: jest.fn(async (k: string) => (mockStore.has(k) ? mockStore.get(k)! : null)),
  setItem: jest.fn(async (k: string, v: string) => {
    mockStore.set(k, v);
  }),
};
jest.mock('expo-sqlite/kv-store', () => ({ __esModule: true, default: mockStorage }));

let mockAppStateHandler: ((s: string) => void) | null = null;
jest.mock('react-native', () => ({
  AppState: {
    addEventListener: (_: string, fn: (s: string) => void) => {
      mockAppStateHandler = fn;
      return { remove: () => {} };
    },
  },
}));

// The server's current answer: a version string, or an Error to simulate no signal.
let mockServer: { version: string } | Error = { version: 'v1' };
const mockCfg = { apiUrl: 'https://api.test' };
const mockApi = jest.fn(async (path: string) => {
  if (path !== '/content-version/') throw new Error(`unexpected path ${path}`);
  if (mockServer instanceof Error) throw mockServer;
  return mockServer;
});
jest.mock('../lib/config', () => ({
  config: mockCfg,
  isConfigured: () => Boolean(mockCfg.apiUrl),
  api: (...args: [string]) => mockApi(...args),
}));

let live: typeof import('../lib/live');
let rntl: typeof import('@testing-library/react-native/pure');

function load() {
  jest.isolateModules(() => {
    live = require('../lib/live');
    // Same registry, so the hook and the renderer share one React. "pure" skips the auto-cleanup hooks,
    // which can't be registered from inside a test; afterEach unmounts instead.
    rntl = require('@testing-library/react-native/pure');
  });
}

/** Lets pending promise chains (awaits inside lib/live) run. */
async function flush() {
  for (let i = 0; i < 10; i++) await Promise.resolve();
}

function foreground() {
  if (!mockAppStateHandler) throw new Error('startLive did not listen to AppState');
  mockAppStateHandler('active');
}

beforeEach(() => {
  jest.useFakeTimers({ now: new Date('2026-11-10T08:00:00Z') });
  mockStore.clear();
  mockAppStateHandler = null;
  mockServer = { version: 'v1' };
  mockCfg.apiUrl = 'https://api.test';
  mockApi.mockClear();
  mockStorage.setItem.mockImplementation(async (k: string, v: string) => {
    mockStore.set(k, v);
  });
  load();
});

afterEach(async () => {
  await rntl.cleanup();
  jest.useRealTimers();
});

describe('refreshContent', () => {
  test('first check with no saved version notifies and remembers the version', async () => {
    const reload = jest.fn();
    live.subscribeContent(reload);
    await expect(live.refreshContent()).resolves.toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(mockStore.get('content_version')).toBe('v1');
  });

  test('same version again does not notify', async () => {
    mockStore.set('content_version', 'v1');
    const reload = jest.fn();
    live.subscribeContent(reload);
    await expect(live.refreshContent()).resolves.toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  test('notifies only when the version changes', async () => {
    const reload = jest.fn();
    live.subscribeContent(reload);
    await live.refreshContent(); // v1
    await live.refreshContent(); // v1 again
    mockServer = { version: 'v2' };
    await live.refreshContent(); // v2
    await live.refreshContent(); // v2 again
    expect(reload).toHaveBeenCalledTimes(2);
    expect(mockStore.get('content_version')).toBe('v2');
  });

  test('an empty version from the server is ignored', async () => {
    mockServer = { version: '' };
    const reload = jest.fn();
    live.subscribeContent(reload);
    await expect(live.refreshContent()).resolves.toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });

  test('no signal: resolves false, does not notify, and the next check still works', async () => {
    const reload = jest.fn();
    live.subscribeContent(reload);
    mockServer = new Error('Network request failed');
    await expect(live.refreshContent()).resolves.toBe(false);
    expect(reload).not.toHaveBeenCalled();
    mockServer = { version: 'v1' };
    await expect(live.refreshContent()).resolves.toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  test('not configured (no API url): never touches the network', async () => {
    mockCfg.apiUrl = '';
    await expect(live.refreshContent()).resolves.toBe(false);
    expect(mockApi).not.toHaveBeenCalled();
  });

  test('unsubscribe stops that listener only', async () => {
    const a = jest.fn();
    const b = jest.fn();
    const stopA = live.subscribeContent(a);
    live.subscribeContent(b);
    stopA();
    await live.refreshContent();
    expect(a).not.toHaveBeenCalled();
    expect(b).toHaveBeenCalledTimes(1);
  });

  test('one throwing screen does not stop the others, and the version stays unseen for a retry', async () => {
    const good = jest.fn();
    live.subscribeContent(() => {
      throw new Error('render failed');
    });
    live.subscribeContent(good);
    await expect(live.refreshContent()).resolves.toBe(true);
    expect(good).toHaveBeenCalledTimes(1);
    expect(mockStore.has('content_version')).toBe(false);
    await live.refreshContent();
    expect(good).toHaveBeenCalledTimes(2); // retried, since the broken screen missed it
  });

  test('a reload that fell back to the phone copy leaves the version unseen, and the next check retries', async () => {
    let offline = true;
    const reload = jest.fn(async () => {
      if (offline) live.noteStaleContent();
    });
    live.subscribeContent(reload);
    await expect(live.refreshContent()).resolves.toBe(true);
    expect(mockStore.has('content_version')).toBe(false);

    offline = false; // signal is back
    await expect(live.refreshContent()).resolves.toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
    expect(mockStore.get('content_version')).toBe('v1');
    await expect(live.refreshContent()).resolves.toBe(false); // now seen
  });

  test('a stale reload from before a check does not block that check from saving', async () => {
    live.noteStaleContent(); // some earlier list load used the phone copy
    live.subscribeContent(jest.fn());
    await live.refreshContent();
    expect(mockStore.get('content_version')).toBe('v1');
  });

  test('waits for async reloads before remembering the version', async () => {
    let finish!: () => void;
    live.subscribeContent(() => new Promise<void>((r) => (finish = r)));
    const p = live.refreshContent();
    await flush();
    expect(mockStore.has('content_version')).toBe(false);
    finish();
    await p;
    expect(mockStore.get('content_version')).toBe('v1');
  });

  test('a check asked for while one is running runs once more after it, so a new version is not missed', async () => {
    let release!: () => void;
    mockApi.mockImplementationOnce(
      () => new Promise((r) => (release = () => r({ version: 'v1' }))) as Promise<{ version: string }>,
    );
    const reload = jest.fn();
    live.subscribeContent(reload);
    const first = live.refreshContent();
    mockServer = { version: 'v2' }; // a push says v2 was just published
    const second = live.refreshContent();
    release();
    await expect(first).resolves.toBe(true);
    await expect(second).resolves.toBe(true);
    expect(mockApi).toHaveBeenCalledTimes(2);
    expect(mockStore.get('content_version')).toBe('v2');
    expect(reload).toHaveBeenCalledTimes(2);
  });

  test('storage failure while saving the version does not reject, and the next check notifies again', async () => {
    mockStorage.setItem.mockImplementation(async () => {
      throw new Error('disk full');
    });
    const reload = jest.fn();
    live.subscribeContent(reload);
    await expect(live.refreshContent()).resolves.toBe(true);
    await expect(live.refreshContent()).resolves.toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  test('storage failure while reading the saved version resolves false without notifying', async () => {
    mockStorage.getItem.mockImplementationOnce(async () => {
      throw new Error('db locked');
    });
    const reload = jest.fn();
    live.subscribeContent(reload);
    await expect(live.refreshContent()).resolves.toBe(false);
    expect(reload).not.toHaveBeenCalled();
  });
});

describe('useContentRefresh (screens)', () => {
  test('runs the latest reload while mounted and stops after unmount', async () => {
    const first = jest.fn();
    const second = jest.fn();
    const { rerender, unmount } = await rntl.renderHook(({ reload }: { reload: () => unknown }) => live.useContentRefresh(reload), {
      initialProps: { reload: first },
    });
    await rerender({ reload: second }); // the screen re-rendered with a new closure (e.g. new filter)
    await live.refreshContent();
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);

    await unmount();
    mockServer = { version: 'v2' };
    await live.refreshContent();
    expect(second).toHaveBeenCalledTimes(1);
  });

  test('a reload promise that rejects leaves the version unseen', async () => {
    await rntl.renderHook(() => live.useContentRefresh(() => Promise.reject(new Error('offline'))));
    await expect(live.refreshContent()).resolves.toBe(true);
    expect(mockStore.has('content_version')).toBe(false);
  });
});

describe('startLive (foreground checks)', () => {
  test('checks at launch, then on foreground at most once per 60 s', async () => {
    live.startLive();
    await flush();
    expect(mockApi).toHaveBeenCalledTimes(1); // launch

    jest.advanceTimersByTime(30_000);
    foreground();
    await flush();
    expect(mockApi).toHaveBeenCalledTimes(1); // throttled

    jest.advanceTimersByTime(30_000); // 60 s since the last check
    foreground();
    await flush();
    expect(mockApi).toHaveBeenCalledTimes(2);

    foreground();
    await flush();
    expect(mockApi).toHaveBeenCalledTimes(2); // throttled again
  });

  test('going to background or inactive never checks', async () => {
    live.startLive();
    await flush();
    jest.advanceTimersByTime(120_000);
    mockAppStateHandler!('background');
    mockAppStateHandler!('inactive');
    await flush();
    expect(mockApi).toHaveBeenCalledTimes(1);
  });

  test('a failed check still counts toward the throttle and does not break later checks', async () => {
    mockServer = new Error('no signal');
    live.startLive();
    await flush();
    foreground();
    await flush();
    expect(mockApi).toHaveBeenCalledTimes(1);

    const reload = jest.fn();
    live.subscribeContent(reload);
    mockServer = { version: 'v9' };
    jest.advanceTimersByTime(60_000);
    foreground();
    await flush();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  test('foreground after a version change notifies subscribers', async () => {
    const reload = jest.fn();
    live.subscribeContent(reload);
    live.startLive();
    await flush();
    expect(reload).toHaveBeenCalledTimes(1); // learned v1 at launch

    mockServer = { version: 'v2' };
    jest.advanceTimersByTime(61_000);
    foreground();
    await flush();
    expect(reload).toHaveBeenCalledTimes(2);
  });

  test('calling startLive twice does not double-check at launch', async () => {
    live.startLive();
    live.startLive();
    await flush();
    expect(mockApi).toHaveBeenCalledTimes(1);
  });
});
