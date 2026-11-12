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
  skipReason?: SkipReason | null;
  clock: ClockHonesty | null;
  collectedAt: string | null;
  showNoData?: boolean;
  /** Short id shown next to the name when another copy on the page has the same name. */
  shortId?: string | null;
  /** Full instance id, used as the tooltip for the short id. */
  instanceId?: string;
}

export function InstanceShortId(props: { shortId?: string | null; instanceId?: string }) {
  return (
    <Show when={props.shortId}>
      {(id) => (
        <span class="instance-id" data-testid="instance-short-id" title={props.instanceId}>
          {' '}· {id()}
        </span>
      )}
    </Show>
  );
}

export function InstanceMeta(props: InstanceMetaProps) {
  return (
    <>
      <strong>
        {props.name}
        <InstanceShortId shortId={props.shortId} instanceId={props.instanceId} />
      </strong>
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
