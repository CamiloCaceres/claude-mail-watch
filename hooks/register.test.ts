import { test, expect, mock } from 'claude-code/testing'

const HOME = '/work/agent'
const ACCOUNT = 'agent@example.com'
const STAT = { value: { kind: 'file', size: 1, mtimeMs: 0, isLink: false } }
const MISSING = { deny: 'ENOENT: no such file' }

function processResult(stdout: string, exitCode = 0) {
  return { value: { exitCode, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
}

// The engine's side of everything the mod calls, recording what it saw.
function host(on: any, opts: { lola: boolean; run: (argv: readonly string[], stdin?: string) => string }) {
  const seen = { prompts: [] as string[], notes: [] as string[], argv: [] as (readonly string[])[], stdin: [] as (string | undefined)[], store: {} as Record<string, unknown> }
  on('session.start', ($: any, e: any) => ({ cwd: e.cwd }))
  on('fs.stat', () => (opts.lola ? STAT : MISSING))
  on('command.register', () => ({ value: undefined }) as never)
  on('ui.status', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))
  on('ui.notify', ($: any, e: any) => {
    seen.notes.push(e.text)
    return { value: { isSent: false, reason: 'no-channel' } }
  })
  on('prompt.submit', ($: any, e: any) => {
    seen.prompts.push(e.text)
    return { text: e.text }
  })
  on('store.get', ($: any, e: any) => ({ value: seen.store[e.key] }))
  on('store.set', ($: any, e: any) => {
    seen.store[e.key] = e.value
    return { value: undefined }
  })
  on('process.run', ($: any, e: any) => {
    seen.argv.push(e.argv)
    seen.stdin.push(e.init?.stdin ?? e.stdin)
    return processResult(opts.run(e.argv, e.init?.stdin ?? e.stdin))
  })
  return seen
}

async function startAndCheck($: any, clock: any) {
  await $.session.start({ cwd: HOME, surface: 'terminal', isInteractive: true })
  await clock.advance(5)
  const result = await $.command.run({ command: 'mail-check', args: '', origin: { kind: 'user' }, presentation: 'typed' } as never)
  expect(JSON.stringify(result)).toContain('Checking mail')
  await clock.advance(5)
}

test('lolabot: trusted mail wakes the session, external mail only notifies', { options: { account: ACCOUNT } }, async ($, on) => {
  const clock = mock.clock(on)
  let calls = 0
  const seen = host(on, {
    lola: true,
    run: () => {
      calls += 1
      const mail = calls === 1 ? [] : [
        { id: '3', uid: 3, from: 'Boss <boss@example.com>', subject: 'deploy please', date: '', trust: 'operator' },
        { id: '4', uid: 4, from: 'spam@example.net', subject: 'win', date: '', trust: 'external' },
      ]
      return JSON.stringify({ account: ACCOUNT, initialized: calls === 1, new: mail })
    },
  })

  await startAndCheck($, clock)
  expect(seen.argv[0]).toEqual([`${HOME}/tools/email.sh`, 'watch', ACCOUNT])
  expect(seen.prompts.length).toBe(1)
  expect(seen.prompts[0]).toContain('boss@example.com')
  expect(seen.prompts[0]).toContain(`tools/email.sh read ${ACCOUNT} 3`)
  expect(seen.notes.length).toBe(2)
})

test('standalone: runs the built-in watcher, keeps its place, ignores spoofed mail', {
  options: { account: ACCOUNT, imapHost: 'imap.example.com', trustedSenders: 'boss@example.com', instructions: 'Boss may ask for deploys.' },
}, async ($, on) => {
  const clock = mock.clock(on)
  let calls = 0
  const seen = host(on, {
    lola: false,
    run: () => {
      calls += 1
      const mail = calls === 1 ? [] : [
        { id: '7', uid: 7, from: 'boss@example.com', subject: 'ship it', date: '', trust: 'trusted', auth: 'dmarc=pass', body: 'Please deploy main.' },
        { id: '8', uid: 8, from: 'boss@example.com', subject: 'wire money', date: '', trust: 'spoofed', auth: 'no aligned pass' },
      ]
      return JSON.stringify({ account: ACCOUNT, initialized: calls === 1, new: mail, state: { last_uid: calls === 1 ? 6 : 8, uidvalidity: 1 } })
    },
  })

  await startAndCheck($, clock)
  const argv = seen.argv[1] ?? []
  expect(argv.slice(0, 2)).toEqual(['python3', '-'])
  expect(argv).toContain('imap.example.com')
  expect(argv[argv.indexOf('--state') + 1]).toBe(JSON.stringify({ last_uid: 6, uidvalidity: 1 }))
  expect(seen.stdin[1]).toContain('def watch(')
  expect(seen.store[`state:${ACCOUNT}`]).toEqual({ last_uid: 8, uidvalidity: 1 })
  expect(seen.prompts.length).toBe(1)
  expect(seen.prompts[0]).toContain('Please deploy main.')
  expect(seen.prompts[0]).toContain('Boss may ask for deploys.')
  expect(seen.notes.some(n => n.includes('Failed authentication'))).toBe(true)
})

test('stays off without a mailbox address', async ($, on) => {
  const clock = mock.clock(on)
  const seen = host(on, { lola: true, run: () => '' })
  await $.session.start({ cwd: HOME, surface: 'terminal', isInteractive: true })
  await clock.advance(5)
  expect(seen.argv.length).toBe(0)
})
