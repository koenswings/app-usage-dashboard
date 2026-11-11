import { For, Show, createSignal } from 'solid-js';
import type { HelpEvent, HelpEventsResponse, ScorecardThresholds } from '../api/types';
import { DEFAULT_THRESHOLDS, helpRulesText } from '../config/thresholds';
import { SchoolNav } from '../components/SchoolNav';
import { formatPercent } from '../lib/format';
import { formatWeekLabel, fridayOf } from '../lib/week';

interface HelpTimelineProps {
  deploymentId: string;
  week: string;
  school: string;
  data: HelpEventsResponse;
  thresholds?: ScorecardThresholds;
  onCreate: (input: { offeredOn: string; tutorialChapters: string[]; note: string }) => Promise<void>;
}

export function HelpTimeline(props: HelpTimelineProps) {
  const [offeredOn, setOfferedOn] = createSignal(props.week);
  const [chapters, setChapters] = createSignal('');
  const [note, setNote] = createSignal('');
  const [error, setError] = createSignal('');
  const [saving, setSaving] = createSignal(false);

  const eventIds = () => props.data.events.map((event) => event.id);
  const weekIds = () => props.data.weeklyTrend.map((row) => row.weekStart);

  const submit = async (event: Event) => {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      const tutorialChapters = chapters()
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean);
      await props.onCreate({ offeredOn: offeredOn(), tutorialChapters, note: note() });
      setNote('');
      setChapters('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not record the offer of help.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <SchoolNav deploymentId={props.deploymentId} week={props.week} current="help" />
      <div class="wrap">
        <h2>{props.school} · Help offered</h2>
        <p class="muted">
          Record when help was offered. The dashboard never invents an event and never
          decides to move a kit. Wording stays “offer help”.
        </p>
        <p class="help-rules" data-testid="help-rules">
          {helpRulesText(props.thresholds ?? DEFAULT_THRESHOLDS)}
          {' '}
          The collector computes the streak and the unused flag. The dashboard shows
          any help suggestions it sends and does not recompute them here.
        </p>
        <Show when={props.data.events.length === 0}>
          <p>No help has been recorded for this school yet.</p>
        </Show>
        <Show when={props.data.events.length > 0}>
        <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Offered on</th>
              <th>Chapters</th>
              <th>Note</th>
              <th>Recorded by</th>
            </tr>
          </thead>
          <tbody>
            <For each={eventIds()}>
              {(id) => {
                const row = () => props.data.events.find((item) => item.id === id);
                return (
                  <Show when={row()}>
                    {(item) => (
                      <tr>
                        <td>{item().offeredOn}</td>
                        <td>{item().tutorialChapters.join(', ') || '—'}</td>
                        <td>{item().note || '—'}</td>
                        <td>{item().createdBy}</td>
                      </tr>
                    )}
                  </Show>
                );
              }}
            </For>
          </tbody>
        </table>
        </div>
        </Show>
        <Show when={props.data.weeklyTrend.length > 0}>
        <h3 class="section-heading">Weekly trend (raw counts, not a grade)</h3>
        <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Week</th>
              <th>Learner minutes share</th>
              <th>Lessons visible</th>
              <th>Wikipedia views</th>
            </tr>
          </thead>
          <tbody>
            <For each={weekIds()}>
              {(id) => {
                const row = () => props.data.weeklyTrend.find((item) => item.weekStart === id);
                return (
                  <Show when={row()}>
                    {(item) => (
                      <tr>
                        <td>{formatWeekLabel(item().weekStart, fridayOf(item().weekStart))}</td>
                        <td>{formatPercent(item().scorecard.learnersOperate.learnerShareOfMinutes)}</td>
                        <td>{item().scorecard.teachingCycle.lessonsVisible ?? '—'}</td>
                        <td>{item().scorecard.wikipedia.pageViewsOwn ?? '—'}</td>
                      </tr>
                    )}
                  </Show>
                );
              }}
            </For>
          </tbody>
        </table>
        </div>
        </Show>
        <form class="panel" style={{ 'margin-top': '16px' }} onSubmit={submit} data-testid="help-event-form">
          <strong>Record that help was offered</strong>
          <div class="form-row">
            <label>
              Date offered
              <input type="date" value={offeredOn()} onInput={(event) => setOfferedOn(event.currentTarget.value)} required />
            </label>
            <label>
              Tutorial chapters
              <input
                value={chapters()}
                onInput={(event) => setChapters(event.currentTarget.value)}
                placeholder="3.3, 3.4, 4"
              />
            </label>
            <label>
              Note
              <input value={note()} onInput={(event) => setNote(event.currentTarget.value)} />
            </label>
          </div>
          <p class="login-error">{error()}</p>
          <button class="btn btn-primary" type="submit" disabled={saving()}>
            Offer help
          </button>
        </form>
      </div>
    </>
  );
}

export function helpEventIds(events: HelpEvent[]): string[] {
  return events.map((event) => event.id);
}
