import { useEffect, useState } from 'react';
import { AccessibilityInfo, Animated, Easing, Image, View } from 'react-native';

const OTIS = require('../assets/otis/otis.png'); // smiling OTIS robot; source art in assets/otis/otis.svg
const TEAL = '#25B9CE';

/**
 * OTIS, alive: he floats gently, tips his head now and then, and his antenna light pulses.
 * With Reduce Motion on he holds still. Decorative by default; give it a label where it stands alone.
 */
export function AnimatedOtis({ size = 64 }: { size?: number }) {
  const [float] = useState(() => new Animated.Value(0));
  const [tilt] = useState(() => new Animated.Value(0));
  const [pulse] = useState(() => new Animated.Value(0));
  const [still, setStill] = useState<boolean | null>(null);

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled()
      .then(setStill)
      .catch(() => setStill(false));
  }, []);

  useEffect(() => {
    if (still !== false) return;
    const ease = Easing.inOut(Easing.sin);
    const wave = (v: Animated.Value, ms: number) =>
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: ms, easing: ease, useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: ms, easing: ease, useNativeDriver: true }),
      ]);
    const loops = [
      Animated.loop(wave(float, 1400)),
      Animated.loop(wave(pulse, 900)),
      // A quick head tip to each side, then a rest, so it reads as a hello and not a wobble.
      Animated.loop(
        Animated.sequence([
          Animated.delay(2600),
          Animated.timing(tilt, { toValue: 1, duration: 220, easing: ease, useNativeDriver: true }),
          Animated.timing(tilt, { toValue: -1, duration: 320, easing: ease, useNativeDriver: true }),
          Animated.timing(tilt, { toValue: 0, duration: 220, easing: ease, useNativeDriver: true }),
        ]),
      ),
    ];
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [still, float, tilt, pulse]);

  const art = size * 0.8;
  const glow = art * 0.2; // sits on the antenna tip, which is at 50% across and 13% down the artwork
  return (
    <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: '#151A25', alignItems: 'center', justifyContent: 'center' }}>
      <Animated.View
        style={{
          width: art,
          height: art,
          transform: [
            { translateY: float.interpolate({ inputRange: [0, 1], outputRange: [size * 0.03, -size * 0.04] }) },
            { rotate: tilt.interpolate({ inputRange: [-1, 1], outputRange: ['-9deg', '9deg'] }) },
          ],
        }}>
        <Animated.View
          style={{
            position: 'absolute',
            left: art * 0.5 - glow / 2,
            top: art * 0.133 - glow / 2,
            width: glow,
            height: glow,
            borderRadius: glow / 2,
            backgroundColor: TEAL,
            opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.15, 0.6] }),
            transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.9, 1.7] }) }],
          }}
        />
        <Image source={OTIS} style={{ width: art, height: art }} resizeMode="contain" />
      </Animated.View>
    </View>
  );
}
