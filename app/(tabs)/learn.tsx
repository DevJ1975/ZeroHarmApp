import { useFocusEffect } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { ResourceCard } from '@/components/feed';
import { Body, Button, ComingSoon, Heading, Screen } from '@/components/ui';
import { config } from '@/lib/config';
import { FeedItem, listFeed, RESOURCE_KINDS } from '@/lib/feed';

/** Free courses, tools and videos, published from GoHighLevel. Featured items first. */
export default function LearnScreen() {
  const [items, setItems] = useState<FeedItem[] | null>(null);
  useFocusEffect(useCallback(() => void listFeed(RESOURCE_KINDS).then(setItems), []));
  return (
    <Screen>
      <Heading>Learn</Heading>
      {items === null && <ActivityIndicator />}
      {items?.map((i) => <ResourceCard key={i.id} item={i} />)}
      {items?.length === 0 && (
        <ComingSoon title="Free courses and tools" detail="Short, free safety courses and tools from Trainovate show up here, starting with the OSHA 300 Log Crash Course." />
      )}
      <Body>Get Zero Harm Weekly by email: a 5-minute talk, a real story and a crew question, every Sunday before your Monday meeting.</Body>
      <Button kind="secondary" label="Subscribe to Zero Harm Weekly" onPress={() => WebBrowser.openBrowserAsync(`${config.newsletterUrl}?src=zero-harm-app`)} />
    </Screen>
  );
}
