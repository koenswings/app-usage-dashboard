import { render } from '@solidjs/testing-library';
import { API_SCHEMA } from '../src/api/types';
import type { NextcloudInstanceWeek, ScorecardInputs, SchoolWeekResponse, SetupStatus } from '../src/api/types';
import {
  DEP_CHIGONDA,
  DEP_NHARIRA,
  HARARE,
  SAMPLE_WEEK,
  censusFor,
  nhariraKolibri,
  nhariraNextcloud,
  scorecardFor,
} from '../src/mock/data';
import * as thresholds from '../src/config/thresholds';
import { DEFAULT_THRESHOLDS, SETUP_RULE_MEANING, evaluateLine, setupComplete } from '../src/config/thresholds';
import { appSetupSentence, appSetupWord, setupDetail } from '../src/lib/setup';
import { buildScorecardLines, lineDetail } from '../src/lib/scorecardView';
import { fridayOf } from '../src/lib/week';
import { KolibriPage, censusText, signedInUsersText } from '../src/pages/KolibriPage';
import { NextcloudPage, documentsByGroupText, documentsCreatedText } from '../src/pages/NextcloudPage';
import { SchoolWeek } from '../src/pages/SchoolWeek';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

function clone(inputs: ScorecardInputs): ScorecardInputs {
  return JSON.parse(JSON.stringify(inputs)) as ScorecardInputs;
}

function status(partial: Partial<SetupStatus>): SetupStatus {
  return { complete: null, kolibri: null, nextcloud: null, rule: 'u7-2026-11-11', ...partial };
}

function schoolWeek(deploymentId: string, scorecard: ScorecardInputs): SchoolWeekResponse {
  return {
    schema: API_SCHEMA,
    weekStart: SAMPLE_WEEK,
    weekEnd: fridayOf(SAMPLE_WEEK),
    deploymentId,
    school: deploymentId === DEP_NHARIRA ? 'Nharira' : 'Chigonda',
    engine: 'happy-zebra',
    lastPulled: '2026-11-06T16:10:00+02:00',
    stale: false,
    dataFrom: null,
    hasUsageData: true,
    monitoringEnabled: true,
    unused: false,
    thresholdsConfigured: false,
    sampleData: true,
    clockTrusted: true,
    timezone: HARARE,
    scorecard,
    census: censusFor(deploymentId, SAMPLE_WEEK),
    presence: { timezone: HARARE, segments: [], summary: null },
  };
}

describe('Set up uses the collector verdict (setupStatus.complete)', () => {
  it('maps true → On track, false → Needs help, null or missing → No data', () => {
    const inputs = clone(scorecardFor(DEP_NHARIRA, SAMPLE_WEEK));
    inputs.setupStatus = status({ complete: true });
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).word).toBe('On track');
    inputs.setupStatus = status({ complete: false });
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).word).toBe('Needs help');
    inputs.setupStatus = status({ complete: null });
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('noData');
    inputs.setupStatus = null;
    expect(setupComplete(inputs)).toBeNull();
    delete inputs.setupStatus;
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('noData');
  });

  it('does not re-implement U-7: the old web rule is gone and census numbers never decide', () => {
    expect('setupIsComplete' in thresholds).toBe(false);
    const sources = readdirSync(resolve(__dirname, '../src'), { recursive: true, encoding: 'utf8' })
      .filter((file) => /\.(ts|tsx)$/.test(file))
      .map((file) => readFileSync(resolve(__dirname, '../src', file), 'utf8'));
    expect(sources.some((text) => text.includes('setupIsComplete'))).toBe(false);
    const inputs = clone(scorecardFor(DEP_CHIGONDA, SAMPLE_WEEK));
    inputs.setup.classes = 9;
    inputs.setup.teachers = 9;
    inputs.setup.learnersEnrolled = 9;
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
  });

  it('lists missing and unknown parts in plain words on the fleet line', () => {
    const inputs = scorecardFor(DEP_CHIGONDA, SAMPLE_WEEK);
    expect(lineDetail('setup', inputs)).toBe(
      'Missing: coach, class, enrolment · Nextcloud not known',
    );
    expect(lineDetail('setup', scorecardFor(DEP_NHARIRA, SAMPLE_WEEK))).toBe('Own Kolibri and Nextcloud set up');
    expect(setupDetail(null)).toBe('—');
    const setupLine = buildScorecardLines(inputs, DEFAULT_THRESHOLDS).find((line) => line.id === 'setup');
    expect(setupLine?.word).toBe('Needs help');
  });

  it('explains each app in plain words, and an app with no own copy does not count', () => {
    const chigonda = scorecardFor(DEP_CHIGONDA, SAMPLE_WEEK).setupStatus!;
    expect(appSetupWord(chigonda.kolibri)).toBe('Not set up');
    expect(appSetupSentence(chigonda.kolibri)).toBe(
      'Missing a coach, a class and learners enrolled in a class in the own Kolibri.',
    );
    expect(appSetupWord(chigonda.nextcloud)).toBe('No data');
    expect(appSetupSentence(chigonda.nextcloud)).toBe(
      'Not known yet: teacher accounts beyond the seeds and learner accounts beyond the seeds in the own Nextcloud.',
    );
    expect(appSetupWord(null)).toBe('No own copy');
  });

  it('describes U-7 in the Settings note', () => {
    expect(SETUP_RULE_MEANING).toMatch(/at least one coach, at least one class and learners enrolled in a class/);
    expect(SETUP_RULE_MEANING).toMatch(/teacher and learner accounts beyond the seed accounts/);
  });
});

describe('School week: Set up check, Coaches and graded copies', () => {
  it('shows the per-app check, the Coaches tile and the graded copies', () => {
    const { getByTestId, getByText } = render(() => (
      <SchoolWeek data={schoolWeek(DEP_CHIGONDA, scorecardFor(DEP_CHIGONDA, SAMPLE_WEEK))} headerTimeZone="Europe/Brussels" />
    ));
    expect(getByTestId('setup-check-kolibri').textContent).toMatch(/Own KolibriNot set upMissing a coach/);
    expect(getByTestId('setup-check-nextcloud').textContent).toMatch(/No data/);
    expect(getByTestId('graded-copies').textContent).toMatch(/Kolibri chigon\./);
    expect(getByTestId('graded-copies').querySelector('[title="kolibri-chigonda"]')).not.toBeNull();
    expect(getByText('Coaches')).toBeTruthy();
  });

  it('renders No data when the collector sends no verdict and hides graded copies when absent', () => {
    const inputs = clone(scorecardFor(DEP_NHARIRA, SAMPLE_WEEK));
    delete inputs.setupStatus;
    delete inputs.copies;
    const { getByTestId, queryByTestId } = render(() => (
      <SchoolWeek data={schoolWeek(DEP_NHARIRA, inputs)} headerTimeZone="Europe/Brussels" />
    ));
    expect(getByTestId('setup-check-no-data').textContent).toBe('No data');
    expect(queryByTestId('graded-copies')).toBeNull();
  });
});

describe('Kolibri copies: coaches, census and signed-in users', () => {
  it('labels the coach role Coaches and shows the beyond-seed count when sent', () => {
    const { container, getAllByTestId } = render(() => (
      <KolibriPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances: nhariraKolibri }}
        school="Nharira"
      />
    ));
    expect(container.textContent).toMatch(/Coaches/);
    expect(container.textContent).toMatch(/18 \(17 beyond seeds\)/);
    expect(getAllByTestId('kolibri-copy-census')[0].textContent).toMatch(/2 coaches/);
    expect(signedInUsersText({ users: 3 })).toBe('3');
    expect(signedInUsersText({ users: null, usersBeyondSeed: 2 })).toBe('—');
  });

  it('writes the census with singulars and dashes', () => {
    expect(
      censusText({
        classes: 0,
        classesDelta: null,
        learnersRegistered: 1,
        learnersRegisteredDelta: null,
        learnersEnrolled: null,
        teachers: 1,
        teachersDelta: null,
        admins: 1,
      }),
    ).toBe('0 classes · 1 learner registered (— enrolled in a class) · 1 coach · 1 admin');
    expect(censusText(null)).toBe('No data');
  });
});

describe('Nextcloud documents created', () => {
  it('shows counts when sent and No data for null or missing', () => {
    expect(documentsCreatedText(4)).toBe('4');
    expect(documentsCreatedText(0)).toBe('0');
    expect(documentsCreatedText(null)).toBe('No data');
    expect(documentsCreatedText(undefined)).toBe('No data');
    expect(documentsByGroupText(null)).toBe('No data');
    expect(documentsByGroupText({ admin: 1, teacher: 3, learner: 0 })).toMatch(/1 .* 3 .* 0/);
    const legacy = nhariraNextcloud.map((item) => {
      const copy = { ...item } as NextcloudInstanceWeek;
      delete copy.documentsCreated;
      delete copy.documentsCreatedByGroup;
      return copy;
    });
    const { container } = render(() => (
      <NextcloudPage
        data={{ schema: API_SCHEMA, deploymentId: DEP_NHARIRA, weekStart: SAMPLE_WEEK, clockTrusted: true, instances: legacy }}
        school="Nharira"
      />
    ));
    expect(container.textContent).toMatch(/Documents createdNo data/);
  });
});
