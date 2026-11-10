/* eslint-disable @typescript-eslint/no-require-imports -- require() inside jest.isolateModules gives each test a fresh module instance */
/**
 * lib/push.ts: where a tapped notification takes people, and how the three opt-ins
 * (plus promotional offers) are saved and mirrored to OneSignal tags.
 * Boundaries mocked: react-native-onesignal (native), expo-router (navigation),
 * expo-sqlite/kv-store (storage), ../lib/config (env) and global fetch (network, used by lib/live).
 */

type Listener = (event: any) => void;

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

// Every listener OneSignal was given, by event name, so a double registration would show as a double navigation.
const mockListeners: Record<string, Listener[]> = {};
const mockHandlers: Record<string, Listener> = new Proxy({} as Record<string, Listener>, {
  get: (_t, name: string) =>
    mockListeners[name] ? (event: any) => mockListeners[name].forEach((fn) => fn(event)) : undefined,
});
const mockOneSignal = {
  initialize: jest.fn(),
  Debug: { setLogLevel: jest.fn() },
  Notifications: {
    addEventListener: jest.fn((name: string, fn: Listener) => {
      (mockListeners[name] ??= []).push(fn);
    }),
    requestPermission: jest.fn(async () => true),
  },
  User: { addTags: jest.fn() },
};
jest.mock('react-native-onesignal', () => ({
  OneSignal: mockOneSignal,
  LogLevel: { Warn: 4 },
}));

const mockPushed: string[] = [];
jest.mock('expo-router', () => ({
  router: { push: (href: string) => mockPushed.push(href) },
}));

const mockConfig = { apiUrl: 'https://api.test', oneSignalAppId: 'os-app-id', newsletterUrl: '' };
jest.mock('../lib/config', () => ({
  config: mockConfig,
  isConfigured: () => Boolean(mockConfig.apiUrl),
  api: async (path: string) => {
    const res = await (globalThis as any).fetch(`${mockConfig.apiUrl}/api${path}`);
    if (!res.ok) throw new Error(`API ${res.status}`);
    return res.json();
  },
}));

let push: typeof import('../lib/push');
let live: typeof import('../lib/live');

function load() {
  jest.isolateModules(() => {
    push = require('../lib/push');
    live = require('../lib/live');
  });
}

function tap(additionalData: object | undefined) {
  mockHandlers.click({ notification: { additionalData } });
}

function arrive(additionalData: object | undefined) {
  mockHandlers.foregroundWillDisplay({ getNotification: () => ({ additionalData }) });
}

/** Lets the content-version check started by a push (fetch, storage, listeners) finish. */
const settle = () => new Promise((r) => setTimeout(r, 0));

beforeEach(() => {
  mockStore.clear();
  mockPushed.length = 0;
  for (const k of Object.keys(mockListeners)) delete mockListeners[k];
  jest.clearAllMocks();
  mockOneSignal.Notifications.requestPermission.mockImplementation(async () => true);
  mockConfig.oneSignalAppId = 'os-app-id';
  mockConfig.apiUrl = 'https://api.test';
  (globalThis as any).fetch = jest.fn(async () => ({ ok: true, json: async () => ({ version: 'v1' }) }));
  load();
});

describe('notification tap routing', () => {
  beforeEach(() => push.startPush());

  test('episode opens that Zero Hour episode', () => {
    tap({ episode: 12 });
    expect(mockPushed).toEqual(['/zero-hour/12']);
  });

  test('issue opens that toolbox talk', () => {
    tap({ issue: '204' });
    expect(mockPushed).toEqual(['/talk/204']);
  });

  test('a feed alert opens that alert', () => {
    tap({ feed_id: 77, kind: 'alert' });
    expect(mockPushed).toEqual(['/alert/77']);
  });

  test('any other feed item opens Learn', () => {
    tap({ feed_id: 78, kind: 'course' });
    expect(mockPushed).toEqual(['/learn']);
  });

  test.each(['/learn', '/otis', '/archive', '/talk/204', '/alert/ab_c-9', '/zero-hour/3'])(
    'allow-listed route %s is opened as-is',
    (route) => {
      tap({ route });
      expect(mockPushed).toEqual([route]);
    },
  );

  test('an allowed route wins over episode/issue', () => {
    tap({ route: '/otis', episode: 5, issue: 9 });
    expect(mockPushed).toEqual(['/otis']);
  });

  test.each([
    'https://evil.example.com',
    '/../admin',
    '/admin',
    '/talk/../admin',
    '/talk/',
    '/talk/1/extra',
    '/learn?x=1',
    '//evil.example.com',
    'javascript:alert(1)',
    `/talk/${'a'.repeat(41)}`,
  ])('rejected route %s opens nothing', (route) => {
    tap({ route });
    expect(mockPushed).toEqual([]);
  });

  test('without a route, episode wins over issue, and issue wins over feed_id', () => {
    tap({ episode: 5, issue: 9, feed_id: 3, kind: 'alert' });
    tap({ issue: 9, feed_id: 3, kind: 'alert' });
    expect(mockPushed).toEqual(['/zero-hour/5', '/talk/9']);
  });

  test('kind:"alert" without a feed_id opens nothing', () => {
    tap({ kind: 'alert' });
    expect(mockPushed).toEqual([]);
  });

  test('a push arriving while the app is open never navigates by itself', () => {
    arrive({ episode: 5, route: '/otis' });
    expect(mockPushed).toEqual([]);
  });

  test('a rejected route falls back to the episode it carries', () => {
    tap({ route: 'https://evil.example.com', episode: 4 });
    expect(mockPushed).toEqual(['/zero-hour/4']);
  });

  test('a non-string route is ignored', () => {
    tap({ route: { pathname: '/admin' } });
    tap({ route: 42 });
    expect(mockPushed).toEqual([]);
  });

  test('a push with no data or unknown data opens nothing and does not throw', () => {
    expect(() => tap(undefined)).not.toThrow();
    tap({ something: 'else' });
    expect(mockPushed).toEqual([]);
  });

  // BUG: lib/push.ts:40-42 interpolates data.episode / data.issue / data.feed_id into the path
  // without any check, so the route allow-list (lib/push.ts:63-70) is bypassed by putting the
  // bad path in one of those fields instead of `route`. The comment at :62 promises a bad payload
  // can't send people somewhere odd. Correct behaviour: ids must look like ID_ROUTE ids.
  test.failing('BUG: episode/issue/feed_id are not validated, bypassing the route allow-list', () => {
    tap({ episode: '../admin' });
    tap({ issue: '1/../../admin' });
    tap({ feed_id: '../../settings', kind: 'alert' });
    expect(mockPushed).toEqual([]);
  });

  test('calling startPush again does not double-navigate on one tap', () => {
    push.startPush(); // the outer beforeEach already started it once
    push.startPush();
    tap({ episode: 7 });
    expect(mockPushed).toEqual(['/zero-hour/7']);
    expect(mockOneSignal.initialize).toHaveBeenCalledTimes(1);
  });
});

test('startPush does nothing without a OneSignal app id', () => {
  mockConfig.oneSignalAppId = '';
  load();
  push.startPush();
  expect(mockOneSignal.initialize).not.toHaveBeenCalled();
  expect(mockHandlers.click).toBeUndefined();
});

describe('refresh pushes reload content (lib/live)', () => {
  test('tapping a push with refresh:true checks the version and tells open screens', async () => {
    push.startPush();
    const reload = jest.fn();
    live.subscribeContent(reload);
    tap({ refresh: true });
    await settle();
    expect((globalThis as any).fetch).toHaveBeenCalledTimes(1);
    expect((globalThis as any).fetch).toHaveBeenCalledWith('https://api.test/api/content-version/');
    expect(reload).toHaveBeenCalledTimes(1);
    expect(mockStore.get('content_version')).toBe('v1');
  });

  test('a foreground push with refresh:"true" (string) also triggers a check', async () => {
    push.startPush();
    const reload = jest.fn();
    live.subscribeContent(reload);
    arrive({ refresh: 'true' });
    await settle();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(mockStore.get('content_version')).toBe('v1');
  });

  test('a refresh push that also names an episode both reloads and opens it', async () => {
    push.startPush();
    const reload = jest.fn();
    live.subscribeContent(reload);
    tap({ refresh: true, episode: 3 });
    await settle();
    expect(mockPushed).toEqual(['/zero-hour/3']);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  test('a push without refresh does not hit the network', () => {
    push.startPush();
    tap({ episode: 1 });
    tap({ refresh: 'false', episode: 1 });
    arrive({ refresh: 'no' });
    arrive({ refresh: false });
    arrive(undefined);
    expect((globalThis as any).fetch).not.toHaveBeenCalled();
  });
});

describe('getPrefs', () => {
  test('defaults to everything off', async () => {
    expect(await push.getPrefs()).toEqual({ weeklyTalk: false, alerts: false, zeroHour: false, offers: false });
  });

  test('fills missing keys from an older saved shape with off', async () => {
    mockStore.set('push_prefs', JSON.stringify({ weeklyTalk: true }));
    expect(await push.getPrefs()).toEqual({ weeklyTalk: true, alerts: false, zeroHour: false, offers: false });
  });

  // BUG: lib/push.ts:74 calls JSON.parse on the stored value with no try/catch, so a corrupted
  // or truncated 'push_prefs' row makes getPrefs reject and the settings screen fails to load.
  // Correct behaviour: fall back to all-off.
  test.failing('BUG: corrupted stored prefs make getPrefs throw instead of defaulting to off', async () => {
    mockStore.set('push_prefs', '{not json');
    await expect(push.getPrefs()).resolves.toEqual({
      weeklyTalk: false,
      alerts: false,
      zeroHour: false,
      offers: false,
    });
  });

  // BUG (latent, low): lib/push.ts:74 returns the shared module-level OFF object itself when
  // nothing is saved, so a caller that edits the result in place changes the defaults for every
  // later read. Today's callers (app/settings.tsx:29, app/talk/[issue].tsx:59) spread a copy, so
  // nothing user-visible breaks yet. Correct behaviour: return a fresh object.
  test.failing('BUG: getPrefs returns the shared OFF default, so in-place edits leak', async () => {
    const a = await push.getPrefs();
    a.offers = true;
    expect((await push.getPrefs()).offers).toBe(false);
  });
});

describe('setPrefs', () => {
  const ALL_OFF = { weeklyTalk: false, alerts: false, zeroHour: false, offers: false };

  test('turning a switch on asks permission once, saves, and mirrors on/off tags', async () => {
    const next = { weeklyTalk: true, alerts: false, zeroHour: true, offers: false };
    const result = await push.setPrefs(next);
    expect(mockOneSignal.Notifications.requestPermission).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ prefs: next, permissionDenied: false });
    expect(mockOneSignal.User.addTags).toHaveBeenCalledWith({
      weekly_talk: 'on',
      alerts: 'off',
      zero_hour: 'on',
      offers: 'off',
    });
    expect(await push.getPrefs()).toEqual(next);
    expect(await push.hasBeenAsked()).toBe(true);
  });

  test('denied permission turns everything off, saved and tagged off', async () => {
    mockOneSignal.Notifications.requestPermission.mockImplementation(async () => false);
    const result = await push.setPrefs({ weeklyTalk: true, alerts: true, zeroHour: true, offers: true });
    expect(result).toEqual({ prefs: ALL_OFF, permissionDenied: true });
    expect(mockOneSignal.User.addTags).toHaveBeenCalledWith({
      weekly_talk: 'off',
      alerts: 'off',
      zero_hour: 'off',
      offers: 'off',
    });
    expect(await push.getPrefs()).toEqual(ALL_OFF);
    expect(await push.hasBeenAsked()).toBe(true);
  });

  test('turning everything off does not prompt and tags all off', async () => {
    const result = await push.setPrefs(ALL_OFF);
    expect(mockOneSignal.Notifications.requestPermission).not.toHaveBeenCalled();
    expect(result.permissionDenied).toBe(false);
    expect(mockOneSignal.User.addTags).toHaveBeenCalledWith({
      weekly_talk: 'off',
      alerts: 'off',
      zero_hour: 'off',
      offers: 'off',
    });
    expect(await push.hasBeenAsked()).toBe(false);
  });

  test('only offers on still asks and tags offers on', async () => {
    await push.setPrefs({ ...ALL_OFF, offers: true });
    expect(mockOneSignal.Notifications.requestPermission).toHaveBeenCalledTimes(1);
    expect(mockOneSignal.User.addTags).toHaveBeenCalledWith({
      weekly_talk: 'off',
      alerts: 'off',
      zero_hour: 'off',
      offers: 'on',
    });
  });

  test('without a OneSignal app id it only saves on the device', async () => {
    mockConfig.oneSignalAppId = '';
    load();
    const next = { ...ALL_OFF, alerts: true };
    const result = await push.setPrefs(next);
    expect(mockOneSignal.Notifications.requestPermission).not.toHaveBeenCalled();
    expect(mockOneSignal.User.addTags).not.toHaveBeenCalled();
    expect(result).toEqual({ prefs: next, permissionDenied: false });
    expect(await push.getPrefs()).toEqual(next);
  });

  // BUG (latent, low; same root cause as the getPrefs one above): lib/push.ts:93 sets next = OFF, the
  // shared module-level default, and returns it. A caller that edits that result in place changes OFF,
  // so the next denied setPrefs saves and tags that switch ON even though permission was denied.
  // (The previous version of this test re-read getPrefs, where the saved row hides the corruption,
  // so it passed while the bug was present.) Correct behaviour: return a fresh all-off object.
  test.failing('BUG: editing a denied result in place makes the next denial tag that switch on', async () => {
    mockOneSignal.Notifications.requestPermission.mockImplementation(async () => false);
    const first = await push.setPrefs({ ...ALL_OFF, alerts: true });
    first.prefs.alerts = true; // a screen keeping the returned object as local state and editing it
    const second = await push.setPrefs({ ...ALL_OFF, offers: true });
    expect(second.prefs).toEqual(ALL_OFF);
    expect(mockOneSignal.User.addTags).toHaveBeenLastCalledWith({
      weekly_talk: 'off',
      alerts: 'off',
      zero_hour: 'off',
      offers: 'off',
    });
  });

  test('a later save overwrites the earlier one', async () => {
    await push.setPrefs({ ...ALL_OFF, weeklyTalk: true, alerts: true });
    await push.setPrefs({ ...ALL_OFF, alerts: true });
    expect(await push.getPrefs()).toEqual({ ...ALL_OFF, alerts: true });
  });
});
