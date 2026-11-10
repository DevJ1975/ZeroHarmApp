import * as Device from 'expo-device';
import { router, Stack } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { ComponentRef, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { models, setTelemetryEnabled, useLLMChatSession } from 'react-native-executorch';
import { SafeAreaView } from 'react-native-safe-area-context';

import { OtisAvatar } from '@/components/OtisAvatar';
import { Body, Button } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { api, isConfigured } from '@/lib/config';
import { useContentRefresh } from '@/lib/live';
import { KbItem, loadKb, search } from '@/lib/otis/kb';
import { clean, looksSpanish, SYSTEM, userTurn } from '@/lib/otis/prompt';
import { looksUrgent } from '@/lib/otis/safety';

setTelemetryEnabled(false); // OTIS keeps everything on the phone, so no download analytics either

type ModelName = 'QWEN3_1_7B' | 'QWEN3_0_6B';
type Config = { enabled: boolean; model: ModelName; small_model: ModelName; min_memory_gb_for_model: number };
type Msg = { id: number; role: 'user' | 'otis' | 'urgent'; text: string; sources?: KbItem[]; pending?: boolean };

const SIZE: Record<ModelName, string> = { QWEN3_1_7B: '1.3 GB', QWEN3_0_6B: '510 MB' };
const DEFAULT_CONFIG: Config = { enabled: true, model: 'QWEN3_1_7B', small_model: 'QWEN3_0_6B', min_memory_gb_for_model: 6 };
const OK_KEY = 'otis_downloaded_model';
const NOT_COVERED = {
  en: "I don't have that in my Zero Harm knowledge base. Ask your supervisor or safety lead.",
  es: 'No tengo eso en mi base de conocimientos de Zero Harm. Pregunte a su supervisor o al encargado de seguridad.',
};

/** The bigger model on phones with enough memory; the small one otherwise. */
function pickModel(cfg: Config): ModelName {
  const gb = (Device.totalMemory ?? 0) / 1024 ** 3;
  return gb >= cfg.min_memory_gb_for_model ? cfg.model : cfg.small_model;
}

export default function OtisScreen() {
  const t = useTheme();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [chosen, setChosen] = useState<ModelName | null>(null);
  const [chatKey, setChatKey] = useState(0);

  useEffect(() => {
    (async () => {
      let c = DEFAULT_CONFIG;
      if (isConfigured()) {
        try {
          c = await api<Config>('/otis/config/');
        } catch {
          // offline: defaults
        }
      }
      setCfg(c);
      const saved = (await Storage.getItem(OK_KEY)) as ModelName | null;
      if (saved) setChosen(saved);
    })();
  }, []);

  if (!cfg) return <SafeAreaView style={{ flex: 1, backgroundColor: t.background }}><ActivityIndicator /></SafeAreaView>;

  if (!cfg.enabled)
    return (
      <SafeAreaView edges={['bottom']} style={[styles.fill, { backgroundColor: t.background, padding: space.md }]}>
        <Body>OTIS is taking a short break. Check back soon.</Body>
      </SafeAreaView>
    );

  if (!chosen) {
    const model = pickModel(cfg);
    return (
      <SafeAreaView edges={['bottom']} style={[styles.fill, { backgroundColor: t.background }]}>
        <ScrollView contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ padding: space.md, gap: space.md }}>
          <OtisAvatar size={112} />
          <Text style={[styles.h1, { color: t.text }]}>Meet OTIS</Text>
          <Body>
            OTIS answers safety questions from Zero Harm Weekly talks and the Zero Harm knowledge base, and tells you where each answer comes from.
          </Body>
          <Body>
            OTIS runs entirely on this phone. Your questions never leave it, and OTIS works with no signal once it is set up.
          </Body>
          <Body muted>
            Setup downloads OTIS once ({SIZE[model]}). Use Wi-Fi if you can. OTIS can be wrong: always follow your site’s written steps and ask
            your supervisor when you are not sure. If someone is hurt, call 911 first.
          </Body>
          <Button
            label={`Set up OTIS (${SIZE[model]})`}
            onPress={async () => {
              await Storage.setItem(OK_KEY, model);
              setChosen(model);
            }}
          />
        </ScrollView>
      </SafeAreaView>
    );
  }

  return <OtisChat key={chatKey} model={chosen} onNewChat={() => setChatKey((k) => k + 1)} />;
}

function OtisChat({ model, onNewChat }: { model: ModelName; onNewChat: () => void }) {
  const t = useTheme();
  const llm = useLLMChatSession(models.llm[model].DEFAULT, {
    initialMessages: [{ role: 'system', content: SYSTEM }],
    generationConfig: { temperature: 0.2, maxNewTokens: 320 },
  });
  const [kb, setKb] = useState<KbItem[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scroller = useRef<ComponentRef<typeof ScrollView>>(null);
  const viewHeight = useRef(0);
  const nextId = useRef(1);
  const turns = msgs.filter((m) => m.role === 'user').length;

  useEffect(() => {
    loadKb().then(setKb);
  }, []);
  useContentRefresh(() => loadKb().then(setKb)); // new talks or KB entries reach OTIS without reopening

  const add = (m: Omit<Msg, 'id'>) => {
    const id = nextId.current++;
    setMsgs((all) => [...all, { ...m, id }]);
    return id;
  };
  const update = (id: number, patch: Partial<Msg>) => setMsgs((all) => all.map((m) => (m.id === id ? { ...m, ...patch } : m)));

  async function ask() {
    const q = input.trim();
    if (!q || busy) return;
    setInput('');
    const lang = looksSpanish(q) ? 'es' : 'en';
    add({ role: 'user', text: q });
    if (looksUrgent(q)) add({ role: 'urgent', text: '' });
    const sources = search(kb, q, lang);
    if (!sources.length) {
      add({ role: 'otis', text: NOT_COVERED[lang] });
      return;
    }
    const id = add({ role: 'otis', text: '', sources, pending: true });
    setBusy(true);
    let streamed = '';
    try {
      await llm.sendMessage?.(userTurn(q, sources), (token) => {
        streamed += token;
        update(id, { text: clean(streamed) });
      });
      update(id, { text: clean(streamed) || NOT_COVERED[lang], pending: false });
    } catch {
      update(id, { text: 'Sorry, OTIS could not answer just now. Try again, or start a new chat.', pending: false });
    } finally {
      setBusy(false);
    }
  }

  const loading = !llm.isReady;
  return (
    <SafeAreaView edges={['bottom']} style={[styles.fill, { backgroundColor: t.background }]}>
      <Stack.Screen
        options={{
          headerRight: () => (
            <Pressable accessibilityRole="button" onPress={onNewChat} hitSlop={12} disabled={busy}>
              <Text style={[styles.link, { color: t.text }]}>New chat</Text>
            </Pressable>
          ),
        }}
      />
      <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={90}>
        <ScrollView
          ref={scroller}
          contentInsetAdjustmentBehavior="automatic"
          onLayout={(e) => (viewHeight.current = e.nativeEvent.layout.height)}
          // Only follow new messages once they overflow; scrollToEnd on short content would park it under the header.
          onContentSizeChange={(_, h) => h > viewHeight.current && scroller.current?.scrollToEnd({ animated: true })}
          contentContainerStyle={{ padding: space.md, gap: space.md }}>
          {loading && (
            <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.rule }]}>
              {llm.error ? (
                <Body>OTIS could not finish setting up. Check your connection, then open OTIS again. ({llm.error.message})</Body>
              ) : (
                <>
                  <Body>{llm.downloadProgress < 1 ? `Setting up OTIS… ${Math.round(llm.downloadProgress * 100)}%` : 'Starting OTIS…'}</Body>
                  <View style={[styles.bar, { backgroundColor: t.rule }]}>
                    <View style={[styles.barFill, { backgroundColor: t.accent, width: `${Math.round(llm.downloadProgress * 100)}%` }]} />
                  </View>
                  <Body muted>This happens once. You can leave this screen; OTIS keeps the download.</Body>
                </>
              )}
            </View>
          )}
          {msgs.length === 0 && !loading && (
            <View style={styles.empty}>
              <OtisAvatar size={88} />
              <Body muted>Ask about lockout, chemicals, heat, ladders, forklifts, or how to use the app. For example: “Who can take off a coworker’s lock?”</Body>
            </View>
          )}
          {msgs.map((m) =>
            m.role === 'urgent' ? (
              <View key={m.id} style={[styles.urgent, { backgroundColor: t.danger }]}>
                <Text style={styles.urgentText}>If someone is hurt or in danger right now, call 911 first.</Text>
                <Button label="Call 911" onPress={() => Linking.openURL('tel:911')} />
              </View>
            ) : m.role === 'user' ? (
              <View key={m.id} style={[styles.bubble, styles.me, { backgroundColor: t.text }]}>
                <Text style={[styles.msg, { color: t.background }]}>{m.text}</Text>
              </View>
            ) : (
              <View key={m.id} style={[styles.bubble, styles.otis, { backgroundColor: t.surface, borderColor: t.rule }]}>
                <View style={styles.whoRow}>
                  <OtisAvatar size={28} />
                  <Text style={[styles.who, { color: t.muted }]}>OTIS</Text>
                </View>
                {m.pending && !m.text ? <ActivityIndicator /> : <Text style={[styles.msg, { color: t.text }]}>{m.text}</Text>}
                {!m.pending && m.sources?.map((s, i) => (
                  <Pressable
                    key={s.id}
                    accessibilityRole={s.issue || s.episode ? 'link' : 'text'}
                    disabled={!s.issue && !s.episode}
                    onPress={() => (s.episode ? router.push(`/zero-hour/${s.episode}`) : s.issue && router.push(`/talk/${s.issue}`))}
                    style={[styles.source, { borderColor: t.rule }]}>
                    <Text style={[styles.sourceText, { color: t.muted }]}>[{i + 1}] {s.source}</Text>
                  </Pressable>
                ))}
              </View>
            ),
          )}
          {turns >= 6 && (
            <Body muted>Long chats slow OTIS down on a phone. Tap New chat to start fresh.</Body>
          )}
        </ScrollView>
        <View style={[styles.composer, { borderColor: t.rule, backgroundColor: t.surface }]}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder={loading ? 'OTIS is getting ready…' : 'Ask OTIS a safety question'}
            placeholderTextColor={t.muted}
            editable={!loading && !busy}
            onSubmitEditing={ask}
            returnKeyType="send"
            accessibilityLabel="Question for OTIS"
            style={[styles.input, { color: t.text }]}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send"
            onPress={ask}
            disabled={loading || busy || !input.trim()}
            style={[styles.send, { backgroundColor: t.accent, opacity: loading || busy || !input.trim() ? 0.4 : 1 }]}>
            <Text style={[styles.sendText, { color: t.onAccent }]}>{busy ? '…' : 'Ask'}</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  h1: { fontFamily: fonts.display, fontSize: 34 },
  link: { fontFamily: fonts.bodyBold, fontSize: 16 },
  card: { borderWidth: 1, borderRadius: 6, padding: space.md, gap: space.sm },
  bar: { height: 8, borderRadius: 4, overflow: 'hidden' },
  barFill: { height: 8 },
  bubble: { borderRadius: 10, padding: 12, gap: 6, maxWidth: '88%' },
  me: { alignSelf: 'flex-end' },
  otis: { alignSelf: 'flex-start', borderWidth: 1 },
  who: { fontFamily: fonts.bodyBold, fontSize: 12, letterSpacing: 1 },
  empty: { alignItems: 'center', gap: space.md, paddingTop: space.lg },
  whoRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  msg: { fontFamily: fonts.body, fontSize: 17, lineHeight: 24 },
  source: { borderTopWidth: 1, paddingTop: 6 },
  sourceText: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  urgent: { borderRadius: 8, padding: space.md, gap: space.sm },
  urgentText: { fontFamily: fonts.bodyBold, fontSize: 18, color: '#FFFFFF' },
  composer: { flexDirection: 'row', gap: space.sm, padding: space.sm, borderTopWidth: 1, alignItems: 'center' },
  input: { flex: 1, fontFamily: fonts.body, fontSize: 17, minHeight: 44, paddingHorizontal: space.sm },
  send: { minHeight: 44, minWidth: 64, borderRadius: 6, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.md },
  sendText: { fontFamily: fonts.bodyBold, fontSize: 17 },
});
