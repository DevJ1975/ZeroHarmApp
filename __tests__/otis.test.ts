import { isRegulation, search, type KbItem } from '@/lib/otis/kb';
import { clean, excerpt, looksSpanish, userTurn } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';

jest.mock('expo-sqlite/kv-store', () => ({ __esModule: true, default: { getItem: jest.fn(), setItem: jest.fn() } }));
jest.mock('@/lib/otis/manifest', () => ({ kbVersionKey: 'otis_kb_version' }));

const item = (id: string, title: string, text: string, extra: Partial<KbItem> = {}): KbItem => ({
  id, title, text, source: title, lang: 'en', issue: null, ...extra,
});

const kb: KbItem[] = [
  item('k1', 'Lockout/tagout: whose lock comes off', 'Each lock must be removed by the person who put it on. Never remove someone else\'s lock.', { tags: 'candado, remove lock' }),
  item('k2', 'Ladders: safe use', 'Check the ladder before you use it each shift. Face the ladder when you climb.'),
  item('k3', 'Forklift: leaving it parked', 'Lower the forks, set the brakes and shut off the power.'),
  item('r1', 'OSHA regulation text: lockout (e)', 'Each lockout device shall be removed from each energy isolating device by the employee who applied the device. '.repeat(3), { source: '29 CFR 1910.147(e)' }),
  item('r2', 'OSHA regulation text: lockout (c)', 'Lockout devices shall be removed lock lock lock by the employee. '.repeat(5), { source: '29 CFR 1910.147(c)' }),
  item('r3', 'OSHA regulation text: lockout (d)', 'The lock shall be applied; remove lock procedures; lock removal. '.repeat(5), { source: '29 CFR 1910.147(d)' }),
];

describe('OTIS search', () => {
  it('finds the plain-language entry first and caps regulation passages at two', () => {
    const hits = search(kb, "Who can remove a coworker's lock?", 'en', 4);
    expect(hits[0].id).toBe('k1');
    expect(hits.filter(isRegulation).length).toBeLessThanOrEqual(2);
  });

  it('answers Spanish questions from English entries through their Spanish tags', () => {
    expect(search(kb, '¿Puedo quitar el candado de otro?', 'es', 2)[0].id).toBe('k1');
  });

  it('returns nothing for an off-topic question', () => {
    expect(search(kb, 'What is the capital of France?', 'en')).toEqual([]);
    expect(search(kb, 'the of and', 'en')).toEqual([]);
  });

  it('gives the same answer when asked twice (cached index)', () => {
    expect(search(kb, 'forklift parked brakes', 'en').map((h) => h.id)).toEqual(search(kb, 'forklift parked brakes', 'en').map((h) => h.id));
  });
});

describe('OTIS prompt', () => {
  const long = `${'Scope and application of this section. '.repeat(30)}Each lock must be removed by the employee who applied it. ${'Training records shall be kept. '.repeat(30)}`;

  it('keeps short passages whole and trims long ones to the relevant part', () => {
    expect(excerpt('Short text.', 'anything')).toBe('Short text.');
    const cut = excerpt(long, 'who removes the lock applied', 400);
    expect(cut.length).toBeLessThanOrEqual(410);
    expect(cut).toContain('removed by the employee who applied');
    expect(cut.startsWith('… ')).toBe(true);
  });

  it('keeps the whole prompt within the phone model budget', () => {
    const sources = [1, 2, 3, 4].map((n) => item(`r${n}`, `Rule ${n}`, long, { source: `29 CFR 1910.14${n}(a)` }));
    const turn = userTurn('who removes the lock', sources);
    expect(turn.length).toBeLessThan(4400);
    expect(turn).toContain('[1] Rule 1 (29 CFR 1910.141(a))');
    expect(turn).toContain('QUESTION: who removes the lock');
    expect(userTurn('hi', [])).toContain('(no matching sources)');
  });

  it('strips hidden reasoning and spots Spanish', () => {
    expect(clean('<think>hmm</think>Lock it out.<|im_end|>')).toBe('Lock it out.');
    expect(clean('<think>never closed')).toBe('');
    expect(looksSpanish('¿Cómo bloqueo la máquina?')).toBe(true);
    expect(looksSpanish('How do I lock out?')).toBe(false);
  });
});

describe('911 rail', () => {
  it.each(['He is not breathing', 'my hand is caught in the conveyor', 'se cayó de la escalera', 'there is a fire', 'chest pain'])('flags "%s"', (text) => {
    expect(looksUrgent(text)).toBe(true);
  });

  it.each(['How do I inspect a ladder?', 'What gloves for solvents?'])('does not flag "%s"', (text) => {
    expect(looksUrgent(text)).toBe(false);
  });
});
