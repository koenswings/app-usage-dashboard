#!/usr/bin/env node
// Usage: node script/check-compose.mjs [--tag <release tag>] [--release] <compose.yaml>...
//
// Default: every service's x-app-version label == x-app.version
// (and == --tag when given). Exit 1 on any problem.
//
// --release (idea#375 U-10): also require the web service to use a
// digest-pinned ghcr image
//   ghcr.io/koenswings/usage-dashboard-web:<version>-<shortsha>@sha256:<64 hex>
// with no build: block. Fails if a packaging placeholder
// (DIGEST_PLACEHOLDER, SHORTSHA, <DIGEST>) is still present.
//
// Engine idea#322 saveName() rejects a digest-only pin (no tag), so the
// release form is repo:tag@sha256:digest, not repo@sha256:digest.

import { readFileSync } from 'node:fs';

const PLACEHOLDER_RE = /DIGEST_PLACEHOLDER|<DIGEST>|SHORTSHA|REPLACE_ME_WITH_PUBLISHED_DIGEST/i;
const GHCR_PIN_RE = /^ghcr\.io\/koenswings\/usage-dashboard-web:\d+\.\d+[0-9A-Za-z._+-]*-[0-9a-f]{7,40}@sha256:[0-9a-f]{64}$/;

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

const webImage = (text) => {
  const block = serviceBlock(text, 'web');
  if (!block) return null;
  for (const line of block.split('\n')) {
    if (/^\s*#/.test(line)) continue;
    const m = line.match(/^\s+image:\s*(.+)$/);
    if (m) return stripQuotes(m[1]);
  }
  return null;
};

const webHasBuild = (text) => {
  const block = serviceBlock(text, 'web');
  if (!block) return false;
  return /^    build:\s*$/m.test(block) || /^    build:\s+\S/m.test(block);
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

  if (release) {
    const image = webImage(text);
    if (!image) {
      errs.push('release web service has no image:');
    } else if (!GHCR_PIN_RE.test(image)) {
      errs.push(
        `release web image must be ghcr.io/koenswings/usage-dashboard-web:<version>-<shortsha>@sha256:<64-hex> (idea#322 tag+digest), got '${image}'`
      );
    }
    if (webHasBuild(text)) {
      errs.push('release web service must drop the build: block');
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
