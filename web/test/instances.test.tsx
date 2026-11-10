import { render } from '@solidjs/testing-library';
import { InstanceBreakdown } from '../src/pages/InstanceBreakdown';
import { instancesFor, SAMPLE_WEEK, DEP_NHARIRA } from '../src/mock/data';

describe('instance breakdown', () => {
  it('keeps unlisted and demo instances on their own lines', () => {
    const data = instancesFor(DEP_NHARIRA, SAMPLE_WEEK);
    const { getByTestId } = render(() => (
      <InstanceBreakdown data={data} school="Nharira" />
    ));
    const own = getByTestId('instance-row-kolibri-a1b2c3');
    const demo = getByTestId('instance-row-kolibri-demo');
    const unlisted = getByTestId('instance-row-kolibri-unlisted-62561');
    expect(own).not.toBe(demo);
    expect(own).not.toBe(unlisted);
    expect(demo.textContent).toMatch(/Demo/);
    expect(unlisted.textContent).toMatch(/unlisted/);
    expect(unlisted.textContent).toMatch(/unlistedBorrowed/);
  });
});
