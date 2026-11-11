import { For, Show } from 'solid-js';
import type { KolibriContentRow, KolibriInstanceWeek, KolibriWeekResponse } from '../api/types';
import { instanceKey } from '../api/types';
import { ClockWeekWarning, InstanceMeta } from '../components/InstanceMeta';
import { SchoolNav } from '../components/SchoolNav';
import { formatCount, formatUnit } from '../lib/format';
import { roleLabel } from '../lib/labels';

interface KolibriPageProps {
  data: KolibriWeekResponse;
  school: string;
}

function contentId(row: KolibriContentRow): string {
  return `${row.channel}|${row.title}|${row.role}`;
}

function InstancePanel(props: { instance: KolibriInstanceWeek }) {
  const signins = () => props.instance.signins;
  const guest = () => props.instance.guest;
  const teaching = () => props.instance.teaching;
  const content = () => props.instance.content ?? [];
  const roles = () => {
    const activity = signins();
    const guestRow = guest();
    if (!activity || !guestRow) return [];
    return [
      { id: 'learner', label: 'Learners', activity: activity.learner },
      { id: 'coach', label: 'Teachers', activity: activity.coach },
      { id: 'admin', label: 'Admin', activity: activity.admin },
      {
        id: 'guest',
        label: 'Guest (not signed in)',
        activity: {
          users: null,
          sessions: guestRow.visits,
          minutes: Math.round(guestRow.seconds / 60),
        },
      },
    ];
  };
  const roleIds = () => roles().map((row) => row.id);
  const contentIds = () => content().map(contentId);
  const hasPayload = () =>
    props.instance.hookStatus === 'ok' && signins() !== null && teaching() !== null;

  return (
    <section class="panel instance-block" data-testid={`kolibri-instance-${instanceKey(props.instance)}`}>
      <InstanceMeta
        name={props.instance.name}
        demo={props.instance.demo}
        listed={props.instance.listed}
        hookStatus={props.instance.hookStatus}
        skipReason={props.instance.skipReason}
        clock={props.instance.clock}
        collectedAt={props.instance.collectedAt}
        showNoData={!hasPayload()}
      />
      <Show when={hasPayload() && teaching()}>
        {(cycle) => (
          <p class="muted">
            Teaching cycle: {formatUnit(cycle().lessonsCreated, 'lesson created', 'lessons created')},
            {' '}{formatUnit(cycle().lessonsVisible, 'visible', 'visible')},
            {' '}{formatUnit(cycle().quizzesCreated, 'quiz created', 'quizzes created')},
            {' '}{formatUnit(cycle().quizzesStarted, 'started', 'started')},
            {' '}{formatUnit(cycle().quizzesEnded, 'ended', 'ended')}.
          </p>
        )}
      </Show>
      <Show when={hasPayload() && roles().length > 0}>
        <table>
          <thead>
            <tr>
              <th>Role</th>
              <th class="right">Accounts</th>
              <th class="right">Sessions</th>
              <th class="right">Minutes</th>
            </tr>
          </thead>
          <tbody>
            <For each={roleIds()}>
              {(id) => {
                const row = () => roles().find((item) => item.id === id);
                return (
                  <Show when={row()}>
                    {(item) => (
                      <tr>
                        <td>{item().label}</td>
                        <td class="right">{formatCount(item().activity.users)}</td>
                        <td class="right">{item().activity.sessions}</td>
                        <td class="right">{item().activity.minutes}</td>
                      </tr>
                    )}
                  </Show>
                );
              }}
            </For>
          </tbody>
        </table>
      </Show>
      <Show when={hasPayload() && content().length > 0}>
        <h3 class="section-heading">Content this week</h3>
        <table>
          <thead>
            <tr>
              <th>Channel / title</th>
              <th>Role</th>
              <th class="right">Visits</th>
              <th class="right">Minutes</th>
              <th>Assigned</th>
            </tr>
          </thead>
          <tbody>
            <For each={contentIds()}>
              {(id) => {
                const row = () => content().find((item) => contentId(item) === id);
                return (
                  <Show when={row()}>
                    {(item) => (
                      <tr>
                        <td>{item().channel} · {item().title}</td>
                        <td>{roleLabel(item().role)}</td>
                        <td class="right">{item().visits}</td>
                        <td class="right">{Math.round(item().seconds / 60)}</td>
                        <td>{item().assigned ? 'assigned' : 'free'}</td>
                      </tr>
                    )}
                  </Show>
                );
              }}
            </For>
          </tbody>
        </table>
      </Show>
    </section>
  );
}

export function KolibriPage(props: KolibriPageProps) {
  const ids = () => props.data.instances.map(instanceKey);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="kolibri" />
      <div class="wrap">
        <h2>{props.school} · Kolibri this week</h2>
        <p class="muted">Each copy stays on its own line, including Demo and extra copies.</p>
        <ClockWeekWarning trusted={props.data.clockTrusted} />
        <Show when={props.data.instances.length === 0}>
          <p>No data</p>
        </Show>
        <For each={ids()}>
          {(id) => {
            const instance = () => props.data.instances.find((item) => instanceKey(item) === id);
            return (
              <Show when={instance()}>
                {(item) => <InstancePanel instance={item()} />}
              </Show>
            );
          }}
        </For>
      </div>
    </>
  );
}
