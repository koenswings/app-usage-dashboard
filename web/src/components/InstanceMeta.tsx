import { Show } from 'solid-js';
import type { ClockHonesty, HookStatus, SkipReason } from '../api/types';
import { copyKindLabel, hookStatusLabel, noDataReason } from '../lib/labels';

export function copyKindClass(demo: boolean, listed: boolean): string {
  if (demo) return 'tag tag--demo';
  if (!listed) return 'tag tag--extra';
  return 'tag';
}

export function ClockWeekWarning(props: { trusted: boolean }) {
  return (
    <Show when={!props.trusted}>
      <p class="clock-warning" data-testid="clock-warning">
        This week’s times may be untrustworthy — the kit clock was not synced
        on at least one day.
      </p>
    </Show>
  );
}

interface InstanceMetaProps {
  name: string;
  demo: boolean;
  listed: boolean;
  hookStatus: HookStatus;
  skipReason?: SkipReason;
  clock: ClockHonesty | null;
  collectedAt: string | null;
  showNoData?: boolean;
}

export function InstanceMeta(props: InstanceMetaProps) {
  return (
    <>
      <strong>{props.name}</strong>
      <div class="instance-meta">
        <span class={copyKindClass(props.demo, props.listed)}>
          {copyKindLabel(props.demo, props.listed)}
        </span>
        <span class="tag">{hookStatusLabel(props.hookStatus, props.skipReason)}</span>
      </div>
      <Show when={props.showNoData && props.hookStatus !== 'ok'}>
        <p data-testid="no-data-reason">
          {noDataReason(props.hookStatus, props.skipReason, props.collectedAt)}
        </p>
      </Show>
    </>
  );
}
