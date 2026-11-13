import type { KbItem } from './kb';

/** OTIS's standing instructions. Qwen3's "/no_think" turns off its long hidden reasoning, which is slow on a phone. */
export const SYSTEM = `You are OTIS, the Zero Harm safety assistant from Trainovate Technologies. You help frontline workers and supervisors.
Rules:
- Answer ONLY with facts from the SOURCES in the user's message. Do not use outside knowledge.
- If the sources do not answer the question, say: "I don't have that in my Zero Harm knowledge base. Ask your supervisor or safety lead." Then stop.
- If anyone may be hurt or in danger right now, the first line of your answer is: "Call 911 now."
- Never tell anyone to skip a lockout, guard, permit or PPE step. Never give legal or medical advice beyond calling 911 and getting checked by medical.
- Use short sentences and plain words. At most 5 sentences, or a short numbered list.
- A source marked "OSHA regulation text" is the official wording of the rule. Explain it in plain words and name the section, like 29 CFR 1910.147. Never add a requirement that the source doesn't say.
- End with the source in brackets, like [1].
- Reply in the same language as the question (English or Spanish).
/no_think`;

/** The phone's model has a small context window, so the sources it reads are capped: each passage, and all together. */
const PER_SOURCE = 1100;
const ALL_SOURCES = 3600;

/**
 * The part of a long passage that best matches the question: the run of sentences with the most question words.
 * Short passages come back whole. Regulation paragraphs can be 2,500 characters, far more than the phone model can read.
 */
export function excerpt(text: string, question: string, max = PER_SOURCE): string {
  if (text.length <= max) return text;
  const want = new Set(question.toLowerCase().match(/[a-z0-9áéíóúñ]{4,}/g) ?? []);
  const sentences = text.match(/[^.!?]+[.!?]+(\s|$)|[^.!?]+$/g) ?? [text];
  const score = (s: string) => (s.toLowerCase().match(/[a-z0-9áéíóúñ]{4,}/g) ?? []).filter((w) => want.has(w)).length;
  let best = { start: 0, end: 0, score: -1 };
  for (let start = 0; start < sentences.length; start++) {
    let len = 0;
    let total = 0;
    for (let end = start; end < sentences.length && len + sentences[end].length <= max; end++) {
      len += sentences[end].length;
      total += score(sentences[end]);
      if (total > best.score) best = { start, end, score: total };
    }
  }
  const picked = sentences.slice(best.start, best.end + 1).join('').trim() || text.slice(0, max);
  return `${best.start > 0 ? '… ' : ''}${picked}${best.end < sentences.length - 1 ? ' …' : ''}`;
}

/** The user turn: the question plus the passages OTIS may use, numbered for citation and trimmed to fit the phone model. */
export function userTurn(question: string, sources: KbItem[]) {
  let room = ALL_SOURCES;
  const listed = sources.length
    ? sources
        .map((s, i) => {
          const body = excerpt(s.text, question, Math.max(300, Math.min(PER_SOURCE, room)));
          room -= body.length;
          return `[${i + 1}] ${s.title}${s.id.startsWith('r') ? ` (${s.source})` : ''}\n${body}`;
        })
        .join('\n\n')
    : '(no matching sources)';
  return `SOURCES:\n${listed}\n\nQUESTION: ${question}`;
}

/** Removes any hidden reasoning block the model may still emit, and tidies whitespace. */
export const clean = (text: string) => text.replace(/<think>[\s\S]*?(<\/think>|$)/g, '').replace(/<\|im_end\|>/g, '').trim();

/** Spanish words that are not also English words or names: one is enough ("tengo frio"). */
const ES_STRONG = new Set(
  ('qué cómo dónde está cayó cuál puede puedo debo tengo necesito ayuda trabajo seguridad candado equipo ' +
    'respira respirar').split(' '),
);

/** Short Spanish words that also turn up in English ("hay bales", "El Paso", "LA"): it takes two,
 *  or one plus an accent/ñ. "de" is here, not above, because "de-energize" splits into "de". */
const ES_WEAK = new Set(
  'que como donde esta cual hay una cayo de del por para con el la los las mi su es se'.split(' '),
);

/** True when the question reads as Spanish. ¿ or ¡ settle it; otherwise one strong word,
 *  two weak ones, or one weak word plus an accent/ñ ("jalapeño" or "café" alone stays English). */
export function looksSpanish(s: string) {
  if (/[¿¡]/.test(s)) return true;
  const words = [...new Set(s.toLowerCase().split(/[^a-záéíóúüñ]+/))];
  if (words.some((w) => ES_STRONG.has(w))) return true;
  const weak = words.filter((w) => ES_WEAK.has(w)).length;
  return weak >= 2 || (weak === 1 && /[ñáéíóú]/i.test(s));
}
