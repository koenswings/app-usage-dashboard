import { For, Show } from 'solid-js';
import type { PresenceSegment, UplinkResponse } from '../api/types';
import { PresenceStrip } from '../components/shared/PresenceStrip';
import { SchoolNav } from '../components/SchoolNav';
import { formatDateTime } from '../lib/format';
import { MONITORING_OFF_MESSAGE } from '../lib/monitoring';
import { fridayOf } from '../lib/week';

interface UplinkHistoryProps {
  data: UplinkResponse;
  school: string;
  segments: PresenceSegment[];
  monitoringEnabled?: boolean;
}

function reachableWord(online: boolean): string {
  return online ? 'Reachable' : 'Not reachable to us';
}

export function UplinkHistory(props: UplinkHistoryProps) {
  const zone = () => props.data.timezone.timeZone;
  const sampleIds = () => props.data.samples.map((sample) => `${sample.timestamp}|${sample.engine}`);
  const transitionIds = () => props.data.transitions.map((item) => `${item.timestamp}|${item.fromState}|${item.toState}`);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="uplink" />
      <div class="wrap">
        <h2>{props.school} · Reachability this week</h2>
        <p class="muted">
          Whether idea could reach the kit, next to the power sampler.
          Not reachable to us is not the same as powered off.
        </p>
        <Show when={props.monitoringEnabled === false}>
          <p class="status-banner" data-testid="monitoring-off-banner" role="status">
            {MONITORING_OFF_MESSAGE}
          </p>
        </Show>
        <div class="panel" style={{ 'margin-bottom': '14px' }}>
          <PresenceStrip
            segments={props.segments}
            timeZone={props.data.timezone.timeZone}
            utcOffset={props.data.timezone.utcOffset}
            timeZoneLabel={props.data.timezone.label}
            weekStart={props.data.weekStart}
            weekEnd={fridayOf(props.data.weekStart)}
            summary="Power sampler (kit-local). Compare with reachability below."
            monitoringOff={props.monitoringEnabled === false}
          />
        </div>
        <div class="grid2">
          <section class="panel">
            <strong>When reachability changed</strong>
            <Show when={props.data.transitions.length === 0}><p>No data</p></Show>
            <Show when={props.data.transitions.length > 0}>
              <div class="table-wrap">
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
                                <td>{formatDateTime(item().timestamp, zone())}</td>
                                <td>{reachableWord(item().fromState === 'online')}</td>
                                <td>{reachableWord(item().toState === 'online')}</td>
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
          </section>
          <section class="panel">
            <strong>Reachability samples</strong>
            <Show when={props.data.samples.length === 0}><p>No data</p></Show>
            <Show when={props.data.samples.length > 0}>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Status</th>
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
                                <td>{formatDateTime(item().timestamp, zone())}</td>
                                <td>{reachableWord(item().online)}</td>
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
          </section>
        </div>
      </div>
    </>
  );
}
