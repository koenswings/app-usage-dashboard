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

  it('places a single known segment on the school-week calendar instead of stretching it', () => {
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
    const flexOf = (el: Element): number => {
      const match = /flex:\s*([0-9.]+)/.exec(el.getAttribute('style') || '');
      return match ? Number(match[1]) : NaN;
    };
    const on = container.querySelector('[data-state="on"]');
    const pads = [...container.querySelectorAll('.presence-seg--pad')];
    expect(on).not.toBeNull();
    expect(pads.length).toBe(2);
    const onFlex = flexOf(on!);
    const padFlex = pads.reduce((sum, el) => sum + flexOf(el), 0);
    expect(onFlex).toBeGreaterThan(0);
    expect(onFlex).toBeLessThan(padFlex);
  });
});
