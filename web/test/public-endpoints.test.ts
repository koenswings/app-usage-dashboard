import { mockFetch } from '../src/mock/fetch';

describe('public collector endpoints', () => {
  it('serves health without a session cookie', async () => {
    const res = await mockFetch('/api/v1/health', { method: 'GET' });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, schema: 'idea-usage-api/1' });
  });

  it('returns authenticated:false on GET /session without a cookie, not an error', async () => {
    const res = await mockFetch('/api/v1/session', { method: 'GET' });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.authenticated).toBe(false);
    expect(body.user).toBeNull();
  });
});
