import { For, Show } from 'solid-js';
import type { NextcloudInstanceWeek, NextcloudWeekResponse, RoleCount } from '../api/types';
import { instanceKey } from '../api/types';
import { ClockWeekWarning, InstanceMeta } from '../components/InstanceMeta';
import { SchoolNav } from '../components/SchoolNav';
import { shortIdsForDuplicateNames } from '../lib/instances';
import { formatCount, formatMinutes } from '../lib/format';
import { nextcloudAppName, roleLabel } from '../lib/labels';

interface NextcloudPageProps {
  data: NextcloudWeekResponse;
  school: string;
}

/** "No data" when the hook sent no apps object, "None recorded" when it sent an empty one. */
export function appsOpenedText(apps: Record<string, number> | null | undefined): string {
  if (apps === null || apps === undefined) return 'No data';
  const ids = Object.keys(apps);
  if (ids.length === 0) return 'None recorded';
  return ids.map((id) => `${nextcloudAppName(id)} ${formatCount(apps[id] ?? null)}`).join(' · ');
}

export function documentsCreatedText(value: number | null | undefined): string {
  return value === null || value === undefined ? 'No data' : formatCount(value);
}

export function documentsByGroupText(
  byGroup: { admin: number; teacher: number; learner: number } | null | undefined,
): string {
  if (!byGroup) return 'No data';
  return `${roleLabel('admin')} ${formatCount(byGroup.admin ?? null)} · ${roleLabel('teacher')} ${formatCount(byGroup.teacher ?? null)} · ${roleLabel('learner')} ${formatCount(byGroup.learner ?? null)}`;
}

function roleCountText(count: RoleCount): string {
  return `${formatCount(count.total)} total · ${formatCount(count.beyondSeed)} beyond seed`;
}

function InstancePanel(props: { instance: NextcloudInstanceWeek; shortId?: string | null }) {
  const setup = () => props.instance.setup;
  const logins = () => props.instance.logins;
  const office = () => props.instance.office;
  const workflows = () => props.instance.workflows;
  const otherGroupIds = () => Object.keys(setup()?.otherGroups ?? {});
  const hasPayload = () =>
    props.instance.hookStatus === 'ok' && setup() !== null && logins() !== null;
  const rows = () => {
    const accounts = setup();
    const signedIn = logins();
    const officeRow = office();
    const flow = workflows();
    if (!accounts || !signedIn) return [];
    const list: Array<{ id: string; label: string; value: string }> = [
      { id: 'setup-admin', label: `Accounts · ${roleLabel('admin')}`, value: roleCountText(accounts.admin) },
      { id: 'setup-teacher', label: `Accounts · ${roleLabel('teacher')}`, value: roleCountText(accounts.teacher) },
      { id: 'setup-learner', label: `Accounts · ${roleLabel('learner')}`, value: roleCountText(accounts.learner) },
      { id: 'logins-admin', label: `Logins this week · ${roleLabel('admin')}`, value: roleCountText(signedIn.admin) },
      { id: 'logins-teacher', label: `Logins this week · ${roleLabel('teacher')}`, value: roleCountText(signedIn.teacher) },
      { id: 'logins-learner', label: `Logins this week · ${roleLabel('learner')}`, value: roleCountText(signedIn.learner) },
    ];
    if (officeRow) {
      list.push(
        { id: 'office-opens', label: 'Office opens', value: formatCount(officeRow.opens) },
        { id: 'office-docs', label: 'Distinct documents (last ok day)', value: formatCount(officeRow.distinctDocuments) },
        { id: 'office-read', label: 'Office reads', value: formatCount(officeRow.read) },
        { id: 'office-edit', label: 'Office edits', value: formatCount(officeRow.edit) },
        {
          id: 'office-minutes',
          label: 'Estimated Office time',
          value: officeRow.estimatedMinutes === null ? '—' : formatMinutes(officeRow.estimatedMinutes),
        },
        {
          id: 'office-group',
          label: 'Office opens by role',
          value: `${roleLabel('admin')} ${formatCount(officeRow.byGroup.admin)} · ${roleLabel('teacher')} ${formatCount(officeRow.byGroup.teacher)} · ${roleLabel('learner')} ${formatCount(officeRow.byGroup.learner)}`,
        },
        {
          id: 'office-mime',
          label: 'Office by type',
          value: `Text ${formatCount(officeRow.mime.text)} · Spreadsheet ${formatCount(officeRow.mime.sheet)} · Slides ${formatCount(officeRow.mime.slides)}`,
        },
      );
    }
    list.push(
      { id: 'docs-created', label: 'Documents created', value: documentsCreatedText(props.instance.documentsCreated) },
      {
        id: 'docs-created-group',
        label: 'Documents created by role',
        value: documentsByGroupText(props.instance.documentsCreatedByGroup),
      },
      { id: 'apps-opened', label: 'Apps opened', value: appsOpenedText(props.instance.appsOpened) },
    );
    if (flow) {
      list.push({
        id: 'workflows',
        label: 'Sharing',
        value: `${formatCount(flow.worksheetShares)} worksheet shares · ${formatCount(flow.editShares)} edit shares · ${formatCount(flow.fileDropLinks)} file-drop links · ${formatCount(flow.fileDropUploads)} file-drop uploads · ${formatCount(flow.schoolFilesShares)} school files shares`,
      });
    }
    return list;
  };
  const rowIds = () => rows().map((row) => row.id);

  return (
    <section class="panel instance-block" data-testid={`nextcloud-instance-${instanceKey(props.instance)}`}>
      <InstanceMeta
        name={props.instance.name}
        demo={props.instance.demo}
        listed={props.instance.listed}
        hookStatus={props.instance.hookStatus}
        skipReason={props.instance.skipReason}
        clock={props.instance.clock}
        collectedAt={props.instance.collectedAt}
        showNoData={!hasPayload()}
        shortId={props.shortId}
        instanceId={instanceKey(props.instance)}
      />
      <Show when={hasPayload()}>
        <table>
          <thead>
            <tr>
              <th>What was counted</th>
              <th>This week</th>
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
                        <td>{item().value}</td>
                      </tr>
                    )}
                  </Show>
                );
              }}
            </For>
          </tbody>
        </table>
      </Show>
      <Show when={hasPayload() && otherGroupIds().length > 0}>
        <p class="muted">
          Other groups:{' '}
          <For each={otherGroupIds()}>
            {(id) => {
              const count = () => setup()?.otherGroups?.[id];
              return <span>{id} · {formatCount(count() ?? null)}. </span>;
            }}
          </For>
        </p>
      </Show>
    </section>
  );
}

export function NextcloudPage(props: NextcloudPageProps) {
  const ids = () => props.data.instances.map(instanceKey);
  const shortIds = () => shortIdsForDuplicateNames(props.data.instances);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="nextcloud" />
      <div class="wrap">
        <h2>{props.school} · Nextcloud this week</h2>
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
                {(item) => <InstancePanel instance={item()} shortId={shortIds().get(id)} />}
              </Show>
            );
          }}
        </For>
      </div>
    </>
  );
}
