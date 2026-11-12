import { router, Stack } from 'expo-router';
import Storage from 'expo-sqlite/kv-store';
import { ComponentRef, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { setTelemetryEnabled, useLLMChatSession } from 'react-native-executorch';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as WebBrowser from 'expo-web-browser';

import { OtisAvatar } from '@/components/OtisAvatar';
import { Body, Button } from '@/components/ui';
import { fonts, space, useTheme } from '@/constants/theme';
import { getAccount } from '@/lib/account';
import { useContentRefresh } from '@/lib/live';
import { getFeedbackPrefs, sendFeedback } from '@/lib/otis/feedback';
import { KbItem, loadKb } from '@/lib/otis/kb';
import { getManifest, llmModel, Manifest, sizeLabel } from '@/lib/otis/manifest';
import { clean, looksSpanish, SYSTEM, userTurn } from '@/lib/otis/prompt';
import { getProfile } from '@/lib/profile';
import { regLinks } from '@/lib/regs';
import { looksUrgent } from '@/lib/otis/safety';
import { entryText, routeQuestion } from '@/lib/support/answer';
import { recordError } from '@/lib/support/crash';
import { deviceInfo } from '@/lib/support/device';
import { ANSWER_REPORT, answerReported, callFirst, flowSent, pauseFlow, startFlow, startReport, stepFlow, type Flow, type FlowAction, type FlowResult, type Lang } from '@/lib/support/flow';
import { fileReport, reportAnswer, type ReportInput } from '@/lib/support/reports';

setTelemetryEnabled(false); // OTIS keeps everything on the phone, so no download analytics either

type OtisModel = NonNullable<Manifest['model']>;
type Msg = {
  id: number;
  role: 'user' | 'otis' | 'urgent';
  text: string;
  sources?: KbItem[];
  pending?: boolean;
  /** The question this reply answers. Every finished reply that has one gets "Report this answer". */
  question?: string;
  lang?: 'en' | 'es';
  rated?: boolean;
  /**
   * Part of the tech-support path: a support entry shown word for word, a line of the report flow, or what the person
   * typed or tapped in answer to one. None of it goes to the model, so it does not count toward the long-chat notice.
   */
  support?: boolean;
  /** Buttons under a report-flow line. Only the newest set can be tapped. */
  actions?: FlowAction[];
  /** What "Report this answer" did, shown in place of the button. */
  reported?: string;
  /** Show the small "Something wrong with the app? Report a problem" link under this reply. */
  reportLink?: boolean;
  /**
   * One short line at the top of the reply (CALL_911_FIRST), on every support reply shown in place of the safety
   * answer. Not part of `text`, so a support entry is still shown, and reported, word for word.
   */
  notice?: string;
};

/** The model set up on this phone, saved as the manifest's model (JSON). OTIS v1 saved a bare built-in name here. */
const OK_KEY = 'otis_downloaded_model';

function savedModel(raw: string | null): OtisModel | null {
  if (!raw) return null;
  if (raw === 'QWEN3_1_7B' || raw === 'QWEN3_0_6B')
    return { key: `builtin-${raw}`, label: 'OTIS', size_mb: 0, builtin: raw, files: null };
  try {
    return JSON.parse(raw) as OtisModel;
  } catch {
    return null;
  }
}
const NOT_COVERED = {
  en: "I don't have that in my Zero Harm knowledge base. Ask your supervisor or safety lead.",
  es: 'No tengo eso en mi base de conocimientos de Zero Harm. Pregunte a su supervisor o al encargado de seguridad.',
};
/** What the message box asks for while a report is being written. */
const FLOW_BOX = {
  describe: { en: 'What went wrong with the app?', es: '¿Qué falló en la app?' },
  email: { en: 'Your email', es: 'Su correo' },
};
/** The small link under a reply that might be about the app, in the reply's language. */
const REPORT_LINK = {
  en: { text: 'Something wrong with the app? Report a problem', label: 'Report a problem with the app' },
  es: { text: '¿Algo anda mal con la app? Reporte un problema', label: 'Reportar un problema con la app' },
};
/** A report left open this long is dropped, so a message typed much later is never taken as part of it. */
const FLOW_IDLE_MS = 5 * 60 * 1000;
/** The time now. Only ever called from event handlers (a send or a tap), never while drawing. */
const clock = () => Date.now();
const SENDING = { en: 'Sending…', es: 'Enviando…' };

/**
 * The way to the Report a problem screen from every OTIS screen that cannot chat: OTIS switched off, an update
 * needed, not set up yet, still downloading, or broken. That screen needs nothing from OTIS.
 */
function ReportLink() {
  const t = useTheme();
  return (
    <Pressable accessibilityRole="link" accessibilityLabel="Report a problem with the app" hitSlop={8} onPress={() => router.push('/report')} style={styles.reportLink}>
      <Text style={[styles.reportLinkText, { color: t.text }]}>Something wrong with the app? Report a problem</Text>
    </Pressable>
  );
}

export default function OtisScreen() {
  const t = useTheme();
  const [man, setMan] = useState<Manifest | null>(null);
  const [chosen, setChosen] = useState<OtisModel | null>(null);
  const [later, setLater] = useState(false);
  const [chatKey, setChatKey] = useState(0);

  useEffect(() => {
    (async () => {
      const m = await getManifest();
      setMan(m);
      setChosen(savedModel(await Storage.getItem(OK_KEY)));
    })();
  }, []);

  if (!man) return <SafeAreaView style={{ flex: 1, backgroundColor: t.background }}><ActivityIndicator /></SafeAreaView>;

  if (man.update_required || !man.enabled || !man.model)
    return (
      <SafeAreaView edges={['bottom']} style={[styles.fill, { backgroundColor: t.background, padding: space.md, gap: space.md }]}>
        <Body>
          {man.update_required
            ? 'Update Zero Harm from the App Store or Google Play to keep using OTIS.'
            : man.message || 'OTIS is taking a short break. Check back soon.'}
        </Body>
        <ReportLink />
      </SafeAreaView>
    );

  const model = man.model;
  if (chosen && later) return <OtisChat key={chatKey} model={chosen} feedbackOn={man.feedback_enabled} onNewChat={() => setChatKey((k) => k + 1)} />;
  if (chosen?.key !== model.key) {
    const updating = chosen !== null;
    const size = sizeLabel(model.size_mb);
    return (
      <SafeAreaView edges={['bottom']} style={[styles.fill, { backgroundColor: t.background }]}>
        <ScrollView contentInsetAdjustmentBehavior="automatic" contentContainerStyle={{ padding: space.md, gap: space.md }}>
          <OtisAvatar size={112} />
          <Text style={[styles.h1, { color: t.text }]}>{updating ? 'OTIS has an update' : 'Meet OTIS'}</Text>
          <Body>
            OTIS answers safety questions from Zero Harm Weekly talks, Zero Hour huddle cards and plain-language OSHA General Industry rules, and
            tells you where each answer comes from.
          </Body>
          <Body>
            OTIS runs on this phone and works with no signal once it is set up. What you ask stays on this phone unless you choose to report a problem
            or an answer, or turn on Include my question in Settings.
          </Body>
          <Body muted>
            {updating ? `The update downloads once (${size}).` : `Setup downloads OTIS once (${size}).`} Use Wi-Fi if you can. OTIS can be wrong:
            always follow your site’s written steps and ask your supervisor when you are not sure. If someone is hurt, call 911 first.
          </Body>
          <Button
            label={updating ? `Update OTIS (${size})` : `Set up OTIS (${size})`}
            onPress={async () => {
              await Storage.setItem(OK_KEY, JSON.stringify(model));
              setChosen(model);
            }}
          />
          {updating && <Button kind="secondary" label="Not now, keep using OTIS as it is" onPress={() => setLater(true)} />}
          <ReportLink />
        </ScrollView>
      </SafeAreaView>
    );
  }

  return <OtisChat key={chatKey} model={model} feedbackOn={man.feedback_enabled} onNewChat={() => setChatKey((k) => k + 1)} />;
}

function OtisChat({ model, feedbackOn, onNewChat }: { model: OtisModel; feedbackOn: boolean; onNewChat: () => void }) {
  const t = useTheme();
  const llm = useLLMChatSession(llmModel(model), {
    initialMessages: [{ role: 'system', content: SYSTEM }],
    generationConfig: { temperature: 0.2, maxNewTokens: 320 },
  });
  const [kb, setKb] = useState<KbItem[]>([]);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  // The report a person is in the middle of making, if any. See lib/support/flow.ts for the steps.
  const [flow, setFlow] = useState<Flow | null>(null);
  const [keyboard, setKeyboard] = useState<FlowResult['keyboard']>(undefined);
  // The one message whose buttons can still be tapped. Buttons from an earlier step are not drawn.
  const [liveActions, setLiveActions] = useState<number | null>(null);
  // When the report flow last moved. An open report left alone for FLOW_IDLE_MS is dropped.
  const flowAt = useRef(0);
  // An email already on this phone, offered at the email step so it need not be typed. Sent only if the person sends it.
  const [knownEmail, setKnownEmail] = useState('');
  const scroller = useRef<ComponentRef<typeof ScrollView>>(null);
  const viewHeight = useRef(0);
  const nextId = useRef(1);
  // Support answers and the report flow never reach the model, so they do not make the chat "long".
  const turns = msgs.filter((m) => m.role === 'user' && !m.support).length;

  const [canRate, setCanRate] = useState(false);

  useEffect(() => {
    loadKb().then(setKb);
    getFeedbackPrefs().then((p) => setCanRate(feedbackOn && p.helpImprove));
    Promise.all([getAccount(), getProfile()])
      .then(([a, p]) => setKnownEmail(a.state === 'in' ? a.email : p.email))
      .catch(() => {});
  }, [feedbackOn]);
  useContentRefresh(() => loadKb().then(setKb)); // new talks or KB entries reach OTIS without reopening

  // A setup that fails is worth a crash report. The error is about the download or the model, never about what was typed.
  useEffect(() => {
    if (llm.error) recordError(llm.error, { fatal: false, screen: '/otis' });
  }, [llm.error]);

  const add = (m: Omit<Msg, 'id'>) => {
    const id = nextId.current++;
    setMsgs((all) => [...all, { ...m, id }]);
    return id;
  };
  const update = (id: number, patch: Partial<Msg>) => setMsgs((all) => all.map((m) => (m.id === id ? { ...m, ...patch } : m)));

  const about = () => ({ device: deviceInfo(), email: knownEmail });

  /** Sends a report the person has just confirmed, and says how it went: the ticket number, or saved for later. */
  async function file(report: ReportInput, lang: Lang) {
    const id = add({ role: 'otis', text: '', pending: true, support: true });
    setBusy(true);
    try {
      update(id, { text: flowSent(lang, await fileReport(report)), pending: false });
    } catch {
      update(id, { text: flowSent(lang, { ref: '', queued: false, failed: true }), pending: false });
    } finally {
      setBusy(false);
    }
  }

  /**
   * Shows one step of the report flow: what OTIS says, the buttons, what goes in the box, and the send when it is time.
   * `notice` (or the step's own) goes at the top of the first line.
   */
  function showFlow(r: FlowResult, lang: Lang, notice = r.notice) {
    setFlow(r.flow);
    flowAt.current = clock();
    setKeyboard(r.keyboard);
    let last: number | null = null;
    r.lines.forEach((text, i) => {
      last = add({
        role: 'otis',
        text,
        support: true,
        ...(i === 0 && notice ? { notice } : {}),
        ...(i === r.lines.length - 1 && r.actions.length ? { actions: r.actions } : {}),
      });
    });
    setLiveActions(r.actions.length ? last : null);
    setInput(r.prefill ?? '');
    if (r.send) void file(r.send, lang);
  }

  /** A tap on a report-flow button. The label is shown as the person's own line, so the chat reads right afterwards. */
  function tapFlow(action: FlowAction) {
    if (!flow || busy) return;
    const r = stepFlow(flow, { tap: action.tap }, about());
    if (r.flow === flow && !r.lines.length && !r.send) return; // a button that means nothing at this step
    add({ role: 'user', text: action.label, support: true });
    showFlow(r, flow.lang);
  }

  /**
   * The "Report a problem" control on the empty chat, and the small link under a reply: straight to who a report goes
   * to and what it sends, then the person's words. Nothing they asked before is put in the box.
   */
  function reportProblem(lang: Lang = 'en') {
    if (busy || flow) return;
    add({ role: 'user', text: lang === 'es' ? 'Reportar un problema' : 'Report a problem', support: true });
    showFlow(startReport('', lang, about()), lang);
  }

  /**
   * "Report this answer" under a reply. It asks first, because this is the one time a question typed to OTIS leaves
   * the phone: that one question and that one answer, and only when the person says to send them.
   */
  function reportThis(m: Msg) {
    const lang: Lang = m.lang ?? 'en';
    const words = ANSWER_REPORT[lang];
    Alert.alert(words.title, words.body, [
      { text: words.cancel, style: 'cancel' },
      {
        text: words.send,
        onPress: async () => {
          update(m.id, { reported: SENDING[lang] });
          try {
            // A fixed reply or a support entry was not written by the model, so it is not blamed on one.
            const filed = await reportAnswer({ question: m.question ?? '', answer: m.text, modelKey: m.sources?.length ? model.key : 'no-model', lang });
            update(m.id, { reported: answerReported(lang, filed) });
          } catch {
            update(m.id, { reported: words.failed });
          }
        },
      },
    ]);
  }

  async function ask() {
    const q = input.trim();
    if (!q || busy) return;
    setInput('');
    const lang: Lang = looksSpanish(q) ? 'es' : 'en';

    // Everything is decided before anything is drawn, in this order. None of it leaves the phone.
    // 1. The 911 rail. It runs first on every message and nothing below can silence it. When it fires, no support path
    //    is taken: the banner is always followed by the safety answer.
    const urgent = looksUrgent(q);
    // 2. A report in progress, unless it was left alone too long. The message is the answer to its step, or it is
    //    handed back as a question (passOn): an emergency or a hazard puts the report on hold first.
    const open = flow && clock() - flowAt.current < FLOW_IDLE_MS ? flow : null;
    const step = open ? stepFlow(open, { say: q }, about()) : null;
    const answered = step !== null && !step.passOn;
    // 3 and 4. Support entries for the app, or the safety answers (lib/support/answer.ts has the order).
    const route = answered ? null : routeQuestion(kb, q, lang, urgent);
    const supportAnswer = route !== null && route.kind !== 'safety';

    add({ role: 'user', text: q, support: answered || supportAnswer });
    if (urgent) add({ role: 'urgent', text: '' });

    if (flow && !open) {
      // Left open too long: dropped without a word, so this message is answered as a question. Nothing was sent.
      setFlow(null);
      setKeyboard(undefined);
      setLiveActions(null);
    } else if (open && step) {
      if (answered || step.lines.length) showFlow(step, open.lang, urgent ? undefined : step.notice);
      else if (!step.flow) {
        // A different question was typed at the offer or the confirm step. The report is dropped; nothing was sent.
        setFlow(null);
        setKeyboard(undefined);
        setLiveActions(null);
      }
    }
    if (!route) return;
    // A report still on hold after this message. A typed question leaves it on hold.
    const onHold = step?.flow?.paused ? step.flow : null;

    // A support reply shown in place of the safety answer starts with the one 911 line (never under the banner, which
    // already says it; the support paths do not run then anyway).
    // A short Spanish message that looksSpanish misses ("otis 1 no contesta") gets the line in both languages.
    const notice = urgent ? undefined : callFirst(q, lang);
    if (route.kind === 'help') {
      add({ role: 'otis', text: entryText(route.entry), support: true, question: q, lang, reportLink: !onHold, notice });
      return;
    }
    if (route.kind === 'problem') {
      if (route.entry) add({ role: 'otis', text: entryText(route.entry), support: true, notice });
      // With a report already on hold, point back to it instead of starting a second one over it.
      showFlow(onHold ? pauseFlow(onHold) : startFlow(q, lang, route.entry !== null), onHold?.lang ?? lang, route.entry ? undefined : notice);
      return;
    }

    const { sources } = route;
    const reportLink = route.link && !onHold;
    if (!sources.length) {
      add({ role: 'otis', text: NOT_COVERED[lang], question: q, lang, reportLink });
      return;
    }
    const id = add({ role: 'otis', text: '', sources, pending: true, question: q, lang, reportLink });
    setBusy(true);
    let streamed = '';
    try {
      await llm.sendMessage?.(userTurn(q, sources), (token) => {
        streamed += token;
        update(id, { text: clean(streamed) });
      });
      update(id, { text: clean(streamed) || NOT_COVERED[lang], pending: false });
    } catch (err) {
      // Only the kind of error is recorded. Its message is left out, in case the model's runtime ever echoes the question.
      recordError({ name: 'OtisAnswerError', message: err instanceof Error ? err.name : 'unknown' }, { fatal: false, screen: '/otis' });
      update(id, { text: 'Sorry, OTIS could not answer just now. Try again, or start a new chat.', pending: false });
    } finally {
      setBusy(false);
    }
  }

  // While a report is being written the message box asks for that step's answer, in the report's language.
  const boxStep = flow && !flow.paused && (flow.step === 'describe' || flow.step === 'email') ? flow.step : null;
  const boxLabel = boxStep && flow ? FLOW_BOX[boxStep][flow.lang] : null;
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
              <ReportLink />
            </View>
          )}
          {msgs.length === 0 && !loading && (
            <View style={styles.empty}>
              <OtisAvatar size={88} />
              <Body muted>Ask about lockout, chemicals, heat, ladders, forklifts, OSHA rules, or how to use the app. For example: “Who can take off a coworker’s lock?”</Body>
              <Pressable accessibilityRole="button" accessibilityLabel="Report a problem with the app" hitSlop={8} onPress={() => reportProblem('en')} style={styles.reportLink}>
                <Text style={[styles.reportLinkText, { color: t.text }]}>Something wrong with the app? Report a problem</Text>
              </Pressable>
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
                {!!m.notice && <Text style={[styles.notice, { color: t.text, borderColor: t.rule }]}>{m.notice}</Text>}
                {m.pending && !m.text ? <ActivityIndicator /> : <Text style={[styles.msg, { color: t.text }]}>{m.text}</Text>}
                {!m.pending && m.sources?.map((s, i) => {
                  const reg = regLinks(s.source)[0];
                  const linked = Boolean(s.issue || s.episode || reg);
                  return (
                    <Pressable
                      key={s.id}
                      accessibilityRole={linked ? 'link' : 'text'}
                      disabled={!linked}
                      onPress={() =>
                        s.episode ? router.push(`/zero-hour/${s.episode}`) : s.issue ? router.push(`/talk/${s.issue}`) : reg && WebBrowser.openBrowserAsync(reg.url)
                      }
                      style={[styles.source, { borderColor: t.rule }]}>
                      <Text style={[styles.sourceText, { color: t.muted }, reg && !s.issue && !s.episode && styles.regLink]}>
                        [{i + 1}] {s.source}{reg && !s.issue && !s.episode ? ' ↗' : ''}
                      </Text>
                    </Pressable>
                  );
                })}
                {canRate && !m.pending && !!m.sources?.length && (
                  <View style={styles.rate}>
                    {m.rated ? (
                      <Text style={[styles.sourceText, { color: t.muted }]}>Thanks. That helps us improve OTIS.</Text>
                    ) : (
                      <>
                        <Text style={[styles.sourceText, { color: t.muted }]}>Was this helpful?</Text>
                        {([true, false] as const).map((helpful) => (
                          <Pressable
                            key={String(helpful)}
                            accessibilityRole="button"
                            accessibilityLabel={helpful ? 'Yes, helpful' : 'No, not helpful'}
                            hitSlop={10}
                            onPress={() => {
                              update(m.id, { rated: true });
                              sendFeedback({ helpful, question: m.question ?? '', sourceIds: m.sources!.map((s) => s.id), modelKey: model.key, lang: m.lang ?? 'en' });
                            }}
                            style={[styles.rateBtn, { borderColor: t.rule }]}>
                            <Text style={[styles.rateText, { color: t.text }]}>{helpful ? 'Yes' : 'No'}</Text>
                          </Pressable>
                        ))}
                      </>
                    )}
                  </View>
                )}
                {m.id === liveActions && !!m.actions?.length && (
                  <View style={styles.actions}>
                    {m.actions.map((a) => (
                      <Pressable
                        key={a.tap}
                        accessibilityRole="button"
                        accessibilityLabel={a.label}
                        accessibilityState={{ disabled: busy }}
                        disabled={busy}
                        onPress={() => tapFlow(a)}
                        style={[styles.actionBtn, { borderColor: t.text, opacity: busy ? 0.4 : 1 }]}>
                        <Text style={[styles.rateText, { color: t.text }]}>{a.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                )}
                {!m.pending && m.reportLink && (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={REPORT_LINK[m.lang ?? 'en'].label}
                    hitSlop={10}
                    disabled={busy || flow !== null}
                    onPress={() => reportProblem(m.lang ?? 'en')}
                    style={styles.flag}>
                    <Text style={[styles.flagText, { color: t.muted }]}>{REPORT_LINK[m.lang ?? 'en'].text}</Text>
                  </Pressable>
                )}
                {!m.pending &&
                  m.question !== undefined &&
                  (m.reported ? (
                    <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.sourceText, { color: t.muted }]}>
                      {m.reported}
                    </Text>
                  ) : (
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={ANSWER_REPORT[m.lang ?? 'en'].button}
                      hitSlop={10}
                      onPress={() => reportThis(m)}
                      style={styles.flag}>
                      <Text style={[styles.flagText, { color: t.muted }]}>{ANSWER_REPORT[m.lang ?? 'en'].button}</Text>
                    </Pressable>
                  ))}
              </View>
            ),
          )}
          {turns >= 6 && (
            <Body muted>Long chats slow OTIS down on a phone. Tap New chat to start fresh.</Body>
          )}
        </ScrollView>
        <Text style={[styles.aiNote, { color: t.muted, backgroundColor: t.background }]}>
          OTIS is an AI assistant and can be wrong. Not legal or medical advice. Emergency: call 911.
        </Text>
        <View style={[styles.composer, { borderColor: t.rule, backgroundColor: t.surface }]}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder={loading ? 'OTIS is getting ready…' : (boxLabel ?? 'Ask OTIS a safety question')}
            placeholderTextColor={t.muted}
            editable={!loading && !busy}
            onSubmitEditing={ask}
            returnKeyType="send"
            keyboardType={keyboard === 'email' ? 'email-address' : 'default'}
            autoCapitalize={keyboard === 'email' ? 'none' : 'sentences'}
            autoCorrect={keyboard !== 'email'}
            accessibilityLabel={boxLabel ?? 'Question for OTIS'}
            style={[styles.input, { color: t.text }]}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send"
            onPress={ask}
            disabled={loading || busy || !input.trim()}
            style={[styles.send, { backgroundColor: t.accent, opacity: loading || busy || !input.trim() ? 0.4 : 1 }]}>
            <Text style={[styles.sendText, { color: t.onAccent }]}>{busy ? '…' : boxStep ? 'Send' : 'Ask'}</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  aiNote: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18, textAlign: 'center', paddingHorizontal: space.md, paddingVertical: 6 },
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
  notice: { fontFamily: fonts.bodyMedium, fontSize: 15, lineHeight: 21, borderBottomWidth: 1, paddingBottom: 6 },
  source: { borderTopWidth: 1, paddingTop: 6 },
  sourceText: { fontFamily: fonts.bodyMedium, fontSize: 14 },
  regLink: { textDecorationLine: 'underline' },
  rate: { flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingTop: 6 },
  rateBtn: { borderWidth: 1, borderRadius: 6, minHeight: 36, minWidth: 52, paddingHorizontal: space.sm, alignItems: 'center', justifyContent: 'center' },
  rateText: { fontFamily: fonts.bodyBold, fontSize: 15 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, paddingTop: 6 },
  actionBtn: { borderWidth: 1.5, borderRadius: 6, minHeight: 44, paddingHorizontal: space.md, alignItems: 'center', justifyContent: 'center' },
  flag: { alignSelf: 'flex-start', minHeight: 32, justifyContent: 'center', paddingTop: 6 },
  flagText: { fontFamily: fonts.bodyMedium, fontSize: 14, textDecorationLine: 'underline' },
  reportLink: { alignSelf: 'center', minHeight: 44, justifyContent: 'center' },
  reportLinkText: { fontFamily: fonts.bodyBold, fontSize: 15, textDecorationLine: 'underline', textAlign: 'center' },
  urgent: { borderRadius: 8, padding: space.md, gap: space.sm },
  urgentText: { fontFamily: fonts.bodyBold, fontSize: 18, color: '#FFFFFF' },
  composer: { flexDirection: 'row', gap: space.sm, padding: space.sm, borderTopWidth: 1, alignItems: 'center' },
  input: { flex: 1, fontFamily: fonts.body, fontSize: 17, minHeight: 44, paddingHorizontal: space.sm },
  send: { minHeight: 44, minWidth: 64, borderRadius: 6, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.md },
  sendText: { fontFamily: fonts.bodyBold, fontSize: 17 },
});
