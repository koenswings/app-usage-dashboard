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
  summary?: string;
}

const STATE_WORD: Record<PresenceStripState, string> = {
  on: 'Powered on',
  off: 'Powered off',
  gapUnknown: 'Gap, length unknown',
  collectorGap: 'Collector gap',
};

const WEEKDAY = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

interface TrackPiece {
  id: string;
  kind: 'pad' | 'seg';
  weight: number;
  segment?: PresenceStripSegment;
}

function trackWeight(segment: PresenceStripSegment): number {
  const start = Date.parse(segment.start);
  const end = Date.parse(segment.end);
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return 1;
  // lengthKnown:false is never a measured duration. Keep the calendar span
  // so the block sits on the week, but do not treat it as a known length.
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

function trackPieces(
  segments: PresenceStripSegment[],
  weekStart: string,
  weekEnd: string,
  utcOffset: string,
): TrackPiece[] {
  const bounds = weekBounds(weekStart, weekEnd, utcOffset);
  const sorted = [...segments].sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
  if (!bounds) {
    return sorted.map((segment) => ({
      id: segmentId(segment),
      kind: 'seg' as const,
      weight: trackWeight(segment),
      segment,
    }));
  }
  const pieces: TrackPiece[] = [];
  let cursor = bounds.origin;
  for (const segment of sorted) {
    const rawStart = Date.parse(segment.start);
    const rawEnd = Date.parse(segment.end);
    if (Number.isNaN(rawStart) || Number.isNaN(rawEnd)) continue;
    const start = Math.max(rawStart, bounds.origin);
    const end = Math.min(rawEnd, bounds.end);
    if (end <= start) continue;
    if (start > cursor) {
      pieces.push({ id: `pad-${cursor}`, kind: 'pad', weight: start - cursor });
    }
    pieces.push({ id: segmentId(segment), kind: 'seg', weight: end - start, segment });
    cursor = end;
  }
  if (cursor < bounds.end) {
    pieces.push({ id: `pad-${cursor}`, kind: 'pad', weight: bounds.end - cursor });
  }
  return pieces;
}

export function PresenceStrip(props: PresenceStripProps) {
  const pieces = () => trackPieces(props.segments, props.weekStart, props.weekEnd, props.utcOffset);
  const ids = () => pieces().map((piece) => piece.id);

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
              const piece = () => pieces().find((item) => item.id === id);
              return (
                <Show when={piece()}>
                  {(item) => (
                    item().kind === 'seg' && item().segment ? (
                      <div
                        class={`presence-seg presence-seg--${item().segment!.state}`}
                        style={{ flex: String(item().weight) }}
                        title={segmentTitle(item().segment!)}
                        data-state={item().segment!.state}
                      />
                    ) : (
                      <div
                        class="presence-seg presence-seg--pad"
                        style={{ flex: String(item().weight) }}
                        aria-hidden="true"
                      />
                    )
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
        {(text) => <p class="presence-strip__summary">{text()}</p>}
      </Show>
    </section>
  );
}
