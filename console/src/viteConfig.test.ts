import type { IncomingMessage, ServerResponse } from 'node:http';

import { describe, expect, test } from 'vitest';

import { apiUrlProblem, guard } from '../vite.config';

describe('apiUrlProblem (the key only travels over https, or http to this Mac)', () => {
  test('https is fine anywhere', () => {
    expect(apiUrlProblem('https://api.zeroharm.app')).toBe('');
    expect(apiUrlProblem('https://api.zeroharm.app:8443/base')).toBe('');
    expect(apiUrlProblem('HTTPS://API.ZEROHARM.APP')).toBe('');
  });

  test('plain http is fine only for a local backend', () => {
    expect(apiUrlProblem('http://localhost:8000')).toBe('');
    expect(apiUrlProblem('http://LOCALHOST:8000')).toBe('');
    expect(apiUrlProblem('http://127.0.0.1:8000')).toBe('');
    expect(apiUrlProblem('http://[::1]:8000')).toBe('');
  });

  test('plain http to anything else is refused', () => {
    const msg = /must start with https:\/\//;
    expect(apiUrlProblem('http://api.zeroharm.app')).toMatch(msg);
    expect(apiUrlProblem('http://localhost.evil.com')).toMatch(msg);
    expect(apiUrlProblem('http://127.0.0.1.nip.io')).toMatch(msg);
    expect(apiUrlProblem('http://192.168.1.20:8000')).toMatch(msg);
    expect(apiUrlProblem('http://0.0.0.0:8000')).toMatch(msg);
  });

  test('other schemes are refused', () => {
    expect(apiUrlProblem('ftp://localhost')).toMatch(/must start with https/);
    expect(apiUrlProblem('ws://localhost:8000')).toMatch(/must start with https/);
  });

  test('missing or malformed values say what to fix', () => {
    expect(apiUrlProblem('')).toMatch(/Set CONSOLE_API_URL/);
    expect(apiUrlProblem('api.zeroharm.app')).toBe('CONSOLE_API_URL "api.zeroharm.app" is not a web address. Use https://, then restart npm run dev.');
  });
});

type Sent = { status: number; error: string } | 'next';

function call(mw: ReturnType<typeof guard>, url: string, headers: Record<string, string>): Sent {
  let sent: Sent | null = null;
  let status = 0;
  const res = {
    headersSent: false,
    writeHead(s: number) { status = s; return this; },
    end(body: string) { sent = { status, error: JSON.parse(body).error }; },
  } as unknown as ServerResponse;
  const req = { url, headers } as unknown as IncomingMessage;
  mw(req, res, () => { sent = 'next'; });
  if (sent === null) throw new Error('guard neither answered nor called next');
  return sent;
}

const GOOD = { host: '127.0.0.1:5174', origin: 'http://127.0.0.1:5174', 'x-zeroharm-console': '1' };
const ok = guard('https://api.zeroharm.app', 'k'.repeat(40));

describe('guard (only the console page may use the keyed proxy)', () => {
  test('lets a well-formed console request through', () => {
    expect(call(ok, '/api/console/overview/', GOOD)).toBe('next');
  });

  test('accepts localhost as well as 127.0.0.1, and a request without Origin', () => {
    expect(call(ok, '/api/x', { host: 'localhost:5174', origin: 'http://localhost:5174', 'x-zeroharm-console': '1' })).toBe('next');
    expect(call(ok, '/api/x', { host: '127.0.0.1:5174', 'x-zeroharm-console': '1' })).toBe('next');
  });

  test('does not touch non-API requests (the page and its assets)', () => {
    expect(call(ok, '/', {})).toBe('next');
    expect(call(ok, '/src/main.tsx', { host: 'evil.com' })).toBe('next');
  });

  test('blocks a foreign Host (DNS rebinding)', () => {
    expect(call(ok, '/api/x', { ...GOOD, host: 'evil.com:5174' })).toEqual({ status: 403, error: 'Open the console at http://127.0.0.1:5174.' });
    expect(call(ok, '/api/x', { ...GOOD, host: '127.0.0.1:5175' })).toMatchObject({ status: 403 });
    const { host: _omit, ...noHost } = GOOD;
    expect(call(ok, '/api/x', noHost)).toMatchObject({ status: 403 });
  });

  test('blocks requests from other sites', () => {
    expect(call(ok, '/api/x', { ...GOOD, origin: 'https://evil.com' })).toEqual({ status: 403, error: 'Requests from other sites are blocked.' });
    expect(call(ok, '/api/x', { ...GOOD, origin: 'http://127.0.0.1:5175' })).toMatchObject({ status: 403 });
    // file:// pages and sandboxed iframes send the literal string "null"; it must not count as "no Origin".
    expect(call(ok, '/api/x', { ...GOOD, origin: 'null' })).toMatchObject({ status: 403 });
  });

  test('guards the bare /api path too, not just /api/...', () => {
    expect(call(ok, '/api', { host: 'evil.com' })).toMatchObject({ status: 403 });
  });

  test('a foreign site is refused even when the key and URL are missing (403 before 503)', () => {
    const misconfigured = guard('', '');
    expect(call(misconfigured, '/api/x', { ...GOOD, origin: 'https://evil.com' })).toMatchObject({ status: 403 });
  });

  test('blocks requests without the console header', () => {
    const { 'x-zeroharm-console': _omit, ...noHeader } = GOOD;
    expect(call(ok, '/api/x', noHeader)).toEqual({ status: 403, error: 'Requests must come from the console page.' });
    expect(call(ok, '/api/x', { ...GOOD, 'x-zeroharm-console': 'true' })).toMatchObject({ status: 403 });
  });

  test('a bad API URL answers 503 with the URL problem', () => {
    const mw = guard('http://api.zeroharm.app', 'k'.repeat(40));
    expect(call(mw, '/api/x', GOOD)).toEqual({ status: 503, error: apiUrlProblem('http://api.zeroharm.app') });
  });

  test('a missing key answers 503', () => {
    const mw = guard('https://api.zeroharm.app', '');
    expect(call(mw, '/api/x', GOOD)).toEqual({ status: 503, error: 'Set CONSOLE_KEY in console/.env.local, then restart npm run dev.' });
  });
});
