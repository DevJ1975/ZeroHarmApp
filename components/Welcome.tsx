/**
 * The welcome sign-in, shown once, the first time the app is opened. It asks for a name and an email and says plainly
 * that the app is free. "Not now" lets the person in without signing in.
 */
import { StatusBar } from 'expo-status-bar';
import * as WebBrowser from 'expo-web-browser';
import { ComponentRef, useEffect, useRef, useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, useColorScheme, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LOGO_RATIO } from '@/components/Holiday';
import { Body, Button, Field, Heading } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { checkSignIn, CONSENT_LINE, FREE_LINE, signIn, SignInErrors, skip } from '@/lib/account';
import { config } from '@/lib/config';
import { getProfile } from '@/lib/profile';

/** `covered` is true while the holiday opening screen is still playing on top: nothing here can be tapped or read out. */
export function Welcome({ onDone, covered = false }: { onDone: () => void; covered?: boolean }) {
  const t = useTheme();
  const dark = useColorScheme() === 'dark';
  const { width } = useWindowDimensions();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [errors, setErrors] = useState<SignInErrors>({});
  const [busy, setBusy] = useState(false);
  const emailBox = useRef<ComponentRef<typeof TextInput>>(null);

  useEffect(() => {
    // Someone who used the app before this screen existed may already have a name and email on the phone.
    getProfile()
      .then((p) => {
        setName((cur) => cur || p.name);
        setEmail((cur) => cur || p.email);
      })
      .catch(() => {});
  }, []);

  async function start() {
    const checked = checkSignIn({ name, email });
    setErrors(checked.errors);
    if (!checked.ok) return;
    setBusy(true);
    try {
      await signIn({ name: checked.name, email: checked.email, source: 'welcome' });
    } catch {
      // The phone could not save it. Let the person in anyway; they can sign in from Settings.
    }
    onDone();
  }

  async function notNow() {
    await skip().catch(() => {});
    onDone();
  }

  const logoWidth = Math.min(280, width - space.lg * 2);

  return (
    <View
      style={[StyleSheet.absoluteFill, styles.cover, { backgroundColor: t.background }]}
      pointerEvents={covered ? 'none' : 'auto'}
      accessibilityElementsHidden={covered}
      importantForAccessibility={covered ? 'no-hide-descendants' : 'auto'}
      accessibilityViewIsModal={!covered}>
      {!covered && <StatusBar style="auto" />}
      <SafeAreaView style={styles.fill}>
        <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
            <Image
              source={dark ? require('@/assets/images/splash-logo-dark.png') : require('@/assets/images/splash-logo.png')}
              style={{ width: logoWidth, height: logoWidth * LOGO_RATIO, alignSelf: 'center', marginVertical: space.md }}
              resizeMode="contain"
              accessible
              accessibilityRole="image"
              accessibilityLabel="Zero Harm"
              accessibilityIgnoresInvertColors
            />
            <View accessibilityRole="header">
              <Heading>Welcome to Zero Harm</Heading>
            </View>
            <View style={[styles.free, { backgroundColor: t.accent }]}>
              <Text style={[styles.freeText, { color: t.onAccent }]}>{FREE_LINE}</Text>
            </View>
            <Body>A 5-minute safety talk for your crew every Monday, with sign-in sheets. It works with no signal.</Body>

            <Field
              label="Your name"
              value={name}
              onChangeText={setName}
              error={errors.name}
              autoComplete="name"
              textContentType="name"
              autoCapitalize="words"
              maxLength={120}
              returnKeyType="next"
              submitBehavior="submit"
              onSubmitEditing={() => emailBox.current?.focus()}
            />
            <Field
              inputRef={emailBox}
              label="Email"
              value={email}
              onChangeText={setEmail}
              error={errors.email}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              textContentType="emailAddress"
              returnKeyType="go"
              onSubmitEditing={start}
            />
            <Button label="Get started" onPress={start} busy={busy} />
            <Body muted>{CONSENT_LINE}</Body>

            <View style={styles.links}>
              {config.privacyUrl !== '' && (
                <Pressable accessibilityRole="link" onPress={() => WebBrowser.openBrowserAsync(config.privacyUrl)} style={styles.link}>
                  <Text style={[styles.linkText, { color: t.text }]}>Privacy policy</Text>
                </Pressable>
              )}
              <Pressable
                accessibilityRole="button"
                accessibilityHint="Opens the app without signing in"
                onPress={notNow}
                disabled={busy}
                style={styles.link}>
                <Text style={[styles.linkText, { color: t.text }]}>Not now</Text>
              </Pressable>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  cover: { zIndex: 5, elevation: 5 },
  fill: { flex: 1 },
  content: { padding: space.md, gap: space.md, paddingBottom: space.xl, width: '100%', maxWidth: 520, alignSelf: 'center' },
  free: { borderRadius: 6, paddingVertical: 10, paddingHorizontal: 14 },
  freeText: { fontFamily: fonts.bodyBold, fontSize: 17, lineHeight: 23 },
  links: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', columnGap: space.lg },
  link: { minHeight: 44, minWidth: 44, justifyContent: 'center', paddingHorizontal: space.sm },
  linkText: { fontFamily: fonts.bodyMedium, fontSize: 16, textDecorationLine: 'underline' },
});
