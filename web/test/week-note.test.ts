import { noDataThisWeekNote } from '../src/lib/week';

describe('noDataThisWeekNote', () => {
  it('is silent when the latest data week is also today', () => {
    expect(noDataThisWeekNote(true, '2026-11-09', '2026-11-09')).toBeNull();
  });

  it('explains when currentWeekHasData is false', () => {
    expect(noDataThisWeekNote(false, '2026-11-09', '2026-11-09')).toBe(
      'No data for this week yet, showing the week of 9 Nov 2026',
    );
  });

  it('explains when today has no data and an older week is shown', () => {
    expect(noDataThisWeekNote(true, '2026-11-02', '2026-11-09')).toBe(
      'No data for this week yet, showing the week of 2 Nov 2026',
    );
  });
});
