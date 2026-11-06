import * as WebBrowser from 'expo-web-browser';

import { Body, Button, ComingSoon, Heading, Screen } from '@/components/ui';
import { config } from '@/lib/config';

export default function LearnScreen() {
  return (
    <Screen>
      <Heading>Learn</Heading>
      <Body>Get Zero Harm Weekly by email: a 5-minute talk, a real story and a crew question, every Sunday before your Monday meeting.</Body>
      <Button label="Subscribe to Zero Harm Weekly" onPress={() => WebBrowser.openBrowserAsync(config.newsletterUrl)} />
      <ComingSoon title="Lockout pocket guide" detail="The six steps, try-out and verify zero energy. Planned for January, hazardous energy month." />
      <ComingSoon title="HazCom label reference" detail="GHS pictograms and label elements. Planned for February." />
      <ComingSoon title="Free short courses" detail="Links to Trainovate's free courses, starting with the OSHA 300 log course." />
    </Screen>
  );
}
