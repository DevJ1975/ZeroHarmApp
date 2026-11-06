import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';
import SignatureScreen, { SignatureViewRef } from 'react-native-signature-canvas';

import { Body, Button, Field, Screen } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { shareSigninSheet } from '@/lib/pdf';
import { addSignin, getSession, listSignins, Signin, SigninSession } from '@/lib/signins';
import { getTalk } from '@/lib/talks';

/** One phone passed around the crew: type your name, sign, hand it on. */
export default function SigninScreen() {
  const t = useTheme();
  const { session: sessionParam } = useLocalSearchParams<{ session: string }>();
  const sessionId = Number(sessionParam);
  const sigRef = useRef<SignatureViewRef>(null);
  const [session, setSession] = useState<SigninSession | null>(null);
  const [signins, setSignins] = useState<Signin[]>([]);
  const [name, setName] = useState('');
  const [sharing, setSharing] = useState(false);
  const [drawing, setDrawing] = useState(false); // stop the page scrolling while someone signs

  const refresh = useCallback(() => listSignins(sessionId).then(setSignins), [sessionId]);
  useEffect(() => {
    getSession(sessionId).then(setSession);
    refresh();
  }, [sessionId, refresh]);

  async function onSignature(signature: string) {
    if (!name.trim()) {
      Alert.alert('Add your name', 'Type your name above the signature box, then tap Save signature.');
      return;
    }
    await addSignin(sessionId, name.trim(), signature);
    setName('');
    sigRef.current?.clearSignature();
    refresh();
  }

  async function share() {
    if (!session) return;
    const talk = await getTalk(session.issue);
    if (!talk) return;
    setSharing(true);
    try {
      await shareSigninSheet(talk, session, signins);
    } finally {
      setSharing(false);
    }
  }

  const padStyle = `.m-signature-pad{box-shadow:none;border:1px solid ${t.rule}}
    .m-signature-pad--footer{display:none} body,html{height:100%}`;

  return (
    <Screen scrollEnabled={!drawing}>
      <Text style={[styles.count, { color: t.text }]}>
        {signins.length} {signins.length === 1 ? 'person' : 'people'} signed
      </Text>
      <Field label="Crew member name" value={name} onChangeText={setName} placeholder="First and last name" autoCapitalize="words" />
      <View style={[styles.pad, { borderColor: t.rule }]}>
        <SignatureScreen
          ref={sigRef}
          onOK={onSignature}
          webStyle={padStyle} autoClear={false}
          descriptionText=""
          onBegin={() => setDrawing(true)}
          onEnd={() => setDrawing(false)}
        />
      </View>
      <View style={styles.actions}>
        <View style={{ flex: 1 }}>
          <Button kind="secondary" label="Clear" onPress={() => sigRef.current?.clearSignature()} />
        </View>
        <View style={{ flex: 2 }}>
          <Button label="Save signature" onPress={() => sigRef.current?.readSignature()} />
        </View>
      </View>

      {signins.map((s) => (
        <Body key={s.id}>✓ {s.crew_name}</Body>
      ))}

      <Button
        kind="secondary"
        label="Share sign-in sheet as PDF"
        onPress={share}
        busy={sharing}
        disabled={signins.length === 0}
      />
      <Body muted>Sign-ins stay on this phone. Share the PDF to keep it with your training records.</Body>
    </Screen>
  );
}

const styles = StyleSheet.create({
  count: { fontFamily: fonts.display, fontSize: 28 },
  pad: { height: 220, borderWidth: 1, borderRadius: 6, overflow: 'hidden' },
  actions: { flexDirection: 'row', gap: space.sm },
});
