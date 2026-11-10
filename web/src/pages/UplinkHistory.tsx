import { For, Show } from 'solid-js';
import type { PresenceSegment, UplinkResponse } from '../api/types';
import { SketchNote } from '../components/Header';
import { PresenceStrip } from '../components/shared/PresenceStrip';
import { SchoolNav } from '../components/SchoolNav';

interface UplinkHistoryProps {
  data: UplinkResponse;
  school: string;
  segments: PresenceSegment[];
}

export function UplinkHistory(props: UplinkHistoryProps) {
  const sampleIds = () => props.data.samples.map((sample) => `${sample.timestamp}|${sample.engine}`);
  const transitionIds = () => props.data.transitions.map((item) => `${item.timestamp}|${item.fromState}|${item.toState}`);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="uplink" />
      <div class="wrap">
        <SketchNote />
        <h2>{props.school} · Uplink history</h2>
        <p class="muted">
          Tailscale reachability from idea, next to the power sampler. Uplink down is not the
          same as powered off.
        </p>
        <div class="panel" style={{ 'margin-bottom': '14px' }}>
          <PresenceStrip
            segments={props.segments}
            timeZone={props.data.timezone.timeZone}
            utcOffset={props.data.timezone.utcOffset}
            timeZoneLabel={props.data.timezone.label}
            weekStart={props.data.weekStart}
            weekEnd={props.data.weekStart}
            summary="Power sampler (kit-local). Compare with the uplink table below."
          />
        </div>
        <div class="grid2">
          <section class="panel">
            <strong>Uplink transitions</strong>
            <Show when={props.data.transitions.length === 0}><p>No data</p></Show>
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>From</th>
                  <th>To</th>
                </tr>
              </thead>
              <tbody>
                <For each={transitionIds()}>
                  {(id) => {
                    const row = () => props.data.transitions.find((item) => `${item.timestamp}|${item.fromState}|${item.toState}` === id);
                    return (
                      <Show when={row()}>
                        {(item) => (
                          <tr>
                            <td>{item().timestamp}</td>
                            <td>{item().fromState}</td>
                            <td>{item().toState}</td>
                          </tr>
                        )}
                      </Show>
                    );
                  }}
                </For>
              </tbody>
            </table>
          </section>
          <section class="panel">
            <strong>Uplink samples</strong>
            <Show when={props.data.samples.length === 0}><p>No data</p></Show>
            <table>
              <thead>
                <tr>
                  <th>When</th>
                  <th>Online</th>
                  <th>Via</th>
                  <th class="right">Latency</th>
                </tr>
              </thead>
              <tbody>
                <For each={sampleIds()}>
                  {(id) => {
                    const row = () => props.data.samples.find((item) => `${item.timestamp}|${item.engine}` === id);
                    return (
                      <Show when={row()}>
                        {(item) => (
                          <tr>
                            <td>{item().timestamp}</td>
                            <td>{item().online ? 'online' : 'offline to us'}</td>
                            <td>{item().via ?? '—'}</td>
                            <td class="right">{item().latencyMs ?? '—'}</td>
                          </tr>
                        )}
                      </Show>
                    );
                  }}
                </For>
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </>
  );
}
