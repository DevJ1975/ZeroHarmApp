import { getMinute, weekLabel } from './monday';
import type { Program, SigninSession } from './signins';
import { getTalk, issueNumber } from './talks';

/** What a sign-in sheet is for: the talk title and the line printed under it. */
export type SheetSubject = { program: Program; issue: number; title: string; label: string };

export async function getSubject(session: SigninSession): Promise<SheetSubject | null> {
  if (session.program === 'mm') {
    const m = await getMinute(session.issue);
    return m ? { program: 'mm', issue: m.id, title: m.title, label: `Monday Minute · week of ${weekLabel(m)}` } : null;
  }
  const t = await getTalk(session.issue);
  return t ? { program: 'zhw', issue: t.issue, title: t.title, label: `Zero Harm Weekly issue ${issueNumber(t)} (${t.month_theme})` } : null;
}
