import { render } from '@solidjs/testing-library';
import { API_SCHEMA } from '../src/api/types';
import { chigondaKiwix, DEP_NHARIRA, nhariraKiwix, SAMPLE_WEEK } from '../src/mock/data';
import { HourlyChart, shouldShowHourlyChart, WikipediaPage } from '../src/pages/WikipediaPage';

describe('hourly chart hiding', () => {
  it('shows the chart at or above the weekly minimum and hides it below', () => {
    expect(shouldShowHourlyChart(142, 20)).toBe(true);
    expect(shouldShowHourlyChart(8, 20)).toBe(false);

    const shown = render(() => (
      <HourlyChart views={nhariraKiwix[0].byHour ?? []} pageViews={nhariraKiwix[0].pageViews ?? 0} minWeekly={20} />
    ));
    expect(shown.getByTestId('hourly-chart')).toBeTruthy();

    const hidden = render(() => (
      <HourlyChart views={chigondaKiwix[0].byHour ?? []} pageViews={chigondaKiwix[0].pageViews ?? 0} minWeekly={20} />
    ));
    expect(hidden.getByTestId('hourly-chart-hidden')).toBeTruthy();
    expect(hidden.queryByTestId('hourly-chart')).toBeNull();
  });
});

describe('weekly distinctArticles wording', () => {
  it('calls the figure a daily maximum, never the week distinct total', () => {
    const { container } = render(() => (
      <WikipediaPage
        data={{
          schema: API_SCHEMA,
          deploymentId: DEP_NHARIRA,
          weekStart: SAMPLE_WEEK,
          clockTrusted: true,
          instances: nhariraKiwix,
        }}
        school="Nharira"
        hourlyChartMinWeeklyViews={20}
      />
    ));
    expect(container.textContent).toMatch(/most different articles in one day/);
    expect(container.textContent).not.toMatch(/week(?:'s|’s)? distinct total/i);
  });
});
