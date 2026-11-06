import { getDb } from './db';

export type Signin = { id: number; crew_name: string; signature: string; signed_at: string };
export type SigninSession = { id: number; issue: number; supervisor: string | null; location: string | null; created_at: string };

export async function startSession(issue: number, supervisor: string, location: string) {
  const db = await getDb();
  const res = await db.runAsync(
    'INSERT INTO signin_sessions (issue, supervisor, location) VALUES (?, ?, ?)',
    issue,
    supervisor || null,
    location || null,
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
