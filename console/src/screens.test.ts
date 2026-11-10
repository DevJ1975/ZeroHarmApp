import { afterEach, describe, expect, test, vi } from 'vitest';

import { screenFromHash } from './nav';
import { feedAudience } from './screens/Feed';

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

  test('unknown or empty hash falls back to the overview', () => {
    expect(at('')).toBe('overview');
    expect(at('#/nope')).toBe('overview');
    expect(at('#/talks/12')).toBe('overview');
  });
});
