import { render } from '@solidjs/testing-library';
import { HourlyChart, shouldShowHourlyChart } from '../src/pages/WikipediaPage';
import { chigondaKiwix, nhariraKiwix } from '../src/mock/data';

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
