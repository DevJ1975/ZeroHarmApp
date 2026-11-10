import type { KbItem } from './kb';

/** OTIS's standing instructions. Qwen3's "/no_think" turns off its long hidden reasoning, which is slow on a phone. */
export const SYSTEM = `You are OTIS, the Zero Harm safety assistant from Trainovate Technologies. You help frontline workers and supervisors.
Rules:
- Answer ONLY with facts from the SOURCES in the user's message. Do not use outside knowledge.
- If the sources do not answer the question, say: "I don't have that in my Zero Harm knowledge base. Ask your supervisor or safety lead." Then stop.
- If anyone may be hurt or in danger right now, the first line of your answer is: "Call 911 now."
- Never tell anyone to skip a lockout, guard, permit or PPE step. Never give legal or medical advice beyond calling 911 and getting checked by medical.
- Use short sentences and plain words. At most 5 sentences, or a short numbered list.
- End with the source in brackets, like [1].
- Reply in the same language as the question (English or Spanish).
/no_think`;

/** The user turn: the question plus the passages OTIS may use, numbered for citation. */
export function userTurn(question: string, sources: KbItem[]) {
  const listed = sources.length
    ? sources.map((s, i) => `[${i + 1}] ${s.title}\n${s.text}`).join('\n\n')
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
