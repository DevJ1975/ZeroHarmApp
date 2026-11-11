import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { EpisodeCard } from '@/components/EpisodeCard';
import { Body, ComingSoon, Screen } from '@/components/ui';
import { Episode, listEpisodes } from '@/lib/episodes';
import { useContentRefresh } from '@/lib/live';
import { markStale } from '@/lib/saved-first';

/** Every released Zero Hour episode, newest first. */
export default function ZeroHourList() {
  const [eps, setEps] = useState<Episode[] | null>(null);
  const load = useCallback(() => listEpisodes(setEps).then(setEps), []);
  useFocusEffect(useCallback(() => void load(), [load]));
  useContentRefresh(() => {
    markStale('episodes'); // a new episode was released, so don't wait out the freshness window
    return load();
  });
  return (
    <Screen>
      <Body>Five-minute audio dramas about how ordinary shifts turn into incidents. Watch with the sound on, then run the 10-minute huddle.</Body>
      {eps === null && <ActivityIndicator />}
      {eps?.length === 0 && <ComingSoon title="New episodes every Thursday" detail="Zero Hour episodes appear here as they come out." />}
      {eps?.map((e) => <EpisodeCard key={e.number} ep={e} />)}
    </Screen>
  );
}
