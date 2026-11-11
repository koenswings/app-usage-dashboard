import type {
  Census,
  DiscoveredInstance,
  HelpSuggestion,
  InstancesResponse,
  KitListItem,
  KitTimezone,
  KiwixInstanceWeek,
  KolibriInstanceWeek,
  MetaResponse,
  NextcloudInstanceWeek,
  OverviewResponse,
  PresenceSegment,
  SchoolCard,
  ScorecardInputs,
  UplinkSample,
  UplinkTransition,
} from '../api/types';
import { API_SCHEMA, DAY_SCHEMA } from '../api/types';
import { fridayOf, formatWeekLabel } from '../lib/week';

export const SAMPLE_WEEK = '2026-11-02';
export const PREV_WEEK = '2026-10-26';
export const DEP_NHARIRA = 'dep-nharira';
export const DEP_CHIGONDA = 'dep-chigonda';
export const DEP_PANDA = 'dep-kind-panda';

export const HARARE: KitTimezone = {
  timeZone: 'Africa/Harare',
  utcOffset: '+02:00',
  label: 'kit local time (Africa/Harare, UTC+2)',
};

export const meta: MetaResponse = {
  schema: API_SCHEMA,
  daySchema: DAY_SCHEMA,
  thresholdsConfigured: false,
  staleAfterHours: 48,
  hourlyChartMinWeeklyViews: 20,
  headerTimeZone: 'Europe/Brussels',
  sampleData: true,
  todayWeekStart: SAMPLE_WEEK,
  currentWeekHasData: true,
};

export const kits: KitListItem[] = [
  {
    engine: 'happy-zebra',
    tailscaleName: 'happy-zebra',
    school: 'Nharira',
    deploymentId: DEP_NHARIRA,
    lastPulled: '2026-11-10T13:40:00+01:00',
    monitoringEnabled: true,
  },
  {
    engine: 'sunny-robin',
    tailscaleName: 'sunny-robin',
    school: 'Chigonda',
    deploymentId: DEP_CHIGONDA,
    lastPulled: '2026-11-04T09:00:00+01:00',
    monitoringEnabled: true,
  },
  {
    engine: 'kind-panda',
    tailscaleName: 'kind-panda',
    school: 'kind-panda',
    deploymentId: DEP_PANDA,
    lastPulled: null,
    monitoringEnabled: false,
  },
];

function emptyScorecard(): ScorecardInputs {
  return {
    available: {
      schoolDaysOn: null,
      schoolDaysExpected: 5,
      schoolHoursOnMinutes: null,
      bootsPerSchoolDay: null,
      longestGapMinutes: null,
    },
    setup: {
      classes: null,
      learnersRegistered: null,
      learnersEnrolled: null,
      teachers: null,
      admins: null,
      nextcloudTeacherBeyondSeed: null,
      nextcloudLearnerBeyondSeed: null,
    },
    teachingCycle: {
      lessonsCreated: null,
      lessonsVisible: null,
      quizzesCreated: null,
      quizzesStarted: null,
      learnerSessionsOnAssigned: null,
      assignedShareOfLearnerVisits: null,
    },
    learnersOperate: {
      learnerSessions: null,
      learnerMinutes: null,
      coachSessions: null,
      coachMinutes: null,
      adminSessions: null,
      adminMinutes: null,
      guestVisits: null,
      guestMinutes: null,
      learnerShareOfMinutes: null,
    },
    nextcloud: {
      worksheetShares: null,
      editShares: null,
      fileDropLinks: null,
      fileDropUploads: null,
      schoolFilesShares: null,
      officeOpens: null,
      officeDistinctDocuments: null,
      officeRead: null,
      officeEdit: null,
      officeEstimatedMinutes: null,
    },
    wikipedia: {
      pageViewsOwn: null,
      sessionsOwn: null,
      distinctArticlesOwn: null,
    },
  };
}

const nhariraScorecard: ScorecardInputs = {
  available: {
    schoolDaysOn: 4,
    schoolDaysExpected: 5,
    schoolHoursOnMinutes: 1680,
    bootsPerSchoolDay: [1, 1, 1, 1, 1],
    longestGapMinutes: 960,
  },
  setup: {
    classes: 2,
    learnersRegistered: 18,
    learnersEnrolled: 12,
    teachers: 2,
    admins: 1,
    nextcloudTeacherBeyondSeed: 2,
    nextcloudLearnerBeyondSeed: 3,
  },
  teachingCycle: {
    lessonsCreated: 3,
    lessonsVisible: 2,
    quizzesCreated: 1,
    quizzesStarted: 1,
    learnerSessionsOnAssigned: 11,
    assignedShareOfLearnerVisits: 0.41,
  },
  learnersOperate: {
    learnerSessions: 27,
    learnerMinutes: 122,
    coachSessions: 11,
    coachMinutes: 186,
    adminSessions: 6,
    adminMinutes: 74,
    guestVisits: 4,
    guestMinutes: 19,
    learnerShareOfMinutes: 122 / (122 + 186 + 74),
  },
  nextcloud: {
    worksheetShares: 1,
    editShares: 1,
    fileDropLinks: 0,
    fileDropUploads: 0,
    schoolFilesShares: 0,
    officeOpens: 12,
    officeDistinctDocuments: 5,
    officeRead: 7,
    officeEdit: 5,
    officeEstimatedMinutes: 107,
  },
  wikipedia: {
    pageViewsOwn: 142,
    sessionsOwn: 11,
    distinctArticlesOwn: 38,
  },
};

const nhariraPrevScorecard: ScorecardInputs = {
  ...nhariraScorecard,
  teachingCycle: {
    ...nhariraScorecard.teachingCycle,
    lessonsCreated: 2,
    lessonsVisible: 1,
    quizzesCreated: 0,
    quizzesStarted: 0,
    learnerSessionsOnAssigned: 4,
    assignedShareOfLearnerVisits: 0.22,
  },
  learnersOperate: {
    ...nhariraScorecard.learnersOperate,
    learnerSessions: 14,
    learnerMinutes: 68,
    learnerShareOfMinutes: 68 / (68 + 140 + 80),
  },
  wikipedia: {
    pageViewsOwn: 90,
    sessionsOwn: 7,
    distinctArticlesOwn: 24,
  },
};

const chigondaScorecard: ScorecardInputs = {
  available: {
    schoolDaysOn: 2,
    schoolDaysExpected: 5,
    schoolHoursOnMinutes: 420,
    bootsPerSchoolDay: [1, 7, 1, 0, 0],
    longestGapMinutes: 210,
  },
  setup: {
    classes: 0,
    learnersRegistered: 1,
    learnersEnrolled: 0,
    teachers: 0,
    admins: 1,
    nextcloudTeacherBeyondSeed: 0,
    nextcloudLearnerBeyondSeed: 0,
  },
  teachingCycle: {
    lessonsCreated: 0,
    lessonsVisible: 0,
    quizzesCreated: 0,
    quizzesStarted: 0,
    learnerSessionsOnAssigned: 0,
    assignedShareOfLearnerVisits: null,
  },
  learnersOperate: {
    learnerSessions: 0,
    learnerMinutes: 0,
    coachSessions: 0,
    coachMinutes: 0,
    adminSessions: 3,
    adminMinutes: 22,
    guestVisits: 1,
    guestMinutes: 4,
    learnerShareOfMinutes: 0,
  },
  nextcloud: {
    worksheetShares: 0,
    editShares: 0,
    fileDropLinks: 0,
    fileDropUploads: 0,
    schoolFilesShares: 0,
    officeOpens: 0,
    officeDistinctDocuments: 0,
    officeRead: 0,
    officeEdit: 0,
    officeEstimatedMinutes: 0,
  },
  wikipedia: {
    pageViewsOwn: 8,
    sessionsOwn: 2,
    distinctArticlesOwn: 3,
  },
};

const emptyCensus: Census = {
  classes: null,
  classesDelta: null,
  learnersRegistered: null,
  learnersRegisteredDelta: null,
  learnersEnrolled: null,
  teachers: null,
  teachersDelta: null,
  admins: null,
};

const nhariraCensus: Census = {
  classes: 2,
  classesDelta: 1,
  learnersRegistered: 18,
  learnersRegisteredDelta: 3,
  learnersEnrolled: 12,
  teachers: 2,
  teachersDelta: 0,
  admins: 1,
};

export const cardsByWeek: Record<string, SchoolCard[]> = {
  [SAMPLE_WEEK]: [
    {
      deploymentId: DEP_NHARIRA,
      school: 'Nharira',
      engine: 'happy-zebra',
      note: 'own apps + Demo',
      lastPulled: '2026-11-10T13:40:00+01:00',
      stale: false,
      dataFrom: null,
      hasUsageData: true,
      monitoringEnabled: true,
      scorecard: nhariraScorecard,
      headlines: { classes: 2, learnersRegistered: 18, teachers: 2, kolibriMinutes: 382 },
    },
    {
      deploymentId: DEP_CHIGONDA,
      school: 'Chigonda',
      engine: 'sunny-robin',
      note: 'intermittent power',
      lastPulled: '2026-11-04T09:00:00+01:00',
      stale: true,
      dataFrom: '2026-11-04',
      hasUsageData: true,
      monitoringEnabled: true,
      scorecard: chigondaScorecard,
      headlines: { classes: 0, learnersRegistered: 1, teachers: 0, kolibriMinutes: 22 },
    },
    {
      deploymentId: DEP_PANDA,
      school: 'kind-panda',
      engine: 'kind-panda',
      note: 'Not installed yet',
      lastPulled: null,
      stale: false,
      dataFrom: null,
      hasUsageData: false,
      monitoringEnabled: false,
      scorecard: emptyScorecard(),
      headlines: { classes: null, learnersRegistered: null, teachers: null, kolibriMinutes: null },
    },
  ],
  [PREV_WEEK]: [
    {
      deploymentId: DEP_NHARIRA,
      school: 'Nharira',
      engine: 'happy-zebra',
      note: 'own apps + Demo',
      lastPulled: '2026-11-03T11:10:00+01:00',
      stale: false,
      dataFrom: null,
      hasUsageData: true,
      monitoringEnabled: true,
      scorecard: nhariraPrevScorecard,
      headlines: { classes: 1, learnersRegistered: 15, teachers: 2, kolibriMinutes: 288 },
    },
    {
      deploymentId: DEP_CHIGONDA,
      school: 'Chigonda',
      engine: 'sunny-robin',
      note: 'intermittent power',
      lastPulled: '2026-11-04T09:00:00+01:00',
      stale: true,
      dataFrom: '2026-11-04',
      hasUsageData: false,
      monitoringEnabled: true,
      scorecard: emptyScorecard(),
      headlines: { classes: null, learnersRegistered: null, teachers: null, kolibriMinutes: null },
    },
    {
      deploymentId: DEP_PANDA,
      school: 'kind-panda',
      engine: 'kind-panda',
      note: 'Not installed yet',
      lastPulled: null,
      stale: false,
      dataFrom: null,
      hasUsageData: false,
      monitoringEnabled: false,
      scorecard: emptyScorecard(),
      headlines: { classes: null, learnersRegistered: null, teachers: null, kolibriMinutes: null },
    },
  ],
};

export const helpSuggestions: Record<string, HelpSuggestion[]> = {
  [SAMPLE_WEEK]: [
    {
      deploymentId: DEP_CHIGONDA,
      engine: 'sunny-robin',
      school: 'Chigonda',
      message:
        'sunny-robin (Chigonda) shows a school-day power pattern but almost no learner activity this week — offer help on tutorial chapters 3.3–3.4 and 4.',
    },
  ],
  [PREV_WEEK]: [],
};

export function overviewFor(weekStart: string): OverviewResponse {
  const cards = cardsByWeek[weekStart] ?? cardsByWeek[SAMPLE_WEEK].map((card) => ({
    ...card,
    hasUsageData: false,
    scorecard: emptyScorecard(),
    headlines: { classes: null, learnersRegistered: null, teachers: null, kolibriMinutes: null },
    lastPulled: card.lastPulled,
  }));
  const weekEnd = fridayOf(weekStart);
  return {
    schema: API_SCHEMA,
    weekStart,
    weekEnd,
    weekLabel: formatWeekLabel(weekStart, weekEnd),
    thresholdsConfigured: false,
    sampleData: true,
    staleAfterHours: meta.staleAfterHours,
    cards,
    helpSuggestions: helpSuggestions[weekStart] ?? [],
  };
}

function seg(state: PresenceSegment['state'], start: string, end: string, lengthKnown: boolean): PresenceSegment {
  return { state, start, end, lengthKnown };
}

/** Nharira week covering all four presence states. Times are kit-local (UTC+2). */
export const nhariraSegments: PresenceSegment[] = [
  seg('off', '2026-11-02T00:00:00+02:00', '2026-11-02T07:00:00+02:00', true),
  seg('on', '2026-11-02T07:00:00+02:00', '2026-11-02T16:00:00+02:00', true),
  seg('off', '2026-11-02T16:00:00+02:00', '2026-11-03T07:00:00+02:00', true),
  seg('on', '2026-11-03T07:00:00+02:00', '2026-11-03T11:00:00+02:00', true),
  seg('gapUnknown', '2026-11-03T11:00:00+02:00', '2026-11-03T14:00:00+02:00', false),
  seg('on', '2026-11-03T14:00:00+02:00', '2026-11-03T16:00:00+02:00', true),
  seg('off', '2026-11-03T16:00:00+02:00', '2026-11-04T07:00:00+02:00', true),
  seg('on', '2026-11-04T07:00:00+02:00', '2026-11-04T10:00:00+02:00', true),
  seg('collectorGap', '2026-11-04T10:00:00+02:00', '2026-11-04T12:00:00+02:00', false),
  seg('on', '2026-11-04T12:00:00+02:00', '2026-11-04T16:00:00+02:00', true),
  seg('off', '2026-11-04T16:00:00+02:00', '2026-11-05T07:00:00+02:00', true),
  seg('on', '2026-11-05T07:00:00+02:00', '2026-11-05T16:00:00+02:00', true),
  seg('off', '2026-11-05T16:00:00+02:00', '2026-11-06T07:00:00+02:00', true),
  seg('on', '2026-11-06T07:00:00+02:00', '2026-11-06T12:00:00+02:00', true),
  seg('off', '2026-11-06T12:00:00+02:00', '2026-11-07T00:00:00+02:00', true),
];

export const chigondaSegments: PresenceSegment[] = [
  seg('off', '2026-11-02T00:00:00+02:00', '2026-11-02T08:00:00+02:00', true),
  seg('on', '2026-11-02T08:00:00+02:00', '2026-11-02T11:00:00+02:00', true),
  seg('off', '2026-11-02T11:00:00+02:00', '2026-11-03T09:00:00+02:00', true),
  seg('on', '2026-11-03T09:00:00+02:00', '2026-11-03T10:20:00+02:00', true),
  seg('off', '2026-11-03T10:20:00+02:00', '2026-11-03T11:00:00+02:00', true),
  seg('on', '2026-11-03T11:00:00+02:00', '2026-11-03T12:10:00+02:00', true),
  seg('gapUnknown', '2026-11-03T12:10:00+02:00', '2026-11-03T15:00:00+02:00', false),
  seg('off', '2026-11-03T15:00:00+02:00', '2026-11-07T00:00:00+02:00', true),
];

/** kind-panda is monitoring off. The collector may still send gap/unknown cover; the UI must not draw it as presence. */
export const pandaOffSegments: PresenceSegment[] = [
  seg('gapUnknown', '2026-11-02T00:00:00+02:00', '2026-11-04T23:48:00+02:00', false),
  seg('collectorGap', '2026-11-04T23:48:00+02:00', '2026-11-05T00:00:00+02:00', false),
  seg('gapUnknown', '2026-11-05T00:00:00+02:00', '2026-11-07T00:00:00+02:00', false),
];

export function segmentsFor(deploymentId: string, weekStart: string): PresenceSegment[] {
  if (weekStart !== SAMPLE_WEEK) return [];
  if (deploymentId === DEP_NHARIRA) return nhariraSegments;
  if (deploymentId === DEP_CHIGONDA) return chigondaSegments;
  if (deploymentId === DEP_PANDA) return pandaOffSegments;
  return [];
}

export function presenceSummary(deploymentId: string, weekStart?: string): string | null {
  if (weekStart && weekStart !== SAMPLE_WEEK) return null;
  if (deploymentId === DEP_NHARIRA) {
    return 'On 4 of 5 school days, 31 h in school hours';
  }
  if (deploymentId === DEP_CHIGONDA) {
    return 'On 2 of 5 school days, 6.5 h in school hours';
  }
  return null;
}

export const nhariraKolibri: KolibriInstanceWeek[] = [
  {
    instance: 'kolibri-a1b2c3',
    instanceId: 'kolibri-a1b2c3',
    name: 'Kolibri',
    app: 'kolibri',
    demo: false,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-06T16:10:00+02:00',
    flags: [],
    clock: { synced: true, correctedBoots: 0 },
    setup: nhariraCensus,
    signins: {
      learner: { users: 18, sessions: 27, minutes: 122 },
      coach: { users: 2, sessions: 11, minutes: 186 },
      admin: { users: 1, sessions: 6, minutes: 74 },
    },
    guest: { visits: 4, seconds: 19 * 60 },
    teaching: {
      lessonsCreated: 3,
      lessonsVisible: 2,
      quizzesCreated: 1,
      quizzesStarted: 1,
      quizzesEnded: 0,
    },
    content: [
      { channel: 'Maths', title: 'Fraction circles', kind: 'exercise', role: 'learner', visits: 14, seconds: 48 * 60, completions: 5, assigned: true },
      { channel: 'Maths', title: 'Fractions practice', kind: 'exercise', role: 'learner', visits: 9, seconds: 37 * 60, completions: 3, assigned: true },
      { channel: 'Grade 5 Science', title: 'Water', kind: 'video', role: 'coach', visits: 3, seconds: 22 * 60, completions: 0, assigned: false },
      { channel: 'Early Reading', title: 'Rudo…', kind: 'html5', role: 'learner', visits: 5, seconds: 15 * 60, completions: 1, assigned: false },
    ],
  },
  {
    instance: 'kolibri-demo',
    instanceId: 'kolibri-demo',
    name: 'Kolibri Demo',
    app: 'kolibri',
    demo: true,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-06T16:10:00+02:00',
    flags: ['demoSeedExcluded'],
    clock: { synced: true, correctedBoots: 0 },
    setup: {
      classes: 1,
      classesDelta: 0,
      learnersRegistered: 6,
      learnersRegisteredDelta: 0,
      learnersEnrolled: 6,
      teachers: 1,
      teachersDelta: 0,
      admins: 1,
    },
    signins: {
      learner: { users: 6, sessions: 4, minutes: 18 },
      coach: { users: 1, sessions: 2, minutes: 25 },
      admin: { users: 1, sessions: 1, minutes: 8 },
    },
    guest: { visits: 0, seconds: 0 },
    teaching: {
      lessonsCreated: 1,
      lessonsVisible: 1,
      quizzesCreated: 0,
      quizzesStarted: 0,
      quizzesEnded: 0,
    },
    content: [
      { channel: 'Demo Maths', title: 'Seed lesson', kind: 'exercise', role: 'learner', visits: 4, seconds: 12 * 60, completions: 0, assigned: true },
    ],
  },
  {
    instance: 'kolibri-unlisted-62561',
    instanceId: 'kolibri-unlisted-62561',
    name: 'Kolibri',
    app: 'kolibri',
    demo: false,
    listed: false,
    hookStatus: 'ok',
    collectedAt: '2026-11-06T16:10:00+02:00',
    flags: [],
    clock: { synced: true, correctedBoots: 0 },
    setup: {
      classes: 0,
      classesDelta: 0,
      learnersRegistered: 0,
      learnersRegisteredDelta: 0,
      learnersEnrolled: 0,
      teachers: 0,
      teachersDelta: 0,
      admins: 1,
    },
    signins: {
      learner: { users: 0, sessions: 0, minutes: 0 },
      coach: { users: 0, sessions: 0, minutes: 0 },
      admin: { users: 1, sessions: 2, minutes: 15 },
    },
    guest: { visits: 1, seconds: 120 },
    teaching: {
      lessonsCreated: 0,
      lessonsVisible: 0,
      quizzesCreated: 0,
      quizzesStarted: 0,
      quizzesEnded: 0,
    },
    content: [],
  },
];

export const chigondaKolibri: KolibriInstanceWeek[] = [
  {
    instance: 'kolibri-chigonda',
    instanceId: 'kolibri-chigonda',
    name: 'Kolibri',
    app: 'kolibri',
    demo: false,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-03T12:10:00+02:00',
    flags: [],
    clock: { synced: false, correctedBoots: 1 },
    setup: {
      classes: 0,
      classesDelta: 0,
      learnersRegistered: 1,
      learnersRegisteredDelta: 0,
      learnersEnrolled: 0,
      teachers: 0,
      teachersDelta: 0,
      admins: 1,
    },
    signins: {
      learner: { users: 1, sessions: 0, minutes: 0 },
      coach: { users: 0, sessions: 0, minutes: 0 },
      admin: { users: 1, sessions: 3, minutes: 22 },
    },
    guest: { visits: 1, seconds: 240 },
    teaching: {
      lessonsCreated: 0,
      lessonsVisible: 0,
      quizzesCreated: 0,
      quizzesStarted: 0,
      quizzesEnded: 0,
    },
    content: [],
  },
];

export const nhariraNextcloud: NextcloudInstanceWeek[] = [
  {
    instance: 'nextcloud-own',
    instanceId: 'nextcloud-own',
    name: 'Nextcloud',
    app: 'nextcloud',
    demo: false,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-06T16:10:00+02:00',
    clock: { synced: true, correctedBoots: 0 },
    setup: {
      admin: { total: 1, beyondSeed: 0 },
      teacher: { total: 3, beyondSeed: 2 },
      learner: { total: 4, beyondSeed: 3 },
      otherGroups: { 'Grade 5': 12 },
    },
    logins: {
      admin: { total: 3, beyondSeed: 0 },
      teacher: { total: 8, beyondSeed: 6 },
      learner: { total: 2, beyondSeed: 2 },
    },
    office: {
      opens: 12,
      distinctDocuments: 5,
      read: 7,
      edit: 5,
      estimatedMinutes: 107,
      byGroup: { admin: 2, teacher: 9, learner: 1 },
      mime: { text: 8, sheet: 3, slides: 1 },
    },
    appsOpened: { files: 46, richdocuments: 12, photos: 0 },
    workflows: {
      worksheetShares: 1,
      editShares: 1,
      fileDropLinks: 0,
      fileDropUploads: 0,
      schoolFilesShares: 0,
    },
  },
  {
    instance: 'nextcloud-demo',
    instanceId: 'nextcloud-demo',
    name: 'Nextcloud Demo',
    app: 'nextcloud',
    demo: true,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-06T16:10:00+02:00',
    clock: { synced: true, correctedBoots: 0 },
    setup: {
      admin: { total: 1, beyondSeed: 0 },
      teacher: { total: 1, beyondSeed: 0 },
      learner: { total: 1, beyondSeed: 0 },
    },
    logins: {
      admin: { total: 1, beyondSeed: 0 },
      teacher: { total: 1, beyondSeed: 0 },
      learner: { total: 0, beyondSeed: 0 },
    },
    office: {
      opens: 1,
      distinctDocuments: 1,
      read: 1,
      edit: 0,
      estimatedMinutes: 8,
      byGroup: { admin: 0, teacher: 1, learner: 0 },
      mime: { text: 1, sheet: 0, slides: 0 },
    },
    appsOpened: { files: 5 },
    workflows: {
      worksheetShares: 0,
      editShares: 0,
      fileDropLinks: 0,
      fileDropUploads: 0,
      schoolFilesShares: 0,
    },
  },
  {
    instance: 'nextcloud-extra',
    instanceId: 'nextcloud-extra',
    name: 'Nextcloud',
    app: 'nextcloud',
    demo: false,
    listed: false,
    hookStatus: 'timeout',
    collectedAt: '2026-11-06T16:10:00+02:00',
    clock: { synced: true, correctedBoots: 0 },
    setup: null,
    logins: null,
    office: null,
    appsOpened: null,
    workflows: null,
  },
];

export const chigondaNextcloud: NextcloudInstanceWeek[] = [
  {
    instance: 'nextcloud-chigonda',
    instanceId: 'nextcloud-chigonda',
    name: 'Nextcloud',
    app: 'nextcloud',
    demo: false,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-03T12:10:00+02:00',
    clock: { synced: false, correctedBoots: 1 },
    setup: {
      admin: { total: 1, beyondSeed: 0 },
      teacher: { total: 1, beyondSeed: 0 },
      learner: { total: 1, beyondSeed: 0 },
    },
    logins: {
      admin: { total: 1, beyondSeed: 0 },
      teacher: { total: 1, beyondSeed: 0 },
      learner: { total: 0, beyondSeed: 0 },
    },
    office: {
      opens: 0,
      distinctDocuments: 0,
      read: 0,
      edit: 0,
      estimatedMinutes: 0,
      byGroup: { admin: 0, teacher: 0, learner: 0 },
      mime: { text: 0, sheet: 0, slides: 0 },
    },
    appsOpened: { files: 3 },
    workflows: {
      worksheetShares: 0,
      editShares: 0,
      fileDropLinks: 0,
      fileDropUploads: 0,
      schoolFilesShares: 0,
    },
  },
];

const nhariraByHour = [2, 1, 0, 0, 1, 2, 3, 14, 22, 28, 19, 10, 24, 26, 12, 6, 3, 2, 1, 1, 0, 0, 0, 0];

export const nhariraKiwix: KiwixInstanceWeek[] = [
  {
    instance: 'kiwix-own',
    instanceId: 'kiwix-own',
    name: 'Wikipedia',
    app: 'kiwix',
    demo: false,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-06T16:10:00+02:00',
    clock: { synced: true, correctedBoots: 0 },
    pageViews: 142,
    distinctArticles: 38,
    sessions: 11,
    topArticles: [
      { title: 'Fraction', views: 21 },
      { title: 'Photosynthesis', views: 14 },
      { title: 'Zimbabwe', views: 11 },
      { title: 'Water cycle', views: 8 },
    ],
    byHour: nhariraByHour,
  },
  {
    instance: 'kiwix-demo',
    instanceId: 'kiwix-demo',
    name: 'Wikipedia (Demo)',
    app: 'kiwix',
    demo: true,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-06T16:10:00+02:00',
    clock: { synced: true, correctedBoots: 0 },
    pageViews: 19,
    distinctArticles: 7,
    sessions: 3,
    topArticles: [
      { title: 'Simple English — Water', views: 6 },
      { title: 'Simple English — School', views: 4 },
    ],
    byHour: [0, 0, 0, 0, 0, 0, 0, 1, 3, 4, 2, 1, 3, 3, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
  },
];

export const chigondaKiwix: KiwixInstanceWeek[] = [
  {
    instance: 'kiwix-chigonda',
    instanceId: 'kiwix-chigonda',
    name: 'Wikipedia',
    app: 'kiwix',
    demo: false,
    listed: true,
    hookStatus: 'ok',
    collectedAt: '2026-11-03T12:10:00+02:00',
    clock: { synced: false, correctedBoots: 1 },
    pageViews: 8,
    distinctArticles: 3,
    sessions: 2,
    topArticles: [
      { title: 'Zimbabwe', views: 4 },
      { title: 'Harare', views: 3 },
      { title: 'School', views: 1 },
    ],
    byHour: [0, 0, 0, 0, 0, 0, 0, 0, 2, 3, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  },
];

const NH_COLLECTED = '2026-11-06T16:10:00+02:00';
const CH_COLLECTED = '2026-11-03T12:10:00+02:00';
const CLOCK_OK = { synced: true, correctedBoots: 0 } as const;
const CLOCK_UNSYNCED = { synced: false, correctedBoots: 1 } as const;

export const nhariraInstances: DiscoveredInstance[] = [
  { instance: 'kolibri-a1b2c3', instanceId: 'kolibri-a1b2c3', name: 'Kolibri', app: 'kolibri', demo: false, listed: true, hookStatus: 'ok', clock: CLOCK_OK, collectedAt: NH_COLLECTED },
  { instance: 'kolibri-demo', instanceId: 'kolibri-demo', name: 'Kolibri Demo', app: 'kolibri', demo: true, listed: true, hookStatus: 'ok', clock: CLOCK_OK, collectedAt: NH_COLLECTED },
  { instance: 'kolibri-unlisted-62561', instanceId: 'kolibri-unlisted-62561', name: 'Kolibri', app: 'kolibri', demo: false, listed: false, hookStatus: 'ok', clock: CLOCK_OK, collectedAt: NH_COLLECTED, note: 'Extra copy, not on the kit’s usual list' },
  { instance: 'nextcloud-own', instanceId: 'nextcloud-own', name: 'Nextcloud', app: 'nextcloud', demo: false, listed: true, hookStatus: 'ok', clock: CLOCK_OK, collectedAt: NH_COLLECTED },
  { instance: 'nextcloud-demo', instanceId: 'nextcloud-demo', name: 'Nextcloud Demo', app: 'nextcloud', demo: true, listed: true, hookStatus: 'ok', clock: CLOCK_OK, collectedAt: NH_COLLECTED },
  { instance: 'nextcloud-extra', instanceId: 'nextcloud-extra', name: 'Nextcloud', app: 'nextcloud', demo: false, listed: false, hookStatus: 'timeout', clock: CLOCK_OK, collectedAt: NH_COLLECTED },
  { instance: 'kiwix-own', instanceId: 'kiwix-own', name: 'Wikipedia', app: 'kiwix', demo: false, listed: true, hookStatus: 'ok', clock: CLOCK_OK, collectedAt: NH_COLLECTED },
  { instance: 'kiwix-demo', instanceId: 'kiwix-demo', name: 'Wikipedia (Demo)', app: 'kiwix', demo: true, listed: true, hookStatus: 'ok', clock: CLOCK_OK, collectedAt: NH_COLLECTED },
];

export const chigondaInstances: DiscoveredInstance[] = [
  { instance: 'kolibri-chigonda', instanceId: 'kolibri-chigonda', name: 'Kolibri', app: 'kolibri', demo: false, listed: true, hookStatus: 'ok', clock: CLOCK_UNSYNCED, collectedAt: CH_COLLECTED },
  { instance: 'nextcloud-chigonda', instanceId: 'nextcloud-chigonda', name: 'Nextcloud', app: 'nextcloud', demo: false, listed: true, hookStatus: 'ok', clock: CLOCK_UNSYNCED, collectedAt: CH_COLLECTED },
  { instance: 'kiwix-chigonda', instanceId: 'kiwix-chigonda', name: 'Wikipedia', app: 'kiwix', demo: false, listed: true, hookStatus: 'ok', clock: CLOCK_UNSYNCED, collectedAt: CH_COLLECTED },
];

export function instancesFor(deploymentId: string, weekStart: string): InstancesResponse {
  const list =
    deploymentId === DEP_NHARIRA ? nhariraInstances :
    deploymentId === DEP_CHIGONDA ? chigondaInstances :
    [];
  return { schema: API_SCHEMA, deploymentId, weekStart, instances: list };
}

export function censusFor(deploymentId: string, weekStart: string): Census {
  if (weekStart !== SAMPLE_WEEK) {
    if (deploymentId === DEP_NHARIRA && weekStart === PREV_WEEK) {
      return { ...nhariraCensus, classes: 1, classesDelta: 0, learnersRegistered: 15, learnersRegisteredDelta: 0, learnersEnrolled: 10 };
    }
    return emptyCensus;
  }
  if (deploymentId === DEP_NHARIRA) return nhariraCensus;
  if (deploymentId === DEP_CHIGONDA) {
    return {
      classes: 0,
      classesDelta: 0,
      learnersRegistered: 1,
      learnersRegisteredDelta: 0,
      learnersEnrolled: 0,
      teachers: 0,
      teachersDelta: 0,
      admins: 1,
    };
  }
  return emptyCensus;
}

export function scorecardFor(deploymentId: string, weekStart: string): ScorecardInputs {
  const card = (cardsByWeek[weekStart] ?? []).find((c) => c.deploymentId === deploymentId);
  return card?.scorecard ?? emptyScorecard();
}

export function cardFor(deploymentId: string, weekStart: string): SchoolCard | undefined {
  return (cardsByWeek[weekStart] ?? cardsByWeek[SAMPLE_WEEK]).find((c) => c.deploymentId === deploymentId);
}

function uplinkPair(engine: string, start: string, end: string, online: boolean, via: UplinkSample['via']): UplinkSample[] {
  return [
    { timestamp: start, engine, online, lastSeen: start, via, latencyMs: online ? 42 : null },
    { timestamp: end, engine, online, lastSeen: online ? end : start, via: online ? via : null, latencyMs: online ? 38 : null },
  ];
}

export function uplinkFor(deploymentId: string): { samples: UplinkSample[]; transitions: UplinkTransition[] } {
  if (deploymentId === DEP_NHARIRA) {
    const engine = 'happy-zebra';
    const samples: UplinkSample[] = [
      ...uplinkPair(engine, '2026-11-02T07:05:00+02:00', '2026-11-02T16:02:00+02:00', true, 'DERP'),
      { timestamp: '2026-11-02T16:10:00+02:00', engine, online: false, lastSeen: '2026-11-02T16:02:00+02:00', via: null, latencyMs: null },
      ...uplinkPair(engine, '2026-11-03T07:04:00+02:00', '2026-11-03T16:01:00+02:00', true, 'DERP'),
      { timestamp: '2026-11-04T07:06:00+02:00', engine, online: true, lastSeen: '2026-11-04T07:06:00+02:00', via: 'DERP', latencyMs: 55 },
      { timestamp: '2026-11-04T10:00:00+02:00', engine, online: true, lastSeen: '2026-11-04T09:58:00+02:00', via: 'DERP', latencyMs: 61 },
      { timestamp: '2026-11-04T12:05:00+02:00', engine, online: true, lastSeen: '2026-11-04T12:05:00+02:00', via: 'DERP', latencyMs: 48 },
      ...uplinkPair(engine, '2026-11-05T07:02:00+02:00', '2026-11-05T16:00:00+02:00', true, 'direct'),
      ...uplinkPair(engine, '2026-11-06T07:03:00+02:00', '2026-11-06T12:04:00+02:00', true, 'DERP'),
    ];
    const transitions: UplinkTransition[] = [
      { timestamp: '2026-11-02T07:05:00+02:00', engine, fromState: 'offline', toState: 'online' },
      { timestamp: '2026-11-02T16:10:00+02:00', engine, fromState: 'online', toState: 'offline' },
      { timestamp: '2026-11-03T07:04:00+02:00', engine, fromState: 'offline', toState: 'online' },
      { timestamp: '2026-11-03T16:08:00+02:00', engine, fromState: 'online', toState: 'offline' },
      { timestamp: '2026-11-04T07:06:00+02:00', engine, fromState: 'offline', toState: 'online' },
      { timestamp: '2026-11-04T16:07:00+02:00', engine, fromState: 'online', toState: 'offline' },
      { timestamp: '2026-11-05T07:02:00+02:00', engine, fromState: 'offline', toState: 'online' },
      { timestamp: '2026-11-05T16:06:00+02:00', engine, fromState: 'online', toState: 'offline' },
      { timestamp: '2026-11-06T07:03:00+02:00', engine, fromState: 'offline', toState: 'online' },
      { timestamp: '2026-11-06T12:10:00+02:00', engine, fromState: 'online', toState: 'offline' },
    ];
    return { samples, transitions };
  }
  if (deploymentId === DEP_CHIGONDA) {
    const engine = 'sunny-robin';
    return {
      samples: [
        { timestamp: '2026-11-02T08:04:00+02:00', engine, online: true, lastSeen: '2026-11-02T08:04:00+02:00', via: 'DERP', latencyMs: 120 },
        { timestamp: '2026-11-02T11:08:00+02:00', engine, online: false, lastSeen: '2026-11-02T11:01:00+02:00', via: null, latencyMs: null },
        { timestamp: '2026-11-03T09:02:00+02:00', engine, online: true, lastSeen: '2026-11-03T09:02:00+02:00', via: 'DERP', latencyMs: 98 },
        { timestamp: '2026-11-03T12:15:00+02:00', engine, online: false, lastSeen: '2026-11-03T12:10:00+02:00', via: null, latencyMs: null },
      ],
      transitions: [
        { timestamp: '2026-11-02T08:04:00+02:00', engine, fromState: 'offline', toState: 'online' },
        { timestamp: '2026-11-02T11:08:00+02:00', engine, fromState: 'online', toState: 'offline' },
        { timestamp: '2026-11-03T09:02:00+02:00', engine, fromState: 'offline', toState: 'online' },
        { timestamp: '2026-11-03T12:15:00+02:00', engine, fromState: 'online', toState: 'offline' },
      ],
    };
  }
  return { samples: [], transitions: [] };
}

export function kolibriFor(deploymentId: string, weekStart: string): KolibriInstanceWeek[] {
  if (weekStart !== SAMPLE_WEEK) return [];
  if (deploymentId === DEP_NHARIRA) return nhariraKolibri;
  if (deploymentId === DEP_CHIGONDA) return chigondaKolibri;
  return [];
}

export function nextcloudFor(deploymentId: string, weekStart: string): NextcloudInstanceWeek[] {
  if (weekStart !== SAMPLE_WEEK) return [];
  if (deploymentId === DEP_NHARIRA) return nhariraNextcloud;
  if (deploymentId === DEP_CHIGONDA) return chigondaNextcloud;
  return [];
}

export function kiwixFor(deploymentId: string, weekStart: string): KiwixInstanceWeek[] {
  if (weekStart !== SAMPLE_WEEK) return [];
  if (deploymentId === DEP_NHARIRA) return nhariraKiwix;
  if (deploymentId === DEP_CHIGONDA) return chigondaKiwix;
  return [];
}
