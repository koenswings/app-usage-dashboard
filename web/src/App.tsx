import { Show, createEffect, createSignal, onCleanup, onMount } from 'solid-js';
import { api } from './api/client';
import type { MetaResponse, SessionResponse, WeeksResponse } from './api/types';
import { Footer, Header, SampleNote } from './components/Header';
import { WeekPicker } from './components/WeekPicker';
import { parseHash, toHash, type Route } from './lib/route';
import { formatWeekLabel, fridayOf } from './lib/week';
import { FleetOverview } from './pages/FleetOverview';
import { HelpTimeline } from './pages/HelpTimeline';
import { InstanceBreakdown } from './pages/InstanceBreakdown';
import { KolibriPage } from './pages/KolibriPage';
import { LoginPage } from './pages/LoginPage';
import { NextcloudPage } from './pages/NextcloudPage';
import { SchoolWeek } from './pages/SchoolWeek';
import { UplinkHistory } from './pages/UplinkHistory';
import { WikipediaPage } from './pages/WikipediaPage';


export default function App() {
  const [session, setSession] = createSignal<SessionResponse | null>(null);
  const [route, setRoute] = createSignal<Route>(parseHash(window.location.hash));
  const [meta, setMeta] = createSignal<MetaResponse | null>(null);
  const [weeks, setWeeks] = createSignal<WeeksResponse | null>(null);
  const [kits, setKits] = createSignal<{ deploymentId: string; school: string }[]>([]);

  const week = () => route().week || weeks()?.currentWeekStart || '2026-11-02';
  const schoolName = (deploymentId: string) =>
    kits().find((item) => item.deploymentId === deploymentId)?.school ?? deploymentId;

  const loadShell = async () => {
    const [nextMeta, nextWeeks, nextKits] = await Promise.all([
      api.getMeta(),
      api.getWeeks(),
      api.getKits(),
    ]);
    setMeta(nextMeta);
    setWeeks(nextWeeks);
    setKits(nextKits.kits.map((item) => ({ deploymentId: item.deploymentId, school: item.school })));
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
    void api.getSession().then(async (current) => {
      setSession(current);
      if (current.authenticated) await loadShell();
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
      navigate({ name: 'overview', week: weeks()?.currentWeekStart || week() });
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
    setSession(next);
    await loadShell();
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
              weekLabel={formatWeekLabel(week(), fridayOf(week()))}
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
            <Show when={pageLoading()}>
              <p class="wrap">Loading…</p>
            </Show>
            <Show when={pageError()}>
              <p class="wrap">Could not load this page.</p>
            </Show>
            <Show when={page().kind === 'overview'}>
              <FleetOverview
                overview={page().data}
                headerTimeZone={meta()?.headerTimeZone ?? 'Europe/Brussels'}
              />
            </Show>
            <Show when={page().kind === 'school'}>
              <SchoolWeek
                data={page().data}
                headerTimeZone={meta()?.headerTimeZone ?? 'Europe/Brussels'}
              />
            </Show>
            <Show when={page().kind === 'kolibri'}>
              <KolibriPage
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
              />
            </Show>
            <Show when={page().kind === 'nextcloud'}>
              <NextcloudPage
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
              />
            </Show>
            <Show when={page().kind === 'wikipedia'}>
              <WikipediaPage
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? route().deploymentId ?? ''))}
                hourlyChartMinWeeklyViews={meta()?.hourlyChartMinWeeklyViews ?? 20}
              />
            </Show>
            <Show when={page().kind === 'help'}>
              <HelpTimeline
                deploymentId={route().deploymentId ?? ''}
                week={week()}
                school={schoolName(route().deploymentId ?? '')}
                data={page().data}
                onCreate={async (input) => {
                  await api.createHelpEvent(route().deploymentId ?? '', input);
                  setReloadToken((value) => value + 1);
                }}
              />
            </Show>
            <Show when={page().kind === 'uplink'}>
              <UplinkHistory
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? ''))}
                segments={page().segments ?? []}
              />
            </Show>
            <Show when={page().kind === 'instances'}>
              <InstanceBreakdown
                data={page().data}
                school={schoolName(String(page().data?.deploymentId ?? ''))}
              />
            </Show>
            <Footer />
          </div>
        </Show>
      )}
    </Show>
  );
}
