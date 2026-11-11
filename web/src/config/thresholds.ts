/**
 * U-7 scorecard thresholds (idea#375, approved 11 Nov 09:42 Europe/Brussels).
 *
 * Comparison lives only in this module. The values here are defaults that an
 * operator can change in Settings. Effective values come from /meta.thresholds
 * or GET /api/v1/settings/thresholds when the collector serves them; otherwise
 * these defaults are used. Grey (no data / not measured) never counts as amber.
 */
import type { ScorecardInputs, ScorecardThresholds } from "../api/types";

export type LineTone = "onTrack" | "needsHelp" | "noData" | "notMeasured";
export type CardPill = "ok" | "help" | "noData" | "monitoringOff";

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
}

export const THRESHOLD_FIELDS: ThresholdFieldMeta[] = [
  {
    id: "availableMinSchoolDays",
    label: "Available",
    meaning: "Kit on in school hours on at least this many school days in the week.",
    kind: "int",
  },
  {
    id: "teachingCycleMinItems",
    label: "Teaching cycle",
    meaning: "At least this many lessons or quizzes made visible or started, followed by learner sessions on assigned content.",
    kind: "int",
  },
  {
    id: "learnerSessionShareMin",
    label: "Learners operate it",
    meaning: "Learner share of Kolibri sessions, versus coaches and admins (guests excluded).",
    kind: "share",
  },
  {
    id: "nextcloudMinActions",
    label: "Nextcloud",
    meaning: "At least this many shares, co-edits or File drop uploads (Office opens by a teacher or learner are included when the collector provides that split).",
    kind: "int",
  },
  {
    id: "wikipediaMinViews",
    label: "Wikipedia",
    meaning: "At least this many article views on the school's own Wikipedia (not Demo).",
    kind: "int",
  },
  {
    id: "helpAfterAmberWeeks",
    label: "Help after amber weeks",
    meaning: "Offer help after this many consecutive school weeks with any line amber. Grey weeks never count.",
    kind: "int",
  },
  {
    id: "unusedAfterHelpWeeks",
    label: "Unused after help",
    meaning: "The school counts as unused if it is still amber with no improvement this many school weeks after help was offered.",
    kind: "int",
  },
];

export const SETUP_RULE_MEANING =
  "Own Kolibri has at least one coach, at least one class, and enrolled learners; own Nextcloud has teacher and learner accounts beyond the seeds. This is a yes/no check with no number to edit.";

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
 * Effective thresholds: /meta.thresholds, then GET settings, then built-in defaults.
 */
export function resolveEffectiveThresholds(
  metaThresholds?: Partial<ScorecardThresholds> | null,
  settingsThresholds?: Partial<ScorecardThresholds> | null,
): ScorecardThresholds {
  return mergeThresholds(DEFAULT_THRESHOLDS, settingsThresholds, metaThresholds);
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
      return { error: `Unknown threshold field: ${key}.`, field: key };
    }
    const value = patch[key as ThresholdKey];
    const meta = THRESHOLD_FIELDS.find((item) => item.id === key);
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return { error: `${meta?.label ?? key} must be a number.`, field: key };
    }
    if (meta?.kind === "share") {
      if (value < 0 || value > 1) {
        return { error: "Learner session share must be between 0 and 1.", field: key };
      }
    } else if (!Number.isInteger(value) || value < 0) {
      return { error: `${meta?.label ?? key} must be a whole number of 0 or more.`, field: key };
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
  return measuredSum([
    inputs.teachingCycle.lessonsVisible,
    inputs.teachingCycle.quizzesStarted,
  ]);
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
  if (total <= 0) return null;
  return learner / total;
}

/**
 * Counted Nextcloud workflow actions: shares, co-edits and File drop uploads.
 * Office opens by teacher or learner are not in ScorecardInputs (only total
 * officeOpens), so they are not added here.
 */
export function nextcloudWorkflowActions(inputs: ScorecardInputs): number | null {
  return measuredSum([
    inputs.nextcloud.worksheetShares,
    inputs.nextcloud.schoolFilesShares,
    inputs.nextcloud.editShares,
    inputs.nextcloud.fileDropUploads,
  ]);
}

export function setupIsComplete(inputs: ScorecardInputs): boolean | null {
  const { teachers, classes, learnersEnrolled, nextcloudTeacherBeyondSeed, nextcloudLearnerBeyondSeed } =
    inputs.setup;
  if (
    teachers === null ||
    classes === null ||
    learnersEnrolled === null ||
    nextcloudTeacherBeyondSeed === null ||
    nextcloudLearnerBeyondSeed === null
  ) {
    return null;
  }
  return (
    teachers >= 1 &&
    classes >= 1 &&
    learnersEnrolled >= 1 &&
    nextcloudTeacherBeyondSeed >= 1 &&
    nextcloudLearnerBeyondSeed >= 1
  );
}

export function evaluateLine(
  id: ScorecardLineId,
  inputs: ScorecardInputs,
  thresholds: ScorecardThresholds,
): LineEvaluation {
  switch (id) {
    case "available": {
      const days = inputs.available.schoolDaysOn;
      if (days === null) return { id, tone: "noData", word: wordForTone("noData") };
      const tone: LineTone = days >= thresholds.availableMinSchoolDays ? "onTrack" : "needsHelp";
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
      const sessions = inputs.teachingCycle.learnerSessionsOnAssigned;
      if (items === null && sessions === null) {
        return { id, tone: "noData", word: wordForTone("noData") };
      }
      if (items === null || sessions === null) {
        if (items !== null && items < thresholds.teachingCycleMinItems) {
          const tone: LineTone = "needsHelp";
          return { id, tone, word: wordForTone(tone) };
        }
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
      if (actions >= thresholds.nextcloudMinActions) {
        return { id, tone: "onTrack", word: wordForTone("onTrack") };
      }
      const officeOpens = inputs.nextcloud.officeOpens;
      if (officeOpens !== null && officeOpens > 0) {
        return { id, tone: "notMeasured", word: wordForTone("notMeasured") };
      }
      return { id, tone: "needsHelp", word: wordForTone("needsHelp") };
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
): CardPill {
  if (monitoringEnabled === false) return "monitoringOff";
  if (!hasUsageData) return "noData";
  if (lineTones.some((tone) => tone === "needsHelp")) return "help";
  if (lineTones.some((tone) => tone === "onTrack")) return "ok";
  return "noData";
}

export function pillWord(pill: CardPill): string {
  switch (pill) {
    case "monitoringOff":
      return "Monitoring off";
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
    `A school counts as unused if it is still amber with no improvement ${unusedAfter} ${unusedWord} after help was offered. ` +
    "Grey (no data) never counts."
  );
}
