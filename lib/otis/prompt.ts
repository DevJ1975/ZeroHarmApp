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

/** The user turn: the question plus the passages OTIS may use, numbered for citation. */
export function userTurn(question: string, sources: KbItem[]) {
  const listed = sources.length
    ? sources.map((s, i) => `[${i + 1}] ${s.title}${s.id.startsWith('r') ? ` (${s.source})` : ''}\n${s.text}`).join('\n\n')
    : '(no matching sources)';
  return `SOURCES:\n${listed}\n\nQUESTION: ${question}`;
}

/** Removes any hidden reasoning block the model may still emit, and tidies whitespace. */
export const clean = (text: string) => text.replace(/<think>[\s\S]*?(<\/think>|$)/g, '').replace(/<\|im_end\|>/g, '').trim();

export const looksSpanish = (s: string) =>
  /[¿¡ñáéíóú]/i.test(s) || /\b(qué|como|cómo|puedo|debo|trabajo|seguridad|candado|equipo|tengo|hay)\b/i.test(s);
