import { For, Show, createSignal } from 'solid-js';
import type { ScorecardThresholds, ThresholdsSettingsResponse } from '../api/types';
import { FleetNav } from '../components/SchoolNav';
import {
  SETUP_RULE_MEANING,
  THRESHOLD_FIELDS,
  cloneThresholds,
  validateThresholdPatch,
  type ThresholdKey,
} from '../config/thresholds';

interface SettingsPageProps {
  week: string;
  thresholds: ScorecardThresholds;
  defaults: ScorecardThresholds;
  updatedAt: string | null;
  updatedBy: string | null;
  writable: boolean;
  onSave: (thresholds: Partial<ScorecardThresholds>) => Promise<ThresholdsSettingsResponse | void>;
  onReset: () => Promise<ThresholdsSettingsResponse | void>;
}

function shareToPercent(share: number): string {
  return String(Math.round(share * 1000) / 10);
}

function parseInteger(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === '') return null;
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

function parsePercent(raw: string): number | null {
  const trimmed = raw.trim().replace(/%$/, '');
  if (trimmed === '') return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  return value;
}

export function SettingsPage(props: SettingsPageProps) {
  const [draft, setDraft] = createSignal(cloneThresholds(props.thresholds));
  const [shareInput, setShareInput] = createSignal(shareToPercent(props.thresholds.learnerSessionShareMin));
  const [error, setError] = createSignal('');
  const [fieldError, setFieldError] = createSignal<string>('');
  const [saving, setSaving] = createSignal(false);
  const [message, setMessage] = createSignal('');

  const syncFrom = (thresholds: ScorecardThresholds) => {
    setDraft(cloneThresholds(thresholds));
    setShareInput(shareToPercent(thresholds.learnerSessionShareMin));
  };

  const fieldIds = () => THRESHOLD_FIELDS.map((field) => field.id);

  const setInt = (id: ThresholdKey, raw: string) => {
    const parsed = parseInteger(raw);
    if (parsed === null) return;
    setDraft((current) => ({ ...current, [id]: parsed }));
  };

  const validateDraft = (): { error: string; field: string } | null => {
    const percent = parsePercent(shareInput());
    if (percent === null || percent < 0 || percent > 100) {
      return { error: 'Learner session share must be a percentage between 0 and 100.', field: 'learnerSessionShareMin' };
    }
    return validateThresholdPatch({ ...draft(), learnerSessionShareMin: percent / 100 });
  };

  const save = async (event: Event) => {
    event.preventDefault();
    if (!props.writable) return;
    setError('');
    setFieldError('');
    setMessage('');
    const failure = validateDraft();
    if (failure) {
      setError(failure.error);
      setFieldError(failure.field);
      return;
    }
    const percent = parsePercent(shareInput()) ?? 0;
    const next = { ...draft(), learnerSessionShareMin: percent / 100 };
    setSaving(true);
    try {
      const result = await props.onSave(next);
      if (result?.thresholds) syncFrom(result.thresholds);
      setMessage('Saved.');
    } catch (err) {
      const field = err && typeof err === 'object' && 'field' in err ? String((err as { field?: string }).field ?? '') : '';
      setFieldError(field);
      setError(err instanceof Error ? err.message : 'Could not save the thresholds.');
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!props.writable) return;
    setError('');
    setFieldError('');
    setMessage('');
    setSaving(true);
    try {
      const result = await props.onReset();
      if (result?.thresholds) syncFrom(result.thresholds);
      else syncFrom(props.defaults);
      setMessage('Reset to defaults.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reset the thresholds.');
    } finally {
      setSaving(false);
    }
  };

  const defaultLabel = (id: ThresholdKey) => {
    const value = props.defaults[id];
    const field = THRESHOLD_FIELDS.find((item) => item.id === id);
    if (field?.kind === 'share') return `${Math.round(value * 100)}%`;
    return String(value);
  };

  return (
    <>
      <FleetNav week={props.week} current="settings" />
      <div class="wrap">
        <h2>Scorecard thresholds</h2>
        <p class="muted">
          These are the starting U-7 cut-offs Koen approved. They grade each school week.
          Grey (no data) never counts as amber. Set up is a yes/no check and has no number.
        </p>
        <Show when={!props.writable}>
          <p class="status-banner" data-testid="settings-readonly-note" role="status">
            Changing these values needs a collector update. The settings endpoint is not
            available yet, so the defaults below are shown read-only.
          </p>
        </Show>
        <form class="panel settings-form" onSubmit={save} data-testid="settings-form">
          <div class="settings-setup" data-testid="settings-setup">
            <strong>Set up</strong>
            <p>{SETUP_RULE_MEANING}</p>
          </div>
          <For each={fieldIds()}>
            {(id) => {
              const field = () => THRESHOLD_FIELDS.find((item) => item.id === id);
              return (
                <Show when={field()}>
                  {(item) => (
                    <label class="settings-field" data-testid={`settings-field-${id}`}>
                      <span class="settings-field__copy">
                        <span class="settings-field__label">{item().label}</span>
                        <span class="settings-field__meaning">{item().meaning}</span>
                        <Show when={item().help}>
                          {(help) => <span class="settings-field__meaning">{help()}</span>}
                        </Show>
                        <span class="settings-field__default">Default: {defaultLabel(id)}</span>
                      </span>
                      <span class="settings-field__control">
                        <Show when={item().kind === 'share'} fallback={
                          <input
                            type="number"
                            min={item().min}
                            max={item().max}
                            step="1"
                            value={draft()[id]}
                            disabled={!props.writable}
                            aria-invalid={fieldError() === id}
                            onInput={(event) => setInt(id, event.currentTarget.value)}
                          />
                        }>
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="0.1"
                            value={shareInput()}
                            disabled={!props.writable}
                            aria-invalid={fieldError() === id}
                            aria-label={`${item().label} as a percentage`}
                            onInput={(event) => setShareInput(event.currentTarget.value)}
                          />
                        </Show>
                        <Show when={item().kind === 'share'}>
                          <span class="settings-field__unit">%</span>
                        </Show>
                      </span>
                    </label>
                  )}
                </Show>
              );
            }}
          </For>
          <Show when={props.updatedAt || props.updatedBy}>
            <p class="muted" data-testid="settings-updated">
              Last changed
              <Show when={props.updatedAt}>{(stamp) => ` at ${stamp()}`}</Show>
              <Show when={props.updatedBy}>{(name) => ` by ${name()}`}</Show>
              .
            </p>
          </Show>
          <p class="login-error" data-testid="settings-error">{error()}</p>
          <Show when={message()}>
            {(text) => <p class="settings-saved" data-testid="settings-saved">{text()}</p>}
          </Show>
          <div class="settings-actions">
            <button
              class="btn btn-primary"
              type="submit"
              disabled={!props.writable || saving()}
              data-testid="settings-save"
            >
              Save
            </button>
            <button
              class="btn"
              type="button"
              disabled={!props.writable || saving()}
              data-testid="settings-reset"
              onClick={() => void reset()}
            >
              Reset to defaults
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

