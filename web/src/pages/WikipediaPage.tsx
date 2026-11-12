import { For, Show } from 'solid-js';
import type { KiwixInstanceWeek, KiwixWeekResponse } from '../api/types';
import { instanceKey } from '../api/types';
import { ClockWeekWarning, InstanceMeta } from '../components/InstanceMeta';
import { SchoolNav } from '../components/SchoolNav';
import { formatUnit } from '../lib/format';
import { shortIdsForDuplicateNames } from '../lib/instances';

export function shouldShowHourlyChart(pageViews: number, minWeekly: number): boolean {
  return pageViews >= minWeekly;
}

/** Whose views a chart shows: the whole school (all copies) or one copy. */
export type HourlyScope = 'school' | 'copy';

export interface SchoolHourly {
  pageViews: number;
  views: number[];
  copies: number;
}

function hasHourly(instance: KiwixInstanceWeek): boolean {
  return instance.hookStatus === 'ok' && instance.pageViews !== null && Array.isArray(instance.byHour);
}

/**
 * The school's week across every measured copy (own, Demo and extra): summed
 * page views and summed views by hour. The hourly minimum is applied to this
 * total, not to each copy. Null when no copy has hourly data.
 */
export function schoolHourly(instances: KiwixInstanceWeek[]): SchoolHourly | null {
  const measured = instances.filter(hasHourly);
  if (measured.length === 0) return null;
  const views = Array.from({ length: 24 }, () => 0);
  let pageViews = 0;
  for (const item of measured) {
    pageViews += item.pageViews ?? 0;
    (item.byHour ?? []).forEach((value, hour) => {
      if (hour < 24) views[hour] += value;
    });
  }
  return { pageViews, views, copies: measured.length };
}

const HOUR_IDS = Array.from({ length: 24 }, (_, hour) => String(hour));

export function HourlyChart(props: {
  views: number[];
  pageViews: number;
  minWeekly: number;
  scope?: HourlyScope;
}) {
  const max = () => Math.max(1, ...props.views);
  const scope = () => props.scope ?? 'school';

  return (
    <Show
      when={shouldShowHourlyChart(props.pageViews, props.minWeekly)}
      fallback={
        <p class="muted" data-testid="hourly-chart-hidden">
          <Show
            when={scope() === 'copy'}
            fallback={
              <>
                Views by hour are hidden when the school’s week has fewer than {props.minWeekly} page
                views, so a small school does not get a picture that is almost hour-by-hour.
              </>
            }
          >
            Views by hour for this copy are hidden because this copy has fewer than {props.minWeekly} page
            views this week.
          </Show>
        </p>
      }
    >
      <div class="hours" data-testid="hourly-chart" data-scope={scope()} aria-label="Views by hour in kit local time">
        <For each={HOUR_IDS}>
          {(id) => {
            const hour = () => Number(id);
            const value = () => props.views[hour()] ?? 0;
            const height = () => Math.max(4, Math.round((value() / max()) * 100));
            return <span style={{ height: `${height()}%` }} title={`${hour()}:00 · ${value()} views`} />;
          }}
        </For>
      </div>
      <p class="muted">
        {scope() === 'copy' ? 'Views by hour on this copy' : 'Views by hour'} (kit local time, 00–23).
      </p>
    </Show>
  );
}

function InstancePanel(props: {
  instance: KiwixInstanceWeek;
  minWeekly: number;
  shortId?: string | null;
  hourlyScope: HourlyScope;
}) {
  const articles = () => props.instance.topArticles ?? [];
  const articleIds = () => articles().map((article) => article.title);
  const pageViews = () => props.instance.pageViews;
  const byHour = () => props.instance.byHour;
  const hasPayload = () =>
    props.instance.hookStatus === 'ok' && pageViews() !== null && props.instance.sessions !== null;

  return (
    <section class="panel instance-block" data-testid={`kiwix-instance-${instanceKey(props.instance)}`}>
      <InstanceMeta
        name={props.instance.name}
        demo={props.instance.demo}
        listed={props.instance.listed}
        hookStatus={props.instance.hookStatus}
        skipReason={props.instance.skipReason}
        clock={props.instance.clock}
        collectedAt={props.instance.collectedAt}
        showNoData={!hasPayload()}
        shortId={props.shortId}
        instanceId={instanceKey(props.instance)}
      />
      <Show when={hasPayload()}>
        <p class="muted">No accounts — page views and articles only, never a person.</p>
        <div class="scorecard-card__stats scorecard-card__stats--flush">
          <div><strong>{pageViews()}</strong>page views</div>
          <div><strong>{props.instance.distinctArticles}</strong>distinct articles (most in one day)</div>
          <div><strong>{props.instance.sessions}</strong>sessions</div>
        </div>
        <Show when={articles().length > 0}>
          <table>
            <thead>
              <tr>
                <th>Top articles</th>
                <th class="right">Views</th>
              </tr>
            </thead>
            <tbody>
              <For each={articleIds()}>
                {(id) => {
                  const row = () => articles().find((item) => item.title === id);
                  return (
                    <Show when={row()}>
                      {(item) => (
                        <tr>
                          <td>{item().title}</td>
                          <td class="right">{item().views}</td>
                        </tr>
                      )}
                    </Show>
                  );
                }}
              </For>
            </tbody>
          </table>
        </Show>
        <Show when={byHour() && pageViews() !== null}>
          <HourlyChart
            views={byHour() ?? []}
            pageViews={pageViews() ?? 0}
            minWeekly={props.minWeekly}
            scope={props.hourlyScope}
          />
        </Show>
      </Show>
    </section>
  );
}

interface WikipediaPageProps {
  data: KiwixWeekResponse;
  school: string;
  hourlyChartMinWeeklyViews: number;
}

export function WikipediaPage(props: WikipediaPageProps) {
  const ids = () => props.data.instances.map(instanceKey);
  const shortIds = () => shortIdsForDuplicateNames(props.data.instances);
  const total = () => schoolHourly(props.data.instances);
  /** With two or more measured copies, the school total gets its own panel and copies say "this copy". */
  const showSchoolTotal = () => (total()?.copies ?? 0) > 1;

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="wikipedia" />
      <div class="wrap">
        <h2>{props.school} · Wikipedia offline</h2>
        <ClockWeekWarning trusted={props.data.clockTrusted} />
        <Show when={props.data.instances.length === 0}>
          <p>No data</p>
        </Show>
        <Show when={showSchoolTotal() && total()}>
          {(sum) => (
            <section class="panel instance-block" data-testid="kiwix-school-total">
              <strong>All copies this week</strong>
              <p class="muted">
                {formatUnit(sum().pageViews, 'page view', 'page views')} across {sum().copies} copies.
                The views-by-hour minimum applies to this school total.
              </p>
              <HourlyChart
                views={sum().views}
                pageViews={sum().pageViews}
                minWeekly={props.hourlyChartMinWeeklyViews}
                scope="school"
              />
            </section>
          )}
        </Show>
        <For each={ids()}>
          {(id) => {
            const instance = () => props.data.instances.find((item) => instanceKey(item) === id);
            return (
              <Show when={instance()}>
                {(item) => (
                  <InstancePanel
                    instance={item()}
                    minWeekly={props.hourlyChartMinWeeklyViews}
                    shortId={shortIds().get(id)}
                    hourlyScope={showSchoolTotal() ? 'copy' : 'school'}
                  />
                )}
              </Show>
            );
          }}
        </For>
      </div>
    </>
  );
}
