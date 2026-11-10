import * as WebBrowser from 'expo-web-browser';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, space, useTheme } from '@/constants/theme';
import type { RegLink } from '@/lib/regs';

/** "Read the regulation" links: each opens the OSHA standard in the in-app browser. */
export function RegLinks({ links, title = 'Read the regulation' }: { links: RegLink[]; title?: string }) {
  const t = useTheme();
  if (!links.length) return null;
  return (
    <View style={styles.wrap}>
      <Text style={[styles.title, { color: t.text }]}>{title}</Text>
      {links.map((l) => (
        <Pressable
          key={l.section}
          accessibilityRole="link"
          accessibilityLabel={`${l.label}, opens the OSHA standard`}
          onPress={() => WebBrowser.openBrowserAsync(l.url)}
          hitSlop={6}
          style={styles.row}>
          <Text style={[styles.link, { color: t.text }]}>{l.label} ↗</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 2, marginTop: space.sm },
  title: { fontFamily: fonts.bodyBold, fontSize: 16 },
  row: { minHeight: 36, justifyContent: 'center' },
  link: { fontFamily: fonts.bodyMedium, fontSize: 16, textDecorationLine: 'underline' },
});
