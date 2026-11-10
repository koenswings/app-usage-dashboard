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
});
