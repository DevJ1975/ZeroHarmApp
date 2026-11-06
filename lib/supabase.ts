import 'expo-sqlite/localStorage/install'; // gives supabase-js a persistent localStorage on device
import { createClient } from '@supabase/supabase-js';

import { config } from './config';

export const supabase = createClient(
  config.supabaseUrl || 'https://placeholder.supabase.co',
  config.supabaseKey || 'placeholder',
  {
    auth: { storage: localStorage, autoRefreshToken: true, persistSession: true, detectSessionInUrl: false },
  },
);
