#!/usr/bin/env node
// Usage: node script/check-compose.mjs [--tag <release tag>] [--release] <compose.yaml>...
//
// Default: every service's x-app-version label == x-app.version
// (and == --tag when given). Exit 1 on any problem.
//
// --release (idea#375 U-10, idea#461): every service must use a
// digest-pinned image (repo:tag@sha256:<64 hex>) with no build: block.
// The web service must be
//   ghcr.io/koenswings/usage-dashboard-web:<version>@sha256:<64 hex>
//   (a :<version>-<shortsha>@sha256:<64 hex> pin is also accepted)
// and the collector service must be
//   ghcr.io/koenswings/usage-dashboard-collector:<version>@sha256:<64 hex>
//   (same optional -<shortsha> suffix).
// Also (idea#446) an x-app.backup.verify block when the backup method is
// hook. Fails if a packaging placeholder (DIGEST_PLACEHOLDER, SHORTSHA,
// <DIGEST>) is still present.
//
// Engine idea#322 saveName() rejects a digest-only pin (no tag), so the
// release form is repo:tag@sha256:digest, not repo@sha256:digest.

import { readFileSync } from 'node:fs';

const PLACEHOLDER_RE = /DIGEST_PLACEHOLDER|<DIGEST>|SHORTSHA|REPLACE_ME_WITH_PUBLISHED_DIGEST/i;
const GHCR_PIN_RE = /^ghcr\.io\/koenswings\/usage-dashboard-web:\d+\.\d+[0-9A-Za-z._+-]*@sha256:[0-9a-f]{64}$/;
const COLLECTOR_PIN_RE = /^ghcr\.io\/koenswings\/usage-dashboard-collector:\d+\.\d+[0-9A-Za-z._+-]*@sha256:[0-9a-f]{64}$/;
// Same rule as agent-app-dev lib/check-compose.mjs TAG_DIGEST_PIN (idea#49).
const TAG_DIGEST_PIN = /^(?:[a-z0-9.-]+(?::[0-9]+)?\/)?[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)*:[A-Za-z0-9_][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}$/;

const stripQuotes = (value) => String(value).trim().replace(/^['"]|['"]$/g, '');

const labelOf = (text, serviceName) => {
  const block = serviceBlock(text, serviceName);
  if (!block) return undefined;
  const m = block.match(/^\s+x-app-version:\s*(.+)$/m);
  return m ? stripQuotes(m[1]) : undefined;
};

const serviceBlock = (text, serviceName) => {
  const lines = text.split('\n');
  let inServices = false;
  let capturing = false;
  const out = [];
  for (const line of lines) {
    if (line === 'services:') {
      inServices = true;
      capturing = false;
      continue;
    }
    if (inServices && /^\S/.test(line) && !line.startsWith('#')) {
      inServices = false;
      capturing = false;
    }
    if (inServices && new RegExp(`^  ${serviceName}:\\s*$`).test(line)) {
      capturing = true;
      out.length = 0;
      out.push(line);
      continue;
    }
    if (capturing) {
      if (/^  [A-Za-z0-9_-]+:\s*$/.test(line) && !line.startsWith('   ')) {
        capturing = false;
        continue;
      }
      out.push(line);
    }
  }
  return out.length ? out.join('\n') : null;
};

const serviceImage = (text, serviceName) => {
  const block = serviceBlock(text, serviceName);
  if (!block) return null;
  for (const line of block.split('\n')) {
    if (/^\s*#/.test(line)) continue;
    const m = line.match(/^\s+image:\s*(.+)$/);
    if (m) return stripQuotes(m[1]);
  }
  return null;
};

const webImage = (text) => serviceImage(text, 'web');

const serviceHasBuild = (text, serviceName) => {
  const block = serviceBlock(text, serviceName);
  if (!block) return false;
  return /^    build:\s*$/m.test(block) || /^    build:\s+\S/m.test(block);
};

const webHasBuild = (text) => serviceHasBuild(text, 'web');


const envValue = (block, name) => {
  const re = new RegExp('^\\s+-\\s+' + name + '=(.*)$', 'm');
  const m = block.match(re);
  return m ? stripQuotes(m[1]) : undefined;
};

const checkTailscalePersist = (text, errs) => {
  const block = serviceBlock(text, 'tailscale');
  if (!block) return;
  const stateDir = envValue(block, 'TS_STATE_DIR');
  const hasVolume = /^\s+volumes:\s*$/m.test(block);
  if (!stateDir && !hasVolume) return;

  if (!stateDir) {
    errs.push('tailscale service TS_STATE_DIR is missing');
    return;
  }
  const authOnce = envValue(block, 'TS_AUTH_ONCE');
  if (authOnce !== 'true') {
    errs.push("tailscale service TS_AUTH_ONCE must be true (containerboot defaults to forcing tailscale up every start), got '" + authOnce + "'");
  }
  const kubeSecret = envValue(block, 'TS_KUBE_SECRET');
  if (kubeSecret === undefined) {
    errs.push('tailscale service TS_KUBE_SECRET must be set to empty (containerboot default is "tailscale")');
  } else if (kubeSecret !== '' && kubeSecret !== '${TS_KUBE_SECRET:-}') {
    errs.push("tailscale service TS_KUBE_SECRET must be empty so state stays on the bind mount, got '" + kubeSecret + "'");
  }
  const volRe = /^\s+-\s+(\S+):(\S+)\s*$/gm;
  let matched = false;
  let m;
  while ((m = volRe.exec(block)) !== null) {
    if (m[2] === stateDir) {
      matched = true;
      if (m[1] !== './data/tailscale') {
        errs.push('tailscale service volume for TS_STATE_DIR should be ./data/tailscale:' + stateDir + ', got ' + m[1] + ':' + m[2]);
      }
    }
  }
  if (!matched) {
    errs.push('tailscale service TS_STATE_DIR=' + stateDir + ' has no matching bind-mount destination');
  }
};

const collectorVolumeSources = (block) => {
  const srcs = [];
  const volRe = /^\s+-\s+(\S+):(\S+)\s*$/gm;
  let m;
  while ((m = volRe.exec(block)) !== null) {
    srcs.push({ src: m[1], dest: m[2] });
  }
  return srcs;
};

const checkCollectorDoesNotMountState = (text, errs) => {
  const block = serviceBlock(text, 'collector');
  if (!block) return;
  for (const { src, dest } of collectorVolumeSources(block)) {
    // tmpfs short form is "- /data/tailscale:mode=0700" (dest starts with mode=),
    // which hides the state dir; it is not a bind of ./data/tailscale.
    if (dest.startsWith('mode=')) continue;
    const base = src.replace(/\/$/, '');
    if (base === './data/tailscale' || /(?:^|\/)data\/tailscale$/.test(base)) {
      if (!base.endsWith('tailscale-run')) {
        errs.push(
          'collector must not mount the sidecar state dir ./data/tailscale (node key lives there); share only ./data/tailscale-run, got ' +
            src + ':' + dest
        );
      }
    }
  }
  const hasSocketDir = collectorVolumeSources(block).some(
    ({ src, dest }) => src === './data/tailscale-run' || dest === '/var/run/tailscale'
  );
  // Only require the socket-dir share when this compose already uses the new layout.
  if (/TS_SOCKET=/.test(block) && !hasSocketDir) {
    errs.push('collector has TS_SOCKET but does not bind-mount the socket dir ./data/tailscale-run');
  }
};



const xAppBackupBlock = (text) => {
  const start = text.search(/^  backup:\s*$/m);
  if (start < 0) return null;
  const rest = text.slice(start);
  const endMatch = rest.slice(1).search(/\nservices:|\n\S/);
  return endMatch === -1 ? rest : rest.slice(0, endMatch + 1);
};

const backupField = (block, key) => {
  const m = block.match(new RegExp('^    ' + key + ':\\s*(\\S+)\\s*$', 'm'));
  return m ? stripQuotes(m[1]) : undefined;
};

const backupList = (block, key) => {
  const header = new RegExp('^    ' + key + ':\\s*$', 'm');
  const m = header.exec(block);
  if (!m) return null;
  const from = block.slice(m.index + m[0].length);
  const items = [];
  for (const line of from.split('\n')) {
    if (/^    [A-Za-z]/.test(line)) break;
    if (/^\s*#/.test(line) || line.trim() === '') continue;
    const item = line.match(/^\s+- ([^\s#]+)/);
    if (item) items.push(item[1]);
  }
  return items;
};

const sameList = (got, want) =>
  Array.isArray(got) && got.length === want.length && got.every((v, i) => v === want[i]);

const HOOK_EXCLUDE_ALWAYS = ['keys', 'tailscale', 'tailscale-run', 'data/backup/daily'];
const HOOK_EXCLUDE_AFTER_PREHOOK = ['usage.sqlite', 'usage.sqlite-wal', 'usage.sqlite-shm'];
const HOOK_DUMP_PATHS = ['data/backup/usage.sqlite', 'backup/usage.sqlite', 'backup'];

const checkBackupHook = (text, errs) => {
  const block = xAppBackupBlock(text);
  if (!block) return;
  const method = backupField(block, 'method');
  if (method !== undefined && method !== 'hook' && method !== 'stop') {
    errs.push("x-app.backup.method must be 'hook' or 'stop', got '" + method + "'");
    return;
  }
  if (method !== 'hook') return;

  const fallback = backupField(block, 'fallback');
  if (fallback !== undefined && fallback !== 'stop' && fallback !== 'fail') {
    errs.push("x-app.backup.fallback must be 'stop' or 'fail', got '" + fallback + "'");
  }
  const timeout = backupField(block, 'hookTimeout');
  if (timeout !== undefined && !/^[1-9][0-9]*$/.test(timeout)) {
    errs.push("x-app.backup.hookTimeout must be a positive integer, got '" + timeout + "'");
  }
  if (!/^    preHook:\s*$/m.test(block)) errs.push('x-app.backup.preHook is required when method is hook');
  if (!/^    postHook:\s*$/m.test(block)) errs.push('x-app.backup.postHook is required when method is hook');
  if (!/service:\s*collector/.test(block)) {
    errs.push("x-app.backup hooks must run in the collector service");
  }
  if (!/command:\s*\/app\/scripts\/backup-snapshot\.sh/.test(block)) {
    errs.push('x-app.backup.preHook.command must be /app/scripts/backup-snapshot.sh');
  }
  if (!/command:\s*\/app\/scripts\/backup-cleanup\.sh/.test(block)) {
    errs.push('x-app.backup.postHook.command must be /app/scripts/backup-cleanup.sh');
  }

  const exclude = backupList(block, 'exclude') || [];
  const hookExclude = backupList(block, 'hookExclude') || [];
  if (!sameList(exclude, HOOK_EXCLUDE_ALWAYS)) {
    errs.push(
      'x-app.backup.exclude must be keys, tailscale, tailscale-run, data/backup/daily (always applied); got ' +
        JSON.stringify(exclude)
    );
  }
  if (!sameList(hookExclude, HOOK_EXCLUDE_AFTER_PREHOOK)) {
    errs.push(
      'x-app.backup.hookExclude must be usage.sqlite, usage.sqlite-wal, usage.sqlite-shm (after a successful preHook only); got ' +
        JSON.stringify(hookExclude)
    );
  }
  const combined = exclude.concat(hookExclude);
  for (const path of HOOK_DUMP_PATHS) {
    if (combined.includes(path)) {
      errs.push('hook dump data/backup/usage.sqlite must stay in the archive; do not list ' + path);
    }
  }
};


// idea#446 verify lists. Port of agent-engine-dev src/utils/backupExclude.ts
// normalizeBackupExclude: a bare name (no slash, not "data", no leading dot)
// means data/<name>; a path with a slash or a leading dot is instance-relative.
const normalizeBackupPath = (raw) => {
  let p = String(raw).trim();
  if (!p || p.includes('\0') || p.startsWith('-') || p.startsWith('/')) return null;
  while (p.startsWith('./')) p = p.slice(2);
  p = p.replace(/\/+$/, '');
  if (!p || p.includes('//')) return null;
  if (p.split('/').some((c) => c === '' || c === '.' || c === '..')) return null;
  if (/[*?[\]]/.test(p) || !/^[A-Za-z0-9._][A-Za-z0-9._/-]*$/.test(p)) return null;
  if (!p.includes('/') && p !== 'data' && !p.startsWith('.')) p = `data/${p}`;
  return p;
};

// a covers b: a equals b or is a parent directory of b.
const covers = (a, b) => a === b || b.startsWith(a + '/');

// Nested list under "    verify:" ("      present:" / "      absent:").
const verifyList = (block, key) => {
  const vm = /^    verify:\s*$/m.exec(block);
  if (!vm) return null;
  const lines = block.slice(vm.index + vm[0].length).split('\n');
  let inKey = false;
  let found = false;
  const items = [];
  for (const line of lines) {
    if (/^    [A-Za-z]/.test(line) || /^\S/.test(line)) break;
    if (/^\s*#/.test(line) || line.trim() === '') continue;
    const km = line.match(/^      ([A-Za-z]+):\s*$/);
    if (km) {
      inKey = km[1] === key;
      if (inKey) found = true;
      continue;
    }
    const item = inKey && line.match(/^\s+- ([^\s#]+)/);
    if (item) items.push(stripQuotes(item[1]));
  }
  return found ? items : null;
};

// Paths a hook archive packs that a fallback-stop archive may lack, and the
// reverse. A verify entry must hold for both, so neither side may name them.
const LIVE_DB = ['data/usage.sqlite', 'data/usage.sqlite-wal', 'data/usage.sqlite-shm'];
const HOOK_DUMP = 'data/backup/usage.sqlite';

const checkBackupVerify = (text, errs, { release } = {}) => {
  const block = xAppBackupBlock(text);
  if (!block) return;
  const hasVerify = /^    verify:\s*$/m.test(block);
  if (!hasVerify) {
    if (release && backupField(block, 'method') === 'hook') {
      errs.push('release: x-app.backup.verify (present/absent, idea#446) is required when method is hook');
    }
    return;
  }
  const present = verifyList(block, 'present');
  const absent = verifyList(block, 'absent');
  if (!present || !present.length) errs.push('x-app.backup.verify.present must be a non-empty list');
  if (!absent || !absent.length) errs.push('x-app.backup.verify.absent must be a non-empty list');
  const norm = (raw, field) => {
    const n = normalizeBackupPath(raw);
    if (n === null) errs.push(`x-app.backup.verify.${field} entry '${raw}' is not an allowed path`);
    return n;
  };
  const exclude = (backupList(block, 'exclude') || []).map((r) => normalizeBackupPath(r)).filter(Boolean);
  const hookExclude = (backupList(block, 'hookExclude') || []).map((r) => normalizeBackupPath(r)).filter(Boolean);
  const presentN = [];
  for (const raw of present || []) {
    const p = norm(raw, 'present');
    if (p === null) continue;
    // A bare name means data/<name>; "compose.yaml" would check data/compose.yaml.
    if (!String(raw).includes('/') && !String(raw).startsWith('.')) {
      errs.push(`x-app.backup.verify.present entry '${raw}' is a bare name (means ${p}); write the instance-relative path with a '/' or a leading '.'`);
    }
    for (const ex of exclude) {
      if (covers(ex, p)) errs.push(`x-app.backup.verify.present entry '${raw}' is under exclude '${ex}', so it is never in an archive`);
    }
    for (const hx of hookExclude.concat(LIVE_DB)) {
      if (covers(p, hx) || covers(hx, p)) {
        errs.push(`x-app.backup.verify.present entry '${raw}' names the live db '${hx}', which a hook archive leaves out (hookExclude)`);
        break;
      }
    }
    if (covers(p, HOOK_DUMP) || covers(HOOK_DUMP, p)) {
      errs.push(`x-app.backup.verify.present entry '${raw}' names the hook dump ${HOOK_DUMP}, which a HOOK_FALLBACK stop archive does not have`);
    }
    presentN.push(p);
  }
  for (const raw of absent || []) {
    const a = norm(raw, 'absent');
    if (a === null) continue;
    for (const hx of hookExclude.concat(LIVE_DB)) {
      if (covers(a, hx)) {
        errs.push(`x-app.backup.verify.absent entry '${raw}' covers the live db '${hx}', which a HOOK_FALLBACK stop archive packs`);
        break;
      }
    }
    if (covers(a, HOOK_DUMP)) {
      errs.push(`x-app.backup.verify.absent entry '${raw}' covers the hook dump ${HOOK_DUMP}, which a hook archive packs`);
    }
    for (const p of presentN) {
      if (covers(a, p)) errs.push(`x-app.backup.verify.absent entry '${raw}' covers present entry '${p}'`);
    }
  }
};


export function checkCompose(text, { tag, release } = {}) {
  const errs = [];
  if (PLACEHOLDER_RE.test(text)) {
    errs.push(
      'packaging placeholder still present (DIGEST_PLACEHOLDER, SHORTSHA, or <DIGEST>); fill it in from script/publish-web-image.sh before a release'
    );
  }

  const vm = text.match(/^x-app:[\s\S]*?^  version:\s*(.+)$/m);
  if (!vm) {
    errs.push('x-app.version missing');
  } else {
    const ver = stripQuotes(vm[1]);
    if (tag !== undefined && ver !== tag) {
      errs.push(`x-app.version '${ver}' != tag '${tag}'`);
    }
    const svcNames = [];
    let inServices = false;
    for (const line of text.split('\n')) {
      if (line === 'services:') {
        inServices = true;
        continue;
      }
      if (inServices && /^\S/.test(line) && !line.startsWith('#')) inServices = false;
      const sm = inServices && line.match(/^  ([A-Za-z0-9_-]+):\s*$/);
      if (sm) svcNames.push(sm[1]);
    }
    if (!svcNames.length) errs.push('no services');
    for (const name of svcNames) {
      const l = labelOf(text, name);
      if (l === undefined) errs.push(`service ${name}: label x-app-version missing`);
      else if (l !== ver) errs.push(`service ${name}: label x-app-version '${l}' != x-app.version '${ver}'`);
    }
  }

  checkTailscalePersist(text, errs);
  checkCollectorDoesNotMountState(text, errs);
  checkBackupHook(text, errs);
  checkBackupVerify(text, errs, { release });

  if (release) {
    const svcNames = [];
    let inServices = false;
    for (const line of text.split('\n')) {
      if (line === 'services:') {
        inServices = true;
        continue;
      }
      if (inServices && /^\S/.test(line) && !line.startsWith('#')) inServices = false;
      const sm = inServices && line.match(/^  ([A-Za-z0-9_-]+):\s*$/);
      if (sm) svcNames.push(sm[1]);
    }
    for (const name of svcNames) {
      const image = serviceImage(text, name);
      if (!image) {
        errs.push(`release service ${name} has no image:`);
      } else if (!TAG_DIGEST_PIN.test(image)) {
        errs.push(
          `release service ${name} image must be <repo>:<tag>@sha256:<64-hex> (idea#322 tag+digest), got '${image}'`
        );
      }
      if (serviceHasBuild(text, name)) {
        errs.push(`release service ${name} must drop the build: block`);
      }
    }
    const web = serviceImage(text, 'web');
    if (web && !GHCR_PIN_RE.test(web)) {
      errs.push(
        `release web image must be ghcr.io/koenswings/usage-dashboard-web:<version>@sha256:<64-hex> (idea#322 tag+digest; optional -<shortsha> suffix is accepted), got '${web}'`
      );
    }
    const collector = serviceImage(text, 'collector');
    if (collector && !COLLECTOR_PIN_RE.test(collector)) {
      errs.push(
        `release collector image must be ghcr.io/koenswings/usage-dashboard-collector:<version>@sha256:<64-hex> (idea#322 tag+digest; optional -<shortsha> suffix is accepted), got '${collector}'`
      );
    }
  }
  return errs;
}

const args = process.argv.slice(2);
let tag;
let release = false;
const files = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--tag') {
    tag = args[++i];
    continue;
  }
  if (args[i] === '--release') {
    release = true;
    continue;
  }
  files.push(args[i]);
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1] && process.argv[1].endsWith('check-compose.mjs')) {
  if (!files.length) {
    console.error('Usage: node script/check-compose.mjs [--tag <release tag>] [--release] <compose.yaml>...');
    process.exit(2);
  }
  let bad = 0;
  for (const f of files) {
    const text = readFileSync(f, 'utf8');
    const errs = checkCompose(text, { tag, release });
    for (const m of errs) console.error(`FAIL ${f}: ${m}`);
    if (errs.length) bad = 1;
    else console.log(`ok   ${f}`);
  }
  process.exit(bad);
}
