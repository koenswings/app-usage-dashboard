import type { AppSetupStatus, SetupPart, SetupStatus } from '../api/types';

/** Short words for one-line details (fleet card). */
const SHORT: Record<SetupPart, string> = {
  coach: 'coach',
  class: 'class',
  enrolledLearner: 'enrolment',
  teacherBeyondSeed: 'Nextcloud teachers',
  learnerBeyondSeed: 'Nextcloud learners',
  noOwnKolibri: 'no own Kolibri',
  noOwnNextcloud: 'no own Nextcloud',
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

function uniqueParts(status: SetupStatus, key: 'missing' | 'unknown'): SetupPart[] {
  const parts: SetupPart[] = [];
  for (const app of [status.kolibri, status.nextcloud]) {
    for (const part of app?.[key] ?? []) {
      if (!parts.includes(part)) parts.push(part);
    }
  }
  return parts;
}

/** One-line Set up detail from the collector verdict; "—" when there is nothing to say. */
export function setupDetail(status: SetupStatus | null | undefined): string {
  if (!status) return '—';
  const missing = uniqueParts(status, 'missing');
  const unknown = uniqueParts(status, 'unknown');
  if (status.complete === true) {
    const apps = [status.kolibri ? 'Kolibri' : null, status.nextcloud ? 'Nextcloud' : null].filter(Boolean);
    return apps.length > 0 ? `Own ${apps.join(' and ')} set up` : 'Set up';
  }
  const parts: string[] = [];
  if (missing.length > 0) parts.push(`Missing: ${missing.map(setupPartShort).join(', ')}`);
  if (unknown.length > 0) {
    const apps = [
      status.kolibri && status.kolibri.unknown.length > 0 ? 'Kolibri' : null,
      status.nextcloud && status.nextcloud.unknown.length > 0 ? 'Nextcloud' : null,
    ].filter(Boolean);
    parts.push(`${apps.join(' and ')} not known`);
  }
  if (parts.length === 0) return '—';
  return parts.join(' · ');
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
  const noOwn = app.missing.filter(isNoOwnPart);
  const otherMissing = app.missing.filter((part) => !isNoOwnPart(part));
  if (noOwn.length > 0) sentences.push(`${noOwn.map(setupPartLong).join('. ')}.`);
  if (otherMissing.length > 0) sentences.push(`Missing ${partsPhrase(otherMissing)}.`);
  if (app.unknown.length > 0) sentences.push(`Not known yet: ${partsPhrase(app.unknown)}.`);
  if (sentences.length === 0) sentences.push('No data this week.');
  return sentences.join(' ');
}
