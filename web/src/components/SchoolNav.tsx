import { For } from 'solid-js';
import type { PageName } from '../lib/route';
import { schoolHref } from '../lib/route';

interface SchoolNavProps {
  deploymentId: string;
  week: string;
  current: PageName;
}

const LINKS: Array<{ id: PageName; label: string }> = [
  { id: 'overview', label: 'Fleet' },
  { id: 'school', label: 'Week' },
  { id: 'kolibri', label: 'Kolibri' },
  { id: 'nextcloud', label: 'Nextcloud' },
  { id: 'wikipedia', label: 'Wikipedia' },
  { id: 'help', label: 'Help' },
  { id: 'uplink', label: 'Reachability' },
  { id: 'instances', label: 'Apps' },
  { id: 'settings', label: 'Settings' },
];

export function SchoolNav(props: SchoolNavProps) {
  const ids = () => LINKS.map((link) => link.id);

  return (
    <nav class="nav" aria-label="Dashboard">
      <For each={ids()}>
        {(id) => {
          const link = () => LINKS.find((item) => item.id === id);
          const href = () =>
            id === 'overview'
              ? `#/?week=${props.week}`
              : id === 'settings'
                ? (props.week ? `#/settings?week=${props.week}` : '#/settings')
                : schoolHref(props.deploymentId, props.week, id);
          return (
            <a href={href()} aria-current={props.current === id ? 'page' : undefined}>
              {link()?.label}
            </a>
          );
        }}
      </For>
    </nav>
  );
}

export function FleetNav(props: { week: string; current?: 'overview' | 'settings' }) {
  const current = () => props.current ?? 'overview';
  return (
    <nav class="nav" aria-label="Dashboard">
      <a href={`#/?week=${props.week}`} aria-current={current() === 'overview' ? 'page' : undefined}>Fleet</a>
      <a href={props.week ? `#/settings?week=${props.week}` : '#/settings'} aria-current={current() === 'settings' ? 'page' : undefined}>Settings</a>
    </nav>
  );
}
