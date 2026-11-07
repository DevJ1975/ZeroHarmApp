import { router } from 'expo-router';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, space, useTheme } from '@/constants/theme';
import type { Episode } from '@/lib/episodes';

/** A Zero Hour episode tile: dark, like the show's look, with the incident clock time. */
export function EpisodeCard({ ep, compact }: { ep: Episode; compact?: boolean }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Zero Hour episode ${ep.number}: ${ep.title}. ${ep.hazard}`}
      onPress={() => router.push(`/zero-hour/${ep.number}`)}
      style={[styles.card, { borderColor: t.rule }]}>
      {ep.thumbnail_url && (
        <Image source={{ uri: ep.thumbnail_url }} style={compact ? styles.thumbSmall : styles.thumb} resizeMode="cover" accessible={false} />
      )}
      <View style={styles.body}>
        <Text style={styles.kicker}>
          ZERO HOUR · EP {String(ep.number).padStart(2, '0')}
          {ep.zero_hour ? ` · ${ep.zero_hour}` : ''}
        </Text>
        <Text style={styles.title}>{ep.title}</Text>
        <Text style={styles.hazard}>{ep.hazard}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: 8, overflow: 'hidden', backgroundColor: '#0E1116', borderWidth: 1 },
  thumb: { width: '100%', aspectRatio: 1 },
  thumbSmall: { width: '100%', aspectRatio: 16 / 9 },
  body: { padding: space.md, gap: 2 },
  kicker: { fontFamily: fonts.bodyBold, fontSize: 13, letterSpacing: 1.2, color: '#F5C400' },
  title: { fontFamily: fonts.display, fontSize: 26, color: '#FFFFFF' },
  hazard: { fontFamily: fonts.bodyMedium, fontSize: 15, color: '#B8C0CA' },
});
