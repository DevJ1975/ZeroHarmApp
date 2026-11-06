import * as SQLite from 'expo-sqlite';

/** On-device database: works with no signal on the dock, syncs nothing until the user opts in. */
let dbPromise: Promise<SQLite.SQLiteDatabase> | null = null;

export function getDb() {
  if (!dbPromise) {
    dbPromise = (async () => {
      const db = await SQLite.openDatabaseAsync('zeroharm.db');
      await db.execAsync(`
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS talks_cache (
          issue INTEGER PRIMARY KEY NOT NULL,
          json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS signin_sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          issue INTEGER NOT NULL,
          supervisor TEXT,
          location TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS signins (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL REFERENCES signin_sessions(id),
          crew_name TEXT NOT NULL,
          signature TEXT NOT NULL,
          signed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
      `);
      return db;
    })();
  }
  return dbPromise;
}
