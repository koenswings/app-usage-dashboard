import { For, Show } from 'solid-js';
import type { SchoolWeekResponse } from '../api/types';
import { PresenceStrip } from '../components/shared/PresenceStrip';
import { ScorecardCard } from '../components/shared/ScorecardCard';
import { ClockWeekWarning } from '../components/InstanceMeta';
import { SchoolNav } from '../components/SchoolNav';
import { formatCount, formatDataFrom, formatDateTime, formatMinutes, formatPercent } from '../lib/format';
import { isMonitoringOff, MONITORING_OFF_MESSAGE, showStale } from '../lib/monitoring';
import { buildHeadlines, buildPill, buildScorecardLines } from '../lib/scorecardView';

interface SchoolWeekProps {
  data: SchoolWeekResponse;
  headerTimeZone: string;
}

export function SchoolWeek(props: SchoolWeekProps) {
  const census = () => props.data.census;
  const score = () => props.data.scorecard;
  const kpis = () => [
    {
      id: 'classes',
      label: 'Classes created (own Kolibri)',
      value: formatCount(census().classes),
      sub: `current count · ${formatCount(census().classesDelta)} added vs last snapshot`,
    },
    {
      id: 'learners',
      label: 'Learners registered',
      value: formatCount(census().learnersRegistered),
      sub: `${formatCount(census().learnersEnrolled)} enrolled in a class`,
    },
    {
      id: 'teachers',
      label: 'Teachers / coaches',
      value: formatCount(census().teachers),
      sub: `${formatCount(census().admins)} admin · own instance, not Demo`,
    },
    {
      id: 'share',
      label: 'Learner share of time',
      value: formatPercent(score().learnersOperate.learnerShareOfMinutes),
      sub: `${formatMinutes(score().learnersOperate.learnerMinutes)} learner · rest coach/admin`,
    },
  ];
  const kpiIds = () => kpis().map((item) => item.id);
  const kolibriMinutes = () => {
    const parts = [
      score().learnersOperate.learnerMinutes,
      score().learnersOperate.coachMinutes,
      score().learnersOperate.adminMinutes,
    ];
    if (parts.every((value) => value === null)) return null;
    return parts.reduce<number>((sum, value) => sum + (value ?? 0), 0);
  };

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="school" />
      <div class="wrap">
        <h2>
          {props.data.school} · {props.data.engine} · week detail
        </h2>
        <ClockWeekWarning trusted={props.data.clockTrusted} />
        <Show when={isMonitoringOff(props.data.monitoringEnabled, undefined)}>
          <p class="status-banner" data-testid="monitoring-off-banner" role="status">
            {MONITORING_OFF_MESSAGE}
          </p>
        </Show>
        <p class="muted">
          Last pulled: {formatDateTime(props.data.lastPulled, props.headerTimeZone)}
          <Show when={showStale(props.data.stale, isMonitoringOff(props.data.monitoringEnabled, undefined)) && props.data.dataFrom}>
            <span class="old-data-marker" data-testid="old-data-marker">
              {' '}{formatDataFrom(props.data.dataFrom)}
            </span>
          </Show>
        </p>
        <div class="grid4" style={{ 'margin-bottom': '14px' }}>
          <For each={kpiIds()}>
            {(id) => {
              const item = () => kpis().find((kpi) => kpi.id === id);
              return (
                <Show when={item()}>
                  {(kpi) => (
                    <div class="kpi">
                      <div class="label">{kpi().label}</div>
                      <div class="value">{kpi().value}</div>
                      <div class="sub">{kpi().sub}</div>
                    </div>
                  )}
                </Show>
              );
            }}
          </For>
        </div>
        <div class="grid2">
          <div class="panel">
            <PresenceStrip
              segments={props.data.presence.segments}
              timeZone={props.data.presence.timezone.timeZone}
              utcOffset={props.data.presence.timezone.utcOffset}
              timeZoneLabel={props.data.presence.timezone.label}
              weekStart={props.data.weekStart}
              weekEnd={props.data.weekEnd}
              summary={props.data.presence.summary}
              monitoringOff={isMonitoringOff(props.data.monitoringEnabled, undefined)}
            />
          </div>
          <ScorecardCard
            school={props.data.school}
            engine={props.data.engine}
            note="Scorecard inputs this week"
            pill={buildPill(props.data.hasUsageData, props.data.thresholdsConfigured, props.data.monitoringEnabled).pill}
            pillLabel={buildPill(props.data.hasUsageData, props.data.thresholdsConfigured, props.data.monitoringEnabled).pillLabel}
            lines={isMonitoringOff(props.data.monitoringEnabled, undefined) ? [] : buildScorecardLines(props.data.scorecard, props.data.thresholdsConfigured)}
            headlines={isMonitoringOff(props.data.monitoringEnabled, undefined) ? [] : buildHeadlines({
              classes: census().classes,
              learnersRegistered: census().learnersRegistered,
              teachers: census().teachers,
              kolibriMinutes: kolibriMinutes(),
            })}
            message={isMonitoringOff(props.data.monitoringEnabled, undefined) ? MONITORING_OFF_MESSAGE : undefined}
            lastPulledLabel={formatDateTime(props.data.lastPulled, props.headerTimeZone)}
            stale={showStale(props.data.stale, isMonitoringOff(props.data.monitoringEnabled, undefined))}
            dataFromLabel={formatDataFrom(props.data.dataFrom)}
          />
        </div>
      </div>
    </>
  );
}
