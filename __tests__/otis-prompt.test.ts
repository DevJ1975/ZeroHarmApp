import { SYSTEM, clean, looksSpanish, userTurn } from '@/lib/otis/prompt';
import type { KbItem } from '@/lib/otis/kb';

const item = (over: Partial<KbItem>): KbItem => ({
  id: 'x',
  title: 'Untitled',
  text: '',
  source: 'test',
  lang: 'en',
  issue: null,
  ...over,
});

describe('clean()', () => {
  test('removes a closed <think> block and keeps the answer', () => {
    expect(clean('<think>\nThe user asks about LOTO.\n</think>\n\nApply your own lock. [1]')).toBe('Apply your own lock. [1]');
  });

  test('removes the empty think block Qwen3 emits under /no_think', () => {
    expect(clean('<think>\n\n</think>\n\nCall 911 now.')).toBe('Call 911 now.');
  });

  test('hides an unclosed <think> block while it is still streaming', () => {
    expect(clean('<think>Let me look at source 1 and')).toBe('');
    expect(clean('Answer first. <think>still reasoning')).toBe('Answer first.');
  });

  test('removes several think blocks and keeps the text between them', () => {
    expect(clean('<think>a</think>Wear gloves.<think>b</think> [2]')).toBe('Wear gloves. [2]');
  });

  test('strips <|im_end|> end-of-turn tokens wherever they appear', () => {
    expect(clean('Wear a hard hat. [1]<|im_end|>')).toBe('Wear a hard hat. [1]');
    expect(clean('One.<|im_end|> Two.<|im_end|>')).toBe('One. Two.');
  });

  test('trims surrounding whitespace and leaves ordinary text untouched', () => {
    expect(clean('   Lock out before you reach in.\n\n')).toBe('Lock out before you reach in.');
    expect(clean('Use 3 points of contact < 6 ft > ladder.')).toBe('Use 3 points of contact < 6 ft > ladder.');
  });

  test('empty input stays empty', () => {
    expect(clean('')).toBe('');
  });

  // app/otis.tsx:146 calls clean() on the growing text after every token, so no
  // intermediate render may show the think tags or the hidden reasoning.
  test('token-by-token streaming never shows think tags or reasoning', () => {
    const tokens = ['<think>', '\n', 'source 1 says', '\n', '</think>', '\n\n', 'Call', ' 911', ' now.', '<|im_end|>'];
    let streamed = '';
    const shown: string[] = [];
    for (const tok of tokens) {
      streamed += tok;
      shown.push(clean(streamed));
    }
    for (const text of shown) {
      expect(text).not.toMatch(/think|source 1|<\|im_end\|>/);
    }
    expect(shown[shown.length - 1]).toBe('Call 911 now.');
  });
});

describe('looksSpanish()', () => {
  test.each([
    '¿Qué hago si alguien se cae?',
    '¡Cuidado con el montacargas!',
    'Necesito el candado de mi compañero',
    'Dónde está el extintor',
  ])('accented Spanish: %s', (q) => {
    expect(looksSpanish(q)).toBe(true);
  });

  test('accents typed in capitals still count (caps lock, shouting)', () => {
    expect(looksSpanish('MI COMPAÑERO SE CAYÓ')).toBe(true);
    expect(looksSpanish('ESTÁ CERRADO EL TABLERO')).toBe(true);
  });

  test.each([
    'como bloqueo la maquina',
    'que debo hacer antes de entrar',
    'tengo que usar arnes',
    'hay una fuga de amoniaco',
    'necesito mi candado y mi equipo',
    'reglas de seguridad en el trabajo',
  ])('unaccented Spanish with a keyword: %s', (q) => {
    expect(looksSpanish(q)).toBe(true);
  });

  test.each([
    'How do I lock out a conveyor?',
    'What PPE do I need for the freezer?',
    'Is the eyewash station checked weekly?',
    'Who signs the confined space permit?',
  ])('plain English stays English: %s', (q) => {
    expect(looksSpanish(q)).toBe(false);
  });

  test('keyword match is whole-word only (no hits inside English words)', () => {
    // "hay" inside "Hayward", "como" inside "comorbidity", "equipo" inside "equipoise".
    expect(looksSpanish('Hayward plant comorbidity equipoise report')).toBe(false);
  });

  // How the result is used: app/otis.tsx:132 sets lang from looksSpanish(). lang picks
  // the fallback message (NOT_COVERED[lang], app/otis.tsx:137 and :148) and filters the
  // knowledge-base search (lib/otis/kb.ts:48 drops every Spanish passage when lang is 'en').
  // So a wrong answer here changes what the worker sees, not just a hint.

  // BUG: lib/otis/prompt.ts:27 — the keyword list contains "hay", which is also an
  // everyday English word. An English question about hay bales (farms, feed mills,
  // ag workers) is classified as Spanish, so a no-match reply comes back in Spanish.
  test.failing('BUG: English question with the word "hay" is treated as Spanish', () => {
    expect(looksSpanish('Can hay bales be stacked near the exit?')).toBe(false);
  });

  // BUG: lib/otis/prompt.ts:27 — the unaccented check knows only a handful of words, so
  // Spanish typed on a phone without accents is treated as English. lang becomes 'en',
  // search() then skips every Spanish passage (lib/otis/kb.ts:48), and if no English
  // passage matches the Spanish words the worker gets the English "not covered" line.
  // "No puede respirar" (someone cannot breathe) is one of the misses.
  test.failing.each([
    'donde esta el extintor',
    'No puede respirar',
    'necesito ayuda',
    'se cayo mi companero',
  ])('BUG: unaccented Spanish without a listed keyword is missed: %s', (q) => {
    expect(looksSpanish(q)).toBe(true);
  });

  // BUG: lib/otis/prompt.ts:27 — "ñ" and the accented vowels also appear in English
  // loanwords/names, so an English question mentioning a jalapeño or café is Spanish
  // and a no-match reply comes back in Spanish.
  test.failing('BUG: English with an accented loanword is treated as Spanish', () => {
    expect(looksSpanish('Can I take my jalapeño lunch into the café area?')).toBe(false);
  });
});

describe('userTurn()', () => {
  test('numbers sources [1]..[n] with title and text, then the question', () => {
    const out = userTurn('How do I lock out?', [
      item({ title: 'LOTO basics', text: 'Each worker applies their own lock.' }),
      item({ title: 'Try-out', text: 'Test the start button after locking.' }),
      item({ title: 'Removal', text: 'Only the person who applied a lock removes it.' }),
    ]);
    expect(out).toBe(
      'SOURCES:\n' +
        '[1] LOTO basics\nEach worker applies their own lock.\n\n' +
        '[2] Try-out\nTest the start button after locking.\n\n' +
        '[3] Removal\nOnly the person who applied a lock removes it.\n\n' +
        'QUESTION: How do I lock out?'
    );
  });

  test('zero sources says so explicitly instead of an empty list', () => {
    expect(userTurn('What is the speed limit on the dock?', [])).toBe(
      'SOURCES:\n(no matching sources)\n\nQUESTION: What is the speed limit on the dock?'
    );
  });

  test('a single source is [1] and there is no [2]', () => {
    expect(userTurn('q', [item({ title: 'Only', text: 'One passage.' })])).toBe('SOURCES:\n[1] Only\nOne passage.\n\nQUESTION: q');
  });

  test('keeps the question verbatim, including Spanish punctuation', () => {
    expect(userTurn('¿Qué hago?', [])).toMatch(/QUESTION: ¿Qué hago\?$/);
  });
});

describe('SYSTEM prompt', () => {
  test('restricts answers to the provided sources', () => {
    expect(SYSTEM).toMatch(/Answer ONLY with facts from the SOURCES/);
    expect(SYSTEM).toMatch(/Do not use outside knowledge/);
  });

  // Must be the same line the app shows when search finds nothing (NOT_COVERED.en,
  // app/otis.tsx:28), so the worker sees one consistent message either way.
  test('gives the same fixed fallback line the app uses when sources do not answer', () => {
    expect(SYSTEM).toContain(`say: "I don't have that in my Zero Harm knowledge base. Ask your supervisor or safety lead." Then stop.`);
  });

  test('puts "Call 911 now." first when someone may be hurt', () => {
    expect(SYSTEM).toMatch(/may be hurt or in danger.*first line.*"Call 911 now\."/);
  });

  test('forbids advice to skip lockout, guards, permits or PPE', () => {
    expect(SYSTEM).toMatch(/Never tell anyone to skip a lockout, guard, permit or PPE step/);
  });

  test('asks for a bracketed citation and same-language replies', () => {
    expect(SYSTEM).toMatch(/source in brackets, like \[1\]/);
    expect(SYSTEM).toMatch(/same language as the question/);
  });

  test('ends with /no_think so Qwen3 skips long reasoning on device', () => {
    expect(SYSTEM.trimEnd().endsWith('/no_think')).toBe(true);
  });
});
