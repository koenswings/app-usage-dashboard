import { createApiClient } from '../src/api/client';

describe('API client methods', () => {
  it('uses GET for reads and writes only for help events, session auth and settings', async () => {
    const calls: Array<{ method: string; url: string }> = [];
    const fetcher = async (url: string, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      calls.push({ method, url });
      const isHelpPost = url.includes('/help-events') && method === 'POST';
      return new Response(
        JSON.stringify(
          isHelpPost
            ? {
                id: 'help-1',
                deploymentId: 'dep-nharira',
                offeredOn: '2026-11-06',
                tutorialChapters: ['4'],
                note: 'followed up',
                createdBy: 'koen',
                createdAt: '2026-11-10T13:45:00+01:00',
              }
            : { schema: 'idea-usage-api/1', ok: true },
        ),
        { status: isHelpPost ? 201 : 200, headers: { 'Content-Type': 'application/json' } },
      );
    };

    const client = createApiClient(fetcher);
    await client.getHealth();
    await client.getSession();
    await client.getMeta();
    await client.getKits();
    await client.getWeeks();
    await client.getOverview('2026-11-02');
    await client.getSchoolWeek('2026-11-02', 'dep-nharira');
    await client.getPresence('2026-11-02', 'dep-nharira');
    await client.getUplink('2026-11-02', 'dep-nharira');
    await client.getKolibri('2026-11-02', 'dep-nharira');
    await client.getNextcloud('2026-11-02', 'dep-nharira');
    await client.getKiwix('2026-11-02', 'dep-nharira');
    await client.getInstances('2026-11-02', 'dep-nharira');
    await client.getHelpEvents('dep-nharira');
    await client.login('koen', 'mock-operator');
    await client.changePassword('mock-operator', 'mock-operator-2');
    await client.logout();
    await client.getThresholds();
    await client.putThresholds({ thresholds: { wikipediaMinViews: 12 } });
    await client.createHelpEvent('dep-nharira', {
      offeredOn: '2026-11-06',
      tutorialChapters: ['4'],
      note: 'followed up',
    });

    const dataWrites = calls.filter(
      (call) => call.method !== 'GET' && !call.url.endsWith('/api/v1/session'),
    );
    expect(dataWrites).toEqual([
      { method: 'PUT', url: '/api/v1/session/password' },
      { method: 'PUT', url: '/api/v1/settings/thresholds' },
      { method: 'POST', url: '/api/v1/schools/dep-nharira/help-events' },
    ]);
    expect(calls.filter((call) => call.url.endsWith('/api/v1/session')).map((call) => call.method).sort()).toEqual([
      'DELETE',
      'GET',
      'POST',
    ]);
  });
});
