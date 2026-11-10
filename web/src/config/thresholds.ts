/**
 * Scorecard threshold comparison lives only in this module (idea#415 / idea#375).
 *
 * Koen has not set cut-offs yet. Until `thresholdsConfigured` is true AND
 * values are filled in here, every data-bearing line is "Thresholds not set"
 * and no Help / OK grade is invented.
 */
import type { ScorecardInputs } from '../api/types';

export type LineTone = 'onTrack' | 'needsHelp' | 'noData' | 'thresholdsNotSet';
export type CardPill = 'ok' | 'help' | 'noData' | 'thresholdsNotSet';

export type ScorecardLineId =
  | 'available'
  | 'setup'
  | 'teachingCycle'
  | 'learnersOperate'
  | 'nextcloud'
  | 'wikipedia';

export const SCORECARD_LINE_IDS: ScorecardLineId[] = [
  'available',
  'setup',
  'teachingCycle',
  'learnersOperate',
  'nextcloud',
  'wikipedia',
];

export const SCORECARD_LINE_LABELS: Record<ScorecardLineId, string> = {
  available: 'Available',
  setup: 'Set up',
  teachingCycle: 'Teaching cycle',
  learnersOperate: 'Learners operate',
  nextcloud: 'Nextcloud',
  wikipedia: 'Wikipedia',
};

export function lineHasData(id: ScorecardLineId, inputs: ScorecardInputs): boolean {
  switch (id) {
    case 'available':
      return inputs.available.schoolDaysOn !== null || inputs.available.schoolHoursOnMinutes !== null;
    case 'setup':
      return inputs.setup.classes !== null || inputs.setup.learnersRegistered !== null;
    case 'teachingCycle':
      return inputs.teachingCycle.lessonsCreated !== null || inputs.teachingCycle.quizzesCreated !== null;
    case 'learnersOperate':
      return inputs.learnersOperate.learnerShareOfMinutes !== null || inputs.learnersOperate.learnerSessions !== null;
    case 'nextcloud':
      return inputs.nextcloud.worksheetShares !== null || inputs.nextcloud.officeOpens !== null;
    case 'wikipedia':
      return inputs.wikipedia.pageViewsOwn !== null;
  }
}

export function toneForLine(hasData: boolean, thresholdsConfigured: boolean): LineTone {
  if (!hasData) return 'noData';
  if (!thresholdsConfigured) return 'thresholdsNotSet';
  return 'thresholdsNotSet';
}

export function wordForTone(tone: LineTone): string {
  switch (tone) {
    case 'noData':
      return 'No data';
    case 'thresholdsNotSet':
      return 'Thresholds not set';
    case 'onTrack':
      return 'On track';
    case 'needsHelp':
      return 'Needs help';
  }
}

export function pillForCard(hasUsageData: boolean, thresholdsConfigured: boolean): CardPill {
  if (!hasUsageData) return 'noData';
  if (!thresholdsConfigured) return 'thresholdsNotSet';
  return 'thresholdsNotSet';
}

export function pillWord(pill: CardPill): string {
  switch (pill) {
    case 'noData':
      return 'No data';
    case 'thresholdsNotSet':
      return 'Thresholds not set';
    case 'ok':
      return 'OK';
    case 'help':
      return 'Help';
  }
}
