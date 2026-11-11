/**
 * U-7 scorecard thresholds (idea#375, approved 11 Nov 09:42 Europe/Brussels).
 *
 * Comparison lives only in this module. The values here are defaults that an
 * operator can change in Settings. Effective values come from /meta.thresholds
 * (served with thresholdsConfigured: true). If that object is absent, these
 * defaults are used. Grey (no data) never counts as amber.
 * Tones follow the collector in PR #2 (Kid 7880247, not yet pushed).
 */
import type { ScorecardInputs, ScorecardThresholds } from "../api/types";

export type LineTone = "onTrack" | "needsHelp" | "noData" | "notMeasured";
export type CardPill = "ok" | "help" | "noData" | "monitoringOff" | "unused";

export type ScorecardLineId =
  | "available"
  | "setup"
  | "teachingCycle"
  | "learnersOperate"
  | "nextcloud"
  | "wikipedia";

export const SCORECARD_LINE_IDS: ScorecardLineId[] = [
  "available",
  "setup",
  "teachingCycle",
  "learnersOperate",
  "nextcloud",
  "wikipedia",
];

export const SCORECARD_LINE_LABELS: Record<ScorecardLineId, string> = {
  available: "Available",
  setup: "Set up",
  teachingCycle: "Teaching cycle",
  learnersOperate: "Learners operate",
  nextcloud: "Nextcloud",
  wikipedia: "Wikipedia",
};

/** Koen-approved starting thresholds (idea#375 U-7). Set up is a yes/no check. */
export const DEFAULT_THRESHOLDS: ScorecardThresholds = {
  availableMinSchoolDays: 3,
  teachingCycleMinItems: 1,
  learnerSessionShareMin: 0.5,
  nextcloudMinActions: 1,
  wikipediaMinViews: 10,
  helpAfterAmberWeeks: 3,
  unusedAfterHelpWeeks: 4,
};

export const THRESHOLD_KEYS = [
  "availableMinSchoolDays",
  "teachingCycleMinItems",
  "learnerSessionShareMin",
  "nextcloudMinActions",
  "wikipediaMinViews",
  "helpAfterAmberWeeks",
  "unusedAfterHelpWeeks",
] as const;

export type ThresholdKey = (typeof THRESHOLD_KEYS)[number];

export type ThresholdFieldKind = "int" | "share";

export interface ThresholdFieldMeta {
  id: ThresholdKey;
  label: string;
  meaning: string;
  kind: ThresholdFieldKind;
  min: number;
  max?: number;
}

export const THRESHOLD_FIELDS: ThresholdFieldMeta[] = [
  {
    id: "availableMinSchoolDays",
    label: "Available",
    meaning: "Kit on in school hours on at least this many school days in the week.",
    kind: "int",
    min: 0,
    max: 5,
  },
  {
    id: "teachingCycleMinItems",
    label: "Teaching cycle",
    meaning: "At least this many lessons or quizzes made visible or started, followed by learner sessions on assigned content.",
    kind: "int",
    min: 0,
  },
  {
    id: "learnerSessionShareMin",
    label: "Learners operate it",
    meaning: "Learner share of Kolibri sessions, versus coaches and admins (guests excluded). Not a share of minutes.",
    kind: "share",
    min: 0,
    max: 1,
  },
  {
    id: "nextcloudMinActions",
    label: "Nextcloud",
    meaning: "At least this many worksheet shares, co-edits, school-files shares, File drop uploads or Office opens by a teacher or learner. Admin Office opens and File drop links do not count.",
    kind: "int",
    min: 0,
  },
  {
    id: "wikipediaMinViews",
    label: "Wikipedia",
    meaning: "At least this many article views on the school's own Wikipedia (not Demo).",
    kind: "int",
    min: 0,
  },
  {
    id: "helpAfterAmberWeeks",
    label: "Help after amber weeks",
    meaning: "Offer help after this many consecutive school weeks with any line amber. A grey week neither counts nor breaks the streak; a green week resets it. A school with no pulled data yet is offered help at once.",
    kind: "int",
    min: 1,
  },
  {
    id: "unusedAfterHelpWeeks",
    label: "Unused after help",
    meaning: "The school counts as unused if it is still amber with no improvement this many school weeks after help was offered. Unused schools are not listed in the offer-help banner.",
    kind: "int",
    min: 1,
  },
];

export const SETUP_RULE_MEANING =
  "Yes when registered learners and teachers are both more than zero. Without a Kolibri census, yes when a Nextcloud beyond-seed count is more than zero. This is a yes/no check with no number to edit.";

export function cloneThresholds(value: ScorecardThresholds): ScorecardThresholds {
  return {
    availableMinSchoolDays: value.availableMinSchoolDays,
    teachingCycleMinItems: value.teachingCycleMinItems,
    learnerSessionShareMin: value.learnerSessionShareMin,
    nextcloudMinActions: value.nextcloudMinActions,
    wikipediaMinViews: value.wikipediaMinViews,
    helpAfterAmberWeeks: value.helpAfterAmberWeeks,
    unusedAfterHelpWeeks: value.unusedAfterHelpWeeks,
  };
}

export function mergeThresholds(
  ...sources: Array<Partial<ScorecardThresholds> | null | undefined>
): ScorecardThresholds {
  const merged = cloneThresholds(DEFAULT_THRESHOLDS);
  for (const source of sources) {
    if (!source) continue;
    for (const key of THRESHOLD_KEYS) {
      const value = source[key];
      if (typeof value === "number" && Number.isFinite(value)) {
        merged[key] = value;
      }
    }
  }
  return merged;
}

/**
 * Effective thresholds: /meta.thresholds when present, otherwise built-in defaults.
 * Settings GET/PUT is only for the operator Settings page.
 */
export function resolveEffectiveThresholds(
  metaThresholds?: Partial<ScorecardThresholds> | null,
): ScorecardThresholds {
  return mergeThresholds(DEFAULT_THRESHOLDS, metaThresholds);
}

export interface ThresholdValidationFailure {
  error: string;
  field: string;
}

export function validateThresholdPatch(
  patch: Partial<ScorecardThresholds>,
): ThresholdValidationFailure | null {
  for (const key of Object.keys(patch) as string[]) {
    if (!(THRESHOLD_KEYS as readonly string[]).includes(key)) {
      return { error: "unknown threshold", field: key };
    }
    const value = patch[key as ThresholdKey];
    const meta = THRESHOLD_FIELDS.find((item) => item.id === key);
    if (meta?.kind === "share") {
      if (typeof value !== "number" || !Number.isFinite(value) || typeof value === "boolean") {
        return { error: "must be a number between 0 and 1", field: key };
      }
      if (value < 0 || value > 1) {
        return { error: "must be a number between 0 and 1", field: key };
      }
      continue;
    }
    const isInt = typeof value === "number" && Number.isInteger(value);
    if (!isInt) {
      return { error: "must be an integer", field: key };
    }
    const minimum = meta?.min ?? 0;
    const maximum = meta?.max;
    if (value < minimum) {
      return { error: `must be an integer >= ${minimum}`, field: key };
    }
    if (maximum !== undefined && value > maximum) {
      return { error: `must be an integer <= ${maximum}`, field: key };
    }
  }
  return null;
}

export function isGreyTone(tone: LineTone): boolean {
  return tone === "noData" || tone === "notMeasured";
}

export interface LineEvaluation {
  id: ScorecardLineId;
  tone: LineTone;
  word: string;
}

function measuredSum(values: Array<number | null>): number | null {
  if (values.every((value) => value === null)) return null;
  return values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
}

/** Lessons or quizzes made visible or started this week. */
export function teachingCycleItemCount(inputs: ScorecardInputs): number | null {
  const { lessonsVisible, quizzesStarted, lessonsCreated, quizzesCreated, learnerSessionsOnAssigned } =
    inputs.teachingCycle;
  if (
    lessonsVisible === null &&
    quizzesStarted === null &&
    lessonsCreated === null &&
    quizzesCreated === null &&
    learnerSessionsOnAssigned === null
  ) {
    return null;
  }
  return (lessonsVisible ?? 0) + (quizzesStarted ?? 0);
}

/**
 * Learner share of Kolibri sessions versus coaches and admins (guests excluded).
 * Null when no role session counts are present, or when the total is zero.
 */
export function learnerSessionShare(inputs: ScorecardInputs): number | null {
  const { learnerSessions, coachSessions, adminSessions } = inputs.learnersOperate;
  if (learnerSessions === null && coachSessions === null && adminSessions === null) {
    return null;
  }
  const learner = learnerSessions ?? 0;
  const coach = coachSessions ?? 0;
  const admin = adminSessions ?? 0;
  const total = learner + coach + admin;
  if (total <= 0) return 0;
  return learner / total;
}

/**
 * Counted Nextcloud actions: worksheet, edit and school-files shares,
 * File drop uploads, and Office opens by a teacher or learner
 * (`officeOpensTeacherLearner`). File drop links and admin Office opens
 * do not count. A null teacher/learner split counts as 0 (Kid 34bb193).
 */
export function nextcloudWorkflowActions(inputs: ScorecardInputs): number | null {
  return measuredSum([
    inputs.nextcloud.worksheetShares,
    inputs.nextcloud.editShares,
    inputs.nextcloud.schoolFilesShares,
    inputs.nextcloud.fileDropUploads,
    inputs.nextcloud.officeOpensTeacherLearner,
  ]);
}

export function setupIsComplete(inputs: ScorecardInputs): boolean | null {
  const { classes, learnersRegistered, teachers, nextcloudTeacherBeyondSeed, nextcloudLearnerBeyondSeed } =
    inputs.setup;
  if (classes !== null || learnersRegistered !== null || teachers !== null) {
    return (learnersRegistered ?? 0) > 0 && (teachers ?? 0) > 0;
  }
  if (nextcloudTeacherBeyondSeed === null && nextcloudLearnerBeyondSeed === null) {
    return null;
  }
  return (nextcloudTeacherBeyondSeed ?? 0) > 0 || (nextcloudLearnerBeyondSeed ?? 0) > 0;
}

export function evaluateLine(
  id: ScorecardLineId,
  inputs: ScorecardInputs,
  thresholds: ScorecardThresholds,
): LineEvaluation {
  switch (id) {
    case "available": {
      const days = inputs.available.schoolDaysOn;
      const minutes = inputs.available.schoolHoursOnMinutes;
      if (days === null && minutes === null) {
        return { id, tone: "noData", word: wordForTone("noData") };
      }
      const tone: LineTone = (days ?? 0) >= thresholds.availableMinSchoolDays ? "onTrack" : "needsHelp";
      return { id, tone, word: wordForTone(tone) };
    }
    case "setup": {
      const complete = setupIsComplete(inputs);
      if (complete === null) return { id, tone: "noData", word: wordForTone("noData") };
      const tone: LineTone = complete ? "onTrack" : "needsHelp";
      return { id, tone, word: wordForTone(tone) };
    }
    case "teachingCycle": {
      const items = teachingCycleItemCount(inputs);
      const sessions = inputs.teachingCycle.learnerSessionsOnAssigned ?? 0;
      if (items === null) {
        return { id, tone: "noData", word: wordForTone("noData") };
      }
      const tone: LineTone =
        items >= thresholds.teachingCycleMinItems && sessions >= 1 ? "onTrack" : "needsHelp";
      return { id, tone, word: wordForTone(tone) };
    }
    case "learnersOperate": {
      const share = learnerSessionShare(inputs);
      if (share === null) return { id, tone: "noData", word: wordForTone("noData") };
      const tone: LineTone = share >= thresholds.learnerSessionShareMin ? "onTrack" : "needsHelp";
      return { id, tone, word: wordForTone(tone) };
    }
    case "nextcloud": {
      const actions = nextcloudWorkflowActions(inputs);
      if (actions === null) return { id, tone: "noData", word: wordForTone("noData") };
      const tone: LineTone = actions >= thresholds.nextcloudMinActions ? "onTrack" : "needsHelp";
      return { id, tone, word: wordForTone(tone) };
    }
    case "wikipedia": {
      const views = inputs.wikipedia.pageViewsOwn;
      if (views === null) return { id, tone: "noData", word: wordForTone("noData") };
      const tone: LineTone = views >= thresholds.wikipediaMinViews ? "onTrack" : "needsHelp";
      return { id, tone, word: wordForTone(tone) };
    }
  }
}

export function evaluateLines(
  inputs: ScorecardInputs,
  thresholds: ScorecardThresholds,
): LineEvaluation[] {
  return SCORECARD_LINE_IDS.map((id) => evaluateLine(id, inputs, thresholds));
}

export function wordForTone(tone: LineTone): string {
  switch (tone) {
    case "noData":
      return "No data";
    case "notMeasured":
      return "Not measured yet";
    case "onTrack":
      return "On track";
    case "needsHelp":
      return "Needs help";
  }
}

export function pillForCard(
  hasUsageData: boolean,
  lineTones: LineTone[],
  monitoringEnabled?: boolean,
  unused?: boolean,
): CardPill {
  if (monitoringEnabled === false) return "monitoringOff";
  if (unused) return "unused";
  if (!hasUsageData) return "noData";
  if (lineTones.some((tone) => tone === "needsHelp")) return "help";
  if (lineTones.some((tone) => tone === "onTrack")) return "ok";
  return "noData";
}

export function pillWord(pill: CardPill): string {
  switch (pill) {
    case "monitoringOff":
      return "Monitoring off";
    case "unused":
      return "Unused";
    case "noData":
      return "No data";
    case "ok":
      return "OK";
    case "help":
      return "Help";
  }
}

export function helpRulesText(thresholds: ScorecardThresholds): string {
  const helpAfter = thresholds.helpAfterAmberWeeks;
  const unusedAfter = thresholds.unusedAfterHelpWeeks;
  const helpWord = helpAfter === 1 ? "school week" : "school weeks";
  const unusedWord = unusedAfter === 1 ? "school week" : "school weeks";
  return (
    `Help is offered after ${helpAfter} consecutive ${helpWord} with any line amber. ` +
    "A grey week (no data) neither counts toward that streak nor breaks it; a green week resets it. " +
    "A school with no pulled data yet is offered help at once. " +
    `A school counts as unused if it is still amber with no improvement ${unusedAfter} ${unusedWord} after help was offered. ` +
    "Unused schools are not listed in the offer-help banner."
  );
}

export function unusedRuleText(thresholds: ScorecardThresholds): string {
  const unusedAfter = thresholds.unusedAfterHelpWeeks;
  const unusedWord = unusedAfter === 1 ? "school week" : "school weeks";
  return (
    `This school counts as unused: it is still amber with no improvement ${unusedAfter} ${unusedWord} after help was offered.`
  );
}
