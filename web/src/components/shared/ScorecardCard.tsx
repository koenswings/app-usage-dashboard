import { For, Show, type JSX } from 'solid-js';

export type ScorecardTone = 'onTrack' | 'needsHelp' | 'noData' | 'notMeasured';
export type ScorecardPill = 'ok' | 'help' | 'noData' | 'monitoringOff';

export interface ScorecardLineView {
  id: string;
  label: string;
  tone: ScorecardTone;
  word: string;
  detail: string;
  barPercent: number | null;
}

export interface ScorecardHeadlineView {
  id: string;
  value: string;
  label: string;
}

export interface ScorecardCardProps {
  school: string;
  engine: string;
  note?: string;
  pill: ScorecardPill;
  pillLabel: string;
  lines: ScorecardLineView[];
  headlines: ScorecardHeadlineView[];
  lastPulledLabel: string | null;
  stale: boolean;
  dataFromLabel: string | null;
  /** When set, replaces the scorecard lines (and headlines) with one sentence. */
  message?: string;
  href?: string;
  selected?: boolean;
}

export function ScorecardCard(props: ScorecardCardProps) {
  const lineIds = () => props.lines.map((line) => line.id);
  const headlineIds = () => props.headlines.map((item) => item.id);

  const cardClass = () =>
    `scorecard-card${props.selected ? ' scorecard-card--selected' : ''}${props.href ? ' scorecard-card--link' : ''}`;

  const body: JSX.Element = (
    <>
      <div class="scorecard-card__top">
        <div>
          <h3 class="scorecard-card__school">{props.school}</h3>
          <p class="scorecard-card__engine">
            {props.engine}
            <Show when={props.note}>
              {(note) => ` · ${note()}`}
            </Show>
          </p>
        </div>
        <span class={`pill pill--${props.pill}`} data-testid="scorecard-pill">
          {props.pillLabel}
        </span>
      </div>
      <Show
        when={props.message}
        fallback={
          <>
            <div class="scorecard-card__lines">
              <For each={lineIds()}>
                {(id) => {
                  const line = () => props.lines.find((item) => item.id === id);
                  return (
                    <Show when={line()}>
                      {(item) => (
                        <div class="scorecard-line" data-line-id={item().id}>
                          <span class="scorecard-line__label">
                            <i class={`scorecard-line__icon scorecard-line__icon--${item().tone}`} aria-hidden="true" />
                            {item().label}
                          </span>
                          <span class="scorecard-line__detail">{item().detail}</span>
                          <span class="scorecard-line__word">{item().word}</span>
                        </div>
                      )}
                    </Show>
                  );
                }}
              </For>
            </div>
            <div class="scorecard-card__stats">
              <For each={headlineIds()}>
                {(id) => {
                  const item = () => props.headlines.find((headline) => headline.id === id);
                  return (
                    <Show when={item()}>
                      {(headline) => (
                        <div>
                          <strong>{headline().value}</strong>
                          {headline().label}
                        </div>
                      )}
                    </Show>
                  );
                }}
              </For>
            </div>
          </>
        }
      >
        {(message) => (
          <p class="scorecard-card__message" data-testid="monitoring-off-message">
            {message()}
          </p>
        )}
      </Show>
      <div class="scorecard-card__meta">
        <span>Last pulled: {props.lastPulledLabel ?? 'Never pulled'}</span>
        <Show when={props.stale && props.dataFromLabel}>
          {(label) => (
            <span class="old-data-marker" data-testid="old-data-marker">
              {label()}
            </span>
          )}
        </Show>
      </div>
    </>
  );

  if (props.href) {
    return (
      <a class={cardClass()} href={props.href} data-testid={`school-card-${props.engine}`}>
        {body}
      </a>
    );
  }

  return (
    <section class={cardClass()} data-testid={`school-card-${props.engine}`}>
      {body}
    </section>
  );
}
