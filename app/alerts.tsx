import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { AlertCard } from '@/components/feed';
import { ComingSoon, Screen } from '@/components/ui';
import { FeedItem, listFeed } from '@/lib/feed';
import { useContentRefresh } from '@/lib/live';
import { markStale } from '@/lib/saved-first';

/** Every regulatory alert, newest first. */
export default function AlertsScreen() {
  const [items, setItems] = useState<FeedItem[] | null>(null);
  const load = useCallback(() => listFeed(['alert'], setItems).then(setItems), []);
  useFocusEffect(useCallback(() => void load(), [load]));
  useContentRefresh(() => {
    markStale('feed-alert'); // a new alert was published, so don't wait out the freshness window
    return load();
  });
  return (
    <Screen>
      {items === null && <ActivityIndicator />}
      {items?.length === 0 && (
        <ComingSoon title="No alerts yet" detail="New federal, Nevada and Las Vegas rules that affect your site show up here. Turn on Regulatory alerts in Settings to hear about them first." />
      )}
      {items?.map((i) => <AlertCard key={i.id} item={i} />)}
    </Screen>
  );
}
