import { Link, useFocusEffect } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { EpisodeCard } from '@/components/EpisodeCard';
import { ResourceCard } from '@/components/feed';
import { Body, Button, Heading, Screen } from '@/components/ui';
import { config } from '@/lib/config';
import { Episode, listEpisodes } from '@/lib/episodes';
import { FeedItem, listFeed, RESOURCE_KINDS } from '@/lib/feed';

/** Free courses, tools and videos, published from GoHighLevel. Featured items first. */
export default function LearnScreen() {
  const [items, setItems] = useState<FeedItem[] | null>(null);
  const [eps, setEps] = useState<Episode[]>([]);
  useFocusEffect(
    useCallback(() => {
      listFeed(RESOURCE_KINDS).then(setItems);
      listEpisodes().then(setEps);
    }, []),
  );
  return (
    <Screen>
      <Heading>Learn</Heading>
      {eps.length > 0 && (
        <>
          <EpisodeCard ep={eps[0]} compact />
          <Link href="/zero-hour" style={{ fontSize: 16, fontWeight: '600' }}>
            All Zero Hour episodes and huddle cards →
          </Link>
        </>
      )}
      {items === null && <ActivityIndicator />}
      {items?.map((i) => <ResourceCard key={i.id} item={i} />)}
      <Body>Get Zero Harm Weekly by email: a 5-minute talk, a real story and a crew question, every Sunday before your Monday meeting.</Body>
      <Button kind="secondary" label="Subscribe to Zero Harm Weekly" onPress={() => WebBrowser.openBrowserAsync(`${config.newsletterUrl}?src=zero-harm-app`)} />
    </Screen>
  );
}
