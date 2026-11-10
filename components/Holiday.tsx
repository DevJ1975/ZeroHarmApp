/**
 * The holiday look: string lights, a navy banner, an evergreen accent and an animated opening screen.
 * No red decoration on purpose. In this app red means stop or danger, so the season is shown with evergreen,
 * warm lights and snow. Safety yellow stays the color of the main action.
 */
import { useIsFocused } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, Pressable, StyleSheet, Text, useColorScheme, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fonts, palette, space } from '@/constants/theme';

export const holiday = {
  navy: '#13233F',
  navyDeep: '#0E1A30',
  evergreen: '#1F6B4A',
  pine: '#2E7A4E',
  mint: '#7FD1A6',
  gold: '#F69812',
  paper: '#F7F3EA',
};

export const HOLIDAY_LINE = 'Home safe for the holidays';
const BULBS = [holiday.gold, holiday.mint, palette.safetyYellow, holiday.paper];

/** Evergreen on light screens, mint on dark ones. Both pass contrast for text. */
export function useHolidayAccent() {
  return useColorScheme() === 'dark' ? holiday.mint : holiday.evergreen;
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduced).catch(() => {});
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduced);
    return () => sub.remove();
  }, []);
  return reduced;
}

const SWAGS = 3;
const PER_SWAG = [0.22, 0.5, 0.78]; // where bulbs hang along each swag

/** A string of lights. `lightUp` makes the bulbs come on one after another (the opening screen). */
export function HolidayLights({ width, drop = 20, size = 10, lightUp = false }: { width: number; drop?: number; size?: number; lightUp?: boolean }) {
  const reduced = useReducedMotion();
  const count = SWAGS * PER_SWAG.length;
  const [glow] = useState(() => Array.from({ length: count }, () => new Animated.Value(lightUp ? 0.18 : 1)));

  useEffect(() => {
    if (reduced) {
      glow.forEach((g) => g.setValue(1));
      return;
    }
    const runs = glow.map((g, i) => {
      const twinkle = Animated.loop(
        Animated.sequence([
          Animated.timing(g, { toValue: 0.5, duration: 1200, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
          Animated.timing(g, { toValue: 1, duration: 1200, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
        ]),
      );
      const start = lightUp
        ? Animated.sequence([
            Animated.delay(450 + i * 130),
            Animated.timing(g, { toValue: 1, duration: 300, useNativeDriver: true }),
            Animated.delay((i % 4) * 300),
          ])
        : Animated.delay((i % 4) * 400);
      const run = Animated.sequence([start, twinkle]);
      run.start();
      return run;
    });
    return () => runs.forEach((r) => r.stop());
  }, [glow, lightUp, reduced]);

  const swag = width / SWAGS;
  return (
    <View accessible={false} importantForAccessibility="no-hide-descendants" style={{ width, height: drop + size * 1.6 + 4 }}>
      {Array.from({ length: SWAGS }, (_, s) => (
        <View
          key={s}
          style={{
            position: 'absolute',
            left: s * swag,
            top: -drop,
            width: swag,
            height: drop * 2,
            borderRadius: swag / 2,
            borderWidth: 2,
            borderColor: 'transparent',
            borderBottomColor: 'rgba(247,243,234,0.55)',
            transform: [{ scaleY: (drop * 2) / swag }],
          }}
        />
      ))}
      {glow.map((g, i) => {
        const s = Math.floor(i / PER_SWAG.length);
        const f = PER_SWAG[i % PER_SWAG.length];
        // The wire is half an ellipse, so a bulb hangs lower in the middle of a swag than near its ends.
        const y = drop * Math.sqrt(1 - Math.pow((f - 0.5) / 0.5, 2));
        return (
          <Animated.View
            key={i}
            style={{
              position: 'absolute',
              left: s * swag + f * swag - size / 2,
              top: y * 0.82,
              width: size,
              height: size * 1.4,
              borderRadius: size / 2,
              backgroundColor: BULBS[i % BULBS.length],
              opacity: g,
            }}
          />
        );
      })}
    </View>
  );
}

/** The navy band with lights across the top of a tab screen. It runs up under the clock and battery icons. */
export function HolidayBanner({ children }: { children: ReactNode }) {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const focused = useIsFocused();
  const band = useColorScheme() === 'dark' ? holiday.navyDeep : holiday.navy;
  return (
    <View style={[styles.banner, { backgroundColor: band, marginTop: -space.md - insets.top, paddingTop: insets.top }]}>
      {focused && <StatusBar style="light" />}
      <HolidayLights width={width} />
      <View style={styles.bannerRow}>{children}</View>
    </View>
  );
}

export function HolidayTagline() {
  return <Text style={styles.tagline}>{HOLIDAY_LINE.toUpperCase()}</Text>;
}

/** The season's message on the Today tab. */
export function HomeSafeCard() {
  return (
    <View accessible accessibilityRole="text" style={styles.card}>
      <Text style={styles.cardTitle}>{HOLIDAY_LINE}</Text>
      <Text style={styles.cardBody}>Somebody is waiting on every person on your crew. Take the five minutes.</Text>
    </View>
  );
}

const FLAKES = [
  { x: 0.06, size: 5, o: 0.8, ms: 9000 },
  { x: 0.16, size: 3, o: 0.55, ms: 13000 },
  { x: 0.28, size: 6, o: 0.7, ms: 10000 },
  { x: 0.38, size: 4, o: 0.5, ms: 14000 },
  { x: 0.5, size: 5, o: 0.8, ms: 8500 },
  { x: 0.6, size: 3, o: 0.6, ms: 12000 },
  { x: 0.71, size: 6, o: 0.65, ms: 11000 },
  { x: 0.82, size: 4, o: 0.5, ms: 15000 },
  { x: 0.9, size: 5, o: 0.75, ms: 9500 },
  { x: 0.23, size: 4, o: 0.6, ms: 12500 },
  { x: 0.66, size: 3, o: 0.5, ms: 16000 },
  { x: 0.45, size: 6, o: 0.7, ms: 10500 },
];

function Snow({ width, height }: { width: number; height: number }) {
  const [fall] = useState(() => FLAKES.map((_, i) => new Animated.Value(((i * 37) % 100) / 100)));
  useEffect(() => {
    const runs = fall.map((v, i) => {
      // Each flake starts part of the way down so the sky is already full when the screen appears.
      const first = Animated.timing(v, { toValue: 1, duration: FLAKES[i].ms * (1 - ((i * 37) % 100) / 100), easing: Easing.linear, useNativeDriver: true });
      const loop = Animated.loop(Animated.timing(v, { toValue: 1, duration: FLAKES[i].ms, easing: Easing.linear, useNativeDriver: true }));
      first.start(({ finished }) => {
        if (finished) {
          v.setValue(0);
          loop.start();
        }
      });
      return { first, loop };
    });
    return () => runs.forEach((r) => (r.first.stop(), r.loop.stop()));
  }, [fall]);
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {FLAKES.map((f, i) => (
        <Animated.View
          key={i}
          style={{
            position: 'absolute',
            left: f.x * width,
            top: 0,
            width: f.size,
            height: f.size,
            borderRadius: f.size / 2,
            backgroundColor: holiday.paper,
            opacity: f.o,
            transform: [
              { translateY: fall[i].interpolate({ inputRange: [0, 1], outputRange: [-20, height + 20] }) },
              { translateX: fall[i].interpolate({ inputRange: [0, 0.5, 1], outputRange: [0, 14, 0] }) },
            ],
          }}
        />
      ))}
    </View>
  );
}

function Tree({ left, right, bottom, size, color = holiday.evergreen }: { left?: number; right?: number; bottom: number; size: number; color?: string }) {
  return (
    <View
      style={{
        position: 'absolute',
        left,
        right,
        bottom,
        width: 0,
        height: 0,
        borderLeftWidth: size * 0.42,
        borderRightWidth: size * 0.42,
        borderBottomWidth: size,
        borderLeftColor: 'transparent',
        borderRightColor: 'transparent',
        borderBottomColor: color,
      }}
    />
  );
}

/**
 * The animated opening screen, shown once each time the app starts cold. Lights come on, the logo rises, the line
 * appears, then it fades into the app. A tap skips it. With Reduce Motion on, nothing moves and it clears sooner.
 */
export function HolidaySplash({ onDone }: { onDone: () => void }) {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const reduced = useReducedMotion();
  const [logo] = useState(() => new Animated.Value(0));
  const [rule] = useState(() => new Animated.Value(0));
  const [line] = useState(() => new Animated.Value(0));
  const [sub] = useState(() => new Animated.Value(0));
  const [out] = useState(() => new Animated.Value(1));
  const leaving = useRef(false);

  const leave = useCallback(() => {
    if (leaving.current) return;
    leaving.current = true;
    Animated.timing(out, { toValue: 0, duration: 350, useNativeDriver: true }).start(() => onDone());
  }, [out, onDone]);

  useEffect(() => {
    if (reduced) {
      [logo, rule, line, sub].forEach((v) => v.setValue(1));
      const timer = setTimeout(leave, 1500);
      return () => clearTimeout(timer);
    }
    const rise = (v: Animated.Value, delay: number, duration: number) =>
      Animated.timing(v, { toValue: 1, delay, duration, easing: Easing.out(Easing.cubic), useNativeDriver: true });
    const intro = Animated.parallel([rise(logo, 1100, 700), rise(rule, 1650, 450), rise(line, 1850, 500), rise(sub, 2100, 500)]);
    intro.start();
    const timer = setTimeout(leave, 3800);
    return () => {
      intro.stop();
      clearTimeout(timer);
    };
  }, [reduced, logo, rule, line, sub, leave]);

  const up = (v: Animated.Value, by: number) => ({ opacity: v, transform: [{ translateY: v.interpolate({ inputRange: [0, 1], outputRange: [by, 0] }) }] });
  const logoWidth = Math.min(300, width - 80);

  return (
    <Animated.View style={[StyleSheet.absoluteFill, styles.splash, { opacity: out }]}>
      <StatusBar style="light" />
      <Pressable
        style={StyleSheet.absoluteFill}
        onPress={leave}
        accessibilityRole="button"
        accessibilityLabel={`Zero Harm. ${HOLIDAY_LINE}. Tap to continue.`}>
        {!reduced && <Snow width={width} height={height} />}
        <View style={{ position: 'absolute', top: insets.top + 8, left: 0 }}>
          <HolidayLights width={width} drop={34} size={14} lightUp />
        </View>

        <View style={[styles.splashCenter, { top: height * 0.36 }]}>
          <Animated.View style={up(logo, 14)}>
            <Image
              source={require('@/assets/images/splash-logo-dark.png')}
              style={{ width: logoWidth, height: logoWidth * LOGO_RATIO }}
              resizeMode="contain"
              accessibilityIgnoresInvertColors
            />
          </Animated.View>
          <Animated.View style={[styles.rule, { opacity: rule, transform: [{ scaleX: rule }] }]} />
          <Animated.Text style={[styles.splashLine, up(line, 8)]}>{HOLIDAY_LINE}</Animated.Text>
          <Animated.Text style={[styles.splashSub, up(sub, 8)]}>GO HOME THE WAY YOU CAME IN</Animated.Text>
        </View>

        <View pointerEvents="none" style={styles.ground}>
          {/* Two big circles with only their tops showing read as snowy hills. */}
          <View style={[styles.hill, { width: width * 2, height: width * 2, borderRadius: width, left: -width * 0.9, top: 38, opacity: 0.1 }]} />
          <View style={[styles.hill, { width: width * 2.4, height: width * 2.4, borderRadius: width * 1.2, left: -width * 0.35, top: 62, opacity: 0.16 }]} />
          <Tree left={40} bottom={44} size={36} />
          <Tree right={36} bottom={30} size={46} />
          <Tree right={14} bottom={24} size={28} color={holiday.pine} />
        </View>
      </Pressable>
    </Animated.View>
  );
}

/** Height over width of splash-logo-dark.png. Kept in one place so the logo never stretches. */
export const LOGO_RATIO = 1024 / 4326;

const styles = StyleSheet.create({
  banner: { marginHorizontal: -space.md, paddingBottom: space.md - 2, gap: space.sm },
  bannerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.md, paddingHorizontal: space.md },
  tagline: { flex: 1, textAlign: 'right', fontFamily: fonts.bodyBold, fontSize: 13, letterSpacing: 1.3, color: holiday.gold },
  card: { backgroundColor: holiday.evergreen, borderRadius: 8, padding: space.md, gap: 2 },
  cardTitle: { fontFamily: fonts.display, fontSize: 22, color: holiday.paper },
  cardBody: { fontFamily: fonts.body, fontSize: 15, lineHeight: 21, color: holiday.paper },
  splash: { backgroundColor: holiday.navy, zIndex: 10, elevation: 10 },
  splashCenter: { position: 'absolute', left: 0, right: 0, alignItems: 'center', gap: 22, paddingHorizontal: space.lg },
  rule: { width: 56, height: 3, backgroundColor: holiday.gold },
  splashLine: { fontFamily: fonts.display, fontSize: 34, lineHeight: 38, color: holiday.paper, textAlign: 'center' },
  splashSub: { fontFamily: fonts.bodyMedium, fontSize: 15, letterSpacing: 1.8, color: holiday.gold, textAlign: 'center' },
  ground: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 120, overflow: 'hidden' },
  hill: { position: 'absolute', backgroundColor: holiday.paper },
});
