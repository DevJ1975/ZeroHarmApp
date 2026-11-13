/* eslint-disable @typescript-eslint/no-require-imports -- require() after jest.resetModules gives each test a fresh crash recorder (it remembers what it has seen and whether it is installed) */
type CrashModule = typeof import('@/lib/support/crash');

const mockStore = new Map<string, string>();
const mockFail = { read: false, write: false };
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) => Promise.resolve(mockStore.get(key) ?? null),
    setItem: (key: string, value: string) => Promise.resolve(void mockStore.set(key, value)),
    removeItem: (key: string) => Promise.resolve(mockStore.delete(key)),
    getItemSync: (key: string) => {
      if (mockFail.read) throw new Error('storage is closed');
      return mockStore.get(key) ?? null;
    },
    setItemSync: (key: string, value: string) => {
      if (mockFail.write) throw new Error('disk full');
      mockStore.set(key, value);
    },
    removeItemSync: (key: string) => mockStore.delete(key),
  },
}));
jest.mock('@/lib/config', () => {
  class ApiError extends Error {
    status: number;
    constructor(code: number) {
      super(`API ${code}`);
      this.status = code;
    }
  }
  return { api: jest.fn(), isConfigured: jest.fn(), ApiError };
});
jest.mock('expo-device', () => ({ __esModule: true, modelName: 'Pixel 8', osVersion: '15' }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { version: '1.0.0' } } }));

type Saved = { client_key: string; name: string; message: string; stack: string; fatal: boolean; screen: string; at: string; app_version: string; platform: string; os_version: string; device: string };
const box = () => JSON.parse(mockStore.get('crash_outbox') ?? '[]') as Saved[];

const world = globalThis as unknown as { ErrorUtils?: unknown; HermesInternal?: unknown; __DEV__: boolean };
const realErrorUtils = world.ErrorUtils;
const realHermes = world.HermesInternal;

let crash: CrashModule;
let send: jest.Mock;
let configured: jest.Mock;
let ApiError: new (status: number) => Error;
let platform: { OS: string };

beforeEach(() => {
  mockStore.clear();
  mockFail.read = false;
  mockFail.write = false;
  jest.resetModules();
  platform = require('react-native').Platform;
  platform.OS = 'android';
  const config = require('@/lib/config');
  send = config.api;
  configured = config.isConfigured;
  ApiError = config.ApiError;
  send.mockResolvedValue({ ok: true, number: 'ZH-124' });
  configured.mockReturnValue(true);
  crash = require('@/lib/support/crash');
  jest.useFakeTimers().setSystemTime(new Date('2026-11-11T17:00:00Z'));
});

afterEach(() => {
  jest.useRealTimers();
  world.ErrorUtils = realErrorUtils;
  world.HermesInternal = realHermes;
  world.__DEV__ = true;
});

const boom = (message = 'undefined is not a function') => {
  const error = new TypeError(message);
  error.stack = `TypeError: ${message}\n    at save (address at index.android.bundle:1:234567)\n    at onPress (address at index.android.bundle:1:99)`;
  return error;
};

describe('recordError', () => {
  it('saves the error at once, with the screen, the time and what the phone is', () => {
    crash.recordError(boom(), { fatal: true, screen: '/talk/12?from=push' });
    expect(box()).toEqual([
      {
        client_key: expect.stringMatching(/^c-[a-z0-9]+-[0-9a-f]{16}$/),
        name: 'TypeError',
        message: 'undefined is not a function',
        stack: 'at save (address at index.android.bundle:1:234567)\nat onPress (address at index.android.bundle:1:99)',
        fatal: true,
        screen: '/talk/12',
        at: '2026-11-11T17:00:00.000Z',
        app_version: '1.0.0',
        platform: 'android',
        os_version: '15',
        device: 'Pixel 8',
      },
    ]);
  });

  it('is synchronous: the report is on the phone before the call returns', () => {
    expect(crash.recordError(boom(), { fatal: true })).toBeUndefined();
    expect(box()).toHaveLength(1); // no await anywhere above
  });

  it('holds nothing but the error, the screen and the phone facts', () => {
    crash.recordError(boom(), { fatal: false });
    expect(Object.keys(box()[0]).sort()).toEqual(['app_version', 'at', 'client_key', 'device', 'fatal', 'message', 'name', 'os_version', 'platform', 'screen', 'stack']);
  });

  it('uses the screen the layout last noted when the caller does not say', () => {
    crash.noteScreen('/otis?draft=my%20name%20is%20maria');
    crash.recordError(boom(), { fatal: false });
    expect(box()[0].screen).toBe('/otis');
    crash.recordError(boom('another one'), { fatal: false, screen: '/settings' });
    expect(box()[1].screen).toBe('/settings');
  });

  it('copes with whatever was thrown, and never prints an object', () => {
    crash.recordError('plain string', { fatal: false });
    crash.recordError({ secret: 'maria@example.com', nested: { phone: '702-555-0100' } }, { fatal: false });
    crash.recordError(undefined, { fatal: false });
    crash.recordError(42, { fatal: false });
    crash.recordError({ name: 'CustomError', message: 'custom failed' }, { fatal: false });
    expect(box().map((c) => [c.name, c.message])).toEqual([
      ['Error', 'plain string'],
      ['Error', 'No message'],
      ['Error', '42'],
      ['CustomError', 'custom failed'],
    ]);
    expect(JSON.stringify(box())).not.toMatch(/maria|555/);
  });

  it('never throws, whatever goes wrong inside it', () => {
    mockFail.write = true;
    expect(() => crash.recordError(boom(), { fatal: true })).not.toThrow();
    mockFail.write = false;
    mockFail.read = true;
    expect(() => crash.recordError(boom('second'), { fatal: true })).not.toThrow();
    mockFail.read = false;
    mockStore.set('crash_outbox', '{not json');
    expect(() => crash.recordError(boom('third'), { fatal: true })).not.toThrow();
    expect(box().map((c) => c.message)).toEqual(['third']); // a damaged queue starts again
    const hostile = { get message(): string { throw new Error('getter'); } };
    expect(() => crash.recordError(hostile, { fatal: true })).not.toThrow();
    expect(() => crash.recordError(boom('no options'), undefined as never)).not.toThrow();
  });

  it('does nothing on the web', () => {
    platform.OS = 'web';
    crash.recordError(boom(), { fatal: true });
    expect(mockStore.has('crash_outbox')).toBe(false);
  });
});

describe('scrubbing', () => {
  it('takes out query strings, emails, phone numbers, long numbers and coordinates', () => {
    const { scrub } = crash;
    expect(scrub('GET https://api.example.com/weather/?lat=36.1699&lon=-115.1398 failed')).toBe('GET https://api.example.com/weather/ failed');
    expect(scrub('no user maria.lopez+safety@example.co.uk here')).toBe('no user [email] here');
    expect(scrub('call 702-555-0100 or +1 (702) 555 0100')).toBe('call [number] or [number]');
    expect(scrub('badge 12345678 not found')).toBe('badge [number] not found');
    expect(scrub('at 36.1699, -115.1398')).toBe('at [number], [number]');
    expect(scrub('Request failed with status 404 after 3 tries')).toBe('Request failed with status 404 after 3 tries');
    expect(scrub("undefined is not an object (evaluating 'a.b')")).toBe("undefined is not an object (evaluating 'a.b')");
  });

  it('is applied to the name and the message before anything is saved', () => {
    const error = new Error('Could not load /weather/?lat=36.1699&lon=-115.1398 for maria@example.com (id 9988776655)');
    error.name = 'LoadError for maria@example.com';
    crash.recordError(error, { fatal: false });
    const [saved] = box();
    expect(saved.message).toBe('Could not load /weather/? for [email] (id [number])');
    expect(saved.name).toBe('LoadError for [email]');
    expect(JSON.stringify(saved)).not.toMatch(/maria|36\.1699|115\.1398|9988776655/);
  });

  it('caps the name, the message and the stack', () => {
    const error = new Error('m'.repeat(2000));
    error.name = 'N'.repeat(500);
    error.stack = `Error: x\n${Array.from({ length: 400 }, (_, i) => `    at frame${i} (index.android.bundle:1:${i})`).join('\n')}`;
    crash.recordError(error, { fatal: false });
    const [saved] = box();
    expect(saved.name).toHaveLength(120);
    expect(saved.message).toHaveLength(500);
    expect(saved.stack.length).toBeLessThanOrEqual(6000);
    expect(saved.stack.split('\n').length).toBeGreaterThan(50); // line breaks are kept
  });

  it('keeps stack lines and their positions, and drops the copy of the message above them', () => {
    const stack = ['Error: token for maria@example.com is 1234567890', '    at loadTalk (address at index.android.bundle:1:1848213)', '    at anonymous (address at index.android.bundle:1:77)'].join('\n');
    expect(crash.scrubStack(stack)).toBe('at loadTalk (address at index.android.bundle:1:1848213)\nat anonymous (address at index.android.bundle:1:77)');
  });

  it('cuts a web address in a stack line down to the file, so a development computer is never named', () => {
    const dev = '    at render (http://192.168.1.20:8081/index.bundle//&platform=ios&dev=true&lazy=true&app=com.example:12345:67)';
    expect(crash.scrubStack(`Error: x\n${dev}`)).toBe('at render (index.bundle:12345:67)');
    expect(crash.scrubStack('Error: x\n    at f (file:///var/containers/Bundle/Application/ABC-123/ZeroHarm.app/main.jsbundle:1:2345)')).toBe('at f (main.jsbundle:1:2345)');
    expect(crash.scrubStack('f@http://10.0.0.5:8081/index.bundle?platform=ios&dev=true:10:20')).toBe('f@index.bundle:10:20');
  });

  it('gives an empty stack for no stack', () => {
    expect(crash.scrubStack('')).toBe('');
    expect(crash.describeError(new Error('x')).stack).not.toMatch(/Error: x/);
  });
});

describe('repeats and the cap', () => {
  it('saves the same error once, however many times it is thrown', () => {
    for (let i = 0; i < 500; i++) crash.recordError(boom(), { fatal: false });
    expect(box()).toHaveLength(1);
  });

  it('counts errors that differ only by a number as the same', () => {
    crash.recordError(boom('row 3 is missing'), { fatal: false });
    crash.recordError(boom('row 7 is missing'), { fatal: false });
    crash.recordError(boom('column 7 is missing'), { fatal: false });
    expect(box().map((c) => c.message)).toEqual(['row 3 is missing', 'column 7 is missing']);
  });

  it('does not save the same error again right after it was sent, but does later', async () => {
    crash.recordError(boom(), { fatal: false });
    await crash.flushCrashes();
    expect(box()).toEqual([]);
    crash.recordError(boom(), { fatal: false });
    expect(box()).toEqual([]);
    jest.setSystemTime(new Date('2026-11-11T17:11:00Z'));
    crash.recordError(boom(), { fatal: false });
    expect(box()).toHaveLength(1);
  });

  it('does not save an error that is already waiting from an earlier run of the app', () => {
    crash.recordError(boom(), { fatal: true });
    jest.resetModules(); // the app starts again
    require('react-native').Platform.OS = 'android';
    const again: CrashModule = require('@/lib/support/crash');
    again.recordError(boom(), { fatal: true });
    expect(box()).toHaveLength(1);
  });

  it('a storm of the same error touches the phone storage once, not once per throw', () => {
    const Storage = require('expo-sqlite/kv-store').default;
    const reads = jest.spyOn(Storage, 'getItemSync');
    const writes = jest.spyOn(Storage, 'setItemSync');
    for (let i = 0; i < 1000; i++) crash.recordError(boom(), { fatal: false });
    expect(writes).toHaveBeenCalledTimes(1);
    expect(reads.mock.calls.length).toBeLessThanOrEqual(2); // the switch and the queue, for the first one only
    reads.mockRestore();
    writes.mockRestore();
  });

  it('a storm of errors with crash reports off does not hammer the storage either', () => {
    crash.setCrashReportsOn(false);
    const Storage = require('expo-sqlite/kv-store').default;
    const reads = jest.spyOn(Storage, 'getItemSync');
    for (let i = 0; i < 1000; i++) crash.recordError(boom(`different each time ${'abcdefghij'[i % 10]}`), { fatal: false });
    expect(reads.mock.calls.length).toBeLessThanOrEqual(1);
    expect(mockStore.has('crash_outbox')).toBe(false);
    reads.mockRestore();
  });

  it('handles a huge error message without keeping or scanning all of it', () => {
    const error = new Error(`${'x'.repeat(2_000_000)} maria@example.com`);
    error.stack = `Error: big\n${'    at f (index.android.bundle:1:2)\n'.repeat(100_000)}`;
    const started = Date.now();
    jest.useRealTimers();
    const t0 = performance.now();
    crash.recordError(error, { fatal: true });
    expect(performance.now() - t0).toBeLessThan(500);
    jest.useFakeTimers().setSystemTime(started);
    expect(box()[0].message).toHaveLength(500);
    expect(box()[0].stack.length).toBeLessThanOrEqual(6000);
  });

  it('keeps at most 20 waiting', () => {
    for (let i = 0; i < 60; i++) crash.recordError(boom(`failure ${'abcdefghijklmnopqrstuvwxyz'[i % 26]}${'abc'[Math.floor(i / 26)]}`), { fatal: false });
    expect(box()).toHaveLength(crash.CRASH_QUEUE_MAX);
    expect(crash.CRASH_QUEUE_MAX).toBe(20);
    expect(box()[0].message).toBe('failure aa'); // the first ones are kept: they are closest to the cause
  });

  it('when full, a crash that closed the app takes the place of one that did not', () => {
    for (let i = 0; i < 20; i++) crash.recordError(boom(`minor ${'abcdefghijklmnopqrst'[i]}`), { fatal: false });
    crash.recordError(boom('the big one'), { fatal: true });
    expect(box()).toHaveLength(20);
    expect(box().filter((c) => c.fatal).map((c) => c.message)).toEqual(['the big one']);
    expect(box().map((c) => c.message)).not.toContain('minor t');
  });

  it('skips what is not a bug: no signal, a cancelled request, a server error', () => {
    crash.recordError(new TypeError('Network request failed'), { fatal: false });
    crash.recordError(Object.assign(new Error('Aborted'), { name: 'AbortError' }), { fatal: false });
    crash.recordError(new Error('API 503'), { fatal: false });
    expect(mockStore.has('crash_outbox')).toBe(false);
    crash.recordError(new TypeError('Network request failed'), { fatal: true }); // but anything that closes the app is kept
    expect(box()).toHaveLength(1);
  });

  it('skips the bundler complaining about half-typed code while developing', () => {
    crash.recordError(new Error('Unable to resolve module ./nope from app/otis.tsx'), { fatal: false });
    expect(mockStore.has('crash_outbox')).toBe(false);
    world.__DEV__ = false;
    crash.recordError(new Error('Unable to resolve module ./nope from app/otis.tsx'), { fatal: false });
    expect(box()).toHaveLength(1);
  });
});

describe('the Settings switch', () => {
  it('is on unless the person turned it off', () => {
    expect(crash.crashReportsOn()).toBe(true);
    crash.setCrashReportsOn(false);
    expect(crash.crashReportsOn()).toBe(false);
    expect(mockStore.get('crash_reports')).toBe('off');
    crash.setCrashReportsOn(true);
    expect(crash.crashReportsOn()).toBe(true);
  });

  it('off deletes everything waiting on the phone', () => {
    crash.recordError(boom('one'), { fatal: true });
    crash.recordError(boom('two'), { fatal: false });
    expect(box()).toHaveLength(2);
    crash.setCrashReportsOn(false);
    expect(mockStore.has('crash_outbox')).toBe(false);
  });

  it('off records nothing and sends nothing', async () => {
    crash.setCrashReportsOn(false);
    crash.recordError(boom(), { fatal: true });
    expect(mockStore.has('crash_outbox')).toBe(false);
    await crash.flushCrashes();
    expect(send).not.toHaveBeenCalled();
  });

  it('off sends nothing even if a report is somehow still on the phone', async () => {
    crash.recordError(boom(), { fatal: true });
    mockStore.set('crash_reports', 'off'); // switched off without the queue being cleared
    await crash.flushCrashes();
    expect(send).not.toHaveBeenCalled();
  });

  it('turning it off while reports are going out stops the rest', async () => {
    crash.recordError(boom('one'), { fatal: false });
    crash.recordError(boom('two'), { fatal: false });
    crash.recordError(boom('three'), { fatal: false });
    send.mockImplementationOnce(async () => {
      crash.setCrashReportsOn(false);
      return { ok: true };
    });
    await crash.flushCrashes();
    expect(send).toHaveBeenCalledTimes(1);
    expect(mockStore.has('crash_outbox')).toBe(false);
  });

  it('turning it back on starts clean: an error seen before can be recorded again', () => {
    crash.recordError(boom(), { fatal: false });
    crash.setCrashReportsOn(false);
    crash.setCrashReportsOn(true);
    crash.recordError(boom(), { fatal: false });
    expect(box()).toHaveLength(1);
  });

  it('records nothing if the phone cannot read the setting, and never throws', () => {
    mockFail.read = true;
    expect(crash.crashReportsOn()).toBe(false);
    mockFail.write = true;
    expect(() => crash.setCrashReportsOn(false)).not.toThrow();
  });
});

describe('flushCrashes', () => {
  const body = (call: number) => JSON.parse(send.mock.calls[call][1].body);

  it('sends each waiting report once, with the install id, and clears the queue', async () => {
    crash.recordError(boom('one'), { fatal: true, screen: '/otis' });
    crash.recordError(boom('two'), { fatal: false });
    const keys = box().map((c) => c.client_key);
    await crash.flushCrashes();
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[0][0]).toBe('/v2/support/crash');
    expect(send.mock.calls[0][1].method).toBe('POST');
    expect(send.mock.calls[0][2]).toBe(5000);
    expect(body(0)).toEqual({
      client_key: keys[0],
      install_id: expect.stringMatching(/^zh-[A-Za-z0-9-]{13,61}$/),
      name: 'TypeError',
      message: 'one',
      stack: expect.stringContaining('at save'),
      fatal: true,
      screen: '/otis',
      at: '2026-11-11T17:00:00.000Z',
      app_version: '1.0.0',
      platform: 'android',
      os_version: '15',
      device: 'Pixel 8',
    });
    expect(body(1).client_key).toBe(keys[1]);
    expect(mockStore.has('crash_outbox')).toBe(false);

    await crash.flushCrashes();
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('keeps everything when there is no signal, and sends with the same key next time', async () => {
    crash.recordError(boom('one'), { fatal: true });
    crash.recordError(boom('two'), { fatal: false });
    const keys = box().map((c) => c.client_key);
    send.mockReset().mockRejectedValue(new Error('no signal'));
    await expect(crash.flushCrashes()).resolves.toBeUndefined();
    expect(send).toHaveBeenCalledTimes(1); // the second is not tried behind a first that found no signal
    expect(box().map((c) => c.client_key)).toEqual(keys);

    send.mockReset().mockResolvedValue({ ok: true });
    await crash.flushCrashes();
    expect(send.mock.calls.map((c) => JSON.parse(c[1].body).client_key)).toEqual(keys);
    expect(box()).toEqual([]);
  });

  it('never records its own failure to send as a new crash', async () => {
    crash.recordError(boom(), { fatal: true });
    for (const failure of [new Error('no signal'), new TypeError('Network request failed'), new ApiError(500), new ApiError(429), new Error('something else broke while sending')]) {
      send.mockReset().mockRejectedValue(failure);
      await crash.flushCrashes();
      expect(box().map((c) => c.message)).toEqual(['undefined is not a function']);
    }
  });

  it('drops a report the server refuses for good, and goes on to the next', async () => {
    crash.recordError(boom('one'), { fatal: false });
    crash.recordError(boom('two'), { fatal: false });
    send.mockReset().mockRejectedValueOnce(new ApiError(422)).mockResolvedValue({ ok: true });
    await crash.flushCrashes();
    expect(send).toHaveBeenCalledTimes(2);
    expect(box()).toEqual([]);
  });

  it('sends once when launch and foreground call it together', async () => {
    crash.recordError(boom(), { fatal: true });
    await Promise.all([crash.flushCrashes(), crash.flushCrashes(), crash.flushCrashes()]);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('a crash saved while others are going out is sent in the same pass', async () => {
    crash.recordError(boom('one'), { fatal: false });
    send.mockImplementationOnce(async () => {
      crash.recordError(boom('two'), { fatal: false });
      return { ok: true };
    });
    await crash.flushCrashes();
    expect(send.mock.calls.map((c) => JSON.parse(c[1].body).message)).toEqual(['one', 'two']);
    expect(box()).toEqual([]);
  });

  it('does nothing on the web, with no server address, or with nothing waiting', async () => {
    await crash.flushCrashes();
    crash.recordError(boom(), { fatal: true });
    configured.mockReturnValue(false);
    await crash.flushCrashes();
    configured.mockReturnValue(true);
    platform.OS = 'web';
    await crash.flushCrashes();
    expect(send).not.toHaveBeenCalled();
  });

  it('never throws, even when the phone cannot be read or written', async () => {
    crash.recordError(boom(), { fatal: true });
    mockFail.write = true;
    await expect(crash.flushCrashes()).resolves.toBeUndefined();
    mockFail.write = false;
    await crash.flushCrashes(); // the report it could not take out goes again with the same key; the server keeps one
    expect(new Set(send.mock.calls.map((c) => JSON.parse(c[1].body).client_key)).size).toBe(1);
  });
});

describe('installCrashReporter', () => {
  const fakeErrorUtils = () => {
    const previous = jest.fn();
    let current: (error: unknown, isFatal?: boolean) => void = previous;
    const utils = { getGlobalHandler: jest.fn(() => current), setGlobalHandler: jest.fn((h: typeof current) => void (current = h)) };
    world.ErrorUtils = utils;
    return { previous, utils, raise: (error: unknown, isFatal?: boolean) => current(error, isFatal) };
  };

  it('records an uncaught error and then always calls the handler that was there before', () => {
    const { previous, raise } = fakeErrorUtils();
    crash.installCrashReporter();
    const error = boom();
    raise(error, true);
    expect(box()).toMatchObject([{ message: 'undefined is not a function', fatal: true }]);
    expect(previous).toHaveBeenCalledTimes(1);
    expect(previous).toHaveBeenCalledWith(error, true);

    raise(boom('a small one'), false);
    expect(box()[1]).toMatchObject({ message: 'a small one', fatal: false });
    expect(previous).toHaveBeenCalledTimes(2);
  });

  it('still calls the previous handler when recording fails, is switched off, or the error is a repeat', () => {
    const { previous, raise } = fakeErrorUtils();
    crash.installCrashReporter();
    mockFail.write = true;
    raise(boom('one'), true);
    mockFail.write = false;
    mockFail.read = true;
    raise(boom('two'), true);
    mockFail.read = false;
    crash.setCrashReportsOn(false);
    raise(boom('three'), true);
    crash.setCrashReportsOn(true);
    raise(boom('four'), false);
    raise(boom('four'), false);
    expect(previous).toHaveBeenCalledTimes(5);
    expect(box().map((c) => c.message)).toEqual(['four']);
  });

  it('lets an error from the previous handler through, after recording', () => {
    const { previous, raise } = fakeErrorUtils();
    previous.mockImplementation(() => {
      throw new Error('the native side closes the app here');
    });
    crash.installCrashReporter();
    expect(() => raise(boom(), true)).toThrow('the native side closes the app here');
    expect(box()).toHaveLength(1);
  });

  it('is installed once, however many times it is called', () => {
    const { previous, utils, raise } = fakeErrorUtils();
    crash.installCrashReporter();
    crash.installCrashReporter();
    crash.installCrashReporter();
    expect(utils.setGlobalHandler).toHaveBeenCalledTimes(1);
    raise(boom(), true);
    expect(previous).toHaveBeenCalledTimes(1);
    expect(box()).toHaveLength(1);
  });

  it('uses the screen the layout noted', () => {
    const { raise } = fakeErrorUtils();
    crash.installCrashReporter();
    crash.noteScreen('/sheets');
    raise(boom(), true);
    expect(box()[0].screen).toBe('/sheets');
  });

  it('is skipped on the web', () => {
    const { utils } = fakeErrorUtils();
    const track = jest.fn();
    world.HermesInternal = { enablePromiseRejectionTracker: track };
    world.__DEV__ = false;
    platform.OS = 'web';
    crash.installCrashReporter();
    expect(utils.setGlobalHandler).not.toHaveBeenCalled();
    expect(track).not.toHaveBeenCalled();
  });

  it('does not throw when the hooks are missing or broken', () => {
    world.ErrorUtils = undefined;
    world.HermesInternal = null;
    expect(() => crash.installCrashReporter()).not.toThrow();

    jest.resetModules();
    require('react-native').Platform.OS = 'android';
    const again: CrashModule = require('@/lib/support/crash');
    world.__DEV__ = false;
    world.ErrorUtils = { getGlobalHandler: () => { throw new Error('nope'); }, setGlobalHandler: () => { throw new Error('nope'); } };
    world.HermesInternal = { enablePromiseRejectionTracker: () => { throw new Error('nope'); } };
    expect(() => again.installCrashReporter()).not.toThrow();
  });

  describe('promises that fail with nobody listening', () => {
    it('are recorded in a store build, as not fatal', () => {
      fakeErrorUtils();
      const track = jest.fn();
      world.HermesInternal = { enablePromiseRejectionTracker: track };
      world.__DEV__ = false;
      crash.installCrashReporter();
      expect(track).toHaveBeenCalledTimes(1);
      const options = track.mock.calls[0][0] as { allRejections: boolean; onUnhandled: (id: number, rejection: unknown) => void; onHandled: (id: number) => void };
      expect(options.allRejections).toBe(true);
      options.onUnhandled(1, boom('promise went wrong'));
      options.onUnhandled(2, new TypeError('Network request failed')); // no signal is not a bug
      options.onUnhandled(3, undefined);
      expect(() => options.onHandled(1)).not.toThrow();
      expect(box().map((c) => [c.message, c.fatal])).toEqual([['promise went wrong', false], ['No message', false]]);
    });

    it("are left to React Native while developing, so its own warning keeps working", () => {
      fakeErrorUtils();
      const track = jest.fn();
      world.HermesInternal = { enablePromiseRejectionTracker: track };
      world.__DEV__ = true;
      crash.installCrashReporter();
      expect(track).not.toHaveBeenCalled();
    });

    it('are skipped quietly when the engine has no such hook', () => {
      fakeErrorUtils();
      world.__DEV__ = false;
      world.HermesInternal = {};
      expect(() => crash.installCrashReporter()).not.toThrow();
      world.HermesInternal = undefined;
    });
  });
});

describe('scrubbing ids and web addresses (review fixes)', () => {
  const uuid = () =>
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.floor(Math.random() * 16);
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });

  it('cuts a web address at the first ? or #, with or without an "="', () => {
    const { scrub } = crash;
    expect(scrub('GET https://api.test/v2/x?MariaLopez failed')).toBe('GET https://api.test/v2/x failed');
    expect(scrub('open zeroharm://signin#access_token=SECRETSECRET failed')).toBe('open zeroharm://signin failed');
    expect(scrub('see https://x.example.com/reset?email=jose@acme.com#top now')).toBe('see https://x.example.com/reset now');
  });

  it('turns a whole UUID or a long hex id into one [id], never half an id', () => {
    const { scrub } = crash;
    expect(scrub('OneSignal id 3fa85f64-5717-4562-b3fc-2c963f66afa6')).toBe('OneSignal id [id]');
    expect(scrub('token ' + 'ab12'.repeat(16) + ' bad')).toBe('token [id] bad');
    expect(scrub('id 3f2a9c1e00ffab12 gone')).toBe('id [id] gone');
    expect(scrub('id 3fa85f645717 gone')).toBe('id [id] gone'); // a shorter hex id with a long digit run
    expect(scrub("File '/var/mobile/Containers/Data/Application/E91AC587-2E10-4C33-9C2F-1F0EFD537C5B/Library/Caches/otis/model.pte' is not readable")).toBe(
      "File '/var/mobile/Containers/Data/Application/[id]/Library/Caches/otis/model.pte' is not readable",
    );
    expect(scrub('status 404 after 3 tries, build 1a2b')).toBe('status 404 after 3 tries, build 1a2b');
  });

  it('1,000 phones with the same error in their own app folder give one message', () => {
    const seenMessages = new Set<string>();
    for (let i = 0; i < 1000; i++) {
      const id = i % 2 ? uuid().toUpperCase() : uuid();
      seenMessages.add(crash.describeError(new Error(`File '/var/mobile/Containers/Data/Application/${id}/Library/Caches/otis/model.pte' is not readable`)).message);
    }
    expect([...seenMessages]).toEqual(["File '/var/mobile/Containers/Data/Application/[id]/Library/Caches/otis/model.pte' is not readable"]);
  });
});

describe('a storm of errors in the awkward states (review fixes)', () => {
  const spy = () => {
    const Storage = require('expo-sqlite/kv-store').default;
    return { reads: jest.spyOn(Storage, 'getItemSync'), writes: jest.spyOn(Storage, 'setItemSync') };
  };

  it('the same error already waiting from an earlier run is looked up once, not once per throw', () => {
    crash.recordError(boom(), { fatal: false });
    jest.resetModules(); // the app starts again
    require('react-native').Platform.OS = 'android';
    const again: CrashModule = require('@/lib/support/crash');
    const { reads, writes } = spy();
    for (let i = 0; i < 1000; i++) again.recordError(boom(), { fatal: false });
    expect(reads.mock.calls.length).toBeLessThanOrEqual(2);
    expect(writes).not.toHaveBeenCalled();
    expect(box()).toHaveLength(1);
  });

  it('a full queue is not read again for every new error', () => {
    for (let i = 0; i < 20; i++) crash.recordError(boom(`minor ${'abcdefghijklmnopqrst'[i]}`), { fatal: false });
    const { reads } = spy();
    for (let i = 0; i < 1000; i++) crash.recordError(boom(`storm ${'abcdefghijklmnopqrstuvwxyz'[i % 26]}${'abcdefghijklmnopqrstuvwxyz'[Math.floor(i / 26) % 26]}`), { fatal: false });
    expect(reads.mock.calls.length).toBeLessThanOrEqual(3);
    expect(box()).toHaveLength(20);
    // A minute later it looks again, and a crash that closes the app is always looked at.
    jest.setSystemTime(new Date('2026-11-11T17:01:30Z'));
    crash.recordError(boom('the big one'), { fatal: true });
    expect(box().map((c) => c.message)).toContain('the big one');
  });

  it('a write that keeps failing is tried once for the same error, not once per throw', () => {
    mockFail.write = true;
    const { reads, writes } = spy();
    for (let i = 0; i < 1000; i++) crash.recordError(boom(), { fatal: false });
    expect(writes).toHaveBeenCalledTimes(1);
    expect(reads.mock.calls.length).toBeLessThanOrEqual(2);
  });
});

describe('what is not a bug, on SDK 58 (review fixes)', () => {
  // expo/fetch's FetchError: name "Error", message "fetch failed: <the phone's own words>".
  const fetchError = (message: string) => new Error(`fetch failed: ${message}`);

  it('skips no signal and timeouts the way expo/fetch reports them', () => {
    crash.recordError(fetchError('Unable to resolve host "zero-harm-api.example"'), { fatal: false });
    crash.recordError(fetchError('The Internet connection appears to be offline.'), { fatal: false });
    crash.recordError(fetchError('The operation was aborted.'), { fatal: false });
    crash.recordError(new Error('The operation was aborted.'), { fatal: false });
    crash.recordError(new Error('cancelled'), { fatal: false });
    expect(mockStore.has('crash_outbox')).toBe(false);
  });

  it('still keeps a real bug that only mentions a cancel or a fetch', () => {
    crash.recordError(new TypeError("Cannot read property 'cancelled' of undefined"), { fatal: false });
    crash.recordError(new TypeError('fetchTalks is not a function'), { fatal: false });
    expect(box()).toHaveLength(2);
  });
});

describe('sending: answers that are not final (review fixes)', () => {
  it('keeps a crash report when the server answers 404 (support address not there yet), 401 or 403', async () => {
    crash.recordError(boom(), { fatal: true });
    for (const status of [404, 401, 403, 405]) {
      send.mockReset().mockRejectedValue(new ApiError(status));
      await crash.flushCrashes();
      expect(box()).toHaveLength(1);
    }
    send.mockReset().mockRejectedValue(new ApiError(413));
    await crash.flushCrashes();
    expect(box()).toEqual([]);
  });

  it('installCrashReporter sends what an earlier run saved, without waiting for the layout', async () => {
    crash.recordError(boom(), { fatal: true });
    jest.resetModules(); // the app starts again, and the layout never gets as far as its effects
    require('react-native').Platform.OS = 'android';
    const config = require('@/lib/config');
    config.isConfigured.mockReturnValue(true);
    config.api.mockResolvedValue({ ok: true });
    const again: CrashModule = require('@/lib/support/crash');
    again.installCrashReporter();
    expect(config.api).not.toHaveBeenCalled();
    await jest.runOnlyPendingTimersAsync();
    expect(config.api).toHaveBeenCalledWith('/v2/support/crash', expect.anything(), expect.any(Number));
    await jest.runOnlyPendingTimersAsync();
    expect(box()).toEqual([]);
  });
});

describe('second check of the review fixes', () => {
  const uuid = () =>
    'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = Math.floor(Math.random() * 16);
      return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
    });
  const hex = (n: number) => Array.from({ length: n }, () => '0123456789abcdef'[Math.floor(Math.random() * 16)]).join('');
  /** A random hex id with at least one digit and one letter, the way real ones almost always are. */
  const mixedHex = (n: number) => `1a${hex(n - 2)}`;
  const messages = (make: () => string) => {
    const seenMessages = new Set<string>();
    for (let i = 0; i < 1000; i++) seenMessages.add(crash.describeError(new Error(make())).message);
    return [...seenMessages];
  };

  it('catches a whole id with "_" or a letter next to it', () => {
    expect(messages(() => `Could not open cache_${uuid()}.bin`)).toEqual(['Could not open cache_[id].bin']);
    expect(messages(() => `Could not open cache_${uuid()}_${uuid()}`)).toEqual(['Could not open cache_[id]_[id]']);
    expect(messages(() => `bad key_${hex(16)}`)).toEqual(['bad key_[id]']);
    expect(crash.scrub('3fa85f64-5717-4562-b3fc-2c963f66afa6_3fa85f64-5717-4562-b3fc-2c963f66afa6')).toBe('[id]_[id]');
    expect(crash.scrub('file:x3fa85f64-5717-4562-b3fc-2c963f66afa6')).toBe('file:x[id]');
  });

  it('turns a short hex id (8 to 15 characters with digits and letters) into one [id]', () => {
    expect(messages(() => `session ${mixedHex(10)} expired`)).toEqual(['session [id] expired']);
    expect(messages(() => `cache key ${mixedHex(8)}`)).toEqual(['cache key [id]']);
    expect(crash.scrub('at 0x1f2e3d4c')).toBe('at [id]');
    // Words, short codes and plain numbers stay as they were.
    expect(crash.scrub('status 404 after 3 tries, build 1a2b')).toBe('status 404 after 3 tries, build 1a2b');
    expect(crash.scrub('embedded2024 failed on deadbeef')).toBe('embedded2024 failed on deadbeef');
    expect(crash.scrub('Invariant Violation: abc123')).toBe('Invariant Violation: abc123');
  });

  it('blanks an email whole, even when its first part looks like an id', () => {
    expect(crash.scrub('user fred.ab12345678@acme.com failed')).toBe('user [email] failed');
    expect(crash.scrub('user 3fa85f645717@acme.com failed')).toBe('user [email] failed');
  });

  it('cuts the whole query of an address, through an apostrophe in it', () => {
    expect(crash.scrub("GET https://x.test/a?q=O'Brien failed")).toBe('GET https://x.test/a failed');
    expect(crash.scrub("GET /a?q=O'Brien failed")).toBe('GET /a? failed');
    // The quote or bracket around an address, and a full stop after it, stay.
    expect(crash.scrub("Could not load 'https://x.test/a?q=b' now")).toBe("Could not load 'https://x.test/a' now");
    expect(crash.scrub('(see https://x.test/a?q=b).')).toBe('(see https://x.test/a).');
    expect(crash.scrub('Failed: https://x.test/a?q=b.')).toBe('Failed: https://x.test/a.');
  });

  it('a crash that closes the app is saved after the same error was turned away by a full box', () => {
    for (let i = 0; i < 20; i++) crash.recordError(boom(`filler ${'abcdefghijklmnopqrst'[i]}`), { fatal: false });
    expect(box()).toHaveLength(20);
    crash.recordError(boom('render loop broke'), { fatal: false }); // full: turned away
    expect(box().map((c) => c.message)).not.toContain('render loop broke');
    crash.recordError(boom('render loop broke'), { fatal: true }); // closes the app
    expect(box()).toHaveLength(20);
    expect(box().filter((c) => c.message === 'render loop broke').map((c) => c.fatal)).toEqual([true]);
  });

  it('a crash that closes the app is saved after the same error could not be written', () => {
    mockFail.write = true;
    crash.recordError(boom('disk hiccup'), { fatal: false });
    mockFail.write = false;
    crash.recordError(boom('disk hiccup'), { fatal: true });
    expect(box().filter((c) => c.message === 'disk hiccup').map((c) => c.fatal)).toEqual([true]);
  });

  it('when the same error is already waiting and this time it closed the app, the waiting report says so', () => {
    crash.recordError(boom('list broke'), { fatal: false });
    expect(box().map((c) => c.fatal)).toEqual([false]);
    crash.recordError(boom('list broke'), { fatal: true });
    expect(box()).toHaveLength(1);
    expect(box()[0].fatal).toBe(true);
    crash.recordError(boom('list broke'), { fatal: false }); // a later one that did not close the app changes nothing
    expect(box().map((c) => c.fatal)).toEqual([true]);
  });

  it('a storm of the same crash that closes the app still touches the storage once', () => {
    const Storage = require('expo-sqlite/kv-store').default;
    const writes = jest.spyOn(Storage, 'setItemSync');
    for (let i = 0; i < 1000; i++) crash.recordError(boom(), { fatal: true });
    expect(writes).toHaveBeenCalledTimes(1);
    writes.mockRestore();
  });
});
