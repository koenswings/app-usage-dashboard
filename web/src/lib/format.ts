import type { IsoDate, IsoDateTime } from '../api/types';
import { formatDayLabel } from './week';

export function formatDateTime(iso: IsoDateTime | null, timeZone: string): string {
  if (!iso) return 'Never pulled';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const options: Intl.DateTimeFormatOptions = {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  };
  if (timeZone) options.timeZone = timeZone;
  const fmt = new Intl.DateTimeFormat('en-GB', options);
  return timeZone ? `${fmt.format(date)} ${timeZone}` : fmt.format(date);
}

const FALLBACK_TIME_ZONE = 'Europe/Brussels';

/** Browser zone, or Europe/Brussels when the environment has none. */
export function resolveTimeZone(timeZone?: string | null): string {
  const candidate = timeZone?.trim();
  if (candidate) {
    try {
      Intl.DateTimeFormat('en-GB', { timeZone: candidate }).format(0);
      return candidate;
    } catch {
      // Invalid zone names fall through to the browser zone, then Brussels.
    }
  }
  try {
    const resolved = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (resolved) return resolved;
  } catch {
    // ignore
  }
  return FALLBACK_TIME_ZONE;
}

/**
 * Local date and time with a short zone label, e.g. "11 Nov 2026, 12:45 CET".
 * Uses the browser time zone unless `timeZone` is passed (tests).
 */
export function formatLocalDateTime(iso: IsoDateTime | null, timeZone?: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const zone = resolveTimeZone(timeZone);
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: zone,
    timeZoneName: 'short',
  }).format(date);
}

export function formatDataFrom(iso: IsoDate | null): string | null {
  if (!iso) return null;
  return `data from ${formatDayLabel(iso)}`;
}

export function formatMinutes(total: number | null): string {
  if (total === null) return '—';
  if (total < 60) return `${total}m`;
  const hours = total / 60;
  const rounded = Math.round(hours * 10) / 10;
  return `${rounded}h`;
}

export function formatPercent(share: number | null): string {
  if (share === null) return '—';
  return `${Math.round(share * 100)}%`;
}

export function formatCount(value: number | null): string {
  if (value === null) return '—';
  return String(value);
}

export function formatUnit(value: number | null, singular: string, plural: string): string {
  if (value === null) return '—';
  return `${value} ${value === 1 ? singular : plural}`;
}

/** Singular or plural noun for a count; null keeps the plural ("—" is shown as the value). */
export function pluralWord(value: number | null, singular: string, plural: string): string {
  return value === 1 ? singular : plural;
}

/** "1 learner registered", "3 learners registered", "— learners registered" for null. */
export function formatCountPhrase(value: number | null, singular: string, plural: string): string {
  return `${formatCount(value)} ${pluralWord(value, singular, plural)}`;
}
