import type { IsoDate, IsoDateTime } from '../api/types';
import { formatDayLabel } from './week';

export function formatDateTime(iso: IsoDateTime | null, timeZone: string): string {
  if (!iso) return 'Never pulled';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const fmt = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return `${fmt.format(date)} ${timeZone}`;
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
