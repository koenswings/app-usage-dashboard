import { For, Show } from 'solid-js';
import { addDays } from '../../lib/week';

export type PresenceStripState = 'on' | 'off' | 'gapUnknown' | 'collectorGap';

export interface PresenceStripSegment {
  state: PresenceStripState;
  start: string;
  end: string;
  lengthKnown: boolean;
}

export interface PresenceStripProps {
  segments: PresenceStripSegment[];
  timeZone: string;
  utcOffset: string;
  timeZoneLabel: string;
  weekStart: string;
  weekEnd: string;
  summary?: string | null;
}

const STATE_WORD: Record<PresenceStripState, string> = {
  on: 'Powered on',
  off: 'Powered off',
  gapUnknown: 'Gap, length unknown',
  collectorGap: 'Collector gap',
};

const WEEKDAY = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

interface PlacedSegment {
  id: string;
  segment: PresenceStripSegment;
  left: number;
  width: number;
}

function trackWeight(segment: PresenceStripSegment): number {
  const start = Date.parse(segment.start);
  const end = Date.parse(segment.end);
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return 1;
  return end - start;
}

function segmentTitle(segment: PresenceStripSegment): string {
  if (!segment.lengthKnown) return STATE_WORD[segment.state];
  return `${STATE_WORD[segment.state]} · ${segment.start} – ${segment.end}`;
}

function segmentId(segment: PresenceStripSegment): string {
  return `${segment.start}|${segment.state}|${segment.end}`;
}

function weekBounds(weekStart: string, weekEnd: string, utcOffset: string): { origin: number; end: number } | null {
  const offset = utcOffset || 'Z';
  const origin = Date.parse(`${weekStart}T00:00:00${offset}`);
  const end = Date.parse(`${addDays(weekEnd, 1)}T00:00:00${offset}`);
  if (Number.isNaN(origin) || Number.isNaN(end) || end <= origin) return null;
  return { origin, end };
}

/**
 * Place each collector segment on the Mon–Sat school-week calendar.
 * Does not invent off / gap / pad pieces for uncovered time — the collector
 * now sends a contiguous cover.
 */
export function placedSegments(
  segments: PresenceStripSegment[],
  weekStart: string,
  weekEnd: string,
  utcOffset: string,
): PlacedSegment[] {
  const bounds = weekBounds(weekStart, weekEnd, utcOffset);
  const sorted = [...segments].sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
  if (!bounds) {
    const weights = sorted.map((segment) => ({ segment, weight: trackWeight(segment) }));
    const total = weights.reduce((sum, item) => sum + item.weight, 0) || 1;
    let left = 0;
    return weights.map(({ segment, weight }) => {
      const width = (weight / total) * 100;
      const placed = { id: segmentId(segment), segment, left, width };
      left += width;
      return placed;
    });
  }
  const total = bounds.end - bounds.origin;
  const placed: PlacedSegment[] = [];
  for (const segment of sorted) {
    const rawStart = Date.parse(segment.start);
    const rawEnd = Date.parse(segment.end);
    if (Number.isNaN(rawStart) || Number.isNaN(rawEnd)) continue;
    const start = Math.max(rawStart, bounds.origin);
    const end = Math.min(rawEnd, bounds.end);
    if (end <= start) continue;
    placed.push({
      id: segmentId(segment),
      segment,
      left: ((start - bounds.origin) / total) * 100,
      width: ((end - start) / total) * 100,
    });
  }
  return placed;
}

export function PresenceStrip(props: PresenceStripProps) {
  const placed = () => placedSegments(props.segments, props.weekStart, props.weekEnd, props.utcOffset);
  const ids = () => placed().map((item) => item.id);

  return (
    <section class="presence-strip" data-testid="presence-strip">
      <header class="presence-strip__head">
        <strong>Kit active / idle this week</strong>
        <p>
          Each block is one continuous presence segment. Width follows the calendar.
          A hatched block is a gap whose length is not known — it is not a measured
          duration. Ticks are in {props.timeZoneLabel}.
        </p>
      </header>
      <Show
        when={props.segments.length > 0}
        fallback={<p class="presence-strip__empty">No presence samples for this week.</p>}
      >
        <div class="presence-strip__track" role="img" aria-label="Presence segments for the school week">
          <For each={ids()}>
            {(id) => {
              const item = () => placed().find((row) => row.id === id);
              return (
                <Show when={item()}>
                  {(row) => (
                    <div
                      class={`presence-seg presence-seg--${row().segment.state}`}
                      style={{ left: `${row().left}%`, width: `${row().width}%` }}
                      title={segmentTitle(row().segment)}
                      data-state={row().segment.state}
                    />
                  )}
                </Show>
              );
            }}
          </For>
        </div>
        <div class="presence-strip__days">
          <For each={WEEKDAY}>
            {(day) => <span>{day}</span>}
          </For>
        </div>
      </Show>
      <ul class="presence-legend">
        <li><i class="presence-seg presence-seg--on" /> Powered on</li>
        <li><i class="presence-seg presence-seg--off" /> Powered off</li>
        <li><i class="presence-seg presence-seg--gapUnknown" /> Gap, length unknown</li>
        <li><i class="presence-seg presence-seg--collectorGap" /> Collector gap</li>
      </ul>
      <p class="presence-strip__tz">Times shown in {props.timeZoneLabel} (offset {props.utcOffset}).</p>
      <Show when={props.summary}>
        {(text) => (
          <p class="presence-strip__summary" data-testid="presence-summary">{text()}</p>
        )}
      </Show>
    </section>
  );
}
