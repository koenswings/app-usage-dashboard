import { render } from '@solidjs/testing-library';
import { ScorecardCard } from '../src/components/shared/ScorecardCard';
import { cardsByWeek, SAMPLE_WEEK } from '../src/mock/data';
import { buildHeadlines, buildPill, buildScorecardLines } from '../src/lib/scorecardView';

function renderCard(deploymentId: string) {
  const card = cardsByWeek[SAMPLE_WEEK].find((item) => item.deploymentId === deploymentId);
  if (!card) throw new Error(deploymentId);
  const pill = buildPill(card.hasUsageData, false);
  return render(() => (
    <ScorecardCard
      school={card.school}
      engine={card.engine}
      note={card.note}
      pill={pill.pill}
      pillLabel={pill.pillLabel}
      lines={buildScorecardLines(card.scorecard, false)}
      headlines={buildHeadlines(card.headlines)}
      lastPulledLabel="10 Nov 2026, 13:40 Europe/Brussels"
      stale={card.stale}
      dataFromLabel={card.dataFrom ? `data from 4 Nov 2026` : null}
    />
  ));
}

describe('ScorecardCard wording', () => {
  it('says No data, never Grey, for a school without usage data', () => {
    const { container } = renderCard('dep-kind-panda');
    expect(container.textContent).toMatch(/No data/);
    expect(container.textContent).not.toMatch(/Grey/);
    expect(container.textContent).not.toMatch(/gray/i);
  });

  it('says Thresholds not set on data-bearing lines rather than inventing a grade', () => {
    const { container } = renderCard('dep-nharira');
    expect(container.textContent).toMatch(/Thresholds not set/);
    expect(container.textContent).not.toMatch(/Grey/);
  });
});
