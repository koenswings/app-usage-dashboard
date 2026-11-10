import { For, Show } from 'solid-js';
import type { KiwixInstanceWeek, KiwixWeekResponse } from '../api/types';
import { instanceKey } from '../api/types';
import { ClockWeekWarning, InstanceMeta } from '../components/InstanceMeta';
import { SchoolNav } from '../components/SchoolNav';

export function shouldShowHourlyChart(pageViews: number, minWeekly: number): boolean {
  return pageViews >= minWeekly;
}

const HOUR_IDS = Array.from({ length: 24 }, (_, hour) => String(hour));

export function HourlyChart(props: {
  views: number[];
  pageViews: number;
  minWeekly: number;
}) {
  const max = () => Math.max(1, ...props.views);

  return (
    <Show
      when={shouldShowHourlyChart(props.pageViews, props.minWeekly)}
      fallback={
        <p class="muted" data-testid="hourly-chart-hidden">
          Views by hour are hidden when the week has fewer than {props.minWeekly} page
          views, so a small school does not get a picture that is almost hour-by-hour.
        </p>
      }
    >
      <div class="hours" data-testid="hourly-chart" aria-label="Views by hour in kit local time">
        <For each={HOUR_IDS}>
          {(id) => {
            const hour = () => Number(id);
            const value = () => props.views[hour()] ?? 0;
            const height = () => Math.max(4, Math.round((value() / max()) * 100));
            return <span style={{ height: `${height()}%` }} title={`${hour()}:00 · ${value()} views`} />;
          }}
        </For>
      </div>
      <p class="muted">Views by hour (kit local time, 00–23).</p>
    </Show>
  );
}

function InstancePanel(props: { instance: KiwixInstanceWeek; minWeekly: number }) {
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
      />
      <Show when={hasPayload()}>
        <p class="muted">No accounts — page views and articles only, never a person.</p>
        <div class="scorecard-card__stats scorecard-card__stats--flush">
          <div><strong>{pageViews()}</strong>page views</div>
          <div><strong>{props.instance.distinctArticles}</strong>most different articles in one day</div>
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

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="wikipedia" />
      <div class="wrap">
        <h2>{props.school} · Wikipedia offline</h2>
        <ClockWeekWarning trusted={props.data.clockTrusted} />
        <Show when={props.data.instances.length === 0}>
          <p>No data</p>
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
