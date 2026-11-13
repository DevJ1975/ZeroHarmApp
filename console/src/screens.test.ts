import { afterEach, describe, expect, test, vi } from 'vitest';

import type { Overview } from './api';
import { SCREENS, screenFromHash } from './nav';
import { feedAudience } from './screens/Feed';
import { kbProblem, KB_KINDS, kindLost, kindOf } from './screens/Kb';
import { warningsFor } from './screens/Overview';

describe('feedAudience (who a feed push reaches)', () => {
  test('alerts go to the Regulatory alerts group', () => {
    expect(feedAudience('alert')).toBe('everyone with Regulatory alerts on');
  });

  test('everything else is promotional and goes to News and offers only', () => {
    for (const k of ['course', 'tool', 'video', 'newsletter'] as const) {
      expect(feedAudience(k)).toBe('everyone with News and offers on');
    }
  });
});

describe('screenFromHash', () => {
  afterEach(() => vi.unstubAllGlobals());

  const at = (hash: string) => {
    vi.stubGlobal('window', { location: { hash } });
    return screenFromHash();
  };

  test('reads the screen from #/id or #id', () => {
    expect(at('#/talks')).toBe('talks');
    expect(at('#send')).toBe('send');
    expect(at('#/zero-hour')).toBe('zero-hour');
  });

  test('the support tickets screen is in the menu and opens from its hash', () => {
    expect(SCREENS).toContainEqual({ id: 'tickets', label: 'Support tickets' });
    expect(at('#/tickets')).toBe('tickets');
    expect(at('#tickets')).toBe('tickets');
  });

  test('every menu entry has its own id and a label', () => {
    expect(new Set(SCREENS.map((s) => s.id)).size).toBe(SCREENS.length);
    for (const s of SCREENS) expect(s.label.trim()).not.toBe('');
  });

  test('unknown or empty hash falls back to the overview', () => {
    expect(at('')).toBe('overview');
    expect(at('#/nope')).toBe('overview');
    expect(at('#/talks/12')).toBe('overview');
  });
});

describe('Overview: needs attention', () => {
  const overview = (tickets_open?: number): Overview => ({
    counts: { talks: 5, talks_released: 4, talks_needing_review: 0, feed_live: 2, episodes_released: 1, kb_entries: 40, suggestions_new: 0, sheets_failed: 0, tickets_open },
    upcoming: [], recent_pushes: [], onesignal_configured: true, anthropic_configured: true, content_version: 'abc',
  });

  test('no open tickets, no warning', () => {
    expect(warningsFor(overview(0))).toEqual([]);
  });

  test('open tickets get a line that leads to the tickets screen', () => {
    const many = warningsFor(overview(3));
    expect(many).toHaveLength(1);
    expect(many[0].screen).toBe('tickets');
    expect(many[0].text).toMatch(/^3 support tickets are open\./);
    expect(warningsFor(overview(1))[0].text).toMatch(/^1 support ticket is open\./);
  });

  test('a web service that sends no ticket count yet is not a warning', () => {
    expect(warningsFor(overview(undefined))).toEqual([]);
  });

  test('the older warnings still show beside it', () => {
    const data = overview(2);
    data.counts.talks_needing_review = 1;
    data.onesignal_configured = false;
    expect(warningsFor(data).map((w) => w.screen)).toEqual(['send', 'talks', 'tickets']);
  });
});

describe('knowledge base kind', () => {
  test('the two choices are Safety answer and App help', () => {
    expect(KB_KINDS).toEqual([{ value: 'safety', label: 'Safety answer' }, { value: 'support', label: 'App help' }]);
  });

  test('an entry with no kind (an older web service) is a safety entry', () => {
    expect(kindOf({})).toBe('safety');
    expect(kindOf({ kind: 'safety' })).toBe('safety');
    expect(kindOf({ kind: 'support' })).toBe('support');
  });

  test('a kind the web service did not keep is reported, a kept one is not', () => {
    expect(kindLost('support', { kind: 'support' })).toBe('');
    expect(kindLost('safety', {})).toBe('');
    expect(kindLost('support', {})).toMatch(/kind did not change/);
    expect(kindLost('support', { kind: 'safety' })).toMatch(/Deploy the backend/);
  });

  const entry = { title: 'The app keeps closing', body: '1. Close the app.\n2. Open it again.', source: 'Zero Harm app help' };

  test('a complete entry can be saved', () => {
    expect(kbProblem(entry)).toBe('');
  });

  test('title, text and source are still required', () => {
    expect(kbProblem({ ...entry, title: ' ' })).toBe('An entry needs a title and text.');
    expect(kbProblem({ ...entry, body: '' })).toBe('An entry needs a title and text.');
    expect(kbProblem({ ...entry, source: '' })).toMatch(/^Add a source\./);
  });
});
