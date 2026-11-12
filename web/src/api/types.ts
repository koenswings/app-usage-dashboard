/**
 * HTTP API contract for the programme dashboard (idea#415).
 *
 * Read-only GET /api/v1/... except POST /api/v1/schools/:deploymentId/help-events
 * (operator-only; Koen or Marco records that help was offered) and
 * PUT /api/v1/settings/thresholds (operator session; served by the collector
 * in PR #2, Kid 7880247, not yet pushed).
 *
 * Derived from the merged proposal (idea PR #410):
 *   §7.5 SQLite tables, §7.6 day-summary schema, §4 scorecard inputs,
 *   §8 pages, §9 privacy (role-level counts only; no usernames, no IPs).
 *
 * Presence segment shape agreed with Kid:
 *   { state: 'on' | 'off' | 'gapUnknown' | 'collectorGap', start, end, lengthKnown }
 * lastPulled is returned on every kit / school card.
 *
 * Scorecard thresholds: Koen approved starting defaults on idea#375 U-7
 * (11 Nov 09:42 Europe/Brussels). The API still returns raw counts, never a
 * grade. The UI compares those counts to effective thresholds (defaults, or
 * values from /meta.thresholds / GET /api/v1/settings/thresholds). Grey
 * (no data / not measured) never counts as amber.
 *
 * Schema version: idea-usage-api/1 (this HTTP API).
 * Day-file version: idea-usage-day/1 (§7.6).
 */

export const API_SCHEMA = 'idea-usage-api/1' as const;
export const DAY_SCHEMA = 'idea-usage-day/1' as const;

export type ApiSchema = typeof API_SCHEMA;
export type DaySchema = typeof DAY_SCHEMA;

/** Calendar date, YYYY-MM-DD, in the relevant timezone noted on the response. */
export type IsoDate = string;

/** RFC 3339 timestamp with offset, e.g. 2026-11-10T13:40:00+01:00. */
export type IsoDateTime = string;

/** Monday that starts a school week (YYYY-MM-DD). Path and query param `week`. */
export type WeekStart = IsoDate;

export type PresenceState = 'on' | 'off' | 'gapUnknown' | 'collectorGap';

/**
 * One continuous stretch of kit presence.
 * `gapUnknown`: power-off (or clock gap) whose length is not known until a
 *   synced sample arrives (Axle, no RTC). Never drawn as the kit going dark.
 * `collectorGap`: the idea-side collector / sidecar was down (Atlas watchdog).
 *   Never drawn as the kit going dark.
 * `lengthKnown` is true for measured `on` / `off` and for a collector gap
 *   that has both a start and an end. It is false for `gapUnknown` and for
 *   an open-ended collector outage.
 */
export interface PresenceSegment {
  state: PresenceState;
  start: IsoDateTime;
  end: IsoDateTime;
  lengthKnown: boolean;
}

/** Kit-local timezone so the presence strip can label ticks independently of the Brussels header. */
export interface KitTimezone {
  /**
   * Optional IANA name from idea's registry.json for that kit
   * (not something the kit itself reports). Empty string when the
   * registry has no name; the UI then falls back to `label` / `utcOffset`.
   */
  timeZone: string;
  /**
   * Offset at Monday 00:00 of the requested week, derived from the registry
   * IANA `timeZone` (e.g. "+01:00"). Falls back to the latest presence sample's
   * RFC 3339 offset, then to "+00:00", when the registry has no IANA name.
   */
  utcOffset: string;
  /**
   * Operator-facing label. With a registry name:
   * "kit local time (Africa/Harare, UTC+2)". Without one: "kit local time (UTC±n)".
   */
  label: string;
}

export type ErrorCode =
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'validation'
  | 'conflict'
  | 'unavailable';

export interface ErrorBody {
  error: {
    code: ErrorCode;
    message: string;
    details?: unknown;
  };
}

// ---------------------------------------------------------------------------
// Session (Console operator pattern, cookie on the HTTP API)
// ---------------------------------------------------------------------------

export interface SessionUser {
  username: string;
  role: 'operator';
}

export interface SessionResponse {
  schema: ApiSchema;
  authenticated: boolean;
  user: SessionUser | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

/** `PUT /api/v1/session/password` (operator session, Kid e4c15dd). */
export interface ChangePasswordRequest {
  currentPassword: string;
  newPassword: string;
}

/**
 * `GET /api/v1/health` — public, no cookie.
 * Engine healthCheck probes this on `${port}`.
 */
export interface HealthResponse {
  ok: true;
  schema: ApiSchema;
  /** App version string when the collector reports it (e.g. "1.0"). */
  version?: string;
  /** Git commit of the running build, or null when it is unknown. */
  commit?: string | null;
}

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

export interface MetaResponse {
  schema: ApiSchema;
  daySchema: DaySchema;
  /**
   * True once Koen approved the U-7 defaults. The collector (PR #2, Kid 7880247)
   * sends this as true together with `thresholds`.
   */
  thresholdsConfigured: boolean;
  /**
   * Effective U-7 thresholds from the collector. If omitted, the UI uses the
   * built-in defaults in src/config/thresholds.ts. Grades are computed in the
   * UI; the API never sends scorecard colours.
   */
  thresholds?: ScorecardThresholds;
  /** A card whose lastPulled is older than this is marked "data from <date>". */
  staleAfterHours: number;
  /**
   * Weekly Wikipedia page-view count below which the views-by-hour chart
   * is hidden (§8.1 / §9: a tiny school must not get close to per-hour identity).
   */
  hourlyChartMinWeeklyViews: number;
  /** Header clock, typically Europe/Brussels. */
  headerTimeZone: string;
  /** True when the server (or the UI mock) is serving labelled sample data. */
  sampleData: boolean;
  /** Latest Monday with stored data. Falls back to todayWeekStart when the store is empty. */
  currentWeekStart: WeekStart;
  /** Monday of today (header calendar), even if that week has no stored data. */
  todayWeekStart: WeekStart;
  /** True when at least one stored week exists. */
  currentWeekHasData: boolean;
}

// ---------------------------------------------------------------------------
// Kits / deployments
// ---------------------------------------------------------------------------

export interface KitListItem {
  /** Engine hostname; the kit identity. No deployment id lives on the kit. */
  engine: string;
  tailscaleName: string;
  school: string;
  /** Deployment idea assigned when it stored a pulled summary. */
  deploymentId: string;
  lastPulled: IsoDateTime | null;
  monitoringEnabled: boolean;
}

export interface KitsResponse {
  schema: ApiSchema;
  kits: KitListItem[];
}

export interface WeeksResponse {
  schema: ApiSchema;
  /** Mondays that the picker can offer, newest first. */
  weeks: WeekStart[];
  /** Latest Monday with stored data (daily summaries or presence days). Falls back to todayWeekStart when the store is empty. */
  currentWeekStart: WeekStart;
  /** Monday of today. */
  todayWeekStart: WeekStart;
  /** True when at least one stored week exists. */
  currentWeekHasData: boolean;
}

// ---------------------------------------------------------------------------
// U-7 scorecard thresholds (collector PR #2, Kid 7880247, not yet pushed)
// ---------------------------------------------------------------------------

/**
 * Numeric U-7 cut-offs. Set up is a yes/no check and has no number.
 * `learnerSessionShareMin` is a 0–1 share (shown as a percentage in Settings).
 */
export interface ScorecardThresholds {
  availableMinSchoolDays: number;
  teachingCycleMinItems: number;
  learnerSessionShareMin: number;
  nextcloudMinActions: number;
  wikipediaMinViews: number;
  helpAfterAmberWeeks: number;
  unusedAfterHelpWeeks: number;
}

/**
 * GET /api/v1/settings/thresholds and PUT /api/v1/settings/thresholds.
 * Both require an operator session (same as /meta). The response has no
 * `schema` field. `updatedBy` is the operator username.
 */
export interface ThresholdsSettingsResponse {
  thresholds: ScorecardThresholds;
  defaults: ScorecardThresholds;
  updatedAt: IsoDateTime | null;
  updatedBy: string | null;
}

/** PUT body: a partial `thresholds` object, or `{ reset: true }` to restore defaults. */
export type PutThresholdsRequest =
  | { reset: true; thresholds?: never }
  | { reset?: false; thresholds: Partial<ScorecardThresholds> };

/**
 * 400 body for the settings endpoint. This is a flat `{ error, field }`,
 * not the usual `{ error: { code, message } }` wrapper.
 */
export interface ThresholdsSettingsError {
  error: string;
  field: string;
}

// ---------------------------------------------------------------------------
// Scorecard inputs (raw counts — no grades)
// ---------------------------------------------------------------------------

export interface ScorecardAvailableInputs {
  schoolDaysOn: number | null;
  schoolDaysExpected: number;
  schoolHoursOnMinutes: number | null;
  /** Boots on each expected school day, Monday-first; null if no sampler data. */
  bootsPerSchoolDay: number[] | null;
  longestGapMinutes: number | null;
}

export interface ScorecardSetupInputs {
  classes: number | null;
  learnersRegistered: number | null;
  learnersEnrolled: number | null;
  teachers: number | null;
  admins: number | null;
  /** From own-Nextcloud `setup.teacher.beyondSeed` (hook-emitted, the max across the school's own copies). */
  nextcloudTeacherBeyondSeed: number | null;
  /** From own-Nextcloud `setup.learner.beyondSeed` (hook-emitted, the max across the school's own copies). */
  nextcloudLearnerBeyondSeed: number | null;
}

/**
 * One U-7 Set up requirement (idea#462). The first three are checked on the
 * school's own Kolibri, the last two on its own Nextcloud. `noOwnKolibri` /
 * `noOwnNextcloud` mean the school has no own copy of that app (ruling 1).
 */
export type SetupPart = 'coach' | 'class' | 'enrolledLearner' | 'teacherBeyondSeed' | 'learnerBeyondSeed' | 'noOwnKolibri' | 'noOwnNextcloud';

export interface AppSetupStatus {
  /** null = an input is unknown (no data); never means "no own copy". */
  complete: boolean | null;
  /** Parts that are known and fail; [] when complete or unknown. A missing own app is `['noOwnKolibri']` or `['noOwnNextcloud']`. */
  missing: SetupPart[];
  /** Parts whose input is null (e.g. an old hook). */
  unknown: SetupPart[];
  /** Own copies that meet the rule on their own. */
  passingInstanceIds: string[];
}

/**
 * The collector's U-7 Set up verdict. The UI shows `complete` as the Set up
 * line and never recomputes the rule.
 */
export interface SetupStatus {
  complete: boolean | null;
  /** null = no data for this app (not "no own copy"). A missing own copy is `{ complete: false, missing: ['noOwnKolibri'] }`. */
  kolibri: AppSetupStatus | null;
  /** null = no data for this app (not "no own copy"). A missing own copy is `{ complete: false, missing: ['noOwnNextcloud'] }`. */
  nextcloud: AppSetupStatus | null;
  rule: string;
}

/** Own instance ids that fed this scorecard; [] = no own copy. */
export interface ScorecardCopies {
  kolibri: string[];
  nextcloud: string[];
  kiwix: string[];
}

export interface ScorecardTeachingInputs {
  lessonsCreated: number | null;
  lessonsVisible: number | null;
  quizzesCreated: number | null;
  quizzesStarted: number | null;
  /**
   * Assigned learner *content visits* this week (sum of Kolibri `content[].visits`
   * where `role` is `learner` and `assigned` is true). Not a session count.
   * The collector keeps this field name (kid/i414-collector @9286247).
   */
  learnerSessionsOnAssigned: number | null;
  /** `learnerSessionsOnAssigned` divided by all learner content visits; null if none. */
  assignedShareOfLearnerVisits: number | null;
}

export interface ScorecardLearnersOperateInputs {
  learnerSessions: number | null;
  learnerMinutes: number | null;
  coachSessions: number | null;
  coachMinutes: number | null;
  adminSessions: number | null;
  adminMinutes: number | null;
  guestVisits: number | null;
  guestMinutes: number | null;
  /** 0–1 share of Kolibri minutes that were learner-role; null if no sessions. */
  learnerShareOfMinutes: number | null;
}

export interface ScorecardNextcloudInputs {
  worksheetShares: number | null;
  /**
   * Worksheet shares by a teacher or learner (`workflows.byGroup.worksheetShares`,
   * Kid 10a1cc5, idea#431). Null when no own instance this week had that
   * byGroup (old day files). A null split counts as 0 toward nextcloudMinActions.
   */
  worksheetSharesTeacherLearner: number | null;
  /** Worksheet shares by an admin. Does not count toward the Nextcloud threshold. */
  worksheetSharesAdmin: number | null;
  editShares: number | null;
  editSharesTeacherLearner: number | null;
  editSharesAdmin: number | null;
  /** Unsplit. Creating a File drop link does not count toward nextcloudMinActions. */
  fileDropLinks: number | null;
  fileDropUploads: number | null;
  fileDropUploadsTeacherLearner: number | null;
  fileDropUploadsAdmin: number | null;
  schoolFilesShares: number | null;
  schoolFilesSharesTeacherLearner: number | null;
  schoolFilesSharesAdmin: number | null;
  officeOpens: number | null;
  /**
   * Office opens by a teacher or learner (`office.byGroup.teacher` +
   * `office.byGroup.learner`), summed across the school's own Nextclouds
   * (Kid 34bb193). Null when no instance this week had a byGroup split
   * (old day files). Displayed, but does not count toward nextcloudMinActions
   * until idea#464.
   */
  officeOpensTeacherLearner: number | null;
  /**
   * Office opens by an admin (`office.byGroup.admin`). Null under the same
   * conditions as officeOpensTeacherLearner. Does not count toward the
   * Nextcloud threshold.
   */
  officeOpensAdmin: number | null;
  /**
   * Sum of each own Nextcloud instance's last-ok-day `office.distinctDocuments`.
   * Document ids are salted per instance, so two own Nextclouds hold different
   * documents and the sum is correct.
   */
  officeDistinctDocuments: number | null;
  officeRead: number | null;
  officeEdit: number | null;
  officeEstimatedMinutes: number | null;
  /** Office documents created this week by anyone, own copies summed. Null until the Nextcloud hook sends it. */
  documentsCreated?: number | null;
  /** Documents created by a teacher or learner. Null under the same conditions. */
  documentsCreatedTeacherLearner?: number | null;
  /** Documents created by an admin. */
  documentsCreatedAdmin?: number | null;
  /** App id → open count summed over own copies; null when not measured. */
  appsOpened?: Record<string, number> | null;
}

export interface ScorecardWikipediaInputs {
  pageViewsOwn: number | null;
  sessionsOwn: number | null;
  /**
   * Max of daily `distinctArticles` on the school's own instance.
   * Not a week-wide distinct total (the export has no article set).
   */
  distinctArticlesOwn: number | null;
}

export interface ScorecardInputs {
  available: ScorecardAvailableInputs;
  setup: ScorecardSetupInputs;
  teachingCycle: ScorecardTeachingInputs;
  learnersOperate: ScorecardLearnersOperateInputs;
  nextcloud: ScorecardNextcloudInputs;
  wikipedia: ScorecardWikipediaInputs;
  /** The collector's U-7 Set up verdict (idea#462). Missing on a 1.1 collector. */
  setupStatus?: SetupStatus | null;
  /** Which own copies were graded (idea#462). Optional. */
  copies?: ScorecardCopies | null;
}

export interface SchoolHeadlines {
  classes: number | null;
  learnersRegistered: number | null;
  teachers: number | null;
  kolibriMinutes: number | null;
}

export interface SchoolCard {
  deploymentId: string;
  school: string;
  engine: string;
  /** Short subtitle, e.g. "own apps + Demo" or "Not installed yet". */
  note: string;
  lastPulled: IsoDateTime | null;
  /** True when lastPulled is older than meta.staleAfterHours. */
  stale: boolean;
  /** Calendar date shown in "data from <date>" when stale; otherwise null. */
  dataFrom: IsoDate | null;
  hasUsageData: boolean;
  /**
   * This kit's current monitoring flag. Each overview card is one kit
   * (`engine` + `deploymentId`); the value is not an any-of aggregate.
   * The collector always sends it from f2d4adc. The UI still joins
   * `/api/v1/kits` by deploymentId if a payload omits the field.
   */
  monitoringEnabled: boolean;
  /**
   * True when a help event was recorded and the kit stayed amber with no
   * improvement for unusedAfterHelpWeeks school weeks after that event.
   * Unused kits are not included in helpSuggestions.
   */
  unused: boolean;
  scorecard: ScorecardInputs;
  headlines: SchoolHeadlines;
}

/**
 * Server-owned suggestion for the fleet banner. The UI renders `message`
 * as given and never invents a cut-off or a retraction. Phrasing must
 * say "offer help", never "retract".
 */
export interface HelpSuggestion {
  deploymentId: string;
  engine: string;
  school: string;
  message: string;
}

export interface OverviewResponse {
  schema: ApiSchema;
  weekStart: WeekStart;
  /** Inclusive Friday of the school week (YYYY-MM-DD). */
  weekEnd: IsoDate;
  weekLabel: string;
  thresholdsConfigured: boolean;
  sampleData: boolean;
  staleAfterHours: number;
  cards: SchoolCard[];
  helpSuggestions: HelpSuggestion[];
}

// ---------------------------------------------------------------------------
// School week (scorecard inputs + Q3 census + presence)
// ---------------------------------------------------------------------------

export interface Census {
  classes: number | null;
  classesDelta: number | null;
  learnersRegistered: number | null;
  learnersRegisteredDelta: number | null;
  learnersEnrolled: number | null;
  teachers: number | null;
  teachersDelta: number | null;
  admins: number | null;
}

export interface PresenceBlock {
  timezone: KitTimezone;
  segments: PresenceSegment[];
  /**
   * Short plain sentence built from presence_days school-hour totals,
   * e.g. "On 4 of 5 school days, 31 h in school hours". Null when those
   * roll-ups are missing. Never an empty string.
   */
  summary: string | null;
}

export interface SchoolWeekResponse {
  schema: ApiSchema;
  weekStart: WeekStart;
  weekEnd: IsoDate;
  deploymentId: string;
  school: string;
  engine: string;
  lastPulled: IsoDateTime | null;
  stale: boolean;
  dataFrom: IsoDate | null;
  hasUsageData: boolean;
  monitoringEnabled: boolean;
  /**
   * True when a help event was recorded and the kit stayed amber with no
   * improvement for unusedAfterHelpWeeks school weeks after that event.
   */
  unused: boolean;
  thresholdsConfigured: boolean;
  sampleData: boolean;
  /**
   * False only when an ok day-file this week had `clock.synced === false`.
   * With no ok days, clock is null and clockTrusted is true.
   * The collector serves this name (`clockTrusted`), not `clockTrustworthy`.
   */
  clockTrusted: boolean;
  timezone: KitTimezone;
  scorecard: ScorecardInputs;
  census: Census;
  presence: PresenceBlock;
}

export interface PresenceDayRollup {
  day: IsoDate;
  onMinutes: number | null;
  schoolHoursOnMinutes: number | null;
  boots: number | null;
  longestGapMinutes: number | null;
  lengthKnown: boolean;
}

export interface PresenceResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  timezone: KitTimezone;
  segments: PresenceSegment[];
  days: PresenceDayRollup[];
}

// ---------------------------------------------------------------------------
// Uplink (Tailscale timeline seen from idea)
// ---------------------------------------------------------------------------

export type UplinkVia = 'direct' | 'DERP';
export type UplinkState = 'online' | 'offline';

export interface UplinkSample {
  timestamp: IsoDateTime;
  engine: string;
  online: boolean;
  lastSeen: IsoDateTime | null;
  via: UplinkVia | null;
  latencyMs: number | null;
}

export interface UplinkTransition {
  timestamp: IsoDateTime;
  engine: string;
  fromState: UplinkState;
  toState: UplinkState;
}

export interface UplinkResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  timezone: KitTimezone;
  /**
   * False when reachability was not measured this week (the dashboard's
   * network link is not connected). Optional for older collectors.
   */
  measured?: boolean;
  samples: UplinkSample[];
  transitions: UplinkTransition[];
}

// ---------------------------------------------------------------------------
// Kolibri week aggregates (one object per instance — never collapsed)
// ---------------------------------------------------------------------------

export interface RoleActivity {
  /** Distinct accounts of this role; null for guest. */
  users: number | null;
  /** Lower bound of distinct accounts beyond the seed accounts; optional. */
  usersBeyondSeed?: number | null;
  sessions: number;
  minutes: number;
}

export interface KolibriContentRow {
  channel: string;
  title: string;
  kind: string;
  role: 'learner' | 'coach' | 'admin';
  visits: number;
  seconds: number;
  completions: number;
  assigned: boolean;
}

export interface KolibriTeaching {
  lessonsCreated: number;
  lessonsVisible: number;
  quizzesCreated: number;
  quizzesStarted: number;
  quizzesEnded: number;
}

export interface ClockHonesty {
  synced: boolean;
  correctedBoots: number;
}

/**
 * Engine hookStatus (agent-engine-dev#308). A working borrowed hook on an
 * extra copy is `ok` with `listed: false`. There is no `unlistedBorrowed`.
 * `missing` was renamed to `no-hook`.
 */
export type HookStatus =
  | 'ok'
  | 'timeout'
  | 'failed'
  | 'invalid'
  | 'skipped'
  | 'unlisted-no-hook'
  | 'no-hook';

/** Present when `hookStatus` is `skipped`. */
export type SkipReason = 'backup' | 'update' | 'move' | 'temperature';

export type AppKind = 'kolibri' | 'nextcloud' | 'kiwix' | 'other';

/**
 * Shared envelope on every instance (all three apps). Day-file identity is
 * `instance`. `instanceId` is an accepted alias for the same value.
 *
 * App payloads are optional / null on stubs and failed days so the UI can
 * tell "the hook failed" apart from "nothing has been collected yet"
 * (`collectedAt === null` and no payload).
 */
export interface InstanceEnvelope {
  instance: string;
  /** Alias of `instance`. Prefer `instance`. */
  instanceId?: string;
  name: string;
  hookStatus: HookStatus;
  skipReason?: SkipReason | null;
  listed: boolean;
  demo: boolean;
  clock: ClockHonesty | null;
  collectedAt: IsoDateTime | null;
}

export function instanceKey(row: { instance?: string; instanceId?: string }): string {
  return row.instance || row.instanceId || '';
}

/**
 * clockTrusted is false only when an ok day-file this week had
 * clock.synced === false. With no ok days, clock is null and the week is trusted.
 */
export function weekClockTrusted(instances: Array<{ clock: ClockHonesty | null }>): boolean {
  return instances.every((row) => row.clock === null || row.clock.synced);
}

export interface KolibriInstanceWeek extends InstanceEnvelope {
  app: 'kolibri';
  /** Kolibri-only (e.g. demoSeedExcluded). Other apps omit this. */
  flags?: string[] | null;
  setup: Census | null;
  signins: {
    learner: RoleActivity;
    coach: RoleActivity;
    admin: RoleActivity;
  } | null;
  guest: { visits: number; seconds: number } | null;
  teaching: KolibriTeaching | null;
  content: KolibriContentRow[] | null;
}

export interface KolibriWeekResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  clockTrusted: boolean;
  instances: KolibriInstanceWeek[];
}

// ---------------------------------------------------------------------------
// Nextcloud week aggregates
// ---------------------------------------------------------------------------

/** Hook-emitted role census. `beyondSeed` is not derived on idea; null when the hook omitted it. */
export interface RoleCount {
  total: number;
  beyondSeed: number | null;
}

export type SchoolRole = 'admin' | 'teacher' | 'learner';

export interface NextcloudSetup {
  admin: RoleCount;
  teacher: RoleCount;
  learner: RoleCount;
  /** Extra Nextcloud groups the hook listed; keep unless the Engine drops it. */
  otherGroups?: Record<string, number>;
}

export interface NextcloudLogins {
  admin: RoleCount;
  teacher: RoleCount;
  learner: RoleCount;
}

/**
 * Office activity as already reduced by the Engine. Do not re-reduce into
 * created/edited-by-role. `distinctDocuments` is the Engine's union across
 * that day's samples (not something idea should union again for the day).
 * A week response must not sum daily `distinctDocuments` (that would
 * over-count); it may pass through the last ok day's value.
 */
export interface NextcloudOffice {
  opens: number;
  distinctDocuments: number;
  read: number;
  edit: number;
  /** Single estimate; no per-role split. Null when the hook could not estimate. */
  estimatedMinutes: number | null;
  byGroup: { admin: number; teacher: number; learner: number };
  mime: { text: number; sheet: number; slides: number };
}

export interface NextcloudWorkflows {
  worksheetShares: number;
  editShares: number;
  fileDropLinks: number;
  fileDropUploads: number;
  schoolFilesShares: number;
  /**
   * Per-metric role splits, summed across ok days the same way
   * `office.byGroup` is (collector docs/API.md). Keys match the split
   * workflow totals; `fileDropLinks` has no group split. Optional on
   * old day files with no `byGroup`. The UI does not read this field;
   * U-7 line 5 uses the scorecard `*TeacherLearner` splits.
   */
  byGroup?: {
    worksheetShares: { admin: number; teacher: number; learner: number };
    editShares: { admin: number; teacher: number; learner: number };
    fileDropUploads: { admin: number; teacher: number; learner: number };
    schoolFilesShares: { admin: number; teacher: number; learner: number };
  };
}

export interface NextcloudInstanceWeek extends InstanceEnvelope {
  app: 'nextcloud';
  setup: NextcloudSetup | null;
  logins: NextcloudLogins | null;
  office: NextcloudOffice | null;
  /** App id → open count. May be missing or empty. */
  appsOpened: Record<string, number> | null;
  workflows: NextcloudWorkflows | null;
  /** Office documents created this week (summed over ok days). Null until the Nextcloud hook sends it. */
  documentsCreated?: number | null;
  /** Documents created by role, same keys as office.byGroup. */
  documentsCreatedByGroup?: { admin: number; teacher: number; learner: number } | null;
}

export interface NextcloudWeekResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  clockTrusted: boolean;
  instances: NextcloudInstanceWeek[];
}

// ---------------------------------------------------------------------------
// Wikipedia / Kiwix week aggregates — no identity
// ---------------------------------------------------------------------------

export interface KiwixTopArticle {
  title: string;
  views: number;
}

export interface KiwixInstanceWeek extends InstanceEnvelope {
  app: 'kiwix';
  pageViews: number | null;
  /**
   * Maximum of the daily `distinctArticles` counts. This is not the number of
   * different articles across the week (a union is not possible).
   */
  distinctArticles: number | null;
  sessions: number | null;
  topArticles: KiwixTopArticle[] | null;
  /** Length 24, kit-local hour 0–23. School-level only; never per person. */
  byHour: number[] | null;
}

export interface KiwixWeekResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  clockTrusted: boolean;
  instances: KiwixInstanceWeek[];
}

// ---------------------------------------------------------------------------
// Instance breakdown (every discovered container, including extra copies)
// ---------------------------------------------------------------------------

export interface DiscoveredInstance extends InstanceEnvelope {
  app: AppKind;
  /** Collector always sends `null` (not in the Engine export). The UI does not display it. */
  port?: null;
  note?: string;
}

export interface InstancesResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  instances: DiscoveredInstance[];
}

// ---------------------------------------------------------------------------
// Help events (Q7) — the only write
// ---------------------------------------------------------------------------

export interface HelpEvent {
  id: string;
  deploymentId: string;
  offeredOn: IsoDate;
  tutorialChapters: string[];
  note: string;
  createdBy: string;
  createdAt: IsoDateTime;
}

export interface HelpEventsResponse {
  schema: ApiSchema;
  deploymentId: string;
  events: HelpEvent[];
  /**
   * Weekly raw scorecard inputs so the timeline can annotate before / after
   * an offered-help date. Not a grade.
   */
  weeklyTrend: Array<{
    weekStart: WeekStart;
    scorecard: ScorecardInputs;
  }>;
}

export interface CreateHelpEventRequest {
  offeredOn: IsoDate;
  tutorialChapters: string[];
  note: string;
}
