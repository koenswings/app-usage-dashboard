#!/usr/bin/env node
// Queue an Engine command the same way the Console does: push onto
// engineDB[engineId].commands over the Automerge websocket.
// Does not modify the deployed Engine tree.
//
// Usage:
//   script/send-engine-command.mjs inspect
//   script/send-engine-command.mjs send <command...>
//
// Environment:
//   ENGINE_ROOT   Engine checkout with @automerge deps
//                 (default: /home/pi/idea/agents/agent-engine-dev)
//   ENGINE_API    store-url origin (default: http://127.0.0.1:8080)
//
// Never prints credentials, instance env, or key material.

import { pathToFileURL } from 'node:url'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

const engineRoot = process.env.ENGINE_ROOT || '/home/pi/idea/agents/agent-engine-dev'
const apiOrigin = process.env.ENGINE_API || 'http://127.0.0.1:8080'

const repoJs = join(engineRoot, 'node_modules/@automerge/automerge-repo/dist/entrypoints/fullfat.js')
const wsJs = join(engineRoot, 'node_modules/@automerge/automerge-repo-network-websocket/dist/index.js')
if (!existsSync(repoJs) || !existsSync(wsJs)) {
  console.error(`ERROR: Automerge modules not found under ${engineRoot}`)
  process.exit(1)
}

const { Repo } = await import(pathToFileURL(repoJs).href)
const { BrowserWebSocketClientAdapter } = await import(pathToFileURL(wsJs).href)

const mode = process.argv[2] || 'inspect'
const command = process.argv.slice(3).join(' ')

const info = await fetch(`${apiOrigin}/api/store-url`).then((r) => {
  if (!r.ok) throw new Error(`store-url HTTP ${r.status}`)
  return r.json()
})
const engineId = info.engineId
const storeUrl = info.url
const wsUrl = `ws://127.0.0.1:${info.wsPort}`

const adapter = new BrowserWebSocketClientAdapter(wsUrl)
const repo = new Repo({ network: [adapter] })
const handle = await repo.find(storeUrl)

const waitForDoc = async (timeoutMs = 20000) => {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const doc = typeof handle.doc === 'function' ? handle.doc() : handle.doc
    if (doc && doc.engineDB && doc.engineDB[engineId]) return doc
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error('timed out waiting for store document / local engine')
}

const currentDoc = () => (typeof handle.doc === 'function' ? handle.doc() : handle.doc)

const summariseDisk = (id, d) => ({
  id,
  name: d?.name,
  device: d?.device,
  dockedTo: d?.dockedTo,
  diskTypes: d?.diskTypes,
})

const summariseInstance = (id, i) => ({
  id,
  name: i?.name,
  instanceOf: i?.instanceOf,
  status: i?.status,
  port: i?.port,
  storedOn: i?.storedOn,
  created: i?.created,
})

const snapshot = (doc) => {
  const disks = Object.entries(doc.diskDB || {}).map(([id, d]) => summariseDisk(id, d))
  const instances = Object.entries(doc.instanceDB || {}).map(([id, i]) => summariseInstance(id, i))
  const localDisks = disks.filter((d) => d.dockedTo === engineId)
  const systemDisks = disks.filter((d) => Array.isArray(d.diskTypes) && d.diskTypes.includes('system'))
  const localSystem = systemDisks.filter((d) => d.dockedTo === engineId)
  const localInstances = instances.filter((i) => localDisks.some((d) => d.id === i.storedOn))
  return {
    mode,
    storeUrl,
    wsPort: info.wsPort,
    engineId,
    localEnginePresent: Boolean(doc.engineDB?.[engineId]),
    queuedCommands: (doc.engineDB?.[engineId]?.commands || []).length,
    commands: doc.engineDB?.[engineId]?.commands || [],
    localDisks,
    systemDisks,
    localSystem,
    localInstances,
  }
}

const doc = await waitForDoc()
const before = snapshot(doc)
console.log(JSON.stringify(before, null, 2))

if (mode === 'inspect') {
  process.exit(0)
}

if (mode !== 'send') {
  console.error('usage: send-engine-command.mjs inspect | send <command...>')
  process.exit(2)
}
if (!command) {
  console.error('missing command')
  process.exit(2)
}

if (!doc.engineDB[engineId]) {
  console.error('local engine not in store; refusing to send')
  process.exit(1)
}

handle.change((d) => {
  const engine = d.engineDB?.[engineId]
  if (!engine) throw new Error('engine disappeared during change')
  engine.commands.push(command)
})

const sentAt = Date.now()
let seen = false
while (Date.now() - sentAt < 10000) {
  const now = currentDoc()
  const q = now?.engineDB?.[engineId]?.commands || []
  if (q.includes(command)) {
    seen = true
    break
  }
  if (seen === false && Date.now() - sentAt > 1500) break
  await new Promise((r) => setTimeout(r, 200))
}

// Keep the websocket open so the change reaches the Engine before we exit.
await new Promise((r) => setTimeout(r, 12000))
const after = snapshot(currentDoc())
console.log(JSON.stringify({
  sent: command,
  syncWaitSec: 12,
  stillQueued: (after.commands || []).includes(command),
  queuedAfter: after.commands,
  localSystem: after.localSystem,
  localInstances: after.localInstances,
}, null, 2))
process.exit(0)
