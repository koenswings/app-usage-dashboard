export const MONITORING_OFF_MESSAGE = 'Usage monitoring is switched off on this kit.';

/**
 * Prefer the field on the school / overview card when the collector sends it.
 * Otherwise join `/api/v1/kits` by deploymentId. Undefined means we do not know.
 */
export function resolveMonitoringEnabled(
  fromCard: boolean | undefined,
  fromKit: boolean | undefined,
): boolean | undefined {
  if (typeof fromCard === 'boolean') return fromCard;
  if (typeof fromKit === 'boolean') return fromKit;
  return undefined;
}

export function isMonitoringOff(
  fromCard: boolean | undefined,
  fromKit: boolean | undefined,
): boolean {
  return resolveMonitoringEnabled(fromCard, fromKit) === false;
}

/** A monitoring-off kit is never shown as stale, even if the API marked it so. */
export function showStale(stale: boolean, monitoringOff: boolean): boolean {
  return stale && !monitoringOff;
}
