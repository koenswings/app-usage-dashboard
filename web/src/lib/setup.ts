import type { AppSetupStatus, SetupPart, SetupStatus } from '../api/types';

/** Short words for one-line details (fleet card). */
const SHORT: Record<SetupPart, string> = {
  coach: 'coach',
  class: 'class',
  enrolledLearner: 'enrolment',
  teacherBeyondSeed: 'teachers',
  learnerBeyondSeed: 'learners',
  noOwnKolibri: 'no own copy',
  noOwnNextcloud: 'no own copy',
};

/** Plain words for the school page; the app ("in the own Kolibri") is added by the sentence. */
const LONG: Record<SetupPart, string> = {
  coach: 'a coach',
  class: 'a class',
  enrolledLearner: 'learners enrolled in a class',
  teacherBeyondSeed: 'teacher accounts beyond the seeds',
  learnerBeyondSeed: 'learner accounts beyond the seeds',
  noOwnKolibri: 'The school has no own Kolibri copy',
  noOwnNextcloud: 'The school has no own Nextcloud copy',
};

const PART_APP: Record<SetupPart, 'Kolibri' | 'Nextcloud'> = {
  coach: 'Kolibri',
  class: 'Kolibri',
  enrolledLearner: 'Kolibri',
  teacherBeyondSeed: 'Nextcloud',
  learnerBeyondSeed: 'Nextcloud',
  noOwnKolibri: 'Kolibri',
  noOwnNextcloud: 'Nextcloud',
};

const NO_OWN_PARTS: readonly SetupPart[] = ['noOwnKolibri', 'noOwnNextcloud'];

function isNoOwnPart(part: SetupPart): boolean {
  return (NO_OWN_PARTS as readonly string[]).includes(part);
}

function listWords(words: string[]): string {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

function appOf(part: SetupPart): 'Kolibri' | 'Nextcloud' | null {
  return PART_APP[part] ?? null;
}

function partsPhrase(parts: SetupPart[]): string {
  // noOwn… (and any unknown code) must not become "… in the own undefined"
  // or leak a raw code. noOwn… strings are already complete sentences.
  const standalone = parts.filter((part) => isNoOwnPart(part) || appOf(part) === null);
  const rest = parts.filter((part) => !standalone.includes(part));
  const phrases: string[] = standalone.map(setupPartLong);
  const apps = [...new Set(rest.map(appOf).filter((app): app is 'Kolibri' | 'Nextcloud' => app != null))];
  for (const app of apps) {
    phrases.push(`${listWords(rest.filter((part) => appOf(part) === app).map(setupPartLong))} in the own ${app}`);
  }
  return phrases.join('; ');
}

export function setupPartShort(part: SetupPart): string {
  return SHORT[part] ?? 'a requirement';
}

export function setupPartLong(part: SetupPart): string {
  return LONG[part] ?? 'a requirement';
}

/** Missing parts that are not also unknown: unknown is not a confirmed miss. */
export function confirmedMissing(app: AppSetupStatus): SetupPart[] {
  const unknown = new Set(app.unknown);
  return app.missing.filter((part) => !unknown.has(part));
}

function appFleetDetail(name: 'Kolibri' | 'Nextcloud', app: AppSetupStatus | null | undefined): string | null {
  if (!app) return null;
  const missing = confirmedMissing(app);
  const unknown = app.unknown;
  if (missing.length === 0 && unknown.length === 0) return null;
  const bits: string[] = [];
  const noOwn = missing.filter(isNoOwnPart);
  const other = missing.filter((part) => !isNoOwnPart(part));
  if (noOwn.length > 0) bits.push('no own copy');
  if (other.length > 0) bits.push(other.map(setupPartShort).join(', '));
  if (unknown.length > 0) bits.push('not known');
  return `${name}: ${bits.join('; ')}`;
}

/** One-line Set up detail for the fleet card; "—" when there is nothing to say. */
export function setupDetail(status: SetupStatus | null | undefined): string {
  if (!status) return '—';
  if (status.complete === true) {
    const apps = [status.kolibri ? 'Kolibri' : null, status.nextcloud ? 'Nextcloud' : null].filter(Boolean);
    return apps.length > 0 ? `Own ${apps.join(' and ')} set up` : 'Set up';
  }
  const parts = [
    appFleetDetail('Kolibri', status.kolibri),
    appFleetDetail('Nextcloud', status.nextcloud),
  ].filter((part): part is string => part != null);
  return parts.length > 0 ? parts.join(' · ') : '—';
}

export type AppSetupWord = 'Set up' | 'Not set up' | 'No data';

export function appSetupWord(app: AppSetupStatus | null | undefined): AppSetupWord {
  if (app === null || app === undefined) return 'No data';
  if (app.complete === true) return 'Set up';
  if (app.complete === false) return 'Not set up';
  return 'No data';
}

/** Plain-words explanation for one app on the school page. */
export function appSetupSentence(app: AppSetupStatus | null | undefined): string {
  if (app === null || app === undefined) return 'No data this week.';
  const sentences: string[] = [];
  if (app.complete === true) sentences.push('Every requirement is met.');
  const missing = confirmedMissing(app);
  const noOwn = missing.filter(isNoOwnPart);
  const otherMissing = missing.filter((part) => !isNoOwnPart(part));
  if (noOwn.length > 0) sentences.push(`${noOwn.map(setupPartLong).join('. ')}.`);
  if (otherMissing.length > 0) sentences.push(`Missing ${partsPhrase(otherMissing)}.`);
  if (app.unknown.length > 0) sentences.push(`Not known yet: ${partsPhrase(app.unknown)}.`);
  if (sentences.length === 0) sentences.push('No data this week.');
  return sentences.join(' ');
}
