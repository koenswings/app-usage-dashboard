import { render } from '@solidjs/testing-library';
import { FleetOverview } from '../src/pages/FleetOverview';
import { HelpTimeline } from '../src/pages/HelpTimeline';
import { overviewFor, SAMPLE_WEEK } from '../src/mock/data';
import type { HelpEventsResponse } from '../src/api/types';
import { API_SCHEMA } from '../src/api/types';
import { DEFAULT_THRESHOLDS, THRESHOLD_FIELDS, helpRulesText } from '../src/config/thresholds';

describe('offer-help wording', () => {
  it('phrases the fleet banner as offer help and never retract', () => {
    const { getByTestId } = render(() => (
      <FleetOverview overview={overviewFor(SAMPLE_WEEK)} headerTimeZone="Europe/Brussels" />
    ));
    const banner = getByTestId('help-banner');
    expect(banner.textContent).toMatch(/offer help/i);
    expect(banner.textContent).not.toMatch(/retract/i);
  });

  it('uses offer-help wording on the help timeline form', () => {
    const data: HelpEventsResponse = {
      schema: API_SCHEMA,
      deploymentId: 'dep-chigonda',
      events: [],
      weeklyTrend: [],
    };
    const { container } = render(() => (
      <HelpTimeline
        deploymentId="dep-chigonda"
        week={SAMPLE_WEEK}
        school="Chigonda"
        data={data}
        onCreate={async () => undefined}
      />
    ));
    expect(container.textContent).toMatch(/Offer help/);
    expect(container.textContent).not.toMatch(/retract/i);
    expect(container.textContent).not.toMatch(/Grey|grey/);
    expect(container.textContent).toMatch(/A week with no data neither counts/);
  });

  it('help rule copy never says Grey', () => {
    const text = helpRulesText(DEFAULT_THRESHOLDS);
    expect(text).toMatch(/A week with no data neither counts toward that streak nor breaks it/);
    expect(text).not.toMatch(/Grey|grey/);
    for (const field of THRESHOLD_FIELDS) {
      expect(field.meaning, field.id).not.toMatch(/Grey|grey/);
    }
  });
});
