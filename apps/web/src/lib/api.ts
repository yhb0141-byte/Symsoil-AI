import type { Session } from './types'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'ApiError' }
}
let csrfToken = ''
let unauthorizedHandler: (() => void) | undefined
let generation = 0
const controllers = new Set<AbortController>()
export function setSession(session: Session): void { csrfToken = session.csrf_token }
export function onUnauthorized(handler: () => void): void { unauthorizedHandler = handler }
export function clearSession(): void {
  csrfToken = ''
  generation += 1
  controllers.forEach(controller => controller.abort())
  controllers.clear()
}
export async function endSession(): Promise<void> {
  const token = csrfToken
  clearSession()
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const result = await fetch('/api/v1/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': token, Accept: 'application/json' }, credentials: 'same-origin', cache: 'no-store', keepalive: true, signal: controller.signal })
    if (!result.ok && result.status !== 401) throw new ApiError(result.status, '服务器尚未确认撤销会话。')
  } finally { clearTimeout(timeout) }
}
export function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `r0-${Date.now()}-${Math.random().toString(36).slice(2)}`
}
export async function request<T>(path: string, method = 'GET', body?: unknown, idempotencyKey?: string, timeoutMs = 20000, externalSignal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  // Even reads require the current page's in-memory session proof; cookies alone cannot reopen private data.
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
  const requestGeneration = generation
  const controller = new AbortController()
  controllers.add(controller)
  const abortFromCaller = () => controller.abort()
  externalSignal?.addEventListener('abort', abortFromCaller, { once: true })
  if (externalSignal?.aborted) controller.abort()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const result = await fetch(`/api/v1${path}`, { method, headers, credentials: 'same-origin', cache: 'no-store', body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal })
    const data = await result.json().catch(() => ({}))
    if (generation !== requestGeneration) throw new ApiError(401, '会话已结束，请重新登录。')
    if (result.status === 401) unauthorizedHandler?.()
    if (!result.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : '请求未完成，请检查输入后重试。'
      throw new ApiError(result.status, detail)
    }
    return data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(0, '暂时无法连接社区服务器。请检查连接后重试；当前操作未收到成功确认。')
  } finally { clearTimeout(timeout); externalSignal?.removeEventListener('abort', abortFromCaller); controllers.delete(controller) }
}
export function errorText(error: unknown): string {
  if (error instanceof ApiError && error.status === 409) return '内容或方案版本已变化，或重复请求内容不一致。请重新载入并核对，再由本人确认。'
  return error instanceof Error ? error.message : '操作未完成，请重试。'
}
