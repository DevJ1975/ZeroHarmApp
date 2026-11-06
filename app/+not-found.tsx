import { Link, Stack } from 'expo-router';

import { Body, Screen } from '@/components/ui';

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Page not found' }} />
      <Screen>
        <Body>That page isn’t in the app.</Body>
        <Link href="/">
          <Body>Go to Today</Body>
        </Link>
      </Screen>
    </>
  );
}
