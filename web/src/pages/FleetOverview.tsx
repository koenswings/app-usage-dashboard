import { For, Show } from 'solid-js';
import type { OverviewResponse, ScorecardThresholds } from '../api/types';
import { DEFAULT_THRESHOLDS, unusedRuleText } from '../config/thresholds';
import { ScorecardCard } from '../components/shared/ScorecardCard';
import { FleetNav } from '../components/SchoolNav';
import { isMonitoringOff, MONITORING_OFF_MESSAGE, showStale } from '../lib/monitoring';
import { buildHeadlines, buildPill, buildScorecardLines } from '../lib/scorecardView';
import { formatDataFrom, formatDateTime } from '../lib/format';
import { schoolHref } from '../lib/route';

interface FleetOverviewProps {
  overview: OverviewResponse;
  headerTimeZone: string;
  /** monitoringEnabled from GET /api/v1/kits, keyed by deploymentId. */
  monitoringByDeployment?: Record<string, boolean>;
  thresholds?: ScorecardThresholds;
}

export function FleetOverview(props: FleetOverviewProps) {
  const cardIds = () => props.overview.cards.map((card) => card.deploymentId);
  const suggestionIds = () => props.overview.helpSuggestions.map((item) => item.deploymentId);
  const thresholds = () => props.thresholds ?? DEFAULT_THRESHOLDS;

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
                    const fromKit = () => (props.monitoringByDeployment ?? {})[item().deploymentId];
                    const monitoringOff = () => isMonitoringOff(item().monitoringEnabled, fromKit());
                    const unused = () => !monitoringOff() && item().unused === true;
                    const lines = () =>
                      monitoringOff() ? [] : buildScorecardLines(item().scorecard, thresholds());
                    const pill = () => buildPill(
                      item().hasUsageData,
                      lines(),
                      monitoringOff() ? false : item().monitoringEnabled ?? fromKit(),
                      unused(),
                    );
                    return (
                      <ScorecardCard
                        school={item().school}
                        engine={item().engine}
                        note={item().note}
                        pill={pill().pill}
                        pillLabel={pill().pillLabel}
                        lines={lines()}
                        headlines={monitoringOff() ? [] : buildHeadlines(item().headlines)}
                        message={monitoringOff() ? MONITORING_OFF_MESSAGE : undefined}
                        banner={unused() ? unusedRuleText(thresholds()) : undefined}
                        lastPulledLabel={formatDateTime(item().lastPulled, props.headerTimeZone)}
                        stale={showStale(item().stale, monitoringOff())}
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
