import { healthVersionLabel } from '../src/lib/health';
import { weekClockTrusted } from '../src/api/types';

describe('healthVersionLabel', () => {
  it('formats version and a short commit, and ignores a leading v', () => {
    expect(healthVersionLabel({
      version: '1.0',
      commit: '0d929618656ec82819f29207613c88ad7813a0f1',
    })).toBe('v1.0 · 0d92961');
    expect(healthVersionLabel({ version: 'v1.0', commit: 'abc1234' })).toBe('v1.0 · abc1234');
  });

  it('hides the label when both fields are missing, and shows whichever is present', () => {
    expect(healthVersionLabel(null)).toBeNull();
    expect(healthVersionLabel({})).toBeNull();
    expect(healthVersionLabel({ version: '1.0', commit: null })).toBe('v1.0');
    expect(healthVersionLabel({ commit: '0d92961' })).toBe('0d92961');
  });
});

describe('weekClockTrusted', () => {
  it('is true when there are no ok days (clock is null) and false only for an unsynced ok day', () => {
    expect(weekClockTrusted([])).toBe(true);
    expect(weekClockTrusted([{ clock: null }, { clock: null }])).toBe(true);
    expect(weekClockTrusted([{ clock: { synced: true, correctedBoots: 0 } }])).toBe(true);
    expect(weekClockTrusted([
      { clock: null },
      { clock: { synced: false, correctedBoots: 1 } },
    ])).toBe(false);
  });
});
