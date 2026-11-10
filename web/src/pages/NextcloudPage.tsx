import { For, Show } from 'solid-js';
import type { NextcloudInstanceWeek, NextcloudWeekResponse } from '../api/types';
import { SchoolNav } from '../components/SchoolNav';

interface NextcloudPageProps {
  data: NextcloudWeekResponse;
  school: string;
}

function InstancePanel(props: { instance: NextcloudInstanceWeek }) {
  const rows = () => [
    { id: 'accounts', label: 'Accounts', teachers: String(props.instance.setup.teachers), learners: String(props.instance.setup.learners) },
    { id: 'beyond', label: 'Beyond seeds', teachers: String(props.instance.setup.teachersBeyondSeeds), learners: String(props.instance.setup.learnersBeyondSeeds) },
    { id: 'logins', label: 'Logins this week', teachers: String(props.instance.logins.teachers), learners: String(props.instance.logins.learners) },
    { id: 'office', label: 'Office opens (word processor)', teachers: String(props.instance.office.opensTeachers), learners: String(props.instance.office.opensLearners) },
    { id: 'docs', label: 'Documents created / edited', teachers: String(props.instance.office.documentsCreatedOrEditedTeachers), learners: String(props.instance.office.documentsCreatedOrEditedLearners) },
    {
      id: 'workflows',
      label: 'Worksheet shares · File drops · School Files',
      teachers: `${props.instance.workflows.worksheetShares} · ${props.instance.workflows.fileDrops} · ${props.instance.workflows.schoolFilesShares}`,
      learners: `${props.instance.workflows.editShares} edit shares`,
    },
  ];
  const rowIds = () => rows().map((row) => row.id);
  const appIds = () => props.instance.appsOpened.map((app) => app.appId);

  return (
    <section class="panel instance-block" data-testid={`nextcloud-instance-${props.instance.instanceId}`}>
      <strong>{props.instance.name}</strong>
      <div style={{ 'margin-top': '8px' }}>
        <span class="tag">{props.instance.listed ? 'listed' : 'unlisted'} · {props.instance.instanceId}</span>
        <Show when={props.instance.demo}><span class="tag tag--demo">Demo</span></Show>
      </div>
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th class="right">Teachers</th>
            <th class="right">Learners</th>
          </tr>
        </thead>
        <tbody>
          <For each={rowIds()}>
            {(id) => {
              const row = () => rows().find((item) => item.id === id);
              return (
                <Show when={row()}>
                  {(item) => (
                    <tr>
                      <td>{item().label}</td>
                      <td class="right">{item().teachers}</td>
                      <td class="right">{item().learners}</td>
                    </tr>
                  )}
                </Show>
              );
            }}
          </For>
        </tbody>
      </table>
      <p class="muted">
        Word processor is Nextcloud Office (Collabora CODE). Apps opened:{' '}
        <For each={appIds()}>
          {(id) => {
            const app = () => props.instance.appsOpened.find((item) => item.appId === id);
            return <span>{app()?.appId} {app()?.opens}. </span>;
          }}
        </For>
      </p>
    </section>
  );
}

export function NextcloudPage(props: NextcloudPageProps) {
  const ids = () => props.data.instances.map((item) => item.instanceId);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="nextcloud" />
      <div class="wrap">
        <h2>{props.school} · Nextcloud this week</h2>
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
