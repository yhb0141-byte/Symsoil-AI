import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, clearSession, endSession, onUnauthorized, request, setSession } from './api'
import type { Session } from './types'

const session: Session = { user: { id: 'member-a', username: 'a', display_name: '成员甲', role: 'member', active: true }, csrf_token: 'only-in-memory-csrf' }
const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
beforeEach(() => { clearSession(); onUnauthorized(() => {}); vi.stubGlobal('fetch', vi.fn()) })
afterEach(() => { clearSession(); vi.unstubAllGlobals() })

describe('same-origin authenticated API', () => {
  it('uses the cookie session, in-memory CSRF token, and caller-supplied idempotency key', async () => {
    setSession(session)
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }))
    await request('/utterances/private-id/confirmations', 'POST', { object_version: 2 }, 'repeat-this-key')
    expect(fetch).toHaveBeenCalledWith('/api/v1/utterances/private-id/confirmations', expect.objectContaining({
      credentials: 'same-origin', cache: 'no-store', body: '{"object_version":2}', headers: expect.objectContaining({ 'X-CSRF-Token': 'only-in-memory-csrf', 'Idempotency-Key': 'repeat-this-key' }),
    }))
  })
  it('proves authenticated GET requests with the same in-memory session token', async () => {
    setSession(session)
    vi.mocked(fetch).mockResolvedValue(jsonResponse([]))
    await request('/utterances')
    expect(fetch).toHaveBeenCalledWith('/api/v1/utterances', expect.objectContaining({
      method: 'GET', credentials: 'same-origin', headers: expect.objectContaining({ 'X-CSRF-Token': session.csrf_token }),
    }))
  })
  it('does not recover a private read token from a cookie after local logout', async () => {
    setSession(session)
    clearSession()
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: '缺少页面会话证明' }, 401))
    await expect(request('/auth/me')).rejects.toMatchObject({ status: 401 })
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).not.toHaveProperty('X-CSRF-Token')
  })
  it('returns the server conflict rather than treating an obsolete version as success', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: '内容版本已变化' }, 409))
    await expect(request('/utterances/private-id/confirmations', 'POST', { object_version: 1 }, 'key')).rejects.toMatchObject({ status: 409, message: '内容版本已变化' })
  })
  it('clears current authenticated UI when the server invalidates its session', async () => {
    const unauthorized = vi.fn()
    onUnauthorized(unauthorized)
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: '登录已失效' }, 401))
    await expect(request('/audit')).rejects.toBeInstanceOf(ApiError)
    expect(unauthorized).toHaveBeenCalledOnce()
  })
  it('does not let a late 401 from the previous session clear a newer login', async () => {
    const unauthorized = vi.fn()
    onUnauthorized(unauthorized)
    let resolveJson: (value: unknown) => void = () => {}
    vi.mocked(fetch).mockResolvedValue({ status: 401, ok: false, json: () => new Promise(resolve => { resolveJson = resolve }) } as Response)
    const previousRequest = request('/audit')
    await Promise.resolve()
    clearSession()
    setSession({ ...session, csrf_token: 'new-session-csrf' })
    resolveJson({ detail: '旧会话已失效' })
    await expect(previousRequest).rejects.toMatchObject({ status: 401 })
    expect(unauthorized).not.toHaveBeenCalled()
  })
  it('supports cancelling a model request without retaining its response', async () => {
    const cancellation = new AbortController()
    vi.mocked(fetch).mockImplementationOnce((_path, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')))
    }))
    const inference = request('/utterances/u/suggestions', 'POST', { object_version: 1, context: '', target_context: '', purpose: '' }, undefined, 65000, cancellation.signal)
    cancellation.abort()
    await expect(inference).rejects.toMatchObject({ status: 0 })
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
  })
  it('ends the session immediately while the server logout is still pending', async () => {
    setSession(session)
    let finishLogout: (value: Response) => void = () => {}
    vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finishLogout = resolve }))
    const logout = endSession()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ok: true }))
    await request('/auth/login', 'POST', { username: 'next-person', password: 'test' })
    const loginOptions = vi.mocked(fetch).mock.calls[1]?.[1]
    expect(loginOptions?.headers).not.toHaveProperty('X-CSRF-Token')
    const logoutOptions = vi.mocked(fetch).mock.calls[0]?.[1]
    expect(logoutOptions?.headers).toHaveProperty('X-CSRF-Token', session.csrf_token)
    expect(logoutOptions?.keepalive).toBe(true)
    finishLogout(jsonResponse({ ok: true }))
    await logout
  })
})
