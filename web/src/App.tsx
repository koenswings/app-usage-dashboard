import { Show, createEffect, createSignal, onCleanup, onMount } from 'solid-js';
import { api } from './api/client';
import { API_SCHEMA } from './api/types';
import type { HealthResponse, MetaResponse, ScorecardThresholds, SessionResponse, ThresholdsSettingsResponse, WeeksResponse } from './api/types';
import { Footer, Header, SampleNote } from './components/Header';
import { WeekPicker } from './components/WeekPicker';
import { resolveHourlyChartMinWeeklyViews } from './config/display';
import { DEFAULT_THRESHOLDS, resolveEffectiveThresholds } from './config/thresholds';
import { parseHash, toHash, type Route } from './lib/route';
import { healthVersionLabel } from './lib/health';
import { formatWeekLabel, fridayOf, noDataThisWeekNote } from './lib/week';
import { FleetOverview } from './pages/FleetOverview';
import { HelpTimeline } from './pages/HelpTimeline';
import { InstanceBreakdown } from './pages/InstanceBreakdown';
import { KolibriPage } from './pages/KolibriPage';
import { LoginPage } from './pages/LoginPage';
import { NextcloudPage } from './pages/NextcloudPage';
import { SchoolWeek } from './pages/SchoolWeek';
import { UplinkHistory } from './pages/UplinkHistory';
import { SettingsPage } from './pages/SettingsPage';
import { WikipediaPage } from './pages/WikipediaPage';


export default function App() {
  const [session, setSession] = createSignal<SessionResponse | null>(null);
  const [route, setRoute] = createSignal<Route>(parseHash(window.location.hash));
  const [meta, setMeta] = createSignal<MetaResponse | null>(null);
  const [weeks, setWeeks] = createSignal<WeeksResponse | null>(null);
  const [kits, setKits] = createSignal<{ deploymentId: string; school: string; monitoringEnabled: boolean }[]>([]);
  const [health, setHealth] = createSignal<HealthResponse | null>(null);
  const [thresholdSettings, setThresholdSettings] = createSignal<ThresholdsSettingsResponse | null>(null);
  const [settingsWritable, setSettingsWritable] = createSignal(false);

  const week = () => route().week || weeks()?.currentWeekStart || '';
  const effectiveThresholds = (): ScorecardThresholds =>
    resolveEffectiveThresholds(meta()?.thresholds, thresholdSettings()?.thresholds);
  const schoolName = (deploymentId: string) =>
    kits().find((item) => item.deploymentId === deploymentId)?.school ?? deploymentId;

  const monitoringByDeployment = (): Record<string, boolean> => {
    const map: Record<string, boolean> = {};
    for (const kit of kits()) map[kit.deploymentId] = kit.monitoringEnabled;
    return map;
  };

  const kitMonitoring = (deploymentId: string): boolean | undefined =>
    kits().find((item) => item.deploymentId === deploymentId)?.monitoringEnabled;

  const weekFallbackNote = () => {
    const listed = weeks();
    if (!listed) return null;
    if (week() && week() !== listed.currentWeekStart) return null;
    return noDataThisWeekNote(listed.currentWeekHasData, listed.currentWeekStart, listed.todayWeekStart);
  };

  const loadShell = async () => {
    const [nextMeta, nextWeeks, nextKits, nextHealth] = await Promise.all([
      api.getMeta(),
      api.getWeeks(),
      api.getKits(),
      api.getHealth().catch(() => null),
    ]);
    setMeta(nextMeta);
    setWeeks(nextWeeks);
    setKits(nextKits.kits.map((item) => ({
      deploymentId: item.deploymentId,
      school: item.school,
      monitoringEnabled: item.monitoringEnabled,
    })));
    setHealth(nextHealth);
    try {
      const settings = await api.getThresholds();
      setThresholdSettings(settings);
      setSettingsWritable(true);
    } catch {
      setThresholdSettings(null);
      setSettingsWritable(false);
    }
  };

  const navigate = (next: Route) => {
    const hash = toHash(next);
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
    setRoute(parseHash(hash));
  };

  onMount(() => {
    const onHash = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHash);
    void api.getSession()
      .then(async (current) => {
        if (current.authenticated) await loadShell();
        setSession(current);
      })
      .catch(() => {
        setSession({ schema: API_SCHEMA, authenticated: false, user: null });
      });
  });

  createEffect(() => {
    const current = session();
    const currentRoute = route();
    if (!current) return;
    if (!current.authenticated && currentRoute.name !== 'login') {
      navigate({ name: 'login' });
    }
    if (current.authenticated && currentRoute.name === 'login') {
      const start = weeks()?.currentWeekStart;
      if (start) navigate({ name: 'overview', week: start });
    }
  });

  const [reloadToken, setReloadToken] = createSignal(0);
  const [page, setPage] = createSignal<{ kind: string; data?: any; segments?: any }>({ kind: 'none' });
  const [pageLoading, setPageLoading] = createSignal(false);
  const [pageError, setPageError] = createSignal(false);

  createEffect(() => {
    const current = route();
    const authed = Boolean(session()?.authenticated);
    const weekStart = week();
    const deploymentId = current.deploymentId ?? '';
    const name = current.name;
    reloadToken();
    let cancelled = false;
    if (!authed || name === 'login') {
      setPage({ kind: 'none' });
      setPageLoading(false);
      setPageError(false);
      return;
    }
    if (name === 'settings') {
      setPage({ kind: 'settings' as const });
      setPageLoading(false);
      setPageError(false);
      return;
    }
    if (!weekStart) {
      setPage({ kind: 'none' });
      setPageLoading(true);
      setPageError(false);
      return;
    }
    setPageLoading(true);
    setPageError(false);
    const load = async () => {
      switch (name) {
        case 'overview':
          return { kind: 'overview' as const, data: await api.getOverview(weekStart) };
        case 'school':
          return { kind: 'school' as const, data: await api.getSchoolWeek(weekStart, deploymentId) };
        case 'kolibri':
          return { kind: 'kolibri' as const, data: await api.getKolibri(weekStart, deploymentId) };
        case 'nextcloud':
          return { kind: 'nextcloud' as const, data: await api.getNextcloud(weekStart, deploymentId) };
        case 'wikipedia':
          return { kind: 'wikipedia' as const, data: await api.getKiwix(weekStart, deploymentId) };
        case 'help':
          return { kind: 'help' as const, data: await api.getHelpEvents(deploymentId) };
        case 'uplink': {
          const [data, presence] = await Promise.all([
            api.getUplink(weekStart, deploymentId),
            api.getPresence(weekStart, deploymentId),
          ]);
          return { kind: 'uplink' as const, data, segments: presence.segments };
        }
        case 'instances':
          return { kind: 'instances' as const, data: await api.getInstances(weekStart, deploymentId) };
        default:
          return { kind: 'none' as const };
      }
    };
    void load()
      .then((result) => {
        if (!cancelled) {
          setPage(result);
          setPageLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPageError(true);
          setPageLoading(false);
        }
      });
    onCleanup(() => {
      cancelled = true;
    });
  });

  const changeWeek = (next: string) => {
    const current = route();
    navigate({
      ...current,
      name: current.name === 'login' ? 'overview' : current.name,
      week: next,
    });
  };

  const handleLogin = async (next: SessionResponse) => {
    await loadShell();
    setSession(next);
    navigate({ name: 'overview', week: weeks()?.currentWeekStart || week() });
  };

  const handleLogout = async () => {
    const next = await api.logout();
    setSession(next);
    navigate({ name: 'login' });
  };

  return (
    <Show when={session()} fallback={<p class="wrap">Loading…</p>}>
      {(current) => (
        <Show
          when={current().authenticated}
          fallback={<LoginPage onLoggedIn={(next) => void handleLogin(next)} />}
        >
          <div class="app">
            <Header
              weekLabel={week() ? formatWeekLabel(week(), fridayOf(week())) : 'Week'}
              headerTimeZone={meta()?.headerTimeZone ?? 'Europe/Brussels'}
              username={current().user?.username ?? 'operator'}
              onLogout={() => void handleLogout()}
              weekPicker={
                <WeekPicker
                  week={week()}
                  weeks={weeks()?.weeks ?? [week()]}
                  onChange={changeWeek}
                />
              }
            />
            <Show when={meta()?.sampleData}>
              <SampleNote />
            </Show>
            <Show when={weekFallbackNote()}>
              {(text) => (
                <p class="status-banner" data-testid="week-fallback-note" role="status">{text()}</p>
              )}
            </Show>
            <Show when={pageLoading()}>
              <p class="wrap status-banner" role="status">Loading…</p>
            </Show>
            <Show when={pageError()}>
              <p class="wrap status-banner status-banner--error" role="alert">Could not load this page.</p>
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'overview'}>
              <FleetOverview
                overview={page().data}
                headerTimeZone={meta()?.headerTimeZone ?? 'Europe/Brussels'}
                monitoringByDeployment={monitoringByDeployment()}
                thresholds={effectiveThresholds()}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'school'}>
              <SchoolWeek
                data={page().data}
                headerTimeZone={meta()?.headerTimeZone ?? 'Europe/Brussels'}
                thresholds={effectiveThresholds()}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'kolibri'}>
              <KolibriPage
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'nextcloud'}>
              <NextcloudPage
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'wikipedia'}>
              <WikipediaPage
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
                hourlyChartMinWeeklyViews={resolveHourlyChartMinWeeklyViews(meta()?.hourlyChartMinWeeklyViews)}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'help'}>
              <HelpTimeline
                deploymentId={route().deploymentId ?? ''}
                week={week()}
                school={schoolName(route().deploymentId ?? '')}
                data={page().data}
                thresholds={effectiveThresholds()}
                onCreate={async (input) => {
                  await api.createHelpEvent(route().deploymentId ?? '', input);
                  setReloadToken((value) => value + 1);
                }}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'uplink'}>
              <UplinkHistory
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
                segments={page().segments ?? []}
                monitoringEnabled={kitMonitoring(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'instances'}>
              <InstanceBreakdown
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? ''))}
              />
            </Show>
            <Show when={!pageLoading() && !pageError() && page().kind === 'settings'}>
              <SettingsPage
                week={week()}
                thresholds={effectiveThresholds()}
                defaults={thresholdSettings()?.defaults ?? DEFAULT_THRESHOLDS}
                updatedAt={thresholdSettings()?.updatedAt ?? null}
                updatedBy={thresholdSettings()?.updatedBy ?? null}
                writable={settingsWritable()}
                onSave={async (thresholds) => {
                  const result = await api.putThresholds({ thresholds });
                  setThresholdSettings(result);
                  setMeta((current) => current ? { ...current, thresholds: result.thresholds, thresholdsConfigured: true } : current);
                  return result;
                }}
                onReset={async () => {
                  const result = await api.putThresholds({ reset: true });
                  setThresholdSettings(result);
                  setMeta((current) => current ? { ...current, thresholds: result.thresholds, thresholdsConfigured: true } : current);
                  return result;
                }}
              />
            </Show>
            <Footer versionLabel={healthVersionLabel(health())} />
          </div>
        </Show>
      )}
    </Show>
  );
}
