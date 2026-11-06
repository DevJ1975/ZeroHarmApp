import { Body, ComingSoon, Heading, Screen } from '@/components/ui';

export default function ReportScreen() {
  return (
    <Screen>
      <Heading>Report</Heading>
      <Body muted>Tell someone about a near miss in under a minute.</Body>
      <ComingSoon
        title="Near-miss report"
        detail="Coming in the first update: a photo, where it happened, what almost went wrong. You can leave your name off."
      />
      <Body muted>Something dangerous happening right now? Stop the work and tell your supervisor. For an injury or fire, call 911.</Body>
    </Screen>
  );
}
