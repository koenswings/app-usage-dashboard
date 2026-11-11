import { render } from '@solidjs/testing-library';
import { ScorecardCard } from '../src/components/shared/ScorecardCard';
import { cardsByWeek, PREV_WEEK, SAMPLE_WEEK, scorecardFor } from '../src/mock/data';
import { buildHeadlines, buildPill, buildScorecardLines } from '../src/lib/scorecardView';
import type { ScorecardInputs, ScorecardThresholds } from '../src/api/types';
import {
  DEFAULT_THRESHOLDS,
  evaluateLine,
  evaluateLines,
  pillForCard,
  resolveEffectiveThresholds,
  unusedRuleText,
} from '../src/config/thresholds';

function cloneInputs(base: ScorecardInputs): ScorecardInputs {
  return structuredClone(base);
}

function nharira(): ScorecardInputs {
  return cloneInputs(scorecardFor('dep-nharira', SAMPLE_WEEK));
}

function renderCard(deploymentId: string, weekStart = SAMPLE_WEEK, thresholds: ScorecardThresholds = DEFAULT_THRESHOLDS) {
  const card = cardsByWeek[weekStart].find((item) => item.deploymentId === deploymentId);
  if (!card) throw new Error(deploymentId);
  const lines = buildScorecardLines(card.scorecard, thresholds);
  const pill = buildPill(card.hasUsageData, lines, card.monitoringEnabled);
  return render(() => (
    <ScorecardCard
      school={card.school}
      engine={card.engine}
      note={card.note}
      pill={pill.pill}
      pillLabel={pill.pillLabel}
      lines={lines}
      headlines={buildHeadlines(card.headlines)}
      lastPulledLabel="10 Nov 2026, 13:40 Europe/Brussels"
      stale={card.stale}
      dataFromLabel={card.dataFrom ? `data from 4 Nov 2026` : null}
    />
  ));
}

describe('ScorecardCard wording', () => {
  it('says No data, never Grey, for a school without usage data', () => {
    const { container } = renderCard('dep-chigonda', PREV_WEEK);
    expect(container.textContent).toMatch(/No data/);
    expect(container.textContent).not.toMatch(/Grey/);
    expect(container.textContent).not.toMatch(/gray/i);
  });

  it('grades Nharira as OK and On track with the U-7 defaults', () => {
    const { container, getByTestId } = renderCard('dep-nharira');
    expect(getByTestId('scorecard-pill').textContent).toBe('OK');
    expect(container.textContent).toMatch(/On track/);
    expect(container.textContent).not.toMatch(/Thresholds not set/);
    expect(container.textContent).not.toMatch(/Grey/);
  });

  it('grades Chigonda as Help, with Needs help on amber lines', () => {
    const { container, getByTestId } = renderCard('dep-chigonda');
    expect(getByTestId('scorecard-pill').textContent).toBe('Help');
    expect(container.textContent).toMatch(/Needs help/);
    expect(container.textContent).not.toMatch(/Thresholds not set/);
    expect(container.textContent).not.toMatch(/Grey/);
  });

  it('shows an Unused pill and the plain unused rule without hiding the lines', () => {
    const card = cardsByWeek[SAMPLE_WEEK].find((item) => item.deploymentId === 'dep-chigonda');
    if (!card) throw new Error('missing chigonda');
    const lines = buildScorecardLines(card.scorecard, DEFAULT_THRESHOLDS);
    const pill = buildPill(card.hasUsageData, lines, true, true);
    const { getByTestId, container } = render(() => (
      <ScorecardCard
        school={card.school}
        engine={card.engine}
        pill={pill.pill}
        pillLabel={pill.pillLabel}
        lines={lines}
        headlines={buildHeadlines(card.headlines)}
        lastPulledLabel="4 Nov 2026, 09:00 Europe/Brussels"
        stale={card.stale}
        dataFromLabel={null}
        banner={unusedRuleText(DEFAULT_THRESHOLDS)}
      />
    ));
    expect(pill.pill).toBe('unused');
    expect(getByTestId('scorecard-pill').textContent).toBe('Unused');
    expect(getByTestId('unused-message').textContent).toMatch(/still amber with no improvement 4 school weeks after help/);
    expect(container.textContent).toMatch(/Needs help/);
  });
});

describe('U-7 line evaluation', () => {
  it('Available is green at 3 school days, amber at 2, grey only when days and minutes are missing', () => {
    const inputs = nharira();
    inputs.available.schoolDaysOn = 3;
    expect(evaluateLine('available', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.available.schoolDaysOn = 2;
    expect(evaluateLine('available', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.available.schoolDaysOn = null;
    expect(evaluateLine('available', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.available.schoolHoursOnMinutes = null;
    expect(evaluateLine('available', inputs, DEFAULT_THRESHOLDS)).toEqual({
      id: 'available',
      tone: 'noData',
      word: 'No data',
    });
  });

  it('Set up is yes when registered learners and teachers are both > 0', () => {
    const inputs = nharira();
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.setup.teachers = 0;
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.setup.teachers = 1;
    inputs.setup.learnersRegistered = 1;
    inputs.setup.classes = 0;
    inputs.setup.learnersEnrolled = 0;
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.setup.classes = null;
    inputs.setup.learnersRegistered = null;
    inputs.setup.teachers = null;
    inputs.setup.nextcloudTeacherBeyondSeed = 2;
    inputs.setup.nextcloudLearnerBeyondSeed = 0;
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.setup.nextcloudTeacherBeyondSeed = 0;
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.setup.nextcloudTeacherBeyondSeed = null;
    inputs.setup.nextcloudLearnerBeyondSeed = null;
    expect(evaluateLine('setup', inputs, DEFAULT_THRESHOLDS).tone).toBe('noData');
  });

  it('Teaching cycle needs the item count and at least one assigned learner visit', () => {
    const inputs = nharira();
    inputs.teachingCycle.lessonsVisible = 1;
    inputs.teachingCycle.quizzesStarted = 0;
    inputs.teachingCycle.learnerSessionsOnAssigned = 1;
    expect(evaluateLine('teachingCycle', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.teachingCycle.learnerSessionsOnAssigned = 0;
    expect(evaluateLine('teachingCycle', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.teachingCycle.lessonsVisible = 0;
    inputs.teachingCycle.learnerSessionsOnAssigned = 4;
    expect(evaluateLine('teachingCycle', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.teachingCycle.lessonsVisible = null;
    inputs.teachingCycle.quizzesStarted = null;
    inputs.teachingCycle.lessonsCreated = null;
    inputs.teachingCycle.quizzesCreated = null;
    inputs.teachingCycle.learnerSessionsOnAssigned = null;
    expect(evaluateLine('teachingCycle', inputs, DEFAULT_THRESHOLDS).tone).toBe('noData');
  });

  it('Learners operate uses session share, green at 50%, not minutes', () => {
    const inputs = nharira();
    inputs.learnersOperate.learnerSessions = 1;
    inputs.learnersOperate.coachSessions = 1;
    inputs.learnersOperate.adminSessions = 0;
    inputs.learnersOperate.learnerShareOfMinutes = 0.1;
    expect(evaluateLine('learnersOperate', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.learnersOperate.learnerSessions = 1;
    inputs.learnersOperate.coachSessions = 1;
    inputs.learnersOperate.adminSessions = 1;
    expect(evaluateLine('learnersOperate', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.learnersOperate.learnerSessions = 0;
    inputs.learnersOperate.coachSessions = 0;
    inputs.learnersOperate.adminSessions = 0;
    expect(evaluateLine('learnersOperate', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.learnersOperate.learnerSessions = null;
    inputs.learnersOperate.coachSessions = null;
    inputs.learnersOperate.adminSessions = null;
    inputs.learnersOperate.learnerShareOfMinutes = 0.9;
    expect(evaluateLine('learnersOperate', inputs, DEFAULT_THRESHOLDS).tone).toBe('noData');
  });

  it('Nextcloud sums shares, uploads and office opens, and ignores File drop links', () => {
    const inputs = nharira();
    inputs.nextcloud.worksheetShares = 0;
    inputs.nextcloud.editShares = 0;
    inputs.nextcloud.fileDropUploads = 0;
    inputs.nextcloud.schoolFilesShares = 0;
    inputs.nextcloud.officeOpens = 0;
    inputs.nextcloud.fileDropLinks = 4;
    expect(evaluateLine('nextcloud', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.nextcloud.officeOpens = 1;
    expect(evaluateLine('nextcloud', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.nextcloud.officeOpens = 0;
    inputs.nextcloud.worksheetShares = 1;
    expect(evaluateLine('nextcloud', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.nextcloud.worksheetShares = null;
    inputs.nextcloud.editShares = null;
    inputs.nextcloud.fileDropUploads = null;
    inputs.nextcloud.schoolFilesShares = null;
    inputs.nextcloud.officeOpens = null;
    expect(evaluateLine('nextcloud', inputs, DEFAULT_THRESHOLDS).tone).toBe('noData');
  });

  it('Wikipedia is green at 10 own views, amber at 9, grey when unmeasured', () => {
    const inputs = nharira();
    inputs.wikipedia.pageViewsOwn = 10;
    expect(evaluateLine('wikipedia', inputs, DEFAULT_THRESHOLDS).tone).toBe('onTrack');
    inputs.wikipedia.pageViewsOwn = 9;
    expect(evaluateLine('wikipedia', inputs, DEFAULT_THRESHOLDS).tone).toBe('needsHelp');
    inputs.wikipedia.pageViewsOwn = null;
    expect(evaluateLine('wikipedia', inputs, DEFAULT_THRESHOLDS).tone).toBe('noData');
  });

  it('never treats a grey line as amber on the card pill, and unused wins over Help', () => {
    const inputs = nharira();
    const empty = nharira();
    empty.available.schoolDaysOn = null;
    empty.available.schoolHoursOnMinutes = null;
    empty.setup.teachers = null;
    empty.setup.classes = null;
    empty.setup.learnersRegistered = null;
    empty.setup.learnersEnrolled = null;
    empty.setup.nextcloudTeacherBeyondSeed = null;
    empty.setup.nextcloudLearnerBeyondSeed = null;
    empty.teachingCycle.lessonsCreated = null;
    empty.teachingCycle.lessonsVisible = null;
    empty.teachingCycle.quizzesCreated = null;
    empty.teachingCycle.quizzesStarted = null;
    empty.teachingCycle.learnerSessionsOnAssigned = null;
    empty.learnersOperate.learnerSessions = null;
    empty.learnersOperate.coachSessions = null;
    empty.learnersOperate.adminSessions = null;
    empty.nextcloud.worksheetShares = null;
    empty.nextcloud.editShares = null;
    empty.nextcloud.fileDropUploads = null;
    empty.nextcloud.schoolFilesShares = null;
    empty.nextcloud.officeOpens = null;
    empty.wikipedia.pageViewsOwn = null;
    const tones = evaluateLines(empty, DEFAULT_THRESHOLDS).map((line) => line.tone);
    expect(tones.every((tone) => tone === 'noData')).toBe(true);
    expect(pillForCard(true, tones)).toBe('noData');
    const mixed = evaluateLines(inputs, DEFAULT_THRESHOLDS);
    mixed[0] = { id: 'available', tone: 'noData', word: 'No data' };
    expect(pillForCard(true, mixed.map((line) => line.tone))).toBe('ok');
    mixed[1] = { id: 'setup', tone: 'needsHelp', word: 'Needs help' };
    expect(pillForCard(true, mixed.map((line) => line.tone))).toBe('help');
    expect(pillForCard(true, mixed.map((line) => line.tone), true, true)).toBe('unused');
    expect(pillForCard(true, mixed.map((line) => line.tone), false, true)).toBe('monitoringOff');
    expect(unusedRuleText(DEFAULT_THRESHOLDS)).toMatch(/4 school weeks after help/);
  });
});

describe('settings fallback', () => {
  it('uses built-in defaults when /meta.thresholds is absent', () => {
    expect(resolveEffectiveThresholds(undefined)).toEqual(DEFAULT_THRESHOLDS);
    expect(resolveEffectiveThresholds(null)).toEqual(DEFAULT_THRESHOLDS);
  });

  it('uses /meta.thresholds over the built-in defaults', () => {
    const effective = resolveEffectiveThresholds({ wikipediaMinViews: 15, availableMinSchoolDays: 4 });
    expect(effective.wikipediaMinViews).toBe(15);
    expect(effective.availableMinSchoolDays).toBe(4);
    expect(effective.helpAfterAmberWeeks).toBe(3);
  });
});
