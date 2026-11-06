import { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fonts, space, useTheme } from '@/constants/theme';

export function Screen({
  children,
  scroll = true,
  scrollEnabled = true,
}: {
  children: ReactNode;
  scroll?: boolean;
  scrollEnabled?: boolean;
}) {
  const t = useTheme();
  const body = <View style={{ padding: space.md, gap: space.md }}>{children}</View>;
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: t.background }}>
      {scroll ? <ScrollView scrollEnabled={scrollEnabled} keyboardShouldPersistTaps="handled" contentContainerStyle={{ paddingBottom: space.xl }}>{body}</ScrollView> : body}
    </SafeAreaView>
  );
}

export function Heading({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={[styles.heading, { color: t.text }]}>{children}</Text>;
}

export function Body({ children, muted }: { children: ReactNode; muted?: boolean }) {
  const t = useTheme();
  return <Text style={[styles.body, { color: muted ? t.muted : t.text }]}>{children}</Text>;
}

export function Button({
  label,
  onPress,
  kind = 'primary',
  busy,
  disabled,
}: {
  label: string;
  onPress: () => void;
  kind?: 'primary' | 'secondary';
  busy?: boolean;
  disabled?: boolean;
}) {
  const t = useTheme();
  const primary = kind === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy }}
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor: primary ? t.accent : 'transparent',
          borderColor: primary ? t.accent : t.text,
          opacity: disabled ? 0.4 : pressed ? 0.75 : 1,
        },
      ]}>
      {busy ? (
        <ActivityIndicator color={primary ? t.onAccent : t.text} />
      ) : (
        <Text style={[styles.buttonText, { color: primary ? t.onAccent : t.text }]}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label: string }) {
  const t = useTheme();
  const { label, style, ...rest } = props;
  return (
    <View style={{ gap: space.xs }}>
      <Text style={[styles.label, { color: t.muted }]}>{label}</Text>
      <TextInput
        placeholderTextColor={t.muted}
        style={[styles.input, { color: t.text, borderColor: t.rule, backgroundColor: t.surface }, style]}
        {...rest}
      />
    </View>
  );
}

/** Empty-state block: says what will be here and what to do now. */
export function ComingSoon({ title, detail }: { title: string; detail: string }) {
  const t = useTheme();
  return (
    <View style={[styles.soon, { borderColor: t.rule, backgroundColor: t.surface }]}>
      <Text style={[styles.soonTitle, { color: t.text }]}>{title}</Text>
      <Body muted>{detail}</Body>
    </View>
  );
}

const styles = StyleSheet.create({
  heading: { fontFamily: fonts.display, fontSize: 30, lineHeight: 34 },
  body: { fontFamily: fonts.body, fontSize: 17, lineHeight: 25 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  input: { fontFamily: fonts.body, fontSize: 17, borderWidth: 1, borderRadius: 6, padding: 12 },
  button: { borderWidth: 2, borderRadius: 6, paddingVertical: 14, paddingHorizontal: 18, alignItems: 'center' },
  buttonText: { fontFamily: fonts.bodyBold, fontSize: 17 },
  soon: { borderWidth: 1, borderRadius: 6, padding: space.md, gap: space.sm },
  soonTitle: { fontFamily: fonts.displayMedium, fontSize: 22 },
});
