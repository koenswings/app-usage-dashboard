import type { IsoDate, IsoDateTime, UplinkSample } from '../api/types';
import { formatDayLabel, weekdayShort } from './week';

export const UPLINK_NOT_MEASURED_MESSAGE =
  "Reachability isn't measured yet: the dashboard's network link isn't connected.";

/** measured is optional on older collectors; only an explicit false is "not measured". */
export function uplinkNotMeasured(measured: boolean | undefined): boolean {
  return measured === false;
}

export const UPLINK_NO_CHANGE_MESSAGE = 'No change this week';

/**
 * Text for an empty "When reachability changed" list: measured with no
 * state change is "No change this week"; anything else stays "No data".
 */
export function uplinkTransitionsEmptyText(measured: boolean | undefined): string {
  return measured === true ? UPLINK_NO_CHANGE_MESSAGE : 'No data';
}

export interface UplinkDaySample {
  id: string;
  timestamp: IsoDateTime;
  online: boolean;
}

export interface UplinkDay {
  /** Kit-local calendar day, YYYY-MM-DD. */
  day: IsoDate;
  label: string;
  total: number;
  reachable: number;
  notReachable: number;
  firstTime: string;
  lastTime: string;
  samples: UplinkDaySample[];
}

export function sampleId(sample: Pick<UplinkSample, 'timestamp' | 'engine'>): string {
  return `${sample.timestamp}|${sample.engine}`;
}

function localDay(iso: IsoDateTime, timeZone: string): IsoDate | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const options: Intl.DateTimeFormatOptions = { year: 'numeric', month: '2-digit', day: '2-digit' };
  if (timeZone) options.timeZone = timeZone;
  const parts = new Intl.DateTimeFormat('en-CA', options).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return `${get('year')}-${get('month')}-${get('day')}`;
}

export function localTime(iso: IsoDateTime, timeZone: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hour12: false };
  if (timeZone) options.timeZone = timeZone;
  return new Intl.DateTimeFormat('en-GB', options).format(date);
}

/**
 * Reachability samples grouped by kit-local day, oldest day first, so the
 * page shows one summary row per day with the raw checks behind a toggle.
 */
export function groupSamplesByDay(samples: UplinkSample[], timeZone: string): UplinkDay[] {
  const sorted = [...samples].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  const days = new Map<IsoDate, UplinkDay>();
  for (const sample of sorted) {
    const day = localDay(sample.timestamp, timeZone);
    if (!day) continue;
    let row = days.get(day);
    if (!row) {
      row = {
        day,
        label: `${weekdayShort(day)} ${formatDayLabel(day)}`,
        total: 0,
        reachable: 0,
        notReachable: 0,
        firstTime: localTime(sample.timestamp, timeZone),
        lastTime: '',
        samples: [],
      };
      days.set(day, row);
    }
    row.total += 1;
    if (sample.online) row.reachable += 1;
    else row.notReachable += 1;
    row.lastTime = localTime(sample.timestamp, timeZone);
    row.samples.push({ id: sampleId(sample), timestamp: sample.timestamp, online: sample.online });
  }
  return [...days.values()];
}
