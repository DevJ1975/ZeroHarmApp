import { afterEach, describe, expect, test, vi } from 'vitest';

import { formatPacific, fromLocalInput, isFuture, toLocalInput } from './time';

// Intl puts a narrow no-break space before AM/PM; compare with plain spaces.
const plain = (s: string) => s.replace(/\s/g, ' ');

describe('toLocalInput (API ISO -> datetime-local in Pacific)', () => {
  test('converts a UTC instant to Pacific standard time in winter', () => {
    expect(toLocalInput('2026-11-16T19:59:00Z')).toBe('2026-11-16T11:59');
  });

  test('converts a UTC instant to Pacific daylight time in summer', () => {
    expect(toLocalInput('2026-07-04T19:00:00Z')).toBe('2026-07-04T12:00');
  });

  test('respects an explicit offset in the ISO string', () => {
    expect(toLocalInput('2026-07-04T15:00:00-04:00')).toBe('2026-07-04T12:00');
  });

  test('rolls back across the date (and year) line', () => {
    expect(toLocalInput('2026-01-01T05:00:00Z')).toBe('2025-12-31T21:00');
  });

  test('shows midnight as 00, not 24', () => {
    expect(toLocalInput('2026-11-16T08:00:00Z')).toBe('2026-11-16T00:00');
  });

  test('spring forward: 01:59 PST is followed directly by 03:00 PDT', () => {
    expect(toLocalInput('2026-03-08T09:59:00Z')).toBe('2026-03-08T01:59');
    expect(toLocalInput('2026-03-08T10:00:00Z')).toBe('2026-03-08T03:00');
  });

  test('fall back: both 01:30s show as 01:30 local', () => {
    expect(toLocalInput('2026-11-01T08:30:00Z')).toBe('2026-11-01T01:30'); // PDT
    expect(toLocalInput('2026-11-01T09:30:00Z')).toBe('2026-11-01T01:30'); // PST
    expect(toLocalInput('2026-11-01T10:00:00Z')).toBe('2026-11-01T02:00');
  });

  test('empty, null, undefined and garbage become an empty input', () => {
    expect(toLocalInput('')).toBe('');
    expect(toLocalInput(null)).toBe('');
    expect(toLocalInput(undefined)).toBe('');
    expect(toLocalInput('not a date')).toBe('');
  });
});

describe('fromLocalInput (datetime-local -> naive Pacific ISO)', () => {
  test('adds seconds and no offset', () => {
    expect(fromLocalInput('2026-11-16T11:59')).toBe('2026-11-16T11:59:00');
  });

  test('empty stays empty', () => {
    expect(fromLocalInput('')).toBe('');
  });

  test('round-trips an API time to the same Pacific wall clock', () => {
    expect(fromLocalInput(toLocalInput('2026-07-04T19:00:00Z'))).toBe('2026-07-04T12:00:00');
  });
});

describe('formatPacific', () => {
  test('formats a winter instant in PT', () => {
    expect(plain(formatPacific('2026-11-16T19:59:00Z'))).toBe('Mon, Nov 16, 11:59 AM PT');
  });

  test('formats a summer instant in PT', () => {
    expect(plain(formatPacific('2026-07-04T19:00:00Z'))).toBe('Sat, Jul 4, 12:00 PM PT');
  });

  test('formats both sides of the spring-forward gap', () => {
    expect(plain(formatPacific('2026-03-08T09:59:00Z'))).toBe('Sun, Mar 8, 1:59 AM PT');
    expect(plain(formatPacific('2026-03-08T10:00:00Z'))).toBe('Sun, Mar 8, 3:00 AM PT');
  });

  test('missing value shows a dash, unparseable value is shown as-is', () => {
    expect(formatPacific(null)).toBe('—');
    expect(formatPacific(undefined)).toBe('—');
    expect(formatPacific('')).toBe('—');
    expect(formatPacific('soon')).toBe('soon');
  });
});

describe('isFuture', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  test('compares against the current time', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-10T12:00:00Z'));
    expect(isFuture('2026-11-10T12:00:01Z')).toBe(true);
    expect(isFuture('2026-11-10T12:00:00Z')).toBe(false);
    expect(isFuture('2026-11-10T11:59:59Z')).toBe(false);
  });

  test('missing or garbage is not in the future', () => {
    expect(isFuture(null)).toBe(false);
    expect(isFuture(undefined)).toBe(false);
    expect(isFuture('')).toBe(false);
    expect(isFuture('not a date')).toBe(false);
  });
});
