import { For, Show } from 'solid-js';
import type { InstancesResponse } from '../api/types';
import { instanceKey } from '../api/types';
import { SchoolNav } from '../components/SchoolNav';
import { appDisplayName, copyKindLabel, hookStatusLabel } from '../lib/labels';

interface InstanceBreakdownProps {
  data: InstancesResponse;
  school: string;
}

export function InstanceBreakdown(props: InstanceBreakdownProps) {
  const ids = () => props.data.instances.map(instanceKey);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="instances" />
      <div class="wrap">
        <h2>{props.school} · Apps this week</h2>
        <p class="muted">
          Every copy stays on its own line, including Demo and extra copies,
          so two Kolibris are never added together.
        </p>
        <Show when={props.data.instances.length === 0}>
          <p>No data</p>
        </Show>
        <Show when={props.data.instances.length > 0}>
          <div class="table-wrap">
            <table data-testid="instance-table">
              <thead>
                <tr>
                  <th>App</th>
                  <th>Copy</th>
                  <th>Measurement</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                <For each={ids()}>
                  {(id) => {
                    const row = () => props.data.instances.find((item) => instanceKey(item) === id);
                    return (
                      <Show when={row()}>
                        {(item) => (
                          <tr data-testid={`instance-row-${instanceKey(item())}`}>
                            <td>{item().name || appDisplayName(item().app)}</td>
                            <td>{copyKindLabel(item().demo, item().listed)}</td>
                            <td>{hookStatusLabel(item().hookStatus, item().skipReason)}</td>
                            <td>{item().note || '—'}</td>
                          </tr>
                        )}
                      </Show>
                    );
                  }}
                </For>
              </tbody>
            </table>
          </div>
        </Show>
      </div>
    </>
  );
}
