import type { AppSetupStatus, SetupPart, SetupStatus } from '../api/types';

/** Short words for one-line details (fleet card). */
const SHORT: Record<SetupPart, string> = {
  coach: 'coach',
  class: 'class',
  enrolledLearner: 'enrolment',
  teacherBeyondSeed: 'Nextcloud teachers',
  learnerBeyondSeed: 'Nextcloud learners',
};

/** Plain words for the school page; the app ("in the own Kolibri") is added by the sentence. */
const LONG: Record<SetupPart, string> = {
  coach: 'a coach',
  class: 'a class',
  enrolledLearner: 'learners enrolled in a class',
  teacherBeyondSeed: 'teacher accounts beyond the seeds',
  learnerBeyondSeed: 'learner accounts beyond the seeds',
};

const PART_APP: Record<SetupPart, 'Kolibri' | 'Nextcloud'> = {
  coach: 'Kolibri',
  class: 'Kolibri',
  enrolledLearner: 'Kolibri',
  teacherBeyondSeed: 'Nextcloud',
  learnerBeyondSeed: 'Nextcloud',
};

function listWords(words: string[]): string {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

function partsPhrase(parts: SetupPart[]): string {
  const apps = [...new Set(parts.map((part) => PART_APP[part]))];
  return apps
    .map((app) => `${listWords(parts.filter((part) => PART_APP[part] === app).map(setupPartLong))} in the own ${app}`)
    .join('; ');
}

export function setupPartShort(part: SetupPart): string {
  return SHORT[part] ?? part;
}

export function setupPartLong(part: SetupPart): string {
  return LONG[part] ?? part;
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

export type AppSetupWord = 'Set up' | 'Not set up' | 'No data' | 'No own copy';

export function appSetupWord(app: AppSetupStatus | null | undefined): AppSetupWord {
  if (app === null || app === undefined) return 'No own copy';
  if (app.complete === true) return 'Set up';
  if (app.complete === false) return 'Not set up';
  return 'No data';
}

/** Plain-words explanation for one app on the school page. */
export function appSetupSentence(app: AppSetupStatus | null | undefined): string {
  if (app === null || app === undefined) return 'The school has no own copy this week, so it does not count.';
  const sentences: string[] = [];
  if (app.complete === true) sentences.push('Every requirement is met.');
  if (app.missing.length > 0) sentences.push(`Missing ${partsPhrase(app.missing)}.`);
  if (app.unknown.length > 0) sentences.push(`Not known yet: ${partsPhrase(app.unknown)}.`);
  if (sentences.length === 0) sentences.push('No data this week.');
  return sentences.join(' ');
}
