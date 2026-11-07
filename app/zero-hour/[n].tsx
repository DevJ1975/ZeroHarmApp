import { Stack, useLocalSearchParams } from 'expo-router';
import { useVideoPlayer, VideoView } from 'expo-video';
import * as WebBrowser from 'expo-web-browser';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { Episode, getEpisode, LEGAL } from '@/lib/episodes';

/** One Zero Hour episode: watch it, then run the huddle card with the crew. */
export default function EpisodeScreen() {
  const { n } = useLocalSearchParams<{ n: string }>();
  const [ep, setEp] = useState<Episode | null | undefined>(undefined);
  useEffect(() => void getEpisode(Number(n)).then(setEp), [n]);

  if (ep === undefined) return <Screen><ActivityIndicator /></Screen>;
  if (ep === null) return <Screen><Body>This episode isn’t out yet. New episodes come out Thursdays.</Body></Screen>;
  return <EpisodeView ep={ep} />;
}

function List({ items, ordered }: { items: string[]; ordered?: boolean }) {
  const t = useTheme();
  return (
    <View style={{ gap: space.xs }}>
      {items.map((x, i) => (
        <View key={i} style={styles.li}>
          <Text style={[styles.bullet, { color: t.text }]}>{ordered ? `${i + 1}.` : '☐'}</Text>
          <Text style={[styles.liText, { color: t.text }]}>{x}</Text>
        </View>
      ))}
    </View>
  );
}

function H({ children }: { children: string }) {
  const t = useTheme();
  return (
    <Text accessibilityRole="header" style={[styles.h, { color: t.text }]}>
      {children}
    </Text>
  );
}

function EpisodeView({ ep }: { ep: Episode }) {
  const t = useTheme();
  const player = useVideoPlayer(ep.video_url ?? null, (p) => {
    p.loop = false;
  });

  return (
    <Screen>
      <Stack.Screen options={{ title: `Zero Hour · EP ${String(ep.number).padStart(2, '0')}` }} />
      {ep.video_url ? (
        <VideoView
          player={player}
          style={styles.video}
          nativeControls
          contentFit="contain"
          allowsPictureInPicture
          fullscreenOptions={{ enable: true }}
          accessibilityLabel={`Zero Hour episode ${ep.number}, ${ep.title}`}
        />
      ) : (
        <Body muted>The episode video is on its way.</Body>
      )}
      <Body muted>5-minute episode · 10-minute huddle. Watch first, sound on.</Body>

      <View style={styles.dark}>
        <Text style={styles.kicker}>HUDDLE CARD · EP {String(ep.number).padStart(2, '0')}</Text>
        <Text style={styles.title}>{ep.title}</Text>
        <Text style={styles.hazard}>{ep.hazard}</Text>
        {ep.zero_hour !== '' && <Text style={styles.clock}>ZERO HOUR {ep.zero_hour}</Text>}
      </View>

      <H>The story in 30 seconds</H>
      <Body>{ep.story}</Body>

      <H>Where the chain could have broken</H>
      <List items={ep.chain} ordered />

      <H>{ep.checks_label}</H>
      <List items={ep.checks} />

      <H>Say stop when you see</H>
      <Body>{ep.stop_when}</Body>

      <View style={[styles.emergency, { backgroundColor: t.danger }]}>
        <Text style={styles.emergencyTitle}>{ep.emergency_label}</Text>
        <Text style={styles.emergencyText}>{ep.emergency}</Text>
      </View>

      <H>Talk about it</H>
      <List items={ep.questions} ordered />

      {ep.card_pdf_url && (
        <Button label="Open the printable huddle card (PDF)" onPress={() => WebBrowser.openBrowserAsync(ep.card_pdf_url!)} />
      )}

      <H>References</H>
      {ep.references.map((r, i) => (
        <Body key={i} muted>
          {i + 1}. {r}
        </Body>
      ))}
      <Text style={[styles.legal, { color: t.muted }]}>{LEGAL}</Text>
      <Text style={[styles.credit, { color: t.muted }]}>Written and produced by Jamil Jones</Text>
      <Text style={[styles.tagline, { color: t.text }]}>GO HOME THE WAY YOU CAME IN</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  video: { width: '100%', aspectRatio: 1, borderRadius: 8, backgroundColor: '#000' },
  dark: { backgroundColor: '#0E1116', borderRadius: 8, padding: space.md, gap: 2 },
  kicker: { fontFamily: fonts.bodyBold, fontSize: 13, letterSpacing: 1.2, color: '#F5C400' },
  title: { fontFamily: fonts.display, fontSize: 32, color: '#FFFFFF' },
  hazard: { fontFamily: fonts.bodyMedium, fontSize: 16, color: '#B8C0CA' },
  clock: { fontFamily: fonts.displayMedium, fontSize: 18, color: '#F5C400', marginTop: space.xs },
  h: { fontFamily: fonts.displayMedium, fontSize: 22, marginTop: space.sm },
  li: { flexDirection: 'row', gap: space.sm },
  bullet: { fontFamily: fonts.bodyBold, fontSize: 17, lineHeight: 25, width: 22 },
  liText: { flex: 1, fontFamily: fonts.body, fontSize: 17, lineHeight: 25 },
  emergency: { borderRadius: 8, padding: space.md, gap: space.xs, marginTop: space.sm },
  emergencyTitle: { fontFamily: fonts.displayMedium, fontSize: 20, color: '#FFFFFF' },
  emergencyText: { fontFamily: fonts.bodyMedium, fontSize: 17, lineHeight: 24, color: '#FFFFFF' },
  legal: { fontFamily: fonts.body, fontSize: 13, lineHeight: 19, marginTop: space.md },
  credit: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  tagline: { fontFamily: fonts.display, fontSize: 18, letterSpacing: 1, marginTop: space.xs },
});
