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
        CREATE TABLE IF NOT EXISTS feed_cache (
          id INTEGER PRIMARY KEY NOT NULL,
          kind TEXT NOT NULL,
          json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS monday_cache (
          id INTEGER PRIMARY KEY NOT NULL,
          json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sheet_outbox (
          session_id INTEGER PRIMARY KEY NOT NULL,
          payload TEXT NOT NULL,
          tries INTEGER NOT NULL DEFAULT 0
        );
      `);
      // Columns added after the first release: add them to databases that predate them.
      for (const sql of [
        'ALTER TABLE signin_sessions ADD COLUMN group_photo TEXT',
        'ALTER TABLE signin_sessions ADD COLUMN photo_count INTEGER',
        'ALTER TABLE signin_sessions ADD COLUMN saved_at TEXT',
        "ALTER TABLE signin_sessions ADD COLUMN program TEXT NOT NULL DEFAULT 'zhw'",
        'ALTER TABLE signin_sessions ADD COLUMN pdf_path TEXT',
        'ALTER TABLE signin_sessions ADD COLUMN title TEXT',
      ]) {
        try {
          await db.execAsync(sql);
        } catch {
          // already there
        }
      }
      return db;
    })();
  }
  return dbPromise;
}
