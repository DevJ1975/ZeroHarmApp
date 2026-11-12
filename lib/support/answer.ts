/**
 * Decides, for one message typed to OTIS, where the answer comes from, so the chat screen only has to ask. The order
 * is fixed, and every step of it runs on the phone:
 *
 *   1. The 911 rail (lib/otis/safety.ts). When it fires, no support path is ever taken: the banner is always followed
 *      by the normal safety answer.
 *   2. The app named and going wrong ("the app keeps crashing", "OTIS won't download"): the best support entry word
 *      for word, then the offer to report it.
 *   3. A support entry that fits the message clearly ("how do I find past talks", "the talk is locked"): that entry
 *      word for word, with a small "Report a problem" link.
 *   4. Everything else: the safety answers, as before. When the message looks a little like an app question, the
 *      screen adds the small "Something wrong with the app? Report a problem" link under the answer.
 *
 * Steps 2 and 3 run only for a message that is about the app and nothing else: every word of it is one of the app's
 * words (onlyAboutTheApp in ./intent). "The app froze and mike is not moving", "la app se cerró y me torcí el tobillo"
 * and "the app froze and the floor is slippery" each hold a word that is not the app's, so they get the safety answer,
 * with the Report a problem link under it. That is a closed list of the app's words, not a list of hazards, so a
 * hazard nobody thought of still goes to the safety answers. A message that names a hazard, a machine, a chemical,
 * PPE, lockout or a permit (mentionsSafety) or another person is also kept from steps 2 and 3, as a second check.
 *
 * A support entry is always shown word for word: it never goes through the on-device model, and it is never handed to
 * the model next to safety passages.
 */
import { search, searchSupport, type KbItem } from '../otis/kb';
import { looksUrgent } from '../otis/safety';
import { aboutSomeoneElse, asksAboutApp, looksLikeAppProblem, mentionsSafety, namesTheApp, onlyAboutTheApp, spelledOut } from './intent';

/**
 * `problem`: the person says the app is going wrong. Show the entry word for word if there is one, then offer
 * "Report this problem" and "That fixed it" (startFlow). With no entry, offer to report straight away.
 * `help`: an entry that answers the message clearly ("what is OTIS", "how do I find past talks"). Show it word for word
 * with the small "Report a problem" link under it; no buttons.
 */
export type SupportReply = { kind: 'problem'; entry: KbItem | null } | { kind: 'help'; entry: KbItem };

/**
 * True when a support path may run at all: the message is about the app and nothing else (the gate), and, as a second
 * check that the gate does not depend on, names no hazard and no other person (mentionsSafety, aboutSomeoneElse). So
 * "the app crashes when I open the lockout talk" still gets the safety answer, with the Report a problem link.
 */
export function supportMayRun(question: string): boolean {
  return onlyAboutTheApp(question) && !mentionsSafety(question) && !aboutSomeoneElse(question);
}

/**
 * Steps 1 to 3: a support answer for this message, or null to carry on with the safety answers. Null for anything
 * the 911 rail fires on, and for any message that is not only about the app: one that names a hazard, an illness, a
 * threat, a place, another person ("the app crashed and he is dizzy"), or any word that is not one of the app's.
 */
export function supportReply(kb: KbItem[], question: string, lang: 'en' | 'es'): SupportReply | null {
  if (looksUrgent(question) || !supportMayRun(question)) return null;
  // Past the gate, slang and typos are written out when the words as typed find nothing: "otis wont dl", "notifs
  // stopped comin thru", "la aplicasion se cierra".
  const said = spelledOut(question);
  const find = (strict: boolean) => searchSupport(kb, question, lang, 1, strict)[0] ?? searchSupport(kb, said, lang, 1, strict)[0] ?? null;
  if (looksLikeAppProblem(question) || looksLikeAppProblem(said)) return { kind: 'problem', entry: find(false) };
  // A question that names the app or OTIS outright may use the looser match ("why the app look all different now",
  // "is otis down"); one that names only a part of it must match clearly (strict).
  const entry = find(!(asksAboutApp(question) || asksAboutApp(said) || namesTheApp(question)));
  return entry ? { kind: 'help', entry } : null;
}

/** Where OTIS's answer to one message comes from. `link` asks for the small "Report a problem" link under it. */
export type Route = SupportReply | { kind: 'safety'; sources: KbItem[]; link: boolean };

/**
 * The whole order, for the chat screen: support answer, or the safety passages for the model (none means "I don't
 * have that"). `urgent` is looksUrgent(question), passed in because the screen shows the banner from it.
 */
export function routeQuestion(kb: KbItem[], question: string, lang: 'en' | 'es', urgent: boolean): Route {
  const reply = urgent ? null : supportReply(kb, question, lang);
  if (reply) return reply;
  const sources = search(kb, question, lang);
  // The link fits when the message names the app, or reads like one of the app help entries, but went to safety:
  // "the app froze and the floor is slippery" gets the safety answer and the link. Under the 911 banner it shows only
  // for a message about the app and nothing else ("the app is not responding", "I need help with the app"): a link is
  // not a support path, and the safety answer still comes first.
  const link = urgent
    ? looksLikeAppProblem(question) && supportMayRun(question)
    : looksLikeAppProblem(question) || asksAboutApp(question) || searchSupport(kb, question, lang, 1).length > 0;
  return { kind: 'safety', sources, link };
}

/** A support entry as OTIS shows it: the title, a blank line, then the steps, exactly as written. */
export const entryText = (entry: KbItem) => `${entry.title.trim()}\n\n${entry.text.trim()}`;
