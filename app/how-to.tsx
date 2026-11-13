import { router } from 'expo-router';

import { HowTo } from '@/components/HowTo';

/** The same four steps as the first run, opened from Settings. */
export default function HowToScreen() {
  return <HowTo onDone={() => router.back()} />;
}
