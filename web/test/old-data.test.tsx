import { render } from '@solidjs/testing-library';
import { ScorecardCard } from '../src/components/shared/ScorecardCard';
import { cardsByWeek, SAMPLE_WEEK } from '../src/mock/data';
import { buildHeadlines, buildPill, buildScorecardLines } from '../src/lib/scorecardView';
import { formatDataFrom } from '../src/lib/format';

describe('old-data marker', () => {
  it('marks stale cards as data from a date', () => {
    const card = cardsByWeek[SAMPLE_WEEK].find((item) => item.deploymentId === 'dep-chigonda');
    if (!card) throw new Error('missing chigonda');
    const pill = buildPill(card.hasUsageData, false);
    const { getByTestId } = render(() => (
      <ScorecardCard
        school={card.school}
        engine={card.engine}
        pill={pill.pill}
        pillLabel={pill.pillLabel}
        lines={buildScorecardLines(card.scorecard, false)}
        headlines={buildHeadlines(card.headlines)}
        lastPulledLabel="4 Nov 2026, 09:00 Europe/Brussels"
        stale={card.stale}
        dataFromLabel={formatDataFrom(card.dataFrom)}
      />
    ));
    expect(getByTestId('old-data-marker').textContent).toBe('data from 4 Nov 2026');
  });
});
