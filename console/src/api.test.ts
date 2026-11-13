import { readFileSync } from 'node:fs';

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { api, ApiError, detailText, jurisdictionCode, onConnection, ROUTE_PREFIXES, type Connection } from './api';

type Call = { url: string; method: string; headers: Record<string, string>; body: string | undefined };

let calls: Call[];
let reply: () => Promise<Response>;

function respond(status: number, body: string, statusText = '') {
  reply = async () => new Response(status === 204 ? null : body, { status, statusText });
}

beforeEach(() => {
  calls = [];
  respond(200, '{}');
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    calls.push({ url, method: String(init.method), headers: init.headers as Record<string, string>, body: init.body as string | undefined });
    return reply();
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('request building', () => {
  test('GET goes under /api with the console header and no body', async () => {
    respond(200, JSON.stringify({ issue: 12, title: 'Ladders' }));
    const t = await api.talk(12);
    expect(t).toEqual({ issue: 12, title: 'Ladders' });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/console/talks/12/');
    expect(calls[0].method).toBe('GET');
    expect(calls[0].headers['X-ZeroHarm-Console']).toBe('1');
    expect(calls[0].headers['Content-Type']).toBe('application/json');
    expect(calls[0].body).toBeUndefined();
  });

  test('PATCH sends the patch as JSON', async () => {
    await api.updateTalk(7, { title: 'New title', published: true });
    expect(calls[0].method).toBe('PATCH');
    expect(calls[0].url).toBe('/api/console/talks/7/');
    expect(JSON.parse(calls[0].body!)).toEqual({ title: 'New title', published: true });
  });

  test('push sends {} normally and {force:true} when forced', async () => {
    await api.pushTalk(3);
    await api.pushTalk(3, true);
    await api.pushFeed(9, true);
    expect(calls.map((c) => [c.method, c.url, c.body])).toEqual([
      ['POST', '/api/console/talks/3/push/', '{}'],
      ['POST', '/api/console/talks/3/push/', '{"force":true}'],
      ['POST', '/api/console/feed/9/push/', '{"force":true}'],
    ]);
  });

  test('DELETE unpublishes a feed item or a knowledge base entry, with no body', async () => {
    await api.unpublishFeed(5);
    await api.unpublishKb(8);
    expect(calls.map((c) => [c.method, c.url, c.body])).toEqual([
      ['DELETE', '/api/console/feed/5/', undefined],
      ['DELETE', '/api/console/kb/8/', undefined],
    ]);
  });

  test('episode push and Spanish draft hit their own endpoints with an empty JSON body', async () => {
    await api.pushEpisode(14);
    await api.draftSpanish(31);
    expect(calls.map((c) => [c.method, c.url, c.body])).toEqual([
      ['POST', '/api/console/episodes/14/push/', '{}'],
      ['POST', '/api/console/talks/31/spanish-draft/', '{}'],
    ]);
  });

  test('broadcast posts the full input, including dry_run', async () => {
    respond(200, JSON.stringify({ ok: true, detail: 'dry run' }));
    const r = await api.broadcast({ audience: 'alerts', heading: 'H', message: 'M', route: '/alert/4', dry_run: true });
    expect(r).toEqual({ ok: true, detail: 'dry run' });
    expect(calls[0].url).toBe('/api/console/broadcast/');
    expect(JSON.parse(calls[0].body!)).toEqual({ audience: 'alerts', heading: 'H', message: 'M', route: '/alert/4', dry_run: true });
  });

  test('list endpoints unwrap their envelope', async () => {
    respond(200, JSON.stringify({ talks: [{ issue: 1 }, { issue: 2 }] }));
    expect(await api.talks()).toEqual([{ issue: 1 }, { issue: 2 }]);
    respond(200, JSON.stringify({ entries: [{ id: 4 }] }));
    expect(await api.kb()).toEqual([{ id: 4 }]);
    respond(200, JSON.stringify({ items: [] }));
    expect(await api.feed()).toEqual([]);
  });

  test('an empty success body comes back as null', async () => {
    respond(204, '');
    expect(await api.overview()).toBeNull();
  });
});

describe('support tickets', () => {
  const ticket = {
    id: 12, number: 'ZH-12', kind: 'problem', status: 'new', source: 'form', title: 'The app closes', text: 'The app closes when I open a talk.',
    reply: '', owner_note: '', count: 1, app_version: '1.4.0', platform: 'android', os_version: '15', device: 'Pixel 8', screen: '/talk/[id]',
    lang: 'en', name: 'Sam', email: 'sam@example.com', may_contact: true, created_at: '2026-11-10T18:00:00Z', updated_at: '2026-11-10T18:00:00Z', last_seen: null,
  };

  test('the list asks for open tickets of every kind unless told otherwise, and unwraps its envelope', async () => {
    respond(200, JSON.stringify({ tickets: [ticket] }));
    expect(await api.tickets()).toEqual([ticket]);
    expect(calls[0].method).toBe('GET');
    expect(calls[0].url).toBe('/api/console/tickets/?status=open&kind=all');
    expect(calls[0].body).toBeUndefined();
  });

  test('the list sends the chosen status and kind, one at a time or together', async () => {
    respond(200, JSON.stringify({ tickets: [] }));
    await api.tickets({ status: 'in_progress', kind: 'crash' });
    await api.tickets({ status: 'all' });
    await api.tickets({ kind: 'answer' });
    await api.tickets({ status: 'closed', kind: 'problem' });
    expect(calls.map((c) => c.url)).toEqual([
      '/api/console/tickets/?status=in_progress&kind=crash',
      '/api/console/tickets/?status=all&kind=all',
      '/api/console/tickets/?status=open&kind=answer',
      '/api/console/tickets/?status=closed&kind=problem',
    ]);
  });

  test('one ticket comes back with its crash reports beside it', async () => {
    const crash = { created_at: '2026-11-10T18:00:00Z', fatal: true, name: 'TypeError', message: 'x is undefined', stack: 'at a\nat b', screen: '/otis', app_version: '1.4.0', platform: 'ios', os_version: '26.1', device: 'iPhone 17' };
    respond(200, JSON.stringify({ ticket: { ...ticket, kind: 'crash', count: 3 }, crashes: [crash] }));
    const d = await api.ticket(12);
    expect(calls[0].method).toBe('GET');
    expect(calls[0].url).toBe('/api/console/tickets/12/');
    expect(d.ticket.count).toBe(3);
    expect(d.crashes).toEqual([crash]);
  });

  test('a save PATCHes only what it is given and unwraps the saved ticket', async () => {
    respond(200, JSON.stringify({ ticket: { ...ticket, status: 'fixed', reply: 'Fixed in 1.4.1.' } }));
    const saved = await api.updateTicket(12, { status: 'fixed', reply: 'Fixed in 1.4.1.' });
    expect(calls[0].method).toBe('PATCH');
    expect(calls[0].url).toBe('/api/console/tickets/12/');
    expect(JSON.parse(calls[0].body!)).toEqual({ status: 'fixed', reply: 'Fixed in 1.4.1.' });
    expect(saved.status).toBe('fixed');
    expect(saved.reply).toBe('Fixed in 1.4.1.');
  });

  test('a private note is sent as owner_note, never as reply', async () => {
    respond(200, JSON.stringify({ ticket }));
    await api.updateTicket(12, { owner_note: 'Same bug as ZH-9.' });
    expect(JSON.parse(calls[0].body!)).toEqual({ owner_note: 'Same bug as ZH-9.' });
  });

  test('a field problem (400) gives the server’s own sentence and leaves the connection banner alone', async () => {
    const seen: Connection[] = [];
    const off = onConnection((c) => seen.push(c));
    respond(400, JSON.stringify({ error: 'reply can be 2000 characters at most.' }), 'Bad Request');
    const err = await api.updateTicket(12, { reply: 'x'.repeat(2001) }).catch((e) => e);
    off();
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.message).toBe('reply can be 2000 characters at most.');
    expect(seen).toEqual([]);
  });

  test('an unknown ticket (404) gives the server’s sentence', async () => {
    respond(404, JSON.stringify({ error: 'No ticket with that number.' }), 'Not Found');
    const err = await api.ticket(999).catch((e) => e);
    expect(err.status).toBe(404);
    expect(err.message).toBe('No ticket with that number.');
  });

  test('without the console key (401) the list fails and the banner is told', async () => {
    const seen: Connection[] = [];
    const off = onConnection((c) => seen.push(c));
    respond(401, JSON.stringify({ error: 'Not authorized.' }));
    const err = await api.tickets().catch((e) => e);
    off();
    expect(err.status).toBe(401);
    expect(seen).toEqual([{ ok: false, status: 401, error: 'Not authorized.' }]);
  });
});

describe('knowledge base kind', () => {
  test('a new entry carries its kind', async () => {
    respond(201, JSON.stringify({ id: 9, title: 'The app keeps closing', body: '1. Close the app.', source: 'Zero Harm app help', tags: 'crash', published: true, kind: 'support' }));
    const made = await api.createKb({ kind: 'support', title: 'The app keeps closing', body: '1. Close the app.', source: 'Zero Harm app help', tags: 'crash', published: true });
    expect(calls[0].method).toBe('POST');
    expect(calls[0].url).toBe('/api/console/kb/');
    expect(JSON.parse(calls[0].body!).kind).toBe('support');
    expect(made.kind).toBe('support');
  });

  test('the server’s rule about OSHA numbers in app help comes back as its own sentence', async () => {
    const error = "App help can't name an OSHA section number (like 1910.147). Take the number out, or make this a safety entry.";
    respond(400, JSON.stringify({ error }), 'Bad Request');
    const err = await api.updateKb(9, { kind: 'support' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe(error);
  });

  test('changing only the kind sends only the kind', async () => {
    respond(200, JSON.stringify({ id: 9, kind: 'safety' }));
    await api.updateKb(9, { kind: 'safety' });
    expect(calls[0].method).toBe('PATCH');
    expect(calls[0].url).toBe('/api/console/kb/9/');
    expect(JSON.parse(calls[0].body!)).toEqual({ kind: 'safety' });
  });
});

describe('errors', () => {
  test('uses the server "error" message and keeps the status', async () => {
    respond(400, JSON.stringify({ error: 'Title is required.' }), 'Bad Request');
    const err = await api.createKb({ body: 'x' }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.message).toBe('Title is required.');
  });

  test('a non-JSON error page falls back to status and status text', async () => {
    respond(502, '<html>Bad gateway</html>', 'Bad Gateway');
    const err = await api.overview().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(502);
    expect(err.message).toBe('The API answered 502 Bad Gateway.');
  });

  test('a JSON error without an "error" key also falls back', async () => {
    respond(500, JSON.stringify({ detail: 'boom' }), 'Internal Server Error');
    const err = await api.overview().catch((e) => e);
    expect(err.message).toBe('The API answered 500 Internal Server Error.');
  });

  test('an unreachable console server becomes status 0 with a start-it hint', async () => {
    reply = () => Promise.reject(new TypeError('Failed to fetch'));
    const err = await api.overview().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/npm run dev/);
  });
});

describe('connection reporting', () => {
  let seen: Connection[];
  let off: () => void;

  beforeEach(() => {
    seen = [];
    off = onConnection((c) => seen.push(c));
  });

  afterEach(() => off());

  test('a success reports the connection as ok', async () => {
    await api.overview();
    expect(seen).toEqual([{ ok: true, status: 200, error: '' }]);
  });

  // Every status the console server or backend uses to say "the console can't work at all":
  // 401 wrong key, 403 guard refused (wrong host/origin), 429 key lockout, 502 proxy can't reach the API,
  // 503 console off / not configured, 504 gateway timeout.
  test.each([
    [401, 'Not authorized.'],
    [403, 'Open the console at http://127.0.0.1:5174.'],
    [429, 'Too many wrong keys from this network. Try again in an hour.'],
    [502, "Can't reach the Zero Harm API at https://api.example (ECONNREFUSED)."],
    [503, 'Set CONSOLE_KEY in console/.env.local, then restart npm run dev.'],
    [504, 'Gateway timeout'],
  ])('status %i reports the connection as down with the server message', async (status, error) => {
    respond(status, JSON.stringify({ error }));
    const err = await api.overview().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(seen).toEqual([{ ok: false, status, error }]);
  });

  test('errors about one request (400/404/405/409/500) do not flip the connection banner', async () => {
    respond(400, JSON.stringify({ error: 'Bad field' }), 'Bad Request');
    await api.updateKb(1, { title: '' }).catch(() => undefined);
    respond(404, JSON.stringify({ error: 'No such talk' }), 'Not Found');
    await api.talk(999).catch(() => undefined);
    respond(405, JSON.stringify({ error: 'Method not allowed.' }));
    await api.overview().catch(() => undefined);
    respond(409, JSON.stringify({ error: "This talk isn't live in the app yet" }));
    await api.pushTalk(2).catch(() => undefined);
    respond(500, JSON.stringify({ error: 'Something went wrong on the server.' }));
    await api.overview().catch(() => undefined);
    expect(seen).toEqual([]);
  });

  test('a network failure reports status 0 with the same message the caller gets', async () => {
    reply = () => Promise.reject(new TypeError('Failed to fetch'));
    const err = await api.overview().catch((e) => e);
    expect(seen).toEqual([{ ok: false, status: 0, error: err.message }]);
  });

  test('a success after an outage clears the banner', async () => {
    reply = () => Promise.reject(new TypeError('Failed to fetch'));
    await api.overview().catch(() => undefined);
    respond(200, '{}');
    await api.overview();
    expect(seen.map((c) => c.ok)).toEqual([false, true]);
  });

  test('unsubscribing stops further reports', async () => {
    off();
    await api.overview();
    expect(seen).toEqual([]);
  });
});

describe('jurisdictionCode', () => {
  test('accepts either the stored code or the display name', () => {
    expect(jurisdictionCode('federal')).toBe('federal');
    expect(jurisdictionCode('Federal OSHA')).toBe('federal');
    expect(jurisdictionCode('Las Vegas')).toBe('las_vegas');
    expect(jurisdictionCode('nevada')).toBe('nevada');
  });

  test('unknown or empty becomes no jurisdiction', () => {
    expect(jurisdictionCode(null)).toBe('');
    expect(jurisdictionCode('')).toBe('');
    expect(jurisdictionCode('California')).toBe('');
  });
});

describe('detailText', () => {
  test('turns OneSignal detail into one line', () => {
    expect(detailText(null)).toBe('');
    expect(detailText(undefined)).toBe('');
    expect(detailText('queued')).toBe('queued');
    expect(detailText({ id: 'abc', recipients: 12 })).toBe('{"id":"abc","recipients":12}');
    expect(detailText(['a', 'b'])).toBe('["a","b"]');
  });

  test('a circular object falls back to String() instead of throwing', () => {
    const o: Record<string, unknown> = {};
    o.self = o;
    expect(detailText(o)).toBe('[object Object]');
  });
});

// ROUTE_PREFIXES must stay in step with the two places that actually decide which routes work:
// the app's push click handler (lib/push.ts safeRoute) and the backend's broadcast check (console.py ROUTE).
// Read them from source so a route added or dropped on either side fails here instead of shipping a dead link.
describe('ROUTE_PREFIXES matches what the app and backend accept', () => {
  const root = new URL('../../', import.meta.url);
  const push = readFileSync(new URL('lib/push.ts', root), 'utf8');
  const backend = readFileSync(new URL('backend/talks/console.py', root), 'utf8');

  const fixed: string[] = JSON.parse(push.match(/const FIXED_ROUTES = (\[[^\]]*\]);/)![1].replace(/'/g, '"'));
  const idRoute = new RegExp(push.match(/const ID_ROUTE = \/(.+)\/;/)![1]);
  const backendRoute = new RegExp(backend.match(/ROUTE = re\.compile\(r"(.+)"\)/)![1]);
  const sample = (prefix: string) => (prefix.endsWith('/') ? `${prefix}12` : prefix);

  test('every console prefix opens a screen in the app', () => {
    for (const p of ROUTE_PREFIXES) {
      const route = sample(p);
      expect(fixed.includes(route) || idRoute.test(route), route).toBe(true);
    }
  });

  test('every console prefix passes the backend broadcast check', () => {
    for (const p of ROUTE_PREFIXES) expect(backendRoute.test(sample(p)), sample(p)).toBe(true);
  });

  test('every route the app can open is offered by the console', () => {
    for (const r of fixed) expect(ROUTE_PREFIXES).toContain(r);
    const idKinds = push.match(/const ID_ROUTE = \/\^\\\/\(([^)]+)\)/)![1].split('|');
    for (const k of idKinds) expect(ROUTE_PREFIXES).toContain(`/${k}/`);
  });
});
