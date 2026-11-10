/**
 * HTTP API contract for the programme dashboard (idea#415).
 *
 * Read-only GET /api/v1/... except POST /api/v1/schools/:deploymentId/help-events
 * (operator-only; Koen or Marco records that help was offered).
 *
 * Derived from the merged proposal (idea PR #410):
 *   §7.5 SQLite tables, §7.6 day-summary schema, §4 scorecard inputs,
 *   §8 pages, §9 privacy (role-level counts only; no usernames, no IPs).
 *
 * Presence segment shape agreed with Kid:
 *   { state: 'on' | 'off' | 'gapUnknown' | 'collectorGap', start, end, lengthKnown }
 * lastPulled is returned on every kit / school card.
 *
 * Scorecard thresholds are a Koen item (idea#375) and are not set yet.
 * The API returns raw counts; it never invents cut-offs. When
 * thresholdsConfigured is false the UI shows "Thresholds not set"
 * rather than Help / OK grades.
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
 * `lengthKnown` is false for those two when the duration cannot be trusted.
 */
export interface PresenceSegment {
  state: PresenceState;
  start: IsoDateTime;
  end: IsoDateTime;
  lengthKnown: boolean;
}

/** Kit-local timezone so the presence strip can label ticks independently of the Brussels header. */
export interface KitTimezone {
  /** IANA name, e.g. "Africa/Harare". */
  timeZone: string;
  /** Offset at weekStart, e.g. "+02:00". */
  utcOffset: string;
  /** Operator-facing label, e.g. "kit local time (Africa/Harare, UTC+2)". */
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

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

export interface MetaResponse {
  schema: ApiSchema;
  daySchema: DaySchema;
  /** False until Koen sets scorecard cut-offs (idea#375). */
  thresholdsConfigured: boolean;
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
  currentWeekStart: WeekStart;
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
  nextcloudTeachersBeyondSeeds: number | null;
  nextcloudLearnersBeyondSeeds: number | null;
}

export interface ScorecardTeachingInputs {
  lessonsCreated: number | null;
  lessonsVisible: number | null;
  quizzesCreated: number | null;
  quizzesStarted: number | null;
  learnerSessionsOnAssigned: number | null;
  /** 0–1 share of learner content visits that matched a visible lesson; null if unknown. */
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
  fileDrops: number | null;
  officeOpensTeachers: number | null;
  officeOpensLearners: number | null;
  documentsCreatedOrEditedTeachers: number | null;
  documentsCreatedOrEditedLearners: number | null;
}

export interface ScorecardWikipediaInputs {
  pageViewsOwn: number | null;
  sessionsOwn: number | null;
  distinctArticlesOwn: number | null;
}

export interface ScorecardInputs {
  available: ScorecardAvailableInputs;
  setup: ScorecardSetupInputs;
  teachingCycle: ScorecardTeachingInputs;
  learnersOperate: ScorecardLearnersOperateInputs;
  nextcloud: ScorecardNextcloudInputs;
  wikipedia: ScorecardWikipediaInputs;
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
  /** Optional operator-facing summary; not a grade. */
  summary: string;
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
  thresholdsConfigured: boolean;
  sampleData: boolean;
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
  samples: UplinkSample[];
  transitions: UplinkTransition[];
}

// ---------------------------------------------------------------------------
// Kolibri week aggregates (one object per instance — never collapsed)
// ---------------------------------------------------------------------------

export interface RoleActivity {
  /** Distinct accounts of this role; null for guest. */
  users: number | null;
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

export interface KolibriInstanceWeek {
  instanceId: string;
  name: string;
  app: 'kolibri';
  demo: boolean;
  listed: boolean;
  flags: string[];
  clock: ClockHonesty;
  setup: Census;
  signins: {
    learner: RoleActivity;
    coach: RoleActivity;
    admin: RoleActivity;
  };
  guest: { visits: number; seconds: number };
  teaching: KolibriTeaching;
  content: KolibriContentRow[];
}

export interface KolibriWeekResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  instances: KolibriInstanceWeek[];
}

// ---------------------------------------------------------------------------
// Nextcloud week aggregates
// ---------------------------------------------------------------------------

export interface NextcloudSetup {
  teachers: number;
  learners: number;
  admins: number;
  teachersBeyondSeeds: number;
  learnersBeyondSeeds: number;
}

export interface NextcloudLogins {
  teachers: number;
  learners: number;
  admins: number;
}

export interface NextcloudOffice {
  opensTeachers: number;
  opensLearners: number;
  documentsCreatedOrEditedTeachers: number;
  documentsCreatedOrEditedLearners: number;
  /** Estimate only (WOPI token sampling); exact editing minutes are not stored. */
  estimatedMinutesTeachers: number | null;
  estimatedMinutesLearners: number | null;
}

export interface NextcloudAppOpen {
  appId: string;
  /** Container-log counts have no role (§3 Q5). */
  opens: number;
}

export interface NextcloudWorkflows {
  worksheetShares: number;
  editShares: number;
  fileDrops: number;
  schoolFilesShares: number;
}

export interface NextcloudInstanceWeek {
  instanceId: string;
  name: string;
  app: 'nextcloud';
  demo: boolean;
  listed: boolean;
  flags: string[];
  setup: NextcloudSetup;
  logins: NextcloudLogins;
  office: NextcloudOffice;
  appsOpened: NextcloudAppOpen[];
  workflows: NextcloudWorkflows;
}

export interface NextcloudWeekResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  instances: NextcloudInstanceWeek[];
}

// ---------------------------------------------------------------------------
// Wikipedia / Kiwix week aggregates — no identity
// ---------------------------------------------------------------------------

export interface KiwixTopArticle {
  title: string;
  views: number;
}

export interface KiwixInstanceWeek {
  instanceId: string;
  name: string;
  app: 'kiwix';
  demo: boolean;
  listed: boolean;
  flags: string[];
  pageViews: number;
  distinctArticles: number;
  sessions: number;
  topArticles: KiwixTopArticle[];
  /** Length 24, kit-local hour 0–23. School-level only; never per person. */
  byHour: number[];
}

export interface KiwixWeekResponse {
  schema: ApiSchema;
  deploymentId: string;
  weekStart: WeekStart;
  instances: KiwixInstanceWeek[];
}

// ---------------------------------------------------------------------------
// Instance breakdown (every discovered container, including unlisted)
// ---------------------------------------------------------------------------

export type AppKind = 'kolibri' | 'nextcloud' | 'kiwix' | 'other';

export type HookStatus = 'ok' | 'unlistedBorrowed' | 'unlistedNoHook' | 'missing';

export interface DiscoveredInstance {
  instanceId: string;
  name: string;
  app: AppKind;
  demo: boolean;
  listed: boolean;
  hookStatus: HookStatus;
  port: number | null;
  note: string;
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
