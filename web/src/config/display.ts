/**
 * Display settings that `/api/v1/meta` may override.
 * Server values win; these defaults apply when meta omits a field
 * (Steve, idea#415: staleAfterHours = 48, hourly-chart minimum = 20).
 *
 * Scorecard grade cut-offs (U-7, idea#375) live only in `thresholds.ts`
 * as editable defaults.
 */

export const DEFAULT_STALE_AFTER_HOURS = 48;
export const DEFAULT_HOURLY_CHART_MIN_WEEKLY_VIEWS = 20;

export function resolveStaleAfterHours(value: number | null | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? value
    : DEFAULT_STALE_AFTER_HOURS;
}

export function resolveHourlyChartMinWeeklyViews(value: number | null | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
    ? value
    : DEFAULT_HOURLY_CHART_MIN_WEEKLY_VIEWS;
}

export function isOlderThanHours(
  iso: string | null,
  hours: number,
  nowMs: number = Date.now(),
): boolean {
  if (!iso) return false;
  const stamp = Date.parse(iso);
  if (Number.isNaN(stamp)) return false;
  return nowMs - stamp >= hours * 60 * 60 * 1000;
}
