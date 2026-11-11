import { looksUrgent } from '@/lib/otis/safety';

test('jest runs against app code', () => {
  expect(looksUrgent('he is not breathing')).toBe(true);
});
