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
  { id: 'uplink', label: 'Uplink' },
  { id: 'instances', label: 'Instances' },
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

export function FleetNav(props: { week: string }) {
  return (
    <nav class="nav" aria-label="Dashboard">
      <a href={`#/?week=${props.week}`} aria-current="page">Fleet</a>
    </nav>
  );
}
