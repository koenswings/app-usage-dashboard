import { fireEvent, render, waitFor } from '@solidjs/testing-library';
import { SettingsPage } from '../src/pages/SettingsPage';
import { DEFAULT_THRESHOLDS, cloneThresholds, validateThresholdPatch } from '../src/config/thresholds';
import { mockFetch, resetMockThresholds } from '../src/mock/fetch';


describe('validateThresholdPatch', () => {
  it('rejects values outside the collector ranges', () => {
    expect(validateThresholdPatch({ learnerSessionShareMin: 1.2 })).toEqual({
      error: 'must be a number between 0 and 1',
      field: 'learnerSessionShareMin',
    });
    expect(validateThresholdPatch({ availableMinSchoolDays: -1 })).toEqual({
      error: 'must be an integer >= 0',
      field: 'availableMinSchoolDays',
    });
    expect(validateThresholdPatch({ availableMinSchoolDays: 6 })).toEqual({
      error: 'must be an integer <= 5',
      field: 'availableMinSchoolDays',
    });
    expect(validateThresholdPatch({ helpAfterAmberWeeks: 0 })).toEqual({
      error: 'must be an integer >= 1',
      field: 'helpAfterAmberWeeks',
    });
    expect(validateThresholdPatch({ unusedAfterHelpWeeks: 0 })?.field).toBe('unusedAfterHelpWeeks');
    expect(validateThresholdPatch({ wikipediaMinViews: 1.5 })?.field).toBe('wikipediaMinViews');
    expect(validateThresholdPatch({ wikipediaMinViews: 12 })).toBeNull();
    expect(validateThresholdPatch({ availableMinSchoolDays: 5, helpAfterAmberWeeks: 1 })).toBeNull();
  });
});

describe('Settings page', () => {
  const defaults = cloneThresholds(DEFAULT_THRESHOLDS);

  it('shows each threshold with its default and current value', () => {
    const { getByTestId } = render(() => (
      <SettingsPage
        week="2026-11-02"
        thresholds={{ ...defaults, wikipediaMinViews: 12 }}
        defaults={defaults}
        updatedAt={null}
        updatedBy={null}
        writable={true}
        onSave={async () => undefined}
        onReset={async () => undefined}
      />
    ));
    expect(getByTestId('settings-field-wikipediaMinViews').textContent).toMatch(/Default: 10/);
    expect((getByTestId('settings-field-wikipediaMinViews').querySelector('input') as HTMLInputElement).value).toBe('12');
    expect((getByTestId('settings-field-learnerSessionShareMin').querySelector('input') as HTMLInputElement).value).toBe('50');
    expect(getByTestId('settings-setup').textContent).toMatch(/yes\/no check/i);
    expect(getByTestId('settings-setup').textContent).toMatch(/beyond-seed/);
  });

  it('saves a valid edit and resets to defaults', async () => {
    const saved: unknown[] = [];
    let current = { ...defaults, wikipediaMinViews: 12 };
    const { getByTestId } = render(() => (
      <SettingsPage
        week="2026-11-02"
        thresholds={current}
        defaults={defaults}
        updatedAt={null}
        updatedBy={null}
        writable={true}
        onSave={async (thresholds) => {
          saved.push(thresholds);
          current = { ...current, ...thresholds };
          return { thresholds: current, defaults, updatedAt: '2026-11-11T09:42:00+01:00', updatedBy: 'admin' };
        }}
        onReset={async () => {
          saved.push({ reset: true });
          current = cloneThresholds(defaults);
          return { thresholds: current, defaults, updatedAt: '2026-11-11T09:42:00+01:00', updatedBy: 'admin' };
        }}
      />
    ));
    const views = getByTestId('settings-field-wikipediaMinViews').querySelector('input') as HTMLInputElement;
    fireEvent.input(views, { target: { value: '15' } });
    fireEvent.click(getByTestId('settings-save'));
    await waitFor(() => expect(saved[0]).toMatchObject({ wikipediaMinViews: 15, learnerSessionShareMin: 0.5 }));
    fireEvent.click(getByTestId('settings-reset'));
    await waitFor(() => expect(saved[1]).toEqual({ reset: true }));
    await waitFor(() =>
      expect((getByTestId('settings-field-wikipediaMinViews').querySelector('input') as HTMLInputElement).value).toBe('10'),
    );
  });

  it('rejects a share percent over 100 before calling save', async () => {
    let called = false;
    const { getByTestId } = render(() => (
      <SettingsPage
        week="2026-11-02"
        thresholds={defaults}
        defaults={defaults}
        updatedAt={null}
        updatedBy={null}
        writable={true}
        onSave={async () => {
          called = true;
        }}
        onReset={async () => undefined}
      />
    ));
    const share = getByTestId('settings-field-learnerSessionShareMin').querySelector('input') as HTMLInputElement;
    fireEvent.input(share, { target: { value: '150' } });
    fireEvent.submit(getByTestId('settings-form'));
    await waitFor(() => expect(getByTestId('settings-error').textContent).toMatch(/0 and 100/));
    expect(called).toBe(false);
  });

  it('shows a read-only note when the settings endpoint is missing', () => {
    const { getByTestId, queryByTestId } = render(() => (
      <SettingsPage
        week="2026-11-02"
        thresholds={defaults}
        defaults={defaults}
        updatedAt={null}
        updatedBy={null}
        writable={false}
        onSave={async () => undefined}
        onReset={async () => undefined}
      />
    ));
    expect(getByTestId('settings-readonly-note').textContent).toMatch(/collector update/);
    expect((getByTestId('settings-save') as HTMLButtonElement).disabled).toBe(true);
    expect((getByTestId('settings-reset') as HTMLButtonElement).disabled).toBe(true);
    expect(queryByTestId('settings-form')).toBeTruthy();
  });
});

describe('mock settings endpoint', () => {
  beforeEach(() => {
    resetMockThresholds();
    document.cookie = 'idea_usage_session=op-admin; Path=/';
  });
  afterEach(() => {
    resetMockThresholds();
    document.cookie = 'idea_usage_session=; Path=/; Max-Age=0';
  });

  it('saves a partial PUT and restores defaults on reset', async () => {
    const client = (await import('../src/api/client')).createApiClient(mockFetch);
    const first = await client.getThresholds();
    expect(first.thresholds).toEqual(DEFAULT_THRESHOLDS);
    expect(first.updatedAt).toBeNull();
    const saved = await client.putThresholds({ thresholds: { wikipediaMinViews: 25 } });
    expect(saved.thresholds.wikipediaMinViews).toBe(25);
    expect(saved.thresholds.availableMinSchoolDays).toBe(3);
    expect(saved.updatedBy).toBe('admin');
    try {
      await client.putThresholds({ thresholds: { learnerSessionShareMin: 2 } });
      throw new Error('expected 400');
    } catch (err) {
      expect((err as { status: number; field?: string }).status).toBe(400);
      expect((err as { field?: string }).field).toBe('learnerSessionShareMin');
    }
    const reset = await client.putThresholds({ reset: true });
    expect(reset.thresholds).toEqual(DEFAULT_THRESHOLDS);
  });
});

