import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { clearSession, setSession } from './api'
import { createCorrectionReadGate, createCorrectionsApi } from './corrections'
import type { CorrectionContext } from './corrections'
const preview: CorrectionContext = { document_id: 'doc', revision_id: 'revision', document_version: 3, access_epoch: 7, title: 'Private source title', maintainer: 'Free text is not an account', recipient: { id: 'owner', display_name: '录入者' } }
beforeEach(() => { clearSession(); setSession({ user: { id: 'sender', username: 'sender', display_name: '请求者', role: 'member', active: true }, csrf_token: 'in-memory-proof' }); vi.stubGlobal('fetch', vi.fn()) })
afterEach(() => { clearSession(); vi.unstubAllGlobals() })
const ok = () => new Response(JSON.stringify({ id: 'correction', status: 'submitted' }), { status: 200 })
it('submits the exact preview identities and permission epoch without copying document content', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(ok())
  await createCorrectionsApi().create(preview, '本人写的问题')
  const [url, options] = vi.mocked(fetch).mock.calls[0]!
  expect(url).toBe('/api/v1/knowledge-corrections')
  expect(JSON.parse(options!.body as string)).toEqual({ document_id: 'doc', revision_id: 'revision', access_epoch: 7, expected_recipient_id: 'owner', text: '本人写的问题', consent: true })
  expect(options!.body).not.toContain('Private source title')
  expect(new Headers(options!.headers).get('X-CSRF-Token')).toBe('in-memory-proof')
})
it('reuses the same mutation key only for an identical uncertain network retry', async () => {
  const api = createCorrectionsApi()
  vi.mocked(fetch).mockRejectedValueOnce(new TypeError('network')).mockResolvedValue(ok())
  await expect(api.create(preview, '问题')).rejects.toThrow()
  await api.create(preview, '问题')
  await api.create(preview, '另一问题')
  const keys = vi.mocked(fetch).mock.calls.map(([, opts]) => new Headers(opts!.headers).get('Idempotency-Key'))
  expect(keys[0]).toBeTruthy(); expect(keys[1]).toBe(keys[0]); expect(keys[2]).not.toBe(keys[0])
})
it('late private detail cannot populate a newer or disposed correction view', async () => {
  const gate = createCorrectionReadGate()
  const old = gate.start(), current = gate.start()
  let shown = ''
  await Promise.resolve().then(() => { if (gate.current(old)) shown = 'withdrawn-private-message' })
  expect(shown).toBe(''); expect(gate.current(current)).toBe(true)
  gate.dispose()
  await Promise.resolve().then(() => { if (gate.current(current)) shown = 'previous-member-private-message' })
  expect(shown).toBe(''); expect(gate.current(gate.start())).toBe(false)
})
