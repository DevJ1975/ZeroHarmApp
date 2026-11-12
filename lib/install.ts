import Storage from 'expo-sqlite/kv-store';

const KEY = 'install_id';
// The promise, not the value: two callers that arrive before the id exists must get the same one. Cleared if making it
// fails, so a storage hiccup is not remembered.
let pending: Promise<string> | null = null;

async function make(): Promise<string> {
  let id = await Storage.getItem(KEY);
  if (!id) {
    const hex = () => Math.floor(Math.random() * 0x10000).toString(16).padStart(4, '0');
    id = `zh-${Date.now().toString(36)}-${Array.from({ length: 6 }, hex).join('')}`;
    await Storage.setItem(KEY, id);
  }
  return id;
}

/**
 * A random id made once per install. The server stores only a salted hash of it, so one phone gets one vote per talk and
 * people can block a commenter. It is not tied to a person, an account or the device's hardware ids.
 */
export function installId(): Promise<string> {
  if (!pending) {
    const made = make();
    pending = made;
    made.catch(() => {
      if (pending === made) pending = null;
    });
  }
  return pending;
}
