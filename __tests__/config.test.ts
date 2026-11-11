/* eslint-disable @typescript-eslint/no-require-imports -- require() inside jest.isolateModules gives each test a fresh module instance */
/** api(): the one fetch wrapper every screen uses to reach the Django server. */

const fetchMock = jest.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

function load(apiUrl: string | undefined) {
  if (apiUrl === undefined) delete process.env.EXPO_PUBLIC_API_URL;
  else process.env.EXPO_PUBLIC_API_URL = apiUrl;
  let mod!: typeof import('@/lib/config');
  jest.isolateModules(() => {
    mod = require('@/lib/config');
  });
  return mod;
}

const res = (status: number, body: unknown = {}) =>
  Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body });

beforeEach(() => {
  fetchMock.mockReset();
  jest.useRealTimers();
});

describe('config', () => {
  test('strips one trailing slash from the API url, and leaves a url without one alone', () => {
    expect(load('https://api.example.test/').config.apiUrl).toBe('https://api.example.test');
    expect(load('https://api.example.test').config.apiUrl).toBe('https://api.example.test');
  });

  test('isConfigured is false when no API url is set', () => {
    expect(load(undefined).isConfigured()).toBe(false);
    expect(load('').isConfigured()).toBe(false);
    expect(load('https://api.example.test').isConfigured()).toBe(true);
  });
});

describe('api()', () => {
  test('prefixes /api, sends JSON headers and returns the parsed body', async () => {
    const { api } = load('https://api.example.test/');
    fetchMock.mockReturnValueOnce(res(200, { talks: [1] }));

    await expect(api('/talks/')).resolves.toEqual({ talks: [1] });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.example.test/api/talks/');
    expect(init.headers).toEqual({ Accept: 'application/json', 'Content-Type': 'application/json' });
  });

  test('keeps method/body and lets a caller add or override headers', async () => {
    const { api } = load('https://api.example.test');
    fetchMock.mockReturnValueOnce(res(201, { id: 5 }));

    await api('/signups/', { method: 'POST', body: '{"a":1}', headers: { 'Content-Type': 'text/plain', 'X-A': '1' } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(init.body).toBe('{"a":1}');
    expect(init.headers).toEqual({ Accept: 'application/json', 'Content-Type': 'text/plain', 'X-A': '1' });
  });

  test.each([400, 404, 500, 503])('a %i response throws with the status in the message', async (status) => {
    const { api } = load('https://api.example.test');
    fetchMock.mockReturnValueOnce(res(status));
    await expect(api('/talks/')).rejects.toThrow(`API ${status}`);
  });

  test('a network failure propagates so callers can fall back to the phone copy', async () => {
    const { api } = load('https://api.example.test');
    fetchMock.mockReturnValueOnce(Promise.reject(new TypeError('Network request failed')));
    await expect(api('/talks/')).rejects.toThrow('Network request failed');
  });

  /** A fetch that never answers until its signal aborts, like a dead dock signal. */
  const hangingFetch = (_url: string, init: RequestInit) =>
    new Promise((_resolve, reject) => {
      init.signal!.addEventListener('abort', () => reject(Object.assign(new Error('Aborted'), { name: 'AbortError' })));
    });

  test('aborts after the default 10 s timeout, not before', async () => {
    jest.useFakeTimers();
    const { api } = load('https://api.example.test');
    fetchMock.mockImplementationOnce(hangingFetch);

    let settled = false;
    const p = api('/talks/').finally(() => {
      settled = true;
    });
    p.catch(() => {});

    await jest.advanceTimersByTimeAsync(9_999);
    expect(settled).toBe(false);
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(false);

    await jest.advanceTimersByTimeAsync(1);
    await expect(p).rejects.toThrow('Aborted');
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true);
  });

  test('honours a custom timeout', async () => {
    jest.useFakeTimers();
    const { api } = load('https://api.example.test');
    fetchMock.mockImplementationOnce(hangingFetch);

    let settled = false;
    const p = api('/content-version/', undefined, 8000).finally(() => {
      settled = true;
    });
    p.catch(() => {});
    await jest.advanceTimersByTimeAsync(7_999);
    expect(settled).toBe(false);
    await jest.advanceTimersByTimeAsync(1);
    await expect(p).rejects.toThrow('Aborted');
  });

  test('clears its timer after a reply, so a finished request is never aborted later', async () => {
    jest.useFakeTimers();
    const { api } = load('https://api.example.test');
    fetchMock.mockReturnValueOnce(res(200, { ok: 1 }));

    await expect(api('/talks/')).resolves.toEqual({ ok: 1 });
    expect(jest.getTimerCount()).toBe(0);
  });

  test('clears its timer after an error response too', async () => {
    jest.useFakeTimers();
    const { api } = load('https://api.example.test');
    fetchMock.mockReturnValueOnce(res(500));

    await expect(api('/talks/')).rejects.toThrow('API 500');
    expect(jest.getTimerCount()).toBe(0);
  });
});
