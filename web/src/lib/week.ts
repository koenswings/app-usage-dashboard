import type { IsoDate, WeekStart } from '../api/types';

export function parseIsoDate(iso: string): { y: number; m: number; d: number } {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) throw new Error(`Invalid date: ${iso}`);
  return { y: Number(match[1]), m: Number(match[2]), d: Number(match[3]) };
}

export function isMonday(iso: string): boolean {
  const { y, m, d } = parseIsoDate(iso);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay() === 1;
}

export function addDays(iso: IsoDate, days: number): IsoDate {
  const { y, m, d } = parseIsoDate(iso);
  const date = new Date(Date.UTC(y, m - 1, d + days));
  const yy = date.getUTCFullYear();
  const mm = String(date.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(date.getUTCDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

export function fridayOf(weekStart: WeekStart): IsoDate {
  return addDays(weekStart, 4);
}

export function shiftWeek(weekStart: WeekStart, deltaWeeks: number): WeekStart {
  return addDays(weekStart, deltaWeeks * 7);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatDayLabel(iso: IsoDate): string {
  const { d, m, y } = parseIsoDate(iso);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function formatWeekLabel(weekStart: WeekStart, weekEnd: IsoDate): string {
  const start = parseIsoDate(weekStart);
  const end = parseIsoDate(weekEnd);
  if (start.m === end.m && start.y === end.y) {
    return `Week of ${start.d}–${end.d} ${MONTHS[end.m - 1]} ${end.y}`;
  }
  if (start.y === end.y) {
    return `Week of ${start.d} ${MONTHS[start.m - 1]} – ${end.d} ${MONTHS[end.m - 1]} ${end.y}`;
  }
  return `Week of ${formatDayLabel(weekStart)} – ${formatDayLabel(weekEnd)}`;
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function weekdayShort(iso: IsoDate): string {
  const { y, m, d } = parseIsoDate(iso);
  const day = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return WEEKDAYS[(day + 6) % 7];
}

/**
 * Calm banner when the picker lands on the latest week that has data
 * because today's Monday has none yet, or when the store is empty.
 * Never an error.
 */
export function noDataThisWeekNote(
  currentWeekHasData: boolean,
  currentWeekStart: WeekStart,
  todayWeekStart?: WeekStart,
): string | null {
  const showingOlderWeek = Boolean(todayWeekStart) && todayWeekStart !== currentWeekStart;
  if (currentWeekHasData && !showingOlderWeek) return null;
  return `No data for this week yet, showing the week of ${formatDayLabel(currentWeekStart)}`;
}
