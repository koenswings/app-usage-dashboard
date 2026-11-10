import type { ScorecardInputs, SchoolHeadlines } from '../api/types';
import {
  SCORECARD_LINE_IDS,
  SCORECARD_LINE_LABELS,
  lineHasData,
  pillForCard,
  pillWord,
  toneForLine,
  wordForTone,
  type CardPill,
  type ScorecardLineId,
} from '../config/thresholds';
import { formatCount, formatMinutes, formatPercent } from './format';
import type { ScorecardHeadlineView, ScorecardLineView } from '../components/shared/ScorecardCard';

export function lineDetail(id: ScorecardLineId, inputs: ScorecardInputs): string {
  switch (id) {
    case 'available': {
      const { schoolDaysOn, schoolDaysExpected } = inputs.available;
      if (schoolDaysOn === null) return '—';
      return `${schoolDaysOn} / ${schoolDaysExpected} days`;
    }
    case 'setup': {
      const { classes, learnersRegistered } = inputs.setup;
      if (classes === null && learnersRegistered === null) return '—';
      return `${formatCount(classes)} classes · ${formatCount(learnersRegistered)} registered`;
    }
    case 'teachingCycle': {
      const { lessonsCreated, lessonsVisible } = inputs.teachingCycle;
      if (lessonsCreated === null) return '—';
      return `${formatCount(lessonsCreated)} lessons · ${formatCount(lessonsVisible)} visible`;
    }
    case 'learnersOperate': {
      if (inputs.learnersOperate.learnerShareOfMinutes === null) return '—';
      return `${formatPercent(inputs.learnersOperate.learnerShareOfMinutes)} learner minutes`;
    }
    case 'nextcloud': {
      const { worksheetShares, fileDrops } = inputs.nextcloud;
      if (worksheetShares === null && fileDrops === null) return '—';
      return `${formatCount(worksheetShares)} shares · ${formatCount(fileDrops)} drops`;
    }
    case 'wikipedia': {
      if (inputs.wikipedia.pageViewsOwn === null) return '—';
      return `${formatCount(inputs.wikipedia.pageViewsOwn)} views`;
    }
  }
}

export function buildScorecardLines(
  inputs: ScorecardInputs,
  thresholdsConfigured: boolean,
): ScorecardLineView[] {
  return SCORECARD_LINE_IDS.map((id) => {
    const hasData = lineHasData(id, inputs);
    const tone = toneForLine(hasData, thresholdsConfigured);
    return {
      id,
      label: SCORECARD_LINE_LABELS[id],
      tone,
      word: wordForTone(tone),
      detail: hasData ? lineDetail(id, inputs) : '—',
      barPercent: null,
    };
  });
}

export function buildPill(hasUsageData: boolean, thresholdsConfigured: boolean): {
  pill: CardPill;
  pillLabel: string;
} {
  const pill = pillForCard(hasUsageData, thresholdsConfigured);
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
