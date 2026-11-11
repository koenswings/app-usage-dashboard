/** Footer label from GET /api/v1/health, e.g. "v1.0 · 0d92961". */
export function healthVersionLabel(health: {
  version?: string;
  commit?: string | null;
} | null | undefined): string | null {
  const version = health?.version?.trim() ?? '';
  const commit = health?.commit?.trim() ?? '';
  const short = commit.length > 7 ? commit.slice(0, 7) : commit;
  const ver = version ? (version.startsWith('v') || version.startsWith('V') ? version : `v${version}`) : '';
  if (ver && short) return `${ver} · ${short}`;
  if (ver) return ver;
  if (short) return short;
  return null;
}
