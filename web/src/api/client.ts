import { mockFetch } from '../mock/fetch';
import type {
  CreateHelpEventRequest,
  ErrorBody,
  HelpEvent,
  HelpEventsResponse,
  InstancesResponse,
  IsoDate,
  KitsResponse,
  KiwixWeekResponse,
  KolibriWeekResponse,
  MetaResponse,
  NextcloudWeekResponse,
  OverviewResponse,
  PresenceResponse,
  SchoolWeekResponse,
  SessionResponse,
  UplinkResponse,
  WeeksResponse,
} from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorBody | undefined;

  constructor(status: number, body?: ErrorBody) {
    super(body?.error.message ?? `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

function defaultFetch(input: string, init?: RequestInit): Promise<Response> {
  const options: RequestInit = {
    ...init,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {}),
    },
  };
  if (import.meta.env.VITE_MOCK === '1') {
    return mockFetch(input, options);
  }
  const base = import.meta.env.VITE_API_BASE ?? '';
  return fetch(`${base}${input}`, options);
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let body: ErrorBody | undefined;
    try {
      body = (await res.json()) as ErrorBody;
    } catch {
      body = undefined;
    }
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

export function createApiClient(fetcher: FetchLike = defaultFetch) {
  return {
    async getSession(): Promise<SessionResponse> {
      return readJson<SessionResponse>(await fetcher('/api/v1/session', { method: 'GET' }));
    },

    async login(username: string, password: string): Promise<SessionResponse> {
      return readJson<SessionResponse>(
        await fetcher('/api/v1/session', {
          method: 'POST',
          body: JSON.stringify({ username, password }),
        }),
      );
    },

    async logout(): Promise<SessionResponse> {
      return readJson<SessionResponse>(await fetcher('/api/v1/session', { method: 'DELETE' }));
    },

    async getMeta(): Promise<MetaResponse> {
      return readJson<MetaResponse>(await fetcher('/api/v1/meta', { method: 'GET' }));
    },

    async getKits(): Promise<KitsResponse> {
      return readJson<KitsResponse>(await fetcher('/api/v1/kits', { method: 'GET' }));
    },

    async getWeeks(): Promise<WeeksResponse> {
      return readJson<WeeksResponse>(await fetcher('/api/v1/weeks', { method: 'GET' }));
    },

    async getOverview(weekStart: IsoDate): Promise<OverviewResponse> {
      return readJson<OverviewResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/overview`, { method: 'GET' }),
      );
    },

    async getSchoolWeek(weekStart: IsoDate, deploymentId: string): Promise<SchoolWeekResponse> {
      return readJson<SchoolWeekResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/schools/${deploymentId}`, { method: 'GET' }),
      );
    },

    async getPresence(weekStart: IsoDate, deploymentId: string): Promise<PresenceResponse> {
      return readJson<PresenceResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/schools/${deploymentId}/presence`, { method: 'GET' }),
      );
    },

    async getUplink(weekStart: IsoDate, deploymentId: string): Promise<UplinkResponse> {
      return readJson<UplinkResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/schools/${deploymentId}/uplink`, { method: 'GET' }),
      );
    },

    async getKolibri(weekStart: IsoDate, deploymentId: string): Promise<KolibriWeekResponse> {
      return readJson<KolibriWeekResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/schools/${deploymentId}/kolibri`, { method: 'GET' }),
      );
    },

    async getNextcloud(weekStart: IsoDate, deploymentId: string): Promise<NextcloudWeekResponse> {
      return readJson<NextcloudWeekResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/schools/${deploymentId}/nextcloud`, { method: 'GET' }),
      );
    },

    async getKiwix(weekStart: IsoDate, deploymentId: string): Promise<KiwixWeekResponse> {
      return readJson<KiwixWeekResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/schools/${deploymentId}/kiwix`, { method: 'GET' }),
      );
    },

    async getInstances(weekStart: IsoDate, deploymentId: string): Promise<InstancesResponse> {
      return readJson<InstancesResponse>(
        await fetcher(`/api/v1/weeks/${weekStart}/schools/${deploymentId}/instances`, { method: 'GET' }),
      );
    },

    async getHelpEvents(deploymentId: string): Promise<HelpEventsResponse> {
      return readJson<HelpEventsResponse>(
        await fetcher(`/api/v1/schools/${deploymentId}/help-events`, { method: 'GET' }),
      );
    },

    async createHelpEvent(deploymentId: string, body: CreateHelpEventRequest): Promise<HelpEvent> {
      return readJson<HelpEvent>(
        await fetcher(`/api/v1/schools/${deploymentId}/help-events`, {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      );
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

export const api = createApiClient();
