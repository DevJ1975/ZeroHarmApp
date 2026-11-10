import { api, isConfigured } from './config';
import { getDb } from './db';
import { attendeeCount, buildSigninSheet, pdfBase64 } from './pdf';
import { getProfile } from './profile';
import { markSaved, type Signin, type SigninSession } from './signins';
import type { SheetSubject } from './subject';

/**
 * Saves a finished sign-in sheet to the supervisor's records in GoHighLevel.
 * The PDF goes into an outbox first, so a dead signal on the dock never loses it; flushSheets() sends it later.
 */
export async function saveSheetToRecords(subject: SheetSubject, session: SigninSession, signins: Signin[]) {
  const profile = await getProfile();
  const uri = await buildSigninSheet(subject, session, signins);
  const payload = {
    pdf_base64: await pdfBase64(uri),
    supervisor_email: profile.email,
    supervisor_name: profile.name || session.supervisor || '',
    company: profile.company,
    program: subject.program === 'mm' ? 'monday-minute' : 'zero-harm-weekly',
    issue: subject.issue,
    talk_title: subject.title,
    location: session.location ?? '',
    held_on: session.created_at.slice(0, 10),
    attendee_count: attendeeCount(session, signins),
    has_group_photo: Boolean(session.group_photo),
  };
  const db = await getDb();
  await db.runAsync('INSERT OR REPLACE INTO sheet_outbox (session_id, payload, tries) VALUES (?, ?, 0)', session.id, JSON.stringify(payload));
  const sent = await flushSheets();
  return { sent: sent.includes(session.id), uri };
}

/** Sends any waiting sheets. Returns the session ids that went through. */
export async function flushSheets(): Promise<number[]> {
  if (!isConfigured()) return [];
  const db = await getDb();
  const rows = await db.getAllAsync<{ session_id: number; payload: string }>('SELECT session_id, payload FROM sheet_outbox');
  const done: number[] = [];
  for (const row of rows) {
    try {
      await api('/signin-sheets/', { method: 'POST', body: row.payload }, 60000);
      await db.runAsync('DELETE FROM sheet_outbox WHERE session_id = ?', row.session_id);
      await markSaved(row.session_id);
      done.push(row.session_id);
    } catch {
      await db.runAsync('UPDATE sheet_outbox SET tries = tries + 1 WHERE session_id = ?', row.session_id);
    }
  }
  return done;
}
