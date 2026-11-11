import { API_SCHEMA, weekClockTrusted } from '../api/types';
import type {
  CreateHelpEventRequest,
  HelpEvent,
  HelpEventsResponse,
  PutThresholdsRequest,
  ScorecardThresholds,
} from '../api/types';
import {
  DEFAULT_THRESHOLDS,
  cloneThresholds,
  mergeThresholds,
  validateThresholdPatch,
} from '../config/thresholds';
import { fridayOf, isMonday } from '../lib/week';
import {
  DEP_CHIGONDA,
  DEP_NHARIRA,
  HARARE,
  PREV_WEEK,
  SAMPLE_WEEK,
  cardFor,
  censusFor,
  instancesFor,
  kiwixFor,
  kits,
  kolibriFor,
  meta,
  nextcloudFor,
  overviewFor,
  presenceSummary,
  scorecardFor,
  segmentsFor,
  uplinkFor,
} from './data';

function clockTrustedFor(deploymentId: string, weekStart: string): boolean {
  return weekClockTrusted([
    ...kolibriFor(deploymentId, weekStart),
    ...nextcloudFor(deploymentId, weekStart),
    ...kiwixFor(deploymentId, weekStart),
  ]);
}

const SESSION_COOKIE = 'idea_usage_session';
/** Mock-only operators (U-9). Not the production seed convention. */
const MOCK_OPERATORS = ['koen', 'marco'] as const;
const MOCK_PASSWORD = 'mock-operator';

type MockOperator = (typeof MOCK_OPERATORS)[number];

function emptyOperatorPasswords(): Record<MockOperator, string> {
  return { koen: MOCK_PASSWORD, marco: MOCK_PASSWORD };
}

let operatorPasswords: Record<MockOperator, string> = emptyOperatorPasswords();

function isMockOperator(value: string): value is MockOperator {
  return (MOCK_OPERATORS as readonly string[]).includes(value);
}

const helpStore = new Map<string, HelpEvent[]>();

let currentThresholds: ScorecardThresholds = cloneThresholds(DEFAULT_THRESHOLDS);
let thresholdsUpdatedAt: string | null = null;
let thresholdsUpdatedBy: string | null = null;

function thresholdsPayload() {
  return {
    thresholds: cloneThresholds(currentThresholds),
    defaults: cloneThresholds(DEFAULT_THRESHOLDS),
    updatedAt: thresholdsUpdatedAt,
    updatedBy: thresholdsUpdatedBy,
  };
}

function json(data: unknown, status = 200, headers?: Record<string, string>): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  });
}

function error(status: number, code: string, message: string): Response {
  return json({ error: { code, message } }, status);
}

function readCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(`${SESSION_COOKIE}=`)) {
      return decodeURIComponent(trimmed.slice(SESSION_COOKIE.length + 1));
    }
  }
  return null;
}

function setSessionCookie(value: string): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${SESSION_COOKIE}=${encodeURIComponent(value)}; Path=/; SameSite=Lax`;
}

function clearSessionCookie(): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${SESSION_COOKIE}=; Path=/; SameSite=Lax; Max-Age=0`;
}

function sessionUser(token: string | null): { username: string; role: 'operator' } | null {
  if (!token || !token.startsWith('op-')) return null;
  const username = token.slice(3);
  if (!isMockOperator(username)) return null;
  return { username, role: 'operator' };
}

function requireAuth(): Response | { username: string; role: 'operator' } {
  const user = sessionUser(readCookie());
  if (!user) return error(401, 'unauthorized', 'Operator session required.');
  return user;
}

function parseBody<T>(init?: RequestInit): T | null {
  if (!init?.body || typeof init.body !== 'string') return null;
  try {
    return JSON.parse(init.body) as T;
  } catch {
    return null;
  }
}

function defaultTrend(deploymentId: string): HelpEventsResponse['weeklyTrend'] {
  if (deploymentId === DEP_NHARIRA) {
    return [
      { weekStart: PREV_WEEK, scorecard: scorecardFor(deploymentId, PREV_WEEK) },
      { weekStart: SAMPLE_WEEK, scorecard: scorecardFor(deploymentId, SAMPLE_WEEK) },
    ];
  }
  if (deploymentId === DEP_CHIGONDA) {
    return [{ weekStart: SAMPLE_WEEK, scorecard: scorecardFor(deploymentId, SAMPLE_WEEK) }];
  }
  return [];
}

export function mockFetch(input: string, init?: RequestInit): Promise<Response> {
  const url = new URL(input, 'http://dashboard.local');
  const method = (init?.method ?? 'GET').toUpperCase();
  const path = url.pathname.replace(/\/$/, '') || '/';

  if (path === '/api/v1/health' && method === 'GET') {
    return Promise.resolve(json({
      ok: true,
      schema: API_SCHEMA,
      version: '1.0',
      commit: 'mock0000000000000000000000000000000000000',
    }));
  }

  if (path === '/api/v1/session' && method === 'GET') {
    const user = sessionUser(readCookie());
    return Promise.resolve(json({
      schema: API_SCHEMA,
      authenticated: Boolean(user),
      user,
    }));
  }

  if (path === '/api/v1/session' && method === 'POST') {
    const body = parseBody<{ username?: string; password?: string }>(init);
    if (!body?.username || !body.password) {
      return Promise.resolve(error(400, 'validation', 'Username and password are required.'));
    }
    if (!isMockOperator(body.username) || operatorPasswords[body.username] !== body.password) {
      return Promise.resolve(error(401, 'unauthorized', 'Unknown operator or wrong password'));
    }
    setSessionCookie(`op-${body.username}`);
    return Promise.resolve(json({
      schema: API_SCHEMA,
      authenticated: true,
      user: { username: body.username, role: 'operator' },
    }));
  }

  if (path === '/api/v1/session' && method === 'DELETE') {
    clearSessionCookie();
    return Promise.resolve(json({
      schema: API_SCHEMA,
      authenticated: false,
      user: null,
    }));
  }

  const auth = requireAuth();
  if (auth instanceof Response) return Promise.resolve(auth);

  if (path === '/api/v1/session/password' && method === 'PUT') {
    const body = parseBody<{ currentPassword?: string; newPassword?: string }>(init);
    const current = body?.currentPassword ?? '';
    const next = body?.newPassword ?? '';
    if (!isMockOperator(auth.username) || operatorPasswords[auth.username] !== current) {
      return Promise.resolve(error(401, 'unauthorized', 'Unknown operator or wrong password'));
    }
    if (!next || next.length < 8) {
      return Promise.resolve(error(400, 'validation', 'New password must be at least 8 characters'));
    }
    operatorPasswords[auth.username] = next;
    return Promise.resolve(json({
      schema: API_SCHEMA,
      authenticated: true,
      user: { username: auth.username, role: 'operator' },
    }));
  }

  if (path === '/api/v1/meta' && method === 'GET') {
    return Promise.resolve(json({
      ...meta,
      thresholdsConfigured: true,
      thresholds: cloneThresholds(currentThresholds),
    }));
  }

  if (path === '/api/v1/settings/thresholds' && method === 'GET') {
    return Promise.resolve(json(thresholdsPayload()));
  }

  if (path === '/api/v1/settings/thresholds' && method === 'PUT') {
    const body = parseBody<PutThresholdsRequest>(init);
    if (!body) {
      return Promise.resolve(json({ error: 'Request body is required.', field: 'thresholds' }, 400));
    }
    if (body.reset) {
      currentThresholds = cloneThresholds(DEFAULT_THRESHOLDS);
      thresholdsUpdatedAt = '2026-11-11T09:42:00+01:00';
      thresholdsUpdatedBy = auth.username;
      return Promise.resolve(json(thresholdsPayload()));
    }
    if (!body.thresholds || typeof body.thresholds !== 'object') {
      return Promise.resolve(json({ error: 'thresholds is required unless reset is true.', field: 'thresholds' }, 400));
    }
    const failure = validateThresholdPatch(body.thresholds);
    if (failure) {
      return Promise.resolve(json(failure, 400));
    }
    currentThresholds = mergeThresholds(currentThresholds, body.thresholds);
    thresholdsUpdatedAt = '2026-11-11T09:42:00+01:00';
    thresholdsUpdatedBy = auth.username;
    return Promise.resolve(json(thresholdsPayload()));
  }

  if (path === '/api/v1/kits' && method === 'GET') {
    return Promise.resolve(json({ schema: API_SCHEMA, kits }));
  }

  if (path === '/api/v1/weeks' && method === 'GET') {
    return Promise.resolve(json({
      schema: API_SCHEMA,
      weeks: [SAMPLE_WEEK, PREV_WEEK],
      currentWeekStart: SAMPLE_WEEK,
      todayWeekStart: SAMPLE_WEEK,
      currentWeekHasData: true,
    }));
  }

  const overview = /^\/api\/v1\/weeks\/(\d{4}-\d{2}-\d{2})\/overview$/.exec(path);
  if (overview && method === 'GET') {
    const weekStart = overview[1];
    if (!isMonday(weekStart)) {
      return Promise.resolve(error(400, 'validation', 'weekStart must be a Monday (YYYY-MM-DD).'));
    }
    return Promise.resolve(json(overviewFor(weekStart)));
  }

  const school = /^\/api\/v1\/weeks\/(\d{4}-\d{2}-\d{2})\/schools\/([^/]+)$/.exec(path);
  if (school && method === 'GET') {
    const weekStart = school[1];
    const deploymentId = school[2];
    if (!isMonday(weekStart)) {
      return Promise.resolve(error(400, 'validation', 'weekStart must be a Monday (YYYY-MM-DD).'));
    }
    const card = cardFor(deploymentId, weekStart) ?? cardFor(deploymentId, SAMPLE_WEEK);
    if (!card) return Promise.resolve(error(404, 'not_found', 'Unknown deployment.'));
    return Promise.resolve(json({
      schema: API_SCHEMA,
      weekStart,
      weekEnd: fridayOf(weekStart),
      deploymentId,
      school: card.school,
      engine: card.engine,
      lastPulled: card.lastPulled,
      stale: card.stale,
      dataFrom: card.dataFrom,
      hasUsageData: card.hasUsageData,
      monitoringEnabled: deploymentId !== 'dep-kind-panda',
      unused: card.unused === true,
      thresholdsConfigured: true,
      sampleData: true,
      clockTrusted: clockTrustedFor(deploymentId, weekStart),
      timezone: HARARE,
      scorecard: scorecardFor(deploymentId, weekStart),
      census: censusFor(deploymentId, weekStart),
      presence: {
        timezone: HARARE,
        segments: segmentsFor(deploymentId, weekStart),
        summary: presenceSummary(deploymentId, weekStart),
      },
    }));
  }

  const nested = /^\/api\/v1\/weeks\/(\d{4}-\d{2}-\d{2})\/schools\/([^/]+)\/(presence|uplink|kolibri|nextcloud|kiwix|instances)$/.exec(path);
  if (nested && method === 'GET') {
    const weekStart = nested[1];
    const deploymentId = nested[2];
    const kind = nested[3];
    if (!isMonday(weekStart)) {
      return Promise.resolve(error(400, 'validation', 'weekStart must be a Monday (YYYY-MM-DD).'));
    }
    const card = cardFor(deploymentId, weekStart) ?? cardFor(deploymentId, SAMPLE_WEEK);
    if (!card) return Promise.resolve(error(404, 'not_found', 'Unknown deployment.'));
    if (kind === 'presence') {
      return Promise.resolve(json({
        schema: API_SCHEMA,
        deploymentId,
        weekStart,
        timezone: HARARE,
        segments: segmentsFor(deploymentId, weekStart),
        days: [],
      }));
    }
    if (kind === 'uplink') {
      const uplink = uplinkFor(deploymentId, weekStart);
      return Promise.resolve(json({
        schema: API_SCHEMA,
        deploymentId,
        weekStart,
        timezone: HARARE,
        measured: uplink.measured,
        samples: uplink.samples,
        transitions: uplink.transitions,
      }));
    }
    if (kind === 'kolibri') {
      const instances = kolibriFor(deploymentId, weekStart);
      return Promise.resolve(json({
        schema: API_SCHEMA,
        deploymentId,
        weekStart,
        clockTrusted: weekClockTrusted(instances),
        instances,
      }));
    }
    if (kind === 'nextcloud') {
      const instances = nextcloudFor(deploymentId, weekStart);
      return Promise.resolve(json({
        schema: API_SCHEMA,
        deploymentId,
        weekStart,
        clockTrusted: weekClockTrusted(instances),
        instances,
      }));
    }
    if (kind === 'kiwix') {
      const instances = kiwixFor(deploymentId, weekStart);
      return Promise.resolve(json({
        schema: API_SCHEMA,
        deploymentId,
        weekStart,
        clockTrusted: weekClockTrusted(instances),
        instances,
      }));
    }
    return Promise.resolve(json(instancesFor(deploymentId, weekStart)));
  }

  const help = /^\/api\/v1\/schools\/([^/]+)\/help-events$/.exec(path);
  if (help && method === 'GET') {
    const deploymentId = help[1];
    const known = [DEP_NHARIRA, DEP_CHIGONDA, 'dep-kind-panda'].includes(deploymentId);
    if (!known) return Promise.resolve(error(404, 'not_found', 'Unknown deployment.'));
    return Promise.resolve(json({
      schema: API_SCHEMA,
      deploymentId,
      events: helpStore.get(deploymentId) ?? [],
      weeklyTrend: defaultTrend(deploymentId),
    }));
  }

  if (help && method === 'POST') {
    const deploymentId = help[1];
    const known = [DEP_NHARIRA, DEP_CHIGONDA, 'dep-kind-panda'].includes(deploymentId);
    if (!known) return Promise.resolve(error(404, 'not_found', 'Unknown deployment.'));
    const body = parseBody<CreateHelpEventRequest>(init);
    if (!body?.offeredOn) {
      return Promise.resolve(error(400, 'validation', 'offeredOn is required.'));
    }
    const event: HelpEvent = {
      id: `help-${deploymentId}-${Date.now()}`,
      deploymentId,
      offeredOn: body.offeredOn,
      tutorialChapters: body.tutorialChapters ?? [],
      note: body.note ?? '',
      createdBy: auth.username,
      createdAt: '2026-11-10T13:45:00+01:00',
    };
    const list = helpStore.get(deploymentId) ?? [];
    list.push(event);
    helpStore.set(deploymentId, list);
    return Promise.resolve(json(event, 201));
  }

  return Promise.resolve(error(404, 'not_found', `No mock handler for ${method} ${path}`));
}

export function resetMockHelpEvents(): void {
  helpStore.clear();
}

export function resetMockThresholds(): void {
  currentThresholds = cloneThresholds(DEFAULT_THRESHOLDS);
  thresholdsUpdatedAt = null;
  thresholdsUpdatedBy = null;
}

export function resetMockOperators(): void {
  operatorPasswords = emptyOperatorPasswords();
}
