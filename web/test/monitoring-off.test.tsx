import { render } from '@solidjs/testing-library';
import { ScorecardCard } from '../src/components/shared/ScorecardCard';
import { PresenceStrip } from '../src/components/shared/PresenceStrip';
import { FleetOverview } from '../src/pages/FleetOverview';
import { SchoolWeek } from '../src/pages/SchoolWeek';
import { UplinkHistory } from '../src/pages/UplinkHistory';
import {
  cardsByWeek,
  DEP_PANDA,
  HARARE,
  SAMPLE_WEEK,
  overviewFor,
  pandaOffSegments,
} from '../src/mock/data';
import { API_SCHEMA } from '../src/api/types';
import type { SchoolWeekResponse, UplinkResponse } from '../src/api/types';
import { fridayOf } from '../src/lib/week';
import { MONITORING_OFF_MESSAGE, isMonitoringOff, resolveMonitoringEnabled, showStale } from '../src/lib/monitoring';
import { buildHeadlines, buildPill, buildScorecardLines } from '../src/lib/scorecardView';

describe('resolveMonitoringEnabled', () => {
  it('prefers the card field when present, otherwise joins the kit list', () => {
    expect(resolveMonitoringEnabled(false, true)).toBe(false);
    expect(resolveMonitoringEnabled(true, false)).toBe(true);
    expect(resolveMonitoringEnabled(undefined, false)).toBe(false);
    expect(resolveMonitoringEnabled(undefined, true)).toBe(true);
    expect(resolveMonitoringEnabled(undefined, undefined)).toBeUndefined();
    expect(isMonitoringOff(undefined, false)).toBe(true);
    expect(isMonitoringOff(undefined, true)).toBe(false);
  });

  it('never treats a monitoring-off kit as stale', () => {
    expect(showStale(true, true)).toBe(false);
    expect(showStale(true, false)).toBe(true);
    expect(showStale(false, true)).toBe(false);
  });
});

describe('Monitoring off fleet card', () => {
  it('shows a Monitoring off pill and one sentence instead of No data lines', () => {
    const overview = overviewFor(SAMPLE_WEEK);
    const { container, getAllByText, queryByText } = render(() => (
      <FleetOverview
        overview={overview}
        headerTimeZone="Europe/Brussels"
        monitoringByDeployment={{
          'dep-nharira': true,
          'dep-chigonda': true,
          [DEP_PANDA]: false,
        }}
      />
    ));
    const card = container.querySelector('[data-testid="school-card-kind-panda"]');
    expect(card).not.toBeNull();
    expect(card?.textContent).toMatch(/Monitoring off/i);
    expect(card?.textContent).toContain(MONITORING_OFF_MESSAGE);
    expect(card?.textContent).not.toMatch(/No data/);
    expect(card?.querySelector('[data-testid="old-data-marker"]')).toBeNull();
    expect(card?.querySelector('[data-testid="monitoring-off-message"]')?.textContent).toBe(
      MONITORING_OFF_MESSAGE,
    );
    // Enabled kits still use the existing wording.
    expect(getAllByText('On track').length).toBeGreaterThan(0);
    expect(queryByText('Thresholds not set')).toBeNull();
    expect(queryByText('Grey')).toBeNull();
  });

  it('joins monitoringEnabled from /kits when the overview card omits the field', () => {
    const overview = overviewFor(SAMPLE_WEEK);
    const cards = overview.cards.map((card) => {
      const { monitoringEnabled: _ignored, ...rest } = card;
      return rest as typeof card;
    });
    const { container } = render(() => (
      <FleetOverview
        overview={{ ...overview, cards }}
        headerTimeZone="Europe/Brussels"
        monitoringByDeployment={{ [DEP_PANDA]: false, 'dep-nharira': true, 'dep-chigonda': true }}
      />
    ));
    const card = container.querySelector('[data-testid="school-card-kind-panda"]');
    expect(card?.textContent).toMatch(/Monitoring off/i);
    expect(card?.textContent).toContain(MONITORING_OFF_MESSAGE);
  });

  it('does not show the stale marker on a monitoring-off card even if stale is true', () => {
    const card = cardsByWeek[SAMPLE_WEEK].find((item) => item.deploymentId === DEP_PANDA);
    if (!card) throw new Error('missing panda');
    const pill = buildPill(card.hasUsageData, [], false);
    const { queryByTestId } = render(() => (
      <ScorecardCard
        school={card.school}
        engine={card.engine}
        pill={pill.pill}
        pillLabel={pill.pillLabel}
        lines={[]}
        headlines={[]}
        message={MONITORING_OFF_MESSAGE}
        lastPulledLabel="Never pulled"
        stale={showStale(true, true)}
        dataFromLabel="data from 4 Nov 2026"
      />
    ));
    expect(queryByTestId('old-data-marker')).toBeNull();
    expect(pill.pill).toBe('monitoringOff');
    expect(pill.pillLabel).toBe('Monitoring off');
  });
});

describe('Monitoring off school week and reachability', () => {
  const school: SchoolWeekResponse = {
    schema: API_SCHEMA,
    weekStart: SAMPLE_WEEK,
    weekEnd: fridayOf(SAMPLE_WEEK),
    deploymentId: DEP_PANDA,
    school: 'kind-panda',
    engine: 'kind-panda',
    lastPulled: null,
    stale: true,
    dataFrom: '2026-11-04',
    hasUsageData: false,
    monitoringEnabled: false,
    unused: false,
    thresholdsConfigured: false,
    sampleData: true,
    clockTrusted: true,
    timezone: HARARE,
    scorecard: cardsByWeek[SAMPLE_WEEK].find((item) => item.deploymentId === DEP_PANDA)!.scorecard,
    census: {
      classes: null,
      classesDelta: null,
      learnersRegistered: null,
      learnersRegisteredDelta: null,
      learnersEnrolled: null,
      teachers: null,
      teachersDelta: null,
      admins: null,
    },
    presence: {
      timezone: HARARE,
      segments: pandaOffSegments,
      summary: null,
    },
  };

  it('shows a banner, a muted strip, and no hatched unknown or collector-gap segments', () => {
    const { getByTestId, queryByTestId, container } = render(() => (
      <SchoolWeek data={school} headerTimeZone="Europe/Brussels" />
    ));
    expect(getByTestId('monitoring-off-banner').textContent).toBe(MONITORING_OFF_MESSAGE);
    expect(getByTestId('monitoring-off-strip').textContent).toMatch(/Monitoring off/i);
    expect(container.querySelector('[data-state="gapUnknown"]')).toBeNull();
    expect(container.querySelector('[data-state="collectorGap"]')).toBeNull();
    expect(container.querySelector('.presence-seg--gapUnknown')).toBeNull();
    expect(container.querySelector('.presence-legend')).toBeNull();
    expect(queryByTestId('old-data-marker')).toBeNull();
    expect(container.textContent).toMatch(/Monitoring off/i);
    expect(container.querySelector('[data-testid="scorecard-pill"]')?.textContent).toMatch(/Monitoring off/i);
    expect(container.textContent).toMatch(/Learner share of minutes/);
    expect(container.textContent).not.toMatch(/Learner share of time/);
    expect(container.textContent).toMatch(/The Learners operate scorecard line uses sessions/);
  });

  it('renders the same muted strip and banner on Reachability, keeping the four-state legend off', () => {
    const data: UplinkResponse = {
      schema: API_SCHEMA,
      deploymentId: DEP_PANDA,
      weekStart: SAMPLE_WEEK,
      timezone: HARARE,
      samples: [],
      transitions: [],
    };
    const { getByTestId, container } = render(() => (
      <UplinkHistory data={data} school="kind-panda" segments={pandaOffSegments} monitoringEnabled={false} />
    ));
    expect(getByTestId('monitoring-off-banner').textContent).toBe(MONITORING_OFF_MESSAGE);
    expect(getByTestId('monitoring-off-strip').textContent).toMatch(/Monitoring off/i);
    expect(container.querySelector('[data-state="gapUnknown"]')).toBeNull();
    expect(container.querySelector('.presence-legend')).toBeNull();
  });
});

describe('PresenceStrip monitoringOff', () => {
  it('replaces hatched segments with a muted overlay and hides the four-state legend', () => {
    const off = render(() => (
      <PresenceStrip
        segments={pandaOffSegments}
        timeZone="Africa/Harare"
        utcOffset="+02:00"
        timeZoneLabel="kit local time (Africa/Harare, UTC+2)"
        weekStart="2026-11-02"
        weekEnd="2026-11-06"
        monitoringOff
      />
    ));
    expect(off.getByTestId('monitoring-off-strip').textContent).toMatch(/Monitoring off/i);
    expect(off.container.querySelector('.presence-legend')).toBeNull();
    expect(off.container.querySelector('[data-state="gapUnknown"]')).toBeNull();
    expect(off.container.querySelector('[data-state="collectorGap"]')).toBeNull();
    expect(off.queryByTestId('presence-summary')).toBeNull();

    const on = render(() => (
      <PresenceStrip
        segments={pandaOffSegments}
        timeZone="Africa/Harare"
        utcOffset="+02:00"
        timeZoneLabel="kit local time (Africa/Harare, UTC+2)"
        weekStart="2026-11-02"
        weekEnd="2026-11-06"
      />
    ));
    expect(on.container.querySelector('.presence-legend')).not.toBeNull();
    expect(on.getAllByText('Gap, length unknown').length).toBeGreaterThan(0);
    expect(on.getAllByText('Collector gap').length).toBeGreaterThan(0);
  });
});
