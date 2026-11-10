import { For, Show } from 'solid-js';
import type { InstancesResponse } from '../api/types';
import { SketchNote } from '../components/Header';
import { SchoolNav } from '../components/SchoolNav';

interface InstanceBreakdownProps {
  data: InstancesResponse;
  school: string;
}

export function InstanceBreakdown(props: InstanceBreakdownProps) {
  const ids = () => props.data.instances.map((item) => item.instanceId);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="instances" />
      <div class="wrap">
        <SketchNote />
        <h2>{props.school} · Instance breakdown</h2>
        <p class="muted">
          Every discovered container stays on its own line, including Demo instances and
          Engine-unlisted ones, so two Kolibris are never added together.
        </p>
        <Show when={props.data.instances.length === 0}>
          <p>No data</p>
        </Show>
        <table data-testid="instance-table">
          <thead>
            <tr>
              <th>Instance</th>
              <th>App</th>
              <th>Listed</th>
              <th>Demo</th>
              <th>Hook</th>
              <th>Port</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            <For each={ids()}>
              {(id) => {
                const row = () => props.data.instances.find((item) => item.instanceId === id);
                return (
                  <Show when={row()}>
                    {(item) => (
                      <tr data-testid={`instance-row-${item().instanceId}`}>
                        <td>{item().name} · {item().instanceId}</td>
                        <td>{item().app}</td>
                        <td>{item().listed ? 'listed' : 'unlisted'}</td>
                        <td>{item().demo ? 'Demo' : 'own'}</td>
                        <td>{item().hookStatus}</td>
                        <td>{item().port ?? '—'}</td>
                        <td>{item().note}</td>
                      </tr>
                    )}
                  </Show>
                );
              }}
            </For>
          </tbody>
        </table>
      </div>
    </>
  );
}
