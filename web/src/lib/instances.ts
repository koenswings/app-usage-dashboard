import { instanceKey } from '../api/types';

interface NamedInstance {
  instance?: string;
  instanceId?: string;
  name: string;
}

const MIN_SHORT_ID = 6;


/** The random tail of an instance id, e.g. "kolibri-2htevnk74t5hszft809" → "2htevnk74t5hszft809". */
function idTail(id: string): string {
  const parts = id.split('-').filter(Boolean);
  return parts.length > 0 ? parts[parts.length - 1] : id;
}

/**
 * Short ids for copies that share a display name on one page, keyed by
 * instance key. Copies with a unique name get no entry. Each short id is at
 * least six characters of the id's tail and grows until it is unique within
 * its name group.
 */
/** Six-character short form of one instance id (its random tail). */
export function shortInstanceId(id: string): string {
  return idTail(id).slice(0, MIN_SHORT_ID);
}

export function shortIdsForDuplicateNames<T extends NamedInstance>(
  instances: T[],
  displayName: (item: T) => string = (item) => item.name,
): Map<string, string> {
  const groups = new Map<string, string[]>();
  for (const item of instances) {
    const key = instanceKey(item);
    if (!key) continue;
    const name = displayName(item);
    const list = groups.get(name) ?? [];
    if (!list.includes(key)) list.push(key);
    groups.set(name, list);
  }
  const result = new Map<string, string>();
  for (const keys of groups.values()) {
    if (keys.length < 2) continue;
    const tails = keys.map(idTail);
    const longest = Math.max(...tails.map((tail) => tail.length));
    let length = Math.min(MIN_SHORT_ID, longest);
    while (length < longest && new Set(tails.map((tail) => tail.slice(0, length))).size < tails.length) {
      length += 1;
    }
    const unique = new Set(tails.map((tail) => tail.slice(0, length))).size === tails.length;
    keys.forEach((key, index) => {
      result.set(key, unique ? tails[index].slice(0, length) : key);
    });
  }
  return result;
}
