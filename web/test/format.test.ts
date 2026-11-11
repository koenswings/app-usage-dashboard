import { formatLocalDateTime, resolveTimeZone } from '../src/lib/format';

const BRUSSELS = 'Europe/Brussels';

describe('formatLocalDateTime', () => {
  it('formats a winter UTC stamp in Europe/Brussels as CET', () => {
    expect(formatLocalDateTime('2026-11-11T11:45:22+00:00', BRUSSELS)).toBe(
      '11 Nov 2026, 12:45 CET',
    );
  });

  it('formats a summer UTC stamp in Europe/Brussels as CEST', () => {
    expect(formatLocalDateTime('2026-07-11T11:45:22+00:00', BRUSSELS)).toBe(
      '11 Jul 2026, 13:45 CEST',
    );
  });

  it('returns the original string when the stamp is not a valid date', () => {
    expect(formatLocalDateTime('not-a-date', BRUSSELS)).toBe('not-a-date');
  });

  it('returns an empty string when the stamp is missing', () => {
    expect(formatLocalDateTime(null, BRUSSELS)).toBe('');
  });
});

describe('resolveTimeZone', () => {
  it('keeps a valid explicit zone', () => {
    expect(resolveTimeZone('Europe/Brussels')).toBe('Europe/Brussels');
    expect(resolveTimeZone('Africa/Harare')).toBe('Africa/Harare');
  });

  it('falls back to Europe/Brussels when no zone is available', () => {
    const Original = Intl.DateTimeFormat;
    const Mock = function (
      this: Intl.DateTimeFormat,
      locales?: string | string[],
      options?: Intl.DateTimeFormatOptions,
    ) {
      if (options?.timeZone) return new Original(locales, options);
      const instance = new Original(locales, options);
      return new Proxy(instance, {
        get(target, prop, receiver) {
          if (prop === 'resolvedOptions') {
            return () => ({ ...target.resolvedOptions(), timeZone: undefined });
          }
          const value = Reflect.get(target, prop, receiver) as unknown;
          return typeof value === 'function' ? (value as (...args: unknown[]) => unknown).bind(target) : value;
        },
      });
    } as unknown as typeof Intl.DateTimeFormat;
    Mock.supportedLocalesOf = Original.supportedLocalesOf;
    Intl.DateTimeFormat = Mock;
    try {
      expect(resolveTimeZone(null)).toBe(BRUSSELS);
      expect(resolveTimeZone('')).toBe(BRUSSELS);
      expect(resolveTimeZone('Not/AZone')).toBe(BRUSSELS);
    } finally {
      Intl.DateTimeFormat = Original;
    }
  });
});
