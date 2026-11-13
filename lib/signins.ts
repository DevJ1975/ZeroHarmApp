import { getDb } from './db';

export type Signin = { id: number; crew_name: string; signature: string; signed_at: string };
/** Which talk program a sign-in belongs to: Zero Harm Weekly ('zhw', issue = issue number) or Monday Minute ('mm', issue = its id). */
export type Program = 'zhw' | 'mm';

export type SigninSession = {
  id: number;
  issue: number;
  program: Program;
  supervisor: string | null;
  location: string | null;
  created_at: string;
  /** JPEG data URI of the group photo, if one was taken. */
  group_photo: string | null;
  /** Head count entered for a photo-only sign-in. */
  photo_count: number | null;
  saved_at: string | null;
  /** The finished sheet PDF kept on this phone, and the talk title it was for. */
  pdf_path: string | null;
  title: string | null;
};

export async function startSession(issue: number, supervisor: string, location: string, program: Program = 'zhw') {
  const db = await getDb();
  const res = await db.runAsync(
    'INSERT INTO signin_sessions (issue, supervisor, location, program) VALUES (?, ?, ?, ?)',
    issue,
    supervisor || null,
    location || null,
    program,
  );
  return res.lastInsertRowId;
}

export async function getSession(id: number) {
  const db = await getDb();
  return db.getFirstAsync<SigninSession>('SELECT * FROM signin_sessions WHERE id = ?', id);
}

export async function addSignin(sessionId: number, crewName: string, signature: string) {
  const db = await getDb();
  await db.runAsync('INSERT INTO signins (session_id, crew_name, signature) VALUES (?, ?, ?)', sessionId, crewName, signature);
}

export async function listSignins(sessionId: number) {
  const db = await getDb();
  return db.getAllAsync<Signin>('SELECT id, crew_name, signature, signed_at FROM signins WHERE session_id = ? ORDER BY id', sessionId);
}

export async function setGroupPhoto(sessionId: number, dataUri: string | null, count: number | null) {
  const db = await getDb();
  await db.runAsync('UPDATE signin_sessions SET group_photo = ?, photo_count = ? WHERE id = ?', dataUri, count, sessionId);
}

export async function markSaved(sessionId: number) {
  const db = await getDb();
  await db.runAsync("UPDATE signin_sessions SET saved_at = datetime('now') WHERE id = ?", sessionId);
}

export async function setKeptPdf(sessionId: number, path: string, title: string) {
  const db = await getDb();
  await db.runAsync('UPDATE signin_sessions SET pdf_path = ?, title = ? WHERE id = ?', path, title, sessionId);
}

/** Sheets kept on this phone, newest first, with how many people signed each one. */
export async function listKeptSheets() {
  const db = await getDb();
  return db.getAllAsync<SigninSession & { signed: number }>(
    `SELECT s.*, (SELECT COUNT(*) FROM signins WHERE session_id = s.id) AS signed
     FROM signin_sessions s WHERE s.pdf_path IS NOT NULL ORDER BY s.id DESC`,
  );
}
