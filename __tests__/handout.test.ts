import { handoutHtml } from '@/lib/handout';
import type { Minute } from '@/lib/monday';

jest.mock('expo-print', () => ({}));
jest.mock('expo-sharing', () => ({}));
jest.mock('expo-file-system', () => ({}));
jest.mock('expo-sqlite/kv-store', () => ({ __esModule: true, default: { getItem: jest.fn(), setItem: jest.fn() } }));
jest.mock('@/lib/db', () => ({ getDb: jest.fn() }));

const minute: Minute = {
  id: 1, week: '2026-11-16', published_at: '2026-11-16T13:00:00Z', topic: 'Lockout', category: 'Hazardous energy',
  title: 'Prove it <is> dead', intro: 'Machines can start.', points: ['Lock it out.', 'Verify & try.'], story_title: 'Close',
  story: 'A mechanic almost reached in.', crew_question: 'Where are our procedures?', takeaway: 'Try it.',
  references: ['1910.147'], thumbs_up: 0, thumbs_down: 0, comment_count: 0,
};

describe('printable Monday Minute', () => {
  const html = handoutHtml(minute);

  it('has the talk, then a sign-in sheet on its own page', () => {
    expect(html).toContain('Talk it through');
    expect(html).toContain('<li>Lock it out.</li>');
    expect(html).toContain('class="sheet"');
    expect(html).toContain('page-break-before: always');
    expect((html.match(/<td class="n">/g) ?? []).length).toBe(18);
  });

  it('escapes talk text so it cannot break the page', () => {
    expect(html).toContain('Prove it &lt;is&gt; dead');
    expect(html).toContain('Verify &amp; try.');
    expect(html).not.toContain('<is>');
  });

  it('prints the regulation link in full', () => {
    expect(html).toContain('29 CFR 1910.147: https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147');
    expect(handoutHtml({ ...minute, references: [] })).not.toContain('Read the regulation');
  });
});
