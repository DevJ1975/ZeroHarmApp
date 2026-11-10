import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator } from 'react-native';

import { MondayMinuteView } from '@/components/MondayMinuteView';
import { Body, Screen } from '@/components/ui';
import { getMinute, Minute } from '@/lib/monday';

/** A Monday Minute by id (from the list, a push or a sign-in sheet). */
export default function MondayMinuteScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [m, setM] = useState<Minute | null | undefined>(undefined);
  useEffect(() => {
    getMinute(Number(id)).then(setM);
  }, [id]);
  if (m === undefined) return <Screen><ActivityIndicator /></Screen>;
  if (m === null) return <Screen><Body>This Monday Minute isn’t available.</Body></Screen>;
  return <MondayMinuteView minute={m} onChange={setM} />;
}

