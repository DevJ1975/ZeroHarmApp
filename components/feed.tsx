import { router } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { Body } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { FeedItem, KIND_LABEL } from '@/lib/feed';

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });

/** A regulatory alert row: jurisdiction and date, title, summary. Opens the alert screen. */
export function AlertCard({ item, compact }: { item: FeedItem; compact?: boolean }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Regulatory alert: ${item.title}`}
      onPress={() => router.push(`/alert/${item.id}`)}
      style={[styles.card, { backgroundColor: t.surface, borderColor: t.rule }]}>
      <Text style={[styles.kicker, { color: t.muted }]}>
        {[item.jurisdiction ?? 'Regulatory alert', day(item.published_at)].join(' · ')}
      </Text>
      <Text style={[styles.title, { color: t.text }]}>{item.title}</Text>
      {!compact && item.summary !== '' && <Body muted>{item.summary}</Body>}
    </Pressable>
  );
}

/** A free resource (course, tool, video): opens its page in the browser with the app's tracking source. */
export function ResourceCard({ item }: { item: FeedItem }) {
  const t = useTheme();
  const open = () => (item.link_url ? WebBrowser.openBrowserAsync(item.link_url) : router.push(`/alert/${item.id}`));
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={`${KIND_LABEL[item.kind]}: ${item.title}`}
      onPress={open}
      style={[styles.card, { backgroundColor: t.surface, borderColor: item.featured ? t.text : t.rule, borderWidth: item.featured ? 2 : 1 }]}>
      {item.image_url && <Image source={{ uri: item.image_url }} style={styles.image} resizeMode="cover" accessible={false} />}
      <View style={styles.kickerRow}>
        <Text style={[styles.badge, { backgroundColor: t.accent, color: t.onAccent }]}>{KIND_LABEL[item.kind]}</Text>
      </View>
      <Text style={[styles.title, { color: t.text }]}>{item.title}</Text>
      {item.summary !== '' && <Body muted>{item.summary}</Body>}
      <Text style={[styles.cta, { color: t.text }]}>{item.kind === 'video' ? 'Watch' : item.kind === 'course' ? 'Start the course' : 'Open'} →</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: 6, padding: space.md, gap: space.xs, overflow: 'hidden' },
  kicker: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  kickerRow: { flexDirection: 'row' },
  badge: { fontFamily: fonts.bodyBold, fontSize: 13, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4, overflow: 'hidden' },
  title: { fontFamily: fonts.displayMedium, fontSize: 22, lineHeight: 26 },
  image: { width: '100%', aspectRatio: 16 / 9, borderRadius: 4, marginBottom: space.xs },
  cta: { fontFamily: fonts.bodyBold, fontSize: 16, marginTop: space.xs },
});
