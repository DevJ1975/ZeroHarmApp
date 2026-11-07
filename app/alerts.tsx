import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { AlertCard } from '@/components/feed';
import { ComingSoon, Screen } from '@/components/ui';
import { FeedItem, listFeed } from '@/lib/feed';

/** Every regulatory alert, newest first. */
export default function AlertsScreen() {
  const [items, setItems] = useState<FeedItem[] | null>(null);
  useFocusEffect(useCallback(() => void listFeed(['alert']).then(setItems), []));
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
