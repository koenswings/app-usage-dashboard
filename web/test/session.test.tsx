import { fireEvent, render, waitFor } from '@solidjs/testing-library';
import { createApiClient } from '../src/api/client';
import { DEFAULT_THRESHOLDS, cloneThresholds } from '../src/config/thresholds';
import { mockFetch, resetMockOperators } from '../src/mock/fetch';
import { SettingsPage } from '../src/pages/SettingsPage';

const MOCK_PASSWORD = 'mock-operator';

function clearSessionCookie() {
  document.cookie = 'idea_usage_session=; Path=/; Max-Age=0';
}

function renderPasswordForm(
  onChangePassword: (currentPassword: string, newPassword: string) => Promise<void>,
) {
  const defaults = cloneThresholds(DEFAULT_THRESHOLDS);
  return render(() => (
    <SettingsPage
      week="2026-11-02"
      thresholds={defaults}
      defaults={defaults}
      updatedAt={null}
      updatedBy={null}
      writable={true}
      username="koen"
      onSave={async () => undefined}
      onReset={async () => undefined}
      onChangePassword={onChangePassword}
    />
  ));
}

function fillPasswords(
  getByTestId: (id: string) => HTMLElement,
  current: string,
  next: string,
  confirm: string,
) {
  fireEvent.input(getByTestId('password-current'), { target: { value: current } });
  fireEvent.input(getByTestId('password-new'), { target: { value: next } });
  fireEvent.input(getByTestId('password-confirm'), { target: { value: confirm } });
}

function expectFieldsCleared(getByTestId: (id: string) => HTMLElement) {
  expect((getByTestId('password-current') as HTMLInputElement).value).toBe('');
  expect((getByTestId('password-new') as HTMLInputElement).value).toBe('');
  expect((getByTestId('password-confirm') as HTMLInputElement).value).toBe('');
}

describe('mock operator login', () => {
  const client = createApiClient(mockFetch);

  beforeEach(() => {
    resetMockOperators();
    clearSessionCookie();
  });

  afterEach(() => {
    resetMockOperators();
    clearSessionCookie();
  });

  it('signs in as koen with the mock-only password', async () => {
    const session = await client.login('koen', MOCK_PASSWORD);
    expect(session.authenticated).toBe(true);
    expect(session.user?.username).toBe('koen');
    expect(session.user?.role).toBe('operator');
    const current = await client.getSession();
    expect(current.user?.username).toBe('koen');
  });
});

describe('change-password form', () => {
  const client = createApiClient(mockFetch);

  beforeEach(() => {
    resetMockOperators();
    document.cookie = 'idea_usage_session=op-koen; Path=/';
  });

  afterEach(() => {
    resetMockOperators();
    clearSessionCookie();
  });

  it('validates length, mismatch, and a new password that matches the current one', async () => {
    const called: Array<[string, string]> = [];
    const { getByTestId } = renderPasswordForm(async (current, next) => {
      called.push([current, next]);
    });

    fillPasswords(getByTestId, MOCK_PASSWORD, 'short', 'short');
    fireEvent.submit(getByTestId('change-password-form'));
    expect(getByTestId('password-error').textContent).toMatch(/at least 8 characters/);
    expectFieldsCleared(getByTestId);
    expect(called).toEqual([]);

    fillPasswords(getByTestId, MOCK_PASSWORD, MOCK_PASSWORD, MOCK_PASSWORD);
    fireEvent.submit(getByTestId('change-password-form'));
    expect(getByTestId('password-error').textContent).toMatch(/different from the current password/);
    expectFieldsCleared(getByTestId);
    expect(called).toEqual([]);

    fillPasswords(getByTestId, MOCK_PASSWORD, 'mock-operator-2', 'mock-operator-3');
    fireEvent.submit(getByTestId('change-password-form'));
    expect(getByTestId('password-error').textContent).toMatch(/confirmation do not match/);
    expectFieldsCleared(getByTestId);
    expect(called).toEqual([]);
  });

  it('changes the password and then signs in with the new one', async () => {
    const { getByTestId, queryByTestId } = renderPasswordForm(async (current, next) => {
      await client.changePassword(current, next);
    });

    fillPasswords(getByTestId, MOCK_PASSWORD, 'mock-operator-2', 'mock-operator-2');
    fireEvent.submit(getByTestId('change-password-form'));
    await waitFor(() => {
      expect(getByTestId('password-saved').textContent).toMatch(/Password changed/);
    });
    expect(queryByTestId('password-error')?.textContent).toBe('');
    expectFieldsCleared(getByTestId);

    await client.logout();
    await expect(client.login('koen', MOCK_PASSWORD)).rejects.toMatchObject({ status: 401 });
    const session = await client.login('koen', 'mock-operator-2');
    expect(session.user?.username).toBe('koen');
  });

  it('shows the API error when the current password is wrong', async () => {
    const { getByTestId, queryByTestId } = renderPasswordForm(async (current, next) => {
      await client.changePassword(current, next);
    });

    fillPasswords(getByTestId, 'wrong-current-password', 'mock-operator-2', 'mock-operator-2');
    fireEvent.submit(getByTestId('change-password-form'));
    await waitFor(() => {
      expect(getByTestId('password-error').textContent).toMatch(/Unknown operator or wrong password/);
    });
    expect(queryByTestId('password-saved')).toBeNull();
    expectFieldsCleared(getByTestId);
  });
});
