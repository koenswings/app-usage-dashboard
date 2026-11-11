export type PageName =
  | 'login'
  | 'overview'
  | 'school'
  | 'kolibri'
  | 'nextcloud'
  | 'wikipedia'
  | 'help'
  | 'uplink'
  | 'instances'
  | 'settings';

export interface Route {
  name: PageName;
  deploymentId?: string;
  week?: string;
}

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, '') || '/';
  const qIndex = raw.indexOf('?');
  const path = qIndex === -1 ? raw : raw.slice(0, qIndex);
  const query = qIndex === -1 ? '' : raw.slice(qIndex + 1);
  const params = new URLSearchParams(query);
  const week = params.get('week') ?? undefined;
  const parts = path.split('/').filter(Boolean);

  if (parts[0] === 'login') return { name: 'login' };
  if (parts[0] === 'settings') return { name: 'settings', week };
  if (parts[0] === 'schools' && parts[1]) {
    const deploymentId = parts[1];
    const page = parts[2];
    if (page === 'kolibri') return { name: 'kolibri', deploymentId, week };
    if (page === 'nextcloud') return { name: 'nextcloud', deploymentId, week };
    if (page === 'wikipedia') return { name: 'wikipedia', deploymentId, week };
    if (page === 'help') return { name: 'help', deploymentId, week };
    if (page === 'uplink') return { name: 'uplink', deploymentId, week };
    if (page === 'instances') return { name: 'instances', deploymentId, week };
    return { name: 'school', deploymentId, week };
  }
  return { name: 'overview', week };
}

export function toHash(route: Route): string {
  if (route.name === 'login') return '#/login';
  const q = route.week ? `?week=${route.week}` : '';
  if (route.name === 'settings') return `#/settings${q}`;
  if (route.name === 'overview') return `#/${q}`;
  const id = route.deploymentId ?? '';
  const suffix =
    route.name === 'school' ? '' :
    route.name === 'kolibri' ? '/kolibri' :
    route.name === 'nextcloud' ? '/nextcloud' :
    route.name === 'wikipedia' ? '/wikipedia' :
    route.name === 'help' ? '/help' :
    route.name === 'uplink' ? '/uplink' :
    route.name === 'instances' ? '/instances' : '';
  return `#/schools/${id}${suffix}${q}`;
}

export function schoolHref(deploymentId: string, week: string, name: PageName = 'school'): string {
  return toHash({ name, deploymentId, week });
}
