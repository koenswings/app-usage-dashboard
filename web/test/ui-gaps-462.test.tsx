import { render, fireEvent } from '@solidjs/testing-library';
import { API_SCHEMA } from '../src/api/types';
import type {
  DiscoveredInstance,
  KiwixInstanceWeek,
  KolibriInstanceWeek,
  NextcloudInstanceWeek,
  UplinkResponse,
  UplinkSample,
} from '../src/api/types';
import {
  DEP_NHARIRA,
  HARARE,
  SAMPLE_WEEK,
  chigondaKiwix,
  instancesFor,
  nhariraKiwix,
  nhariraKolibri,
  nhariraNextcloud,
} from '../src/mock/data';
import { ScorecardCard } from '../src/components/shared/ScorecardCard';
import { formatCountPhrase, pluralWord } from '../src/lib/format';
import { shortIdsForDuplicateNames } from '../src/lib/instances';
import { buildHeadlines, lineDetail } from '../src/lib/scorecardView';
import {
  UPLINK_NO_CHANGE_MESSAGE,
  groupSamplesByDay,
  uplinkTransitionsEmptyText,
} from '../src/lib/uplink';
import { InstanceBreakdown } from '../src/pages/InstanceBreakdown';
import { KolibriPage } from '../src/pages/KolibriPage';
import { NextcloudPage, appsOpenedText } from '../src/pages/NextcloudPage';
import { UplinkHistory } from '../src/pages/UplinkHistory';
import { WikipediaPage, schoolHourly } from '../src/pages/WikipediaPage';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const segments = [
  {
    state: 'gapUnknown' as const,
    start: '2026-11-02T00:00:00+02:00',
    end: '2026-11-07T00:00:00+02:00',
    lengthKnown: false,
  },
];

function kolibriCopy(id: string, name = 'i413-Kolibri'): KolibriInstanceWeek {
  return { ...nhariraKolibri[0], instance: id, instanceId: id, name };
}

function nextcloudCopy(partial: Partial<NextcloudInstanceWeek>): NextcloudInstanceWeek {
  return { ...nhariraNextcloud[0], ...partial };
}

function kiwixCopy(id: string, pageViews: number, hour: number): KiwixInstanceWeek {
  const byHour = Array.from({ length: 24 }, (_, h) => (h === hour ? pageViews : 0));
  return { ...chigondaKiwix[0], instance: id, instanceId: id, name: 'i413-Kiwix', pageViews, byHour };
}

function sample(timestamp: string, online = true): UplinkSample {
  return { timestamp, engine: 'idea03', online, lastSeen: null, via: 'DERP', latencyMs: null };
}

function uplink(partial: Partial<UplinkResponse>): UplinkResponse {
  return {
    schema: API_SCHEMA,
    deploymentId: DEP_NHARIRA,
    weekStart: SAMPLE_WEEK,
    timezone: HARARE,
    samples: [],
    transitions: [],
    ...partial,
  };
}

describe('1 · Kolibri role table', () => {
  it('labels the per-role count "Signed-in users", never "Accounts"', () => {
    const { container } = render(() => (
      <KolibriPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances: nhariraKolibri }}
        school="Nharira"
      />
    ));
    const headers = [...container.querySelectorAll('th')].map((th) => th.textContent);
    expect(headers).toContain('Signed-in users');
    expect(headers).not.toContain('Accounts');
  });
});

describe('2 · Nextcloud Apps opened row', () => {
  it('says No data for null, None recorded for {}, and lists counts otherwise', () => {
    expect(appsOpenedText(null)).toBe('No data');
    expect(appsOpenedText(undefined)).toBe('No data');
    expect(appsOpenedText({})).toBe('None recorded');
    expect(appsOpenedText({ files: 4 })).toMatch(/4/);
  });

  it('always renders the row for measured copies', () => {
    const instances = [
      nextcloudCopy({ instance: 'nc-null', instanceId: 'nc-null', name: 'A', appsOpened: null }),
      nextcloudCopy({ instance: 'nc-empty', instanceId: 'nc-empty', name: 'B', appsOpened: {} }),
    ];
    const { getByTestId } = render(() => (
      <NextcloudPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances }}
        school="Nharira"
      />
    ));
    const rowText = (id: string) =>
      [...getByTestId(`nextcloud-instance-${id}`).querySelectorAll('tr')]
        .map((tr) => tr.textContent ?? '')
        .find((text) => text.startsWith('Apps opened'));
    expect(rowText('nc-null')).toBe('Apps openedNo data');
    expect(rowText('nc-empty')).toBe('Apps openedNone recorded');
  });
});

describe('3 · Wikipedia hourly minimum on the school total', () => {
  const copies = [kiwixCopy('kiwix-a', 6, 7), kiwixCopy('kiwix-b', 5, 6), kiwixCopy('kiwix-c', 5, 7), kiwixCopy('kiwix-d', 5, 10)];

  it('sums views and hours across copies', () => {
    const total = schoolHourly(copies);
    expect(total?.pageViews).toBe(21);
    expect(total?.copies).toBe(4);
    expect(total?.views[7]).toBe(11);
    expect(total?.views[6]).toBe(5);
    expect(total?.views[10]).toBe(5);
  });

  it('shows a school-total chart at 21 ≥ 20 while copies below the minimum say "this copy"', () => {
    const { getByTestId, getAllByTestId } = render(() => (
      <WikipediaPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances: copies }}
        school="idea03"
        hourlyChartMinWeeklyViews={20}
      />
    ));
    const total = getByTestId('kiwix-school-total');
    expect(total.querySelector('[data-testid="hourly-chart"]')?.getAttribute('data-scope')).toBe('school');
    const hidden = getAllByTestId('hourly-chart-hidden');
    expect(hidden.length).toBe(4);
    hidden.forEach((el) => expect(el.textContent).toMatch(/this copy/));
  });

  it('hides the school chart when the school total is below the minimum', () => {
    const small = [kiwixCopy('kiwix-a', 6, 7), kiwixCopy('kiwix-b', 5, 6)];
    const { getByTestId } = render(() => (
      <WikipediaPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances: small }}
        school="idea03"
        hourlyChartMinWeeklyViews={20}
      />
    ));
    const total = getByTestId('kiwix-school-total');
    expect(total.querySelector('[data-testid="hourly-chart"]')).toBeNull();
    expect(total.querySelector('[data-testid="hourly-chart-hidden"]')?.textContent).toMatch(/school’s week/);
  });

  it('keeps one chart with school wording when only one copy is measured', () => {
    const { queryByTestId, getByTestId } = render(() => (
      <WikipediaPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances: [nhariraKiwix[0]] }}
        school="Nharira"
        hourlyChartMinWeeklyViews={20}
      />
    ));
    expect(queryByTestId('kiwix-school-total')).toBeNull();
    expect(getByTestId('hourly-chart').getAttribute('data-scope')).toBe('school');
  });
});

describe('4 · short instance ids for copies with the same name', () => {
  it('gives ids only to duplicated names and keeps them unique', () => {
    const ids = shortIdsForDuplicateNames([
      { instance: 'kolibri-2htevnk74t5hszft809', name: 'i413-Kolibri' },
      { instance: 'kolibri-2htevnzzzzzzzzzzzz', name: 'i413-Kolibri' },
      { instance: 'kolibri-x5pfdilbu5hhodwyije', name: 'i413-Kolibri' },
      { instance: 'kolibri-own', name: 'Kolibri' },
    ]);
    expect(ids.get('kolibri-own')).toBeUndefined();
    const short = ['kolibri-2htevnk74t5hszft809', 'kolibri-2htevnzzzzzzzzzzzz', 'kolibri-x5pfdilbu5hhodwyije'].map((key) => ids.get(key));
    expect(new Set(short).size).toBe(3);
    expect(short[2]).toBe('x5pfdil'); // one length per name group
    expect(short[0]).toBe('2htevnk');
  });

  it('shows the short id in Kolibri headings for duplicates only', () => {
    const instances = [kolibriCopy('kolibri-2htevnk74t5hszft809'), kolibriCopy('kolibri-4ege8c1n8kdfbtgxpd6'), kolibriCopy('kolibri-solo', 'Kolibri Demo')];
    const { getByTestId } = render(() => (
      <KolibriPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances }}
        school="idea03"
      />
    ));
    expect(getByTestId('kolibri-instance-kolibri-2htevnk74t5hszft809').querySelector('strong')?.textContent).toBe('i413-Kolibri · 2htevn');
    expect(getByTestId('kolibri-instance-kolibri-4ege8c1n8kdfbtgxpd6').querySelector('strong')?.textContent).toBe('i413-Kolibri · 4ege8c');
    expect(getByTestId('kolibri-instance-kolibri-solo').querySelector('[data-testid="instance-short-id"]')).toBeNull();
  });

  it('shows the short id on Apps rows that share a name', () => {
    const data = instancesFor(DEP_NHARIRA, SAMPLE_WEEK);
    const { getByTestId } = render(() => <InstanceBreakdown data={data} school="Nharira" />);
    expect(getByTestId('instance-row-kolibri-a1b2c3').textContent).toMatch(/Kolibri · a1b2c3/);
    expect(getByTestId('instance-row-kolibri-unlisted-62561').textContent).toMatch(/Kolibri · 62561/);
    expect(getByTestId('instance-row-kolibri-demo').querySelector('[data-testid="instance-short-id"]')).toBeNull();
    const extra: DiscoveredInstance | undefined = data.instances.find((item) => item.instance === 'nextcloud-extra');
    expect(extra).toBeTruthy();
    expect(getByTestId('instance-row-nextcloud-extra').textContent).toMatch(/Nextcloud · extra/);
  });
});

describe('5 · reachability samples bounded by day', () => {
  const samples: UplinkSample[] = [];
  for (let i = 0; i < 200; i += 1) {
    const at = new Date(Date.parse('2026-11-03T06:00:00Z') + i * 5 * 60 * 1000).toISOString();
    samples.push(sample(at, i !== 50));
  }

  it('groups samples into kit-local days with counts and a time range', () => {
    const days = groupSamplesByDay(samples, 'Africa/Harare');
    expect(days.map((day) => day.day)).toEqual(['2026-11-03', '2026-11-04']);
    expect(days[0].total + days[1].total).toBe(200);
    expect(days[0].notReachable).toBe(1);
    expect(days[0].firstTime).toBe('08:00');
    expect(days[0].label).toBe('Tue 3 Nov 2026');
  });

  it('renders one collapsed summary per day instead of one row per sample', () => {
    const { container, getAllByRole } = render(() => (
      <UplinkHistory data={uplink({ measured: true, samples })} school="Nharira" segments={segments} />
    ));
    const days = container.querySelectorAll('details.uplink-day');
    expect(days.length).toBe(2);
    days.forEach((day) => expect(day.hasAttribute('open')).toBe(false));
    expect(getAllByRole('group').length).toBe(2);
    const summary = days[0].querySelector('summary');
    expect(summary?.textContent).toMatch(/checks · \d+ reachable · 1 not reachable to us/);
    fireEvent.click(summary as Element);
    expect(container.querySelectorAll('details.uplink-day')[0].querySelectorAll('tbody tr').length).toBeGreaterThan(0);
  });
});

describe('6 · reachability with no changes', () => {
  it('says No change this week when measured with 0 transitions', () => {
    expect(uplinkTransitionsEmptyText(true)).toBe(UPLINK_NO_CHANGE_MESSAGE);
    expect(uplinkTransitionsEmptyText(undefined)).toBe('No data');
    const { getByTestId } = render(() => (
      <UplinkHistory
        data={uplink({ measured: true, samples: [sample('2026-11-03T08:00:00Z')] })}
        school="Nharira"
        segments={segments}
      />
    ));
    expect(getByTestId('uplink-transitions-empty').textContent).toBe('No change this week');
  });

  it('keeps the not-measured empty state for measured:false', () => {
    const { getByTestId, queryByTestId } = render(() => (
      <UplinkHistory data={uplink({ measured: false })} school="Nharira" segments={segments} />
    ));
    expect(getByTestId('uplink-not-measured')).toBeTruthy();
    expect(queryByTestId('uplink-transitions-empty')).toBeNull();
  });
});

describe('7 · singular and plural counts', () => {
  it('writes "1 learner registered · 1 teacher" and keeps plurals otherwise', () => {
    expect(formatCountPhrase(1, 'learner registered', 'learners registered')).toBe('1 learner registered');
    expect(formatCountPhrase(3, 'learner registered', 'learners registered')).toBe('3 learners registered');
    expect(formatCountPhrase(null, 'learner registered', 'learners registered')).toBe('— learners registered');
    expect(pluralWord(0, 'class', 'classes')).toBe('classes');
    const inputs = {
      setup: { classes: 0, learnersRegistered: 1, learnersEnrolled: null, teachers: 1, admins: 1, nextcloudTeacherBeyondSeed: 0, nextcloudLearnerBeyondSeed: 0 },
    } as unknown as Parameters<typeof lineDetail>[1];
    expect(lineDetail('setup', inputs)).toBe('—');
  });

  it('uses singular headline labels for a count of one', () => {
    const headlines = buildHeadlines({ classes: 1, learnersRegistered: 1, teachers: 2, kolibriMinutes: 24 });
    expect(headlines.map((item) => item.label)).toEqual(['class', 'learner registered', 'coaches', 'Kolibri time']);
    expect(buildHeadlines({ classes: 0, learnersRegistered: 1, teachers: 1, kolibriMinutes: 0 })[2].label).toBe('coach');
  });
});

describe('8 · fleet card detail on one line', () => {
  const css = readFileSync(resolve(__dirname, '../src/main.css'), 'utf8');

  it('keeps fleet line details on one line and uses two fleet columns at laptop widths', () => {
    expect(css).toMatch(/\.schools \.scorecard-line__detail \{[^}]*white-space: nowrap/);
    expect(css).toMatch(/@media \(max-width: 1520px\) \{\s*\.schools \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}/);
  });

  it('puts the full detail in a tooltip in case it is ever clipped', () => {
    const { container } = render(() => (
      <ScorecardCard
        school="idea03"
        engine="idea03"
        pill="help"
        pillLabel="Help"
        lines={[{ id: 'setup', label: 'Set up', tone: 'onTrack', word: 'On track', detail: '1 learner registered · 1 teacher', barPercent: null }]}
        headlines={[]}
        lastPulledLabel={null}
        stale={false}
        dataFromLabel={null}
      />
    ));
    expect(container.querySelector('.scorecard-line__detail')?.getAttribute('title')).toBe('1 learner registered · 1 teacher');
  });
});

describe('9 · Wikipedia distinct-articles label', () => {
  it('says "distinct articles (most in one day)"', () => {
    const { container } = render(() => (
      <WikipediaPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances: [chigondaKiwix[0]] }}
        school="Chigonda"
        hourlyChartMinWeeklyViews={20}
      />
    ));
    expect(container.textContent).toMatch(/distinct articles \(most in one day\)/);
  });
});
