import { Stack, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text } from 'react-native';

import { Body, Button, Screen } from '@/components/ui';
import { fonts, useTheme } from '@/constants/theme';
import { FeedItem, getFeedItem, KIND_LABEL } from '@/lib/feed';

const day = (iso: string) => new Date(`${iso.length === 10 ? `${iso}T12:00:00` : iso}`).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });

export default function AlertScreen() {
  const t = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [item, setItem] = useState<FeedItem | null | undefined>(undefined);
  useEffect(() => void getFeedItem(Number(id)).then(setItem), [id]);

  if (item === undefined) return <Screen><ActivityIndicator /></Screen>;
  if (item === null) return <Screen><Body>This item isn’t available anymore.</Body></Screen>;

  const paragraphs = (item.body_md ?? '').split(/\n\s*\n/).map((p) => p.replace(/^#+\s*/, '').trim()).filter(Boolean);
  return (
    <Screen>
      <Stack.Screen options={{ title: KIND_LABEL[item.kind] }} />
      <Text style={[styles.kicker, { color: t.muted }]}>{[item.jurisdiction, day(item.published_at)].filter(Boolean).join(' · ')}</Text>
      <Text style={[styles.title, { color: t.text }]}>{item.title}</Text>
      {item.effective_date && <Body>Takes effect {day(item.effective_date)}.</Body>}
      {item.summary !== '' && <Body>{item.summary}</Body>}
      {paragraphs.map((p, i) => <Body key={i}>{p}</Body>)}
      {item.link_url && (
        <Button label={item.kind === 'alert' ? 'Read the rule' : 'Open'} onPress={() => WebBrowser.openBrowserAsync(item.link_url!)} />
      )}
      {item.kind === 'alert' && (
        <Body muted>A plain-language summary for awareness, not legal advice. Check the rule itself for what applies to your site.</Body>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  kicker: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  title: { fontFamily: fonts.display, fontSize: 32, lineHeight: 35 },
});
