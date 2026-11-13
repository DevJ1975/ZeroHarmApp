import { api, isConfigured } from '@/lib/config';
import {
  ANSWER_REPORT_SENDS,
  BEFORE_SENDING,
  cleanScreen,
  fileReport,
  flushReports,
  longEnough,
  mergeReports,
  myReports,
  reportAnswer,
  REPORT_MAX,
  REPORT_MIN,
  savedReports,
  tidyText,
  titleOf,
  whyNotSent,
  type Report,
} from '@/lib/support/reports';

const mockStore = new Map<string, string>();
const mockFail = { setItem: false };
jest.mock('expo-sqlite/kv-store', () => ({
  __esModule: true,
  default: {
    getItem: (key: string) => Promise.resolve(mockStore.get(key) ?? null),
    setItem: (key: string, value: string) => (mockFail.setItem ? Promise.reject(new Error('disk full')) : Promise.resolve(void mockStore.set(key, value))),
    removeItem: (key: string) => Promise.resolve(mockStore.delete(key)),
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
jest.mock('expo-device', () => ({ __esModule: true, modelName: 'iPhone 15', osVersion: '18.1' }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { version: '1.0.0' } } }));

const { ApiError } = jest.requireMock('@/lib/config') as { ApiError: new (status: number) => Error };
const send = api as jest.Mock;
const path = (call: number) => send.mock.calls[call][0] as string;
const body = (call: number) => JSON.parse(send.mock.calls[call][1].body);
const outbox = () => JSON.parse(mockStore.get('support_outbox') ?? '[]') as { key: string }[];
const noSignal = () => send.mockReset().mockRejectedValue(new Error('no signal'));
/** The server: a report gets the next ticket number; "mine" lists what the test put in `tickets`. */
let tickets: unknown[] = [];
let nextNumber = 123;
const online = () =>
  send.mockReset().mockImplementation(async (p: string) => (p === '/v2/support/mine' ? { tickets } : { number: `ZH-${nextNumber++}`, status: 'new' }));

const crashed = { text: 'The app closes when I open a talk', source: 'otis' as const };

beforeEach(async () => {
  await flushReports(); // let anything a previous test left in the air finish
  mockStore.clear();
  mockFail.setItem = false;
  tickets = [];
  nextNumber = 123;
  online();
  (isConfigured as jest.Mock).mockReturnValue(true);
});

describe('pure helpers', () => {
  it('tidyText trims, caps, and never leaves half an emoji or a NUL', () => {
    expect(tidyText('  hello  ', 10)).toBe('hello');
    expect(tidyText('abcdef', 3)).toBe('abc');
    expect(tidyText('ab\u0000cd', 10)).toBe('abcd');
    expect(tidyText('ab😀', 3)).toBe('ab'); // the emoji is two code units; half of one is dropped
    expect(tidyText('ab😀', 4)).toBe('ab😀');
    for (const odd of [undefined, null, 5, {}]) expect(tidyText(odd, 10)).toBe('');
  });

  it('titleOf is the first line that has words, at most 120 characters', () => {
    expect(titleOf('\n  App closes  \nIt happens every time')).toBe('App closes');
    expect(titleOf('x'.repeat(300))).toHaveLength(120);
    expect(titleOf('')).toBe('');
  });

  it('cleanScreen drops the query, so nothing typed into a search rides along', () => {
    expect(cleanScreen('/talk/12?from=push&q=maria')).toBe('/talk/12');
    expect(cleanScreen('/otis#top')).toBe('/otis');
    expect(cleanScreen(undefined)).toBe('');
  });

  it('the limits match the server', () => {
    expect(REPORT_MIN).toBe(5);
    expect(REPORT_MAX).toBe(4000);
  });
});

describe('fileReport with signal', () => {
  it('sends the report once and hands back the ticket number', async () => {
    const filed = await fileReport(crashed);
    expect(filed).toEqual({ ref: expect.stringMatching(/^p-[a-z0-9]+-[0-9a-f]{16}$/), number: 'ZH-123', queued: false });
    expect(send).toHaveBeenCalledTimes(1);
    expect(path(0)).toBe('/v2/support/report');
    expect(send.mock.calls[0][1].method).toBe('POST');
    expect(body(0)).toEqual({
      client_key: filed.ref,
      install_id: expect.stringMatching(/^zh-[A-Za-z0-9-]{13,61}$/),
      text: 'The app closes when I open a talk',
      source: 'otis',
      app_version: '1.0.0',
      platform: 'ios',
      os_version: '18.1',
      device: 'iPhone 15',
    });
    expect(outbox()).toEqual([]);
  });

  it('the key fits what the server takes: 8 to 64 letters, digits and dashes', async () => {
    const { ref } = await fileReport(crashed);
    expect(ref).toMatch(/^[A-Za-z0-9-]{8,64}$/);
  });

  it('sends only what the person gave: no email, name or contact flag unless given', async () => {
    await fileReport({ ...crashed, source: 'form' });
    expect(Object.keys(body(0)).sort()).toEqual(['app_version', 'client_key', 'device', 'install_id', 'os_version', 'platform', 'source', 'text']);
    expect(body(0).source).toBe('form');
  });

  it('sends a tidied email, the name, the language and the screen when given', async () => {
    await fileReport({ ...crashed, email: ' Maria@Example.com. ', name: '  Maria Lopez ', may_contact: true, lang: 'es', screen: '/talk/12?x=1' });
    expect(body(0)).toMatchObject({ email: 'maria@example.com', may_contact: true, name: 'Maria Lopez', lang: 'es', screen: '/talk/12' });
  });

  it('an email without "OK to reply" is sent with may_contact false', async () => {
    await fileReport({ ...crashed, email: 'maria@example.com' });
    expect(body(0)).toMatchObject({ email: 'maria@example.com', may_contact: false });
  });

  it('leaves out an email that does not look like one, rather than losing the whole report', async () => {
    const filed = await fileReport({ ...crashed, email: 'maria@', may_contact: true });
    expect(filed.number).toBe('ZH-123');
    expect(body(0)).not.toHaveProperty('email');
    expect(body(0)).not.toHaveProperty('may_contact');
  });

  it('caps the text at what the server takes', async () => {
    await fileReport({ text: 'x'.repeat(5000), source: 'form' });
    expect(body(0).text).toHaveLength(4000);
  });

  it('gives every report its own key', async () => {
    const [a, b] = await Promise.all([fileReport(crashed), fileReport({ ...crashed, text: 'OTIS will not download' })]);
    expect(a.ref).not.toBe(b.ref);
    expect(send).toHaveBeenCalledTimes(2);
    expect(new Set([a.number, b.number])).toEqual(new Set(['ZH-123', 'ZH-124']));
    expect(new Set([body(0).client_key, body(1).client_key])).toEqual(new Set([a.ref, b.ref]));
  });

  it('never throws', async () => {
    send.mockReset().mockRejectedValue(new TypeError('boom'));
    await expect(fileReport(crashed)).resolves.toMatchObject({ queued: true });
  });
});

describe('fileReport with no signal', () => {
  it('saves the report on the phone and says so, with a reference made on the phone', async () => {
    noSignal();
    const filed = await fileReport(crashed);
    expect(filed).toEqual({ ref: expect.stringMatching(/^p-/), queued: true });
    expect(filed).not.toHaveProperty('number');
    expect(outbox().map((w) => w.key)).toEqual([filed.ref]);
    expect(send).toHaveBeenCalledTimes(1); // it tried once, and only once
  });

  it('is saved before anything is sent', async () => {
    let savedFirst = false;
    send.mockReset().mockImplementation(async () => {
      savedFirst = outbox().length === 1;
      throw new Error('no signal');
    });
    await fileReport(crashed);
    expect(savedFirst).toBe(true);
  });

  it('sends it later with the same key, exactly once', async () => {
    noSignal();
    const filed = await fileReport(crashed);
    await flushReports(); // still no signal
    expect(send).toHaveBeenCalledTimes(2);
    expect(outbox()).toHaveLength(1);

    online();
    await flushReports();
    expect(send).toHaveBeenCalledTimes(1);
    expect(body(0).client_key).toBe(filed.ref);
    expect(body(0).text).toBe(crashed.text);
    expect(outbox()).toEqual([]);

    await flushReports();
    await Promise.all([flushReports(), flushReports()]);
    expect(send).toHaveBeenCalledTimes(1); // no duplicate
  });

  it('a request that timed out but reached the server is sent again with the same key, so the server makes one ticket', async () => {
    send.mockReset().mockRejectedValueOnce(new Error('timed out'));
    const filed = await fileReport(crashed);
    send.mockResolvedValue({ number: 'ZH-123', status: 'new' });
    await flushReports();
    expect(send.mock.calls.map((c) => JSON.parse(c[1].body).client_key)).toEqual([filed.ref, filed.ref]);
    expect((await savedReports())[0]).toMatchObject({ ref: filed.ref, number: 'ZH-123', status: 'new' });
  });

  it('waits when the app has no server address, and sends once it does', async () => {
    (isConfigured as jest.Mock).mockReturnValue(false);
    const filed = await fileReport(crashed);
    expect(filed.queued).toBe(true);
    expect(send).not.toHaveBeenCalled();
    (isConfigured as jest.Mock).mockReturnValue(true);
    await Promise.all([flushReports(), flushReports()]);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('keeps the report when the server says slow down, drops it when the server refuses it for good', async () => {
    send.mockReset().mockRejectedValue(new ApiError(429));
    expect(await fileReport(crashed)).toMatchObject({ queued: true });
    expect(outbox()).toHaveLength(1);

    send.mockReset().mockRejectedValue(new ApiError(422));
    await flushReports();
    expect(outbox()).toEqual([]);
    await flushReports();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('a 500 from the server keeps the report for later', async () => {
    send.mockReset().mockRejectedValue(new ApiError(500));
    expect(await fileReport(crashed)).toMatchObject({ queued: true });
    expect(outbox()).toHaveLength(1);
  });

  it('sends queued reports oldest first, and stops at the first one that finds no signal', async () => {
    noSignal();
    const a = await fileReport({ ...crashed, text: 'first problem' });
    const b = await fileReport({ ...crashed, text: 'second problem' });
    expect(outbox().map((w) => w.key)).toEqual([a.ref, b.ref]);

    send.mockReset().mockRejectedValue(new Error('no signal'));
    await flushReports();
    expect(send).toHaveBeenCalledTimes(1); // the second is not tried behind a first that failed

    online();
    await flushReports();
    expect(send.mock.calls.map((c) => JSON.parse(c[1].body).text)).toEqual(['first problem', 'second problem']);
  });

  it('a damaged outbox does not jam the queue', async () => {
    mockStore.set('support_outbox', '{not json');
    await expect(flushReports()).resolves.toBeUndefined();
    expect(await fileReport(crashed)).toMatchObject({ number: 'ZH-123' });
    mockStore.set('support_outbox', JSON.stringify([null, 5, { key: 7 }, { nothing: true }]));
    await expect(flushReports()).resolves.toBeUndefined();
    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe('a report the server does not keep', () => {
  it('says failed, and leaves nothing waiting, when the server refuses it for good', async () => {
    send.mockReset().mockRejectedValue(new ApiError(422));
    const filed = await fileReport({ text: 'hm', source: 'form' });
    expect(filed).toEqual({ ref: expect.any(String), queued: false, failed: true, status: 422 });
    expect(outbox()).toEqual([]);
    expect(await savedReports()).toEqual([]);
  });

  it('says failed when reports are switched off on the server (it answers with no number)', async () => {
    send.mockReset().mockResolvedValue({ number: '', status: 'off' });
    expect(await fileReport(crashed)).toEqual({ ref: expect.any(String), queued: false, failed: true });
    expect(outbox()).toEqual([]);
    expect(await savedReports()).toEqual([]);
  });

  it('when the phone cannot save, it sends straight away and says what happened', async () => {
    mockFail.setItem = true;
    expect(await fileReport(crashed)).toMatchObject({ number: 'ZH-123', queued: false });
    noSignal();
    expect(await fileReport(crashed)).toMatchObject({ queued: false, failed: true });
  });
});

describe('my reports', () => {
  it('shows a report that is still waiting as queued, with its first line as the title', async () => {
    noSignal();
    const filed = await fileReport({ ...crashed, text: 'App closes\nwhen I open a talk' });
    const list = await savedReports();
    expect(list).toEqual([{ ref: filed.ref, status: 'queued', title: 'App closes', created_at: expect.stringMatching(/^\d{4}-\d\d-\d\dT/) }]);
    expect(await myReports()).toEqual(list); // no signal: the saved list, and no throw
  });

  it('remembers the ticket number once sent, so the list opens with no signal', async () => {
    const filed = await fileReport(crashed);
    noSignal();
    expect(await myReports()).toEqual([{ ref: filed.ref, number: 'ZH-123', status: 'new', title: crashed.text, created_at: expect.any(String) }]);
  });

  it("asks the server with a POST and the install id in the body, and takes the server's status and reply", async () => {
    const filed = await fileReport(crashed);
    tickets = [{ number: 'ZH-123', status: 'fixed', title: 'The app closes when I open a talk', created_at: '2026-11-10T17:00:00Z', updated_at: '2026-11-11T09:00:00Z', reply: 'Fixed in the next update.' }];
    send.mockClear();
    const list = await myReports();
    expect(send).toHaveBeenCalledTimes(1);
    expect(path(0)).toBe('/v2/support/mine');
    expect(send.mock.calls[0][1].method).toBe('POST');
    expect(body(0)).toEqual({ install_id: expect.stringMatching(/^zh-/) });
    expect(list).toEqual([{ ref: filed.ref, number: 'ZH-123', status: 'fixed', title: 'The app closes when I open a talk', created_at: '2026-11-10T17:00:00Z', reply: 'Fixed in the next update.' }]);

    noSignal();
    expect(await myReports()).toEqual(list); // the reply is kept for a dead spot
  });

  it('lists queued and sent reports together, newest first', async () => {
    tickets = [
      { number: 'ZH-7', status: 'closed', title: 'Old one', created_at: '2026-01-05T10:00:00Z', reply: '' },
      { number: 'ZH-9', status: 'in_progress', title: 'Newer one', created_at: '2026-03-05T10:00:00Z', reply: '' },
    ];
    await myReports();
    noSignal();
    const waiting = await fileReport({ ...crashed, text: 'Just now' });
    expect((await myReports()).map((r) => [r.number ?? r.ref, r.status])).toEqual([[waiting.ref, 'queued'], ['ZH-9', 'in_progress'], ['ZH-7', 'closed']]);
  });

  it('a report the server no longer lists drops off, but one sent a moment ago stays', async () => {
    tickets = [{ number: 'ZH-7', status: 'new', title: 'Old one', created_at: '2026-01-05T10:00:00Z' }];
    await myReports();
    const filed = await fileReport(crashed); // ZH-123, sent just now
    tickets = [];
    expect((await myReports()).map((r) => r.number)).toEqual(['ZH-123']);
    expect(filed.number).toBe('ZH-123');
  });

  it('never throws, and gives an empty list on a phone with nothing saved and no signal', async () => {
    noSignal();
    await expect(myReports()).resolves.toEqual([]);
    mockStore.set('support_reports', '{not json');
    await expect(myReports()).resolves.toEqual([]);
    (isConfigured as jest.Mock).mockReturnValue(false);
    await expect(myReports()).resolves.toEqual([]);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('an answer that is not a list changes nothing', async () => {
    const filed = await fileReport(crashed);
    send.mockReset().mockResolvedValue({ error: 'nope' });
    expect((await myReports()).map((r) => r.ref)).toEqual([filed.ref]);
  });
});

describe('mergeReports', () => {
  const now = Date.parse('2026-11-11T12:00:00Z');
  const saved: Report[] = [
    { ref: 'p-abc', number: 'ZH-5', status: 'new', title: 'Mine', created_at: '2026-11-01T10:00:00Z' },
    { ref: 'p-new', number: 'ZH-9', status: 'new', title: 'Sent a minute ago', created_at: '2026-11-11T11:59:00Z' },
    { ref: 'p-old', number: 'ZH-2', status: 'new', title: 'Gone from the server', created_at: '2026-10-01T10:00:00Z' },
  ];

  it("keeps the phone's own ref for a ticket it sent, and uses the number for one it did not", () => {
    const merged = mergeReports(saved, [{ number: 'ZH-5', status: 'in_progress', title: 'Mine', created_at: '2026-11-01T10:00:00Z', reply: 'Looking into it.' }, { number: 'ZH-6', status: 'new', title: 'From before a reinstall', created_at: '2026-11-02T10:00:00Z' }], now);
    expect(merged).toEqual([
      { ref: 'p-new', number: 'ZH-9', status: 'new', title: 'Sent a minute ago', created_at: '2026-11-11T11:59:00Z' },
      { ref: 'ZH-6', number: 'ZH-6', status: 'new', title: 'From before a reinstall', created_at: '2026-11-02T10:00:00Z' },
      { ref: 'p-abc', number: 'ZH-5', status: 'in_progress', title: 'Mine', created_at: '2026-11-01T10:00:00Z', reply: 'Looking into it.' },
    ]);
  });

  it('reads odd server rows safely: unknown status is "new", rows without a number and repeats are skipped', () => {
    const merged = mergeReports([], [{ number: 'ZH-1', status: 'weird', title: 5, created_at: null }, { status: 'new' }, null, 'x', { number: 'ZH-1', status: 'fixed' }, { number: '  ' }], now);
    expect(merged).toEqual([{ ref: 'ZH-1', number: 'ZH-1', status: 'new', title: '', created_at: '' }]);
  });

  it('keeps at most 30', () => {
    const many = Array.from({ length: 50 }, (_, i) => ({ number: `ZH-${i}`, status: 'new', title: 't', created_at: new Date(now - i * 1000).toISOString() }));
    expect(mergeReports([], many, now)).toHaveLength(30);
  });
});

describe('reportAnswer', () => {
  const flagged = { question: 'Who can remove a lock?', answer: 'Anyone on the crew. [1]', modelKey: 'builtin-QWEN3_0_6B', lang: 'en' as const };

  it('sends that one question and answer through the same outbox', async () => {
    const filed = await reportAnswer(flagged);
    expect(filed).toEqual({ ref: expect.any(String), number: 'ZH-123', queued: false });
    expect(path(0)).toBe('/v2/support/report');
    expect(body(0)).toEqual({
      client_key: filed.ref,
      install_id: expect.stringMatching(/^zh-/),
      source: 'otis_answer',
      text: 'Flagged OTIS answer',
      question: 'Who can remove a lock?',
      answer: 'Anyone on the crew. [1]',
      model_key: 'builtin-QWEN3_0_6B',
      lang: 'en',
      app_version: '1.0.0',
      platform: 'ios',
      os_version: '18.1',
      device: 'iPhone 15',
    });
  });

  it("carries the person's note when there is one, and caps every field", async () => {
    await reportAnswer({ question: 'q'.repeat(900), answer: 'a'.repeat(5000), modelKey: 'm'.repeat(100), lang: 'es', note: '  This is wrong for our site  ' });
    expect(body(0).text).toBe('This is wrong for our site');
    expect(body(0).question).toHaveLength(500);
    expect(body(0).answer).toHaveLength(2000);
    expect(body(0).model_key).toHaveLength(60);
    expect(body(0).lang).toBe('es');
  });

  it('waits on the phone with no signal and goes out later, once', async () => {
    noSignal();
    const filed = await reportAnswer(flagged);
    expect(filed).toEqual({ ref: expect.any(String), queued: true });
    online();
    await flushReports();
    await flushReports();
    expect(send).toHaveBeenCalledTimes(1);
    expect(body(0)).toMatchObject({ client_key: filed.ref, source: 'otis_answer', question: flagged.question });
  });

  it('is not listed under My reports: that list is for problem reports, as on the server', async () => {
    noSignal();
    await reportAnswer(flagged);
    expect(await savedReports()).toEqual([]);
    online();
    await flushReports();
    expect(await savedReports()).toEqual([]);
  });
});

describe('review fixes: one report never holds up the rest', () => {
  const timeout = () => Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' });

  it('with an older report stuck on a weak signal, Send waits through one try, not two, and says saved', async () => {
    noSignal();
    await fileReport({ ...crashed, text: 'first problem' });
    send.mockReset().mockRejectedValue(timeout());
    const filed = await fileReport({ ...crashed, text: 'second problem' });
    expect(filed).toEqual({ ref: expect.any(String), queued: true });
    expect(send).toHaveBeenCalledTimes(1); // the older report, once; the same one is not sent again straight after
    expect(outbox()).toHaveLength(2);
  });

  it('an older report the server keeps failing on (5xx) is passed over, so the new one still goes', async () => {
    noSignal();
    await fileReport({ ...crashed, text: 'first problem' });
    send.mockReset().mockImplementation(async (_p: string, init: { body: string }) => {
      if (JSON.parse(init.body).text === 'first problem') throw new ApiError(500);
      return { number: `ZH-${nextNumber++}`, status: 'new' };
    });
    const filed = await fileReport({ ...crashed, text: 'second problem' });
    expect(filed).toMatchObject({ number: 'ZH-123', queued: false });
    expect(outbox()).toHaveLength(1); // the first waits for the next try
    online();
    await flushReports();
    expect(outbox()).toEqual([]);
  });
});

describe('review fixes: a saved report never vanishes without a word', () => {
  it('keeps a report waiting when the server answers 404 (support not there yet), 401, 403 or 429', async () => {
    for (const status of [404, 401, 403, 429]) {
      mockStore.clear();
      send.mockReset().mockRejectedValue(new ApiError(status));
      const filed = await fileReport(crashed);
      expect(filed).toEqual({ ref: expect.any(String), queued: true });
      expect(outbox()).toHaveLength(1);
    }
  });

  it('a waiting report the server then turns down for good stays in My reports as "could not be sent"', async () => {
    noSignal();
    const filed = await fileReport({ ...crashed, text: 'App closes\nevery time' });
    send.mockReset().mockImplementation(async (p: string) => {
      if (p === '/v2/support/mine') return { tickets: [] };
      throw new ApiError(422);
    });
    await flushReports();
    expect(outbox()).toEqual([]);
    const list = await myReports();
    expect(list).toEqual([{ ref: filed.ref, status: 'failed', title: 'App closes', created_at: expect.any(String) }]);
  });

  it('a flagged answer that is turned down later is not listed: it was never one of My reports', async () => {
    noSignal();
    await reportAnswer({ question: 'q?', answer: 'a.', modelKey: 'm', lang: 'en' });
    send.mockReset().mockRejectedValue(new ApiError(422));
    await flushReports();
    expect(await savedReports()).toEqual([]);
  });

  it('with 30 waiting, a new report is refused with a plain line; none of the 30 is deleted', async () => {
    noSignal();
    for (let i = 1; i <= 30; i++) await fileReport({ ...crashed, text: `report number ${i}` });
    const filed = await fileReport({ ...crashed, text: 'report number 31' });
    expect(filed).toMatchObject({ queued: false, failed: true, full: true });
    expect(outbox()).toHaveLength(30);
    expect((outbox()[0] as unknown as { body: { text: string } }).body.text).toBe('report number 1');
    expect(whyNotSent('en', filed)).toBe('This phone already has 30 reports waiting for a signal. Send this one after those go out.');
    expect(whyNotSent('es', filed)).toMatch(/^Este teléfono ya tiene 30 reportes/);
  });

  it('whyNotSent asks for more words on a 422 and is silent otherwise', () => {
    expect(whyNotSent('en', { ref: 'p', queued: false, failed: true, status: 422 })).toBe('Tell us a little more about what happened, then send it again.');
    expect(whyNotSent('es', { ref: 'p', queued: false, failed: true, status: 422 })).toBe('Cuéntenos un poco más de lo que pasó y envíelo otra vez.');
    expect(whyNotSent('en', { ref: 'p', queued: false, failed: true })).toBeNull();
    expect(whyNotSent('en', { ref: 'p', queued: true })).toBeNull();
  });

  it('a "could not be sent" row is dropped from the list after a month', () => {
    const now = Date.parse('2026-11-11T17:00:00Z');
    const row: Report = { ref: 'p-1', status: 'failed', title: 'x', created_at: '2026-11-01T17:00:00Z' };
    expect(mergeReports([row], [], now)).toEqual([row]);
    expect(mergeReports([{ ...row, created_at: '2026-09-01T17:00:00Z' }], [], now)).toEqual([]);
  });
});

describe('review fixes: words', () => {
  it('longEnough counts an emoji as one character, as the server does', () => {
    expect('😀😀a'.trim().length).toBe(5);
    expect(longEnough('😀😀a')).toBe(false);
    expect(longEnough('😀😀😀😀😀')).toBe(true);
    expect(longEnough('  abcd  ')).toBe(false);
    expect(longEnough('abcde')).toBe(true);
    expect(REPORT_MIN).toBe(5);
  });

  it('the "Report this answer" confirm names everything reportAnswer sends, in both languages', async () => {
    await reportAnswer({ question: 'q?', answer: 'a.', modelKey: 'm', lang: 'en' });
    const sent = body(0);
    expect(Object.keys(sent).sort()).toEqual(['answer', 'app_version', 'client_key', 'device', 'install_id', 'lang', 'model_key', 'os_version', 'platform', 'question', 'source', 'text']);
    expect(ANSWER_REPORT_SENDS.en).toBe(
      'Send this question and answer to Trainovate so a person can review it? Which OTIS model answered, iPhone or Android, your phone model, the system version, the app version and a random id for this app go with it.',
    );
    for (const words of [/question/, /answer/, /OTIS model/, /iPhone or Android/, /phone model/, /system version/, /app version/, /random id/]) expect(ANSWER_REPORT_SENDS.en).toMatch(words);
    for (const words of [/pregunta/, /respuesta/, /modelo de OTIS/, /si es iPhone o Android/, /modelo de su teléfono/, /versión del sistema/, /versión de la app/, /número al azar/]) expect(ANSWER_REPORT_SENDS.es).toMatch(words);
  });

  it('the line shown before sending is the shared one, in both languages', () => {
    expect(BEFORE_SENDING.en).toBe('This goes to Trainovate, who make the app, not to your employer. For a hazard at work, tell your supervisor. If someone is hurt, call 911.');
    expect(BEFORE_SENDING.es).toMatch(/Trainovate.*no a su empleador.*supervisor.*911/);
  });
});
