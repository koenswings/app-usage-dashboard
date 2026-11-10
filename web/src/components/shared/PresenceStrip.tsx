import { For, Show } from 'solid-js';

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

export function PresenceStrip(props: PresenceStripProps) {
  const ids = () => props.segments.map(segmentId);

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
              const segment = () => props.segments.find((item) => segmentId(item) === id);
              return (
                <Show when={segment()}>
                  {(item) => (
                    <div
                      class={`presence-seg presence-seg--${item().state}`}
                      style={{ flex: String(trackWeight(item())) }}
                      title={segmentTitle(item())}
                      data-state={item().state}
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
        {(text) => <p class="presence-strip__summary">{text()}</p>}
      </Show>
    </section>
  );
}
