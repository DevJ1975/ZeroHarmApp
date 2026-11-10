import { arrangeTalks, isEarly, issueNumber, type Talk } from '@/lib/talks';

jest.mock('@/lib/db', () => ({ getDb: jest.fn() }));

const talk = (issue: number, date: string, early = false): Talk => ({
  issue, issue_date: date, month_theme: 'Heat', title: `Talk ${issue}`, story_title: '', crew_question: '',
  body_md: 'x', hero_url: null, pdf_url: null, early,
});

describe('arrangeTalks', () => {
  it("puts the newest sent talk first and keeps early talks out of 'this week'", () => {
    const { current, past, early } = arrangeTalks([talk(3, '2027-01-18', true), talk(1, '2027-01-04'), talk(2, '2027-01-11'), talk(4, '2027-01-25', true)]);
    expect(current?.issue).toBe(2);
    expect(past.map((t) => t.issue)).toEqual([1]);
    expect(early.map((t) => t.issue)).toEqual([3, 4]); // soonest first
  });

  it('before the first Sunday, shows the first early talk', () => {
    const { current, past, early } = arrangeTalks([talk(2, '2027-01-11', true), talk(1, '2027-01-04', true)]);
    expect(current?.issue).toBe(1);
    expect(past).toEqual([]);
    expect(early.map((t) => t.issue)).toEqual([2]);
  });

  it('stops calling a saved talk early once its send time has passed', () => {
    const saved = { ...talk(3, '2027-01-18', true), send_at: '2027-01-17T20:00:00Z' };
    expect(isEarly(saved, new Date('2027-01-15T12:00:00Z'))).toBe(true);
    expect(isEarly(saved, new Date('2027-01-18T14:00:00Z'))).toBe(false);
    const monday = arrangeTalks([saved, talk(2, '2027-01-11')], new Date('2027-01-18T14:00:00Z'));
    expect(monday.current?.issue).toBe(3);
    expect(monday.early).toEqual([]);
  });

  it('handles no talks', () => {
    expect(arrangeTalks([])).toEqual({ current: null, past: [], early: [] });
  });

  it('uses the printed issue number when there is one', () => {
    expect(issueNumber({ ...talk(7, '2027-02-15'), number: 6 })).toBe(6);
    expect(issueNumber(talk(7, '2027-02-15'))).toBe(7);
  });
});
