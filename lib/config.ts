/** Values come from .env (see .env.example). EXPO_PUBLIC_ vars are bundled into the app, so never put secrets here. */
export const config = {
  supabaseUrl: process.env.EXPO_PUBLIC_SUPABASE_URL ?? '',
  supabaseKey: process.env.EXPO_PUBLIC_SUPABASE_KEY ?? '',
  oneSignalAppId: process.env.EXPO_PUBLIC_ONESIGNAL_APP_ID ?? '',
  newsletterUrl: 'https://go.trainovate.ai/zero-harm-weekly-page',
};

export const isConfigured = () => Boolean(config.supabaseUrl && config.supabaseKey);
