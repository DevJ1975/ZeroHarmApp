import { Image, View } from 'react-native';

const OTIS = require('../assets/otis/otis.png'); // smiling OTIS robot; source art in assets/otis/otis.svg

/** OTIS on a dark round badge, as in the Soteria FIELD intro. The badge keeps his white outline visible on light cards. */
export function OtisAvatar({ size = 48 }: { size?: number }) {
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel="OTIS"
      style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: '#151A25', alignItems: 'center', justifyContent: 'center' }}>
      <Image source={OTIS} style={{ width: size * 0.8, height: size * 0.8 }} resizeMode="contain" />
    </View>
  );
}
