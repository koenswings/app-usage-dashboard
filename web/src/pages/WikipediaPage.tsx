import { For, Show } from 'solid-js';
import type { KiwixInstanceWeek, KiwixWeekResponse } from '../api/types';
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
          Hourly views are hidden below the weekly minimum ({props.minWeekly} page views)
          so a small school stays away from a per-hour picture.
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
  const articleIds = () => props.instance.topArticles.map((article) => article.title);

  return (
    <section class="panel instance-block" data-testid={`kiwix-instance-${props.instance.instanceId}`}>
      <strong>{props.instance.name}</strong>
      <div style={{ 'margin-top': '8px' }}>
        <span class="tag">{props.instance.listed ? 'listed' : 'unlisted'} · {props.instance.instanceId}</span>
        <Show when={props.instance.demo}><span class="tag tag--demo">Demo</span></Show>
      </div>
      <p class="muted">No accounts — page views and articles only, never a person.</p>
      <div class="scorecard-card__stats" style={{ border: 0, padding: 0, margin: '0 0 10px' }}>
        <div><strong>{props.instance.pageViews}</strong>page views</div>
        <div><strong>{props.instance.distinctArticles}</strong>articles</div>
        <div><strong>{props.instance.sessions}</strong>sessions</div>
      </div>
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
              const row = () => props.instance.topArticles.find((item) => item.title === id);
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
      <HourlyChart
        views={props.instance.byHour}
        pageViews={props.instance.pageViews}
        minWeekly={props.minWeekly}
      />
    </section>
  );
}

interface WikipediaPageProps {
  data: KiwixWeekResponse;
  school: string;
  hourlyChartMinWeeklyViews: number;
}

export function WikipediaPage(props: WikipediaPageProps) {
  const ids = () => props.data.instances.map((item) => item.instanceId);

  return (
    <>
      <SchoolNav deploymentId={props.data.deploymentId} week={props.data.weekStart} current="wikipedia" />
      <div class="wrap">
        <h2>{props.school} · Wikipedia offline</h2>
        <Show when={props.data.instances.length === 0}>
          <p>No data</p>
        </Show>
        <For each={ids()}>
          {(id) => {
            const instance = () => props.data.instances.find((item) => item.instanceId === id);
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
