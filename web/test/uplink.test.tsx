import { render } from '@solidjs/testing-library';
import { UplinkHistory } from '../src/pages/UplinkHistory';
import { mockFetch } from '../src/mock/fetch';
import { DEP_NHARIRA, HARARE, PREV_WEEK, SAMPLE_WEEK, uplinkFor } from '../src/mock/data';
import { API_SCHEMA } from '../src/api/types';
import type { UplinkResponse } from '../src/api/types';
import { UPLINK_NOT_MEASURED_MESSAGE } from '../src/lib/uplink';

const emptySegments = [
  {
    state: 'gapUnknown' as const,
    start: '2026-11-02T00:00:00+02:00',
    end: '2026-11-07T00:00:00+02:00',
    lengthKnown: false,
  },
];

function uplink(partial: Partial<UplinkResponse> = {}): UplinkResponse {
  return {
    schema: API_SCHEMA,
    deploymentId: DEP_NHARIRA,
    weekStart: SAMPLE_WEEK,
    timezone: HARARE,
    samples: [],
    transitions: [],
    ...partial,
  };
}

describe('Reachability when uplink is not measured', () => {
  it('shows a clear empty state instead of No data on transitions and samples', () => {
    const { getByTestId, queryByText, container } = render(() => (
      <UplinkHistory
        data={uplink({ measured: false })}
        school="Nharira"
        segments={emptySegments}
      />
    ));
    expect(getByTestId('uplink-not-measured').textContent).toBe(UPLINK_NOT_MEASURED_MESSAGE);
    expect(container.textContent).not.toMatch(/sidecar/i);
    expect(queryByText('No data')).toBeNull();
    expect(queryByText('When reachability changed')).toBeNull();
    expect(queryByText('Reachability samples')).toBeNull();
  });

  it('keeps No data when measured is omitted and the lists are empty (older collectors)', () => {
    const { queryByTestId, getAllByText, getByText } = render(() => (
      <UplinkHistory data={uplink()} school="Nharira" segments={emptySegments} />
    ));
    expect(queryByTestId('uplink-not-measured')).toBeNull();
    expect(getByText('When reachability changed')).toBeTruthy();
    expect(getAllByText('No data').length).toBe(2);
  });

  it('still lists samples when measured is true', () => {
    const sampleWeek = uplinkFor(DEP_NHARIRA, SAMPLE_WEEK);
    const { queryByTestId, getByText, queryByText } = render(() => (
      <UplinkHistory
        data={uplink({ measured: true, samples: sampleWeek.samples, transitions: sampleWeek.transitions })}
        school="Nharira"
        segments={emptySegments}
      />
    ));
    expect(queryByTestId('uplink-not-measured')).toBeNull();
    expect(getByText('When reachability changed')).toBeTruthy();
    expect(queryByText(UPLINK_NOT_MEASURED_MESSAGE)).toBeNull();
  });
});

describe('mock uplink measured case', () => {
  async function login() {
    const res = await mockFetch('/api/v1/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'mock-operator' }),
    });
    expect(res.status).toBe(200);
  }

  it('serves measured:false with empty lists on the previous week', async () => {
    await login();
    const res = await mockFetch(`/api/v1/weeks/${PREV_WEEK}/schools/${DEP_NHARIRA}/uplink`, { method: 'GET' });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.measured).toBe(false);
    expect(body.samples).toEqual([]);
    expect(body.transitions).toEqual([]);
  });

  it('serves measured:true with samples on the sample week', async () => {
    await login();
    const res = await mockFetch(`/api/v1/weeks/${SAMPLE_WEEK}/schools/${DEP_NHARIRA}/uplink`, { method: 'GET' });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.measured).toBe(true);
    expect(body.samples.length).toBeGreaterThan(0);
    expect(body.transitions.length).toBeGreaterThan(0);
  });
});
