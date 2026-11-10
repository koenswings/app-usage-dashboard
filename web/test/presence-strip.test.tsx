import { render } from '@solidjs/testing-library';
import { PresenceStrip } from '../src/components/shared/PresenceStrip';
import { nhariraSegments } from '../src/mock/data';

describe('PresenceStrip', () => {
  it('renders hatched grey words for gapUnknown and collectorGap, never dark', () => {
    const { container, getAllByText } = render(() => (
      <PresenceStrip
        segments={nhariraSegments}
        timeZone="Africa/Harare"
        utcOffset="+02:00"
        timeZoneLabel="kit local time (Africa/Harare, UTC+2)"
        weekStart="2026-11-02"
        weekEnd="2026-11-06"
      />
    ));

    expect(getAllByText('Gap, length unknown').length).toBeGreaterThan(0);
    expect(getAllByText('Collector gap').length).toBeGreaterThan(0);
    expect(container.querySelector('[data-state="on"]')).not.toBeNull();
    expect(container.querySelector('[data-state="off"]')).not.toBeNull();
    expect(container.querySelector('.presence-seg--gapUnknown')).not.toBeNull();
    expect(container.querySelector('.presence-seg--collectorGap')).not.toBeNull();
    expect(container.textContent).not.toMatch(/dark/i);
    expect(container.textContent).toMatch(/kit local time \(Africa\/Harare, UTC\+2\)/);
  });

  it('places a collector segment on the school-week calendar without inventing pad pieces', () => {
    const { container } = render(() => (
      <PresenceStrip
        segments={[
          {
            state: 'on',
            start: '2026-11-09T08:00:00+02:00',
            end: '2026-11-09T12:00:00+02:00',
            lengthKnown: true,
          },
        ]}
        timeZone="Africa/Harare"
        utcOffset="+02:00"
        timeZoneLabel="kit local time (Africa/Harare, UTC+2)"
        weekStart="2026-11-09"
        weekEnd="2026-11-13"
      />
    ));
    const on = container.querySelector('[data-state="on"]');
    expect(on).not.toBeNull();
    expect(container.querySelectorAll('.presence-seg--pad')).toHaveLength(0);
    const style = on?.getAttribute('style') || '';
    const left = Number(/left:\s*([0-9.]+)%/.exec(style)?.[1]);
    const width = Number(/width:\s*([0-9.]+)%/.exec(style)?.[1]);
    expect(left).toBeGreaterThan(0);
    expect(width).toBeGreaterThan(0);
    expect(width).toBeLessThan(20);
  });

  it('shows presence.summary under the strip when it is a sentence, and hides null', () => {
    const shown = render(() => (
      <PresenceStrip
        segments={nhariraSegments}
        timeZone="Africa/Harare"
        utcOffset="+02:00"
        timeZoneLabel="kit local time (Africa/Harare, UTC+2)"
        weekStart="2026-11-02"
        weekEnd="2026-11-06"
        summary="On 4 of 5 school days, 31 h in school hours"
      />
    ));
    expect(shown.getByTestId('presence-summary').textContent).toBe(
      'On 4 of 5 school days, 31 h in school hours',
    );

    const hidden = render(() => (
      <PresenceStrip
        segments={nhariraSegments}
        timeZone="Africa/Harare"
        utcOffset="+02:00"
        timeZoneLabel="kit local time (Africa/Harare, UTC+2)"
        weekStart="2026-11-02"
        weekEnd="2026-11-06"
        summary={null}
      />
    ));
    expect(hidden.queryByTestId('presence-summary')).toBeNull();
  });
});
