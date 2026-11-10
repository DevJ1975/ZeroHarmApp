/** Values come from .env (see .env.example). EXPO_PUBLIC_ vars are bundled into the app, so never put secrets here. */
export const config = {
  apiUrl: (process.env.EXPO_PUBLIC_API_URL ?? '').replace(/\/$/, ''),
  oneSignalAppId: process.env.EXPO_PUBLIC_ONESIGNAL_APP_ID ?? '',
  newsletterUrl: 'https://go.trainovate.ai/zero-harm-weekly-page',
};

export const isConfigured = () => Boolean(config.apiUrl);

/** Small fetch wrapper for the Django API with a timeout, so a dead dock signal fails fast. */
export async function api<T>(path: string, init?: RequestInit, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${config.apiUrl}/api${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init?.headers },
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

/** Like api(), but hands back the Response so callers can read headers and 304 Not Modified. */
export async function apiFetch(path: string, init?: RequestInit, timeoutMs = 10000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${config.apiUrl}/api${path}`, {
      ...init,
      signal: controller.signal,
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...init?.headers },
    });
  } finally {
    clearTimeout(timer);
  }
}
