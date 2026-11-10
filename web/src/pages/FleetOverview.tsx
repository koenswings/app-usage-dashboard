import { For, Show } from 'solid-js';
import type { OverviewResponse } from '../api/types';
import { ScorecardCard } from '../components/shared/ScorecardCard';
import { FleetNav } from '../components/SchoolNav';
import { buildHeadlines, buildPill, buildScorecardLines } from '../lib/scorecardView';
import { formatDataFrom, formatDateTime } from '../lib/format';
import { schoolHref } from '../lib/route';

interface FleetOverviewProps {
  overview: OverviewResponse;
  headerTimeZone: string;
}

export function FleetOverview(props: FleetOverviewProps) {
  const cardIds = () => props.overview.cards.map((card) => card.deploymentId);
  const suggestionIds = () => props.overview.helpSuggestions.map((item) => item.deploymentId);

  return (
    <>
      <FleetNav week={props.overview.weekStart} />
      <Show when={props.overview.helpSuggestions.length > 0}>
        <div class="help-banner" data-testid="help-banner">
          <strong>Offer help first. </strong>
          <For each={suggestionIds()}>
            {(id) => {
              const item = () => props.overview.helpSuggestions.find((row) => row.deploymentId === id);
              return <span>{item()?.message} </span>;
            }}
          </For>
        </div>
      </Show>
      <div class="wrap">
        <h2>Schools this week</h2>
        <div class="schools">
          <For each={cardIds()}>
            {(id) => {
              const card = () => props.overview.cards.find((row) => row.deploymentId === id);
              return (
                <Show when={card()}>
                  {(item) => {
                    const pill = () => buildPill(item().hasUsageData, props.overview.thresholdsConfigured);
                    return (
                      <ScorecardCard
                        school={item().school}
                        engine={item().engine}
                        note={item().note}
                        pill={pill().pill}
                        pillLabel={pill().pillLabel}
                        lines={buildScorecardLines(item().scorecard, props.overview.thresholdsConfigured)}
                        headlines={buildHeadlines(item().headlines)}
                        lastPulledLabel={formatDateTime(item().lastPulled, props.headerTimeZone)}
                        stale={item().stale}
                        dataFromLabel={formatDataFrom(item().dataFrom)}
                        href={schoolHref(item().deploymentId, props.overview.weekStart)}
                      />
                    );
                  }}
                </Show>
              );
            }}
          </For>
        </div>
      </div>
    </>
  );
}
