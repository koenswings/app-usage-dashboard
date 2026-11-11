import type { ScorecardInputs, ScorecardThresholds, SchoolHeadlines } from '../api/types';
import {
  SCORECARD_LINE_IDS,
  SCORECARD_LINE_LABELS,
  evaluateLine,
  pillForCard,
  pillWord,
  setupIsComplete,
  teachingCycleItemCount,
  learnerSessionShare,
  nextcloudWorkflowActions,
  type CardPill,
  type ScorecardLineId,
} from '../config/thresholds';
import { formatCount, formatMinutes, formatPercent, formatUnit } from './format';
import type { ScorecardHeadlineView, ScorecardLineView } from '../components/shared/ScorecardCard';

export function lineDetail(id: ScorecardLineId, inputs: ScorecardInputs): string {
  switch (id) {
    case 'available': {
      const { schoolDaysOn, schoolDaysExpected } = inputs.available;
      if (schoolDaysOn === null) return '—';
      return `${schoolDaysOn} / ${schoolDaysExpected} school days on`;
    }
    case 'setup': {
      const complete = setupIsComplete(inputs);
      const { classes, teachers, learnersEnrolled, nextcloudTeacherBeyondSeed, nextcloudLearnerBeyondSeed } =
        inputs.setup;
      if (complete === null && classes === null && teachers === null && learnersEnrolled === null) {
        return '—';
      }
      return (
        `${formatCount(teachers)} coaches · ${formatCount(classes)} classes · ` +
        `${formatCount(learnersEnrolled)} enrolled · Nextcloud beyond seed: ` +
        `${formatCount(nextcloudTeacherBeyondSeed)} teachers, ${formatCount(nextcloudLearnerBeyondSeed)} learners`
      );
    }
    case 'teachingCycle': {
      const items = teachingCycleItemCount(inputs);
      const sessions = inputs.teachingCycle.learnerSessionsOnAssigned;
      if (items === null && sessions === null) return '—';
      return (
        `${formatUnit(items, 'lesson or quiz visible or started', 'lessons or quizzes visible or started')} · ` +
        `${formatUnit(sessions, 'assigned learner visit', 'assigned learner visits')}`
      );
    }
    case 'learnersOperate': {
      const share = learnerSessionShare(inputs);
      if (share === null) return '—';
      return `${formatPercent(share)} of Kolibri sessions (learners vs coaches and admins)`;
    }
    case 'nextcloud': {
      const actions = nextcloudWorkflowActions(inputs);
      if (actions === null) return '—';
      return `${formatUnit(actions, 'share, co-edit or File drop upload', 'shares, co-edits or File drop uploads')}`;
    }
    case 'wikipedia': {
      if (inputs.wikipedia.pageViewsOwn === null) return '—';
      return `${formatCount(inputs.wikipedia.pageViewsOwn)} views on the school's own Wikipedia`;
    }
  }
}

export function buildScorecardLines(
  inputs: ScorecardInputs,
  thresholds: ScorecardThresholds,
): ScorecardLineView[] {
  return SCORECARD_LINE_IDS.map((id) => {
    const evaluation = evaluateLine(id, inputs, thresholds);
    const hasDetail = evaluation.tone !== 'noData' && evaluation.tone !== 'notMeasured';
    return {
      id,
      label: SCORECARD_LINE_LABELS[id],
      tone: evaluation.tone,
      word: evaluation.word,
      detail: hasDetail || evaluation.tone === 'needsHelp' || evaluation.tone === 'onTrack'
        ? lineDetail(id, inputs)
        : evaluation.tone === 'notMeasured'
          ? 'Not measured yet'
          : '—',
      barPercent: null,
    };
  });
}

export function buildPill(
  hasUsageData: boolean,
  lines: ScorecardLineView[],
  monitoringEnabled?: boolean,
): {
  pill: CardPill;
  pillLabel: string;
} {
  const pill = pillForCard(
    hasUsageData,
    lines.map((line) => line.tone),
    monitoringEnabled,
  );
  return { pill, pillLabel: pillWord(pill) };
}

export function buildHeadlines(headlines: SchoolHeadlines): ScorecardHeadlineView[] {
  return [
    { id: 'classes', value: formatCount(headlines.classes), label: 'classes' },
    { id: 'learners', value: formatCount(headlines.learnersRegistered), label: 'learners registered' },
    { id: 'teachers', value: formatCount(headlines.teachers), label: 'teachers' },
    { id: 'kolibri', value: formatMinutes(headlines.kolibriMinutes), label: 'Kolibri time' },
  ];
}
