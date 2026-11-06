import { Body, ComingSoon, Heading, Screen } from '@/components/ui';

export default function InspectScreen() {
  return (
    <Screen>
      <Heading>Inspect</Heading>
      <Body muted>Pre-use checks with photos and a PDF you can file.</Body>
      <ComingSoon title="Ladder check" detail="Arrives in the first update. Work through each point, snap a photo of anything damaged, and tag the ladder out." />
      <ComingSoon title="Forklift pre-shift" detail="Planned for June, ahead of July forklift month." />
      <ComingSoon title="Harness and lanyard" detail="Planned for May, falls month." />
    </Screen>
  );
}
