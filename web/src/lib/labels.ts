import type { HookStatus, SkipReason } from '../api/types';

export function appDisplayName(app: string): string {
  switch (app) {
    case 'kolibri':
      return 'Kolibri';
    case 'nextcloud':
      return 'Nextcloud';
    case 'kiwix':
      return 'Wikipedia';
    default:
      return app;
  }
}

export function nextcloudAppName(appId: string): string {
  switch (appId) {
    case 'files':
      return 'Files';
    case 'richdocuments':
      return 'Office';
    case 'photos':
      return 'Photos';
    default:
      return appId;
  }
}

export function roleLabel(role: string): string {
  switch (role) {
    case 'learner':
      return 'Learner';
    case 'teacher':
      return 'Teacher';
    case 'coach':
      return 'Teacher';
    case 'admin':
      return 'Admin';
    case 'guest':
      return 'Guest';
    default:
      return role;
  }
}

export function copyKindLabel(demo: boolean, listed: boolean): string {
  if (demo) return 'Demo';
  if (!listed) return 'Extra copy';
  return 'School’s own';
}

export function hookStatusLabel(status: HookStatus, skipReason?: SkipReason): string {
  switch (status) {
    case 'ok':
      return 'Measured';
    case 'timeout':
      return 'Timed out';
    case 'failed':
      return 'Measurement failed';
    case 'invalid':
      return 'Measurement was invalid';
    case 'skipped':
      return skipReasonLabel(skipReason);
    case 'unlisted-no-hook':
      return 'Extra copy, no measurement available';
    case 'no-hook':
      return 'No measurement available';
  }
}

export function skipReasonLabel(reason?: SkipReason): string {
  switch (reason) {
    case 'backup':
      return 'Skipped while a backup was running';
    case 'update':
      return 'Skipped while an update was running';
    case 'move':
      return 'Skipped while the app was being moved';
    case 'temperature':
      return 'Skipped because the kit was too hot';
    default:
      return 'Skipped';
  }
}

/**
 * Plain-English reason for a missing payload. Distinguishes a stub whose
 * measurement failed (`collectedAt` set) from an instance that has never
 * been collected (`collectedAt` null).
 */
export function noDataReason(
  status: HookStatus,
  skipReason?: SkipReason,
  collectedAt?: string | null,
): string {
  if (status === 'ok') return 'No data';
  if (!collectedAt) {
    if (status === 'unlisted-no-hook' || status === 'no-hook') {
      return `No data — ${hookStatusLabel(status, skipReason).toLowerCase()}`;
    }
    return 'No data — nothing has been collected yet';
  }
  return `No data — ${hookStatusLabel(status, skipReason).toLowerCase()}`;
}
