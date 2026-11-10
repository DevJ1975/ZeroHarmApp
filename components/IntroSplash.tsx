import { useVideoPlayer, VideoView } from 'expo-video';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Image, Pressable, StyleSheet, Text, useColorScheme, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fonts, palette } from '@/constants/theme';

const VIDEO = require('../assets/video/intro.mp4');
const POSTER = require('../assets/video/intro-poster.jpg');
const LOGO_LIGHT_BG = require('../assets/images/splash-logo.png');
const LOGO_DARK_BG = require('../assets/images/splash-logo-dark.png');

const NAVY = '#13233F'; // the native splash background in dark mode
const LOGO_RATIO = 4326 / 1024;
const SHOW_MS = 3400; // how long the footage plays before the app takes over
const STILL_MS = 1200; // Reduce Motion: a still frame, briefly

/**
 * The intro that plays once per cold start, right after the native splash.
 * Frame 1 copies the native splash exactly, so the hand-off is invisible; then it fades into footage of
 * crews on the floor with the Zero Harm lockup, and fades out onto Today (already loaded underneath).
 * Tap anywhere or "Skip" to go straight in. With Reduce Motion on, it shows a still frame instead of video.
 */
export function IntroSplash({ onDone }: { onDone: () => void }) {
  const dark = useColorScheme() === 'dark';
  const insets = useSafeAreaInsets();
  const [reduceMotion, setReduceMotion] = useState<boolean | null>(null);
  const [cover] = useState(() => new Animated.Value(1)); // the native-splash look-alike
  const [brand] = useState(() => new Animated.Value(0)); // lockup and tagline over the footage
  const [whole] = useState(() => new Animated.Value(1));
  const finished = useRef(false);

  const player = useVideoPlayer(VIDEO, (p) => {
    p.muted = true;
    p.loop = false;
  });

  const finish = useCallback(() => {
    if (finished.current) return;
    finished.current = true;
    Animated.timing(whole, { toValue: 0, duration: 350, useNativeDriver: true }).start(() => {
      player.pause();
      onDone();
    });
  }, [onDone, player, whole]);

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled()
      .then(setReduceMotion)
      .catch(() => setReduceMotion(false));
  }, []);

  useEffect(() => {
    if (reduceMotion === null) return;
    if (!reduceMotion) player.play();
    Animated.parallel([
      Animated.timing(cover, { toValue: 0, delay: reduceMotion ? 0 : 250, duration: reduceMotion ? 1 : 450, useNativeDriver: true }),
      Animated.timing(brand, { toValue: 1, delay: reduceMotion ? 0 : 500, duration: reduceMotion ? 1 : 500, useNativeDriver: true }),
    ]).start();
    const timer = setTimeout(finish, reduceMotion ? STILL_MS : SHOW_MS);
    return () => clearTimeout(timer);
  }, [reduceMotion, player, cover, brand, finish]);

  const rise = brand.interpolate({ inputRange: [0, 1], outputRange: [16, 0] });

  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.root, { opacity: whole }]} accessibilityViewIsModal>
      <Pressable style={StyleSheet.absoluteFill} onPress={finish} accessibilityLabel="Zero Harm. Tap to skip the intro." accessibilityRole="button">
        {/* The poster sits under the video, so a slow or failed video still shows a real frame. */}
        <Image source={POSTER} style={StyleSheet.absoluteFill} resizeMode="cover" />
        {!reduceMotion && (
          <VideoView player={player} style={StyleSheet.absoluteFill} contentFit="cover" nativeControls={false} allowsPictureInPicture={false} />
        )}
        <View style={styles.dim} />
        <View style={styles.scrim} />

        <Animated.View style={[styles.brand, { paddingBottom: insets.bottom + 56, opacity: brand, transform: [{ translateY: rise }] }]}>
          <Image source={LOGO_DARK_BG} style={styles.lockup} resizeMode="contain" accessibilityIgnoresInvertColors />
          <View style={styles.rule} />
          <Text style={styles.tagline}>Safety talks, tools and answers for the floor.</Text>
        </Animated.View>

        <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.cover, { backgroundColor: dark ? NAVY : palette.safetyYellow, opacity: cover }]}>
          <Image source={dark ? LOGO_DARK_BG : LOGO_LIGHT_BG} style={styles.coverLogo} resizeMode="contain" />
        </Animated.View>
      </Pressable>

      <Animated.View style={[styles.skipWrap, { top: insets.top + 8, opacity: brand }]}>
        <Pressable onPress={finish} hitSlop={8} accessibilityRole="button" accessibilityLabel="Skip intro" style={styles.skip}>
          <Text style={styles.skipText}>Skip</Text>
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  root: { backgroundColor: NAVY, zIndex: 100, elevation: 100 },
  dim: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(19,35,63,0.28)' },
  scrim: { position: 'absolute', left: 0, right: 0, bottom: 0, height: '48%', backgroundColor: 'rgba(19,35,63,0.62)' },
  brand: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: 28, gap: 14 },
  lockup: { width: 250, aspectRatio: LOGO_RATIO },
  rule: { width: 56, height: 5, backgroundColor: palette.safetyYellow },
  tagline: { fontFamily: fonts.bodyMedium, fontSize: 20, lineHeight: 26, color: '#FFFFFF', maxWidth: 320 },
  cover: { alignItems: 'center', justifyContent: 'center' },
  coverLogo: { width: 300, aspectRatio: LOGO_RATIO }, // matches the iOS native splash imageWidth in app.json
  skipWrap: { position: 'absolute', right: 16 },
  skip: { minHeight: 44, minWidth: 64, paddingHorizontal: 16, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(23,33,43,0.55)' },
  skipText: { fontFamily: fonts.bodyBold, fontSize: 16, color: '#FFFFFF' },
});
