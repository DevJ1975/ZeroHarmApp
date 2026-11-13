import { regLinks, regUrl } from '@/lib/regs';

describe('regulation links', () => {
  it('links a section to its OSHA page', () => {
    expect(regUrl('1910.147')).toBe('https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.147');
    expect(regUrl('1904.39')).toContain('/1904/1904.39');
  });

  it('finds each section once, with or without a paragraph', () => {
    const links = regLinks('OSHA 29 CFR 1910.147(e) and (c)(6)', 'see 1910.147(d) and 1904.39', null);
    expect(links.map((l) => l.section)).toEqual(['1910.147', '1904.39']);
    expect(links[0].label).toBe('29 CFR 1910.147');
  });

  it('ignores text with no citation', () => {
    expect(regLinks('Zero Harm app help', undefined, '')).toEqual([]);
    expect(regLinks('call 911, about 1910 people')).toEqual([]);
  });
});
