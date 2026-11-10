import { For, Show } from 'solid-js';
import type { KolibriInstanceWeek, KolibriWeekResponse } from '../api/types';
import { SchoolNav } from '../components/SchoolNav';
import { formatCount } from '../lib/format';

interface KolibriPageProps {
  data: KolibriWeekResponse;
  school: string;
}

function contentId(row: KolibriInstanceWeek['content'][number]): string {
  return `${row.channel}|${row.title}|${row.role}`;
}

function InstancePanel(props: { instance: KolibriInstanceWeek }) {
  const roles = () => [
    { id: 'learner', label: 'Learners', activity: props.instance.signins.learner },
    { id: 'coach', label: 'Teachers / coaches', activity: props.instance.signins.coach },
    { id: 'admin', label: 'Admin', activity: props.instance.signins.admin },
    {
      id: 'guest',
      label: 'Guest (not signed in)',
      activity: {
        users: null,
        sessions: props.instance.guest.visits,
        minutes: Math.round(props.instance.guest.seconds / 60),
      },
    },
  ];
  const roleIds = () => roles().map((row) => row.id);
  const contentIds = () => props.instance.content.map(contentId);
  const teaching = () => props.instance.teaching;

  return (
    <section class="panel instance-block" data-testid={`kolibri-instance-${props.instance.instanceId}`}>
      <strong>{props.instance.name}</strong>
      <div style={{ 'margin-top': '8px' }}>
        <span class="tag">{props.instance.listed ? 'listed' : 'unlisted'} · {props.instance.instanceId}</span>
        <Show when={props.instance.demo}><span class="tag tag--demo">Demo</span></Show>
        <Show when={!props.instance.listed}><span class="tag tag--unlisted">Unlisted</span></Show>
      </div>
      <p class="muted">
        Teaching cycle: {teaching().lessonsCreated} lessons created, {teaching().lessonsVisible} visible,
        {' '}{teaching().quizzesCreated} quizzes created, {teaching().quizzesStarted} started,
        {' '}{teaching().quizzesEnded} ended.
      </p>
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
      <Show when={props.instance.content.length > 0}>
        <h3 style={{ 'font-size': '13px', 'margin-top': '16px' }}>Content this week</h3>
        <table>
          <thead>
            <tr>
              <th>Channel / title</th>
              <th>Role</th>
              <th class="right">Visits</th>
              <th class="right">Min</th>
              <th>Assigned</th>
            </tr>
          </thead>
          <tbody>
            <For each={contentIds()}>
              {(id) => {
                const row = () => props.instance.content.find((item) => contentId(item) === id);
                return (
                  <Show when={row()}>
                    {(item) => (
                      <tr>
                        <td>{item().channel} · {item().title}</td>
                        <td>{item().role}</td>
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
  const ids = () => props.data.instances.map((item) => item.instanceId);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="kolibri" />
      <div class="wrap">
        <h2>{props.school} · Kolibri this week</h2>
        <p class="muted">Each instance stays on its own line, including Demo and unlisted containers.</p>
        <Show when={props.data.instances.length === 0}>
          <p>No data</p>
        </Show>
        <For each={ids()}>
          {(id) => {
            const instance = () => props.data.instances.find((item) => item.instanceId === id);
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
