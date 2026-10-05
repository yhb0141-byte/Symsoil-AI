import { ApiError, mutationKey, request } from './api'
import type { KnowledgeAnswer, KnowledgeDetail, KnowledgeReviewItem, KnowledgeRevisionInput, Member, PublishedDocument } from './types'

/** No DOM rendering or uploading: decode only the explicitly chosen local text. */
export function decodeKnowledgeFile(name: string, bytes: ArrayBuffer): string {
  if (!/\.(txt|md)$/i.test(name)) throw new Error('仅支持 UTF-8 的 .txt 或 .md 文件。请把其他格式整理为文字后粘贴。')
  if (bytes.byteLength > 80000) throw new Error('文件过大。请整理为不超过 20000 字的文字资料。')
  let text: string
  try { text = new TextDecoder('utf-8', { fatal: true }).decode(bytes) }
  catch { throw new Error('无法按 UTF-8 读取。请把文件另存为 UTF-8，或直接粘贴正文。') }
  if (text.includes('\0')) throw new Error('文件含有无法作为正文处理的空字符。请粘贴整理后的文字。')
  if (text.length > 20000) throw new Error('正文超过 20000 字。请先拆分或整理。')
  return text
}

export function emptyKnowledgeInput(): KnowledgeRevisionInput {
  return { title: '', category: '', body: '', source: '', rights: '', purpose: '', maintainer: '', effective_until: null, requested_scope: 'community', requested_member_ids: [] }
}
export function copyKnowledgeInput(revision: KnowledgeRevisionInput): KnowledgeRevisionInput {
  return { title: revision.title, category: revision.category, body: revision.body, source: revision.source, rights: revision.rights, purpose: revision.purpose, maintainer: revision.maintainer, effective_until: revision.effective_until, requested_scope: revision.requested_scope, requested_member_ids: [...revision.requested_member_ids] }
}

/** Mirrors Python str.splitlines(): provenance line numbers include Unicode line boundaries. */
export function splitSourceLines(value: string): string[] {
  if (!value) return []
  const lines = value.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/)
  if (/[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]$/.test(value)) lines.pop()
  return lines
}

/** YYYY-MM-DDTHH:mm in the device's local zone; the API always receives an ISO instant. */
export function localDateInput(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  const pad = (number: number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
export function expiryInstant(value: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) throw new Error('请选择有效的截止日期和时间。')
  return date.toISOString()
}
export function validateKnowledgeInput(input: KnowledgeRevisionInput): string {
  const required: (keyof KnowledgeRevisionInput)[] = ['title', 'category', 'body', 'source', 'rights', 'purpose', 'maintainer']
  if (required.some(key => typeof input[key] !== 'string' || !(input[key] as string).trim())) return '请填写正文、来源、授权依据、用途与维护人等全部必填内容。'
  if (input.requested_scope === 'members' && !input.requested_member_ids.length) return '固定名单发布至少需要明确选择一位当前有效成员。'
  return ''
}

/** Idempotency lives only in this mounted workspace. A network retry reuses the exact body key. */
export function createKnowledgeApi() {
  const keys = new Map<string, string>()
  async function mutate<T>(path: string, body: unknown, keyed = false, method = 'POST'): Promise<T> {
    const signature = `${method}:${path}:${JSON.stringify(body)}`
    const key = keyed ? keys.get(signature) ?? mutationKey() : undefined
    if (key) keys.set(signature, key)
    try { const result = await request<T>(path, method, body, key); keys.delete(signature); return result }
    catch (error) { if (error instanceof ApiError && error.status !== 0) keys.delete(signature); throw error }
  }
  return {
    clear: () => keys.clear(),
    catalog: (query = '') => request<PublishedDocument[]>(`/documents${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ''}`),
    source: (id: string, revision: string) => request<PublishedDocument>(`/documents/${encodeURIComponent(id)}?revision_id=${encodeURIComponent(revision)}`),
    mine: () => request<KnowledgeDetail[]>('/knowledge/mine'),
    detail: (id: string) => request<KnowledgeDetail>(`/knowledge/${encodeURIComponent(id)}`),
    reviewQueue: () => request<KnowledgeReviewItem[]>('/knowledge/reviews'),
    reviewers: () => request<Member[]>('/knowledge/reviewers'),
    members: () => request<Member[]>('/members'),
    save: (input: KnowledgeRevisionInput, current?: KnowledgeDetail | null) => current ? mutate<KnowledgeDetail>(`/knowledge/${current.id}`, { object_version: current.version, ...input }, false, 'PATCH') : mutate<KnowledgeDetail>('/knowledge', input),
    submit: (current: KnowledgeDetail, reviewer: string) => mutate<KnowledgeDetail>(`/knowledge/${current.id}/submit`, { object_version: current.version, revision_id: current.latest.id, reviewer_id: reviewer, consent: true }, true),
    cancelSubmission: (current: KnowledgeDetail) => mutate<KnowledgeDetail>(`/knowledge/${current.id}/cancel-submission`, { object_version: current.version }, true),
    review: (item: KnowledgeReviewItem, decision: 'approve' | 'changes_requested', reason: string) => mutate<{ ok: true; id: string; version: number; decision: string }>(`/knowledge/${item.id}/review`, { object_version: item.version, revision_id: item.revision.id, decision, reason }, true),
    withdraw: (current: KnowledgeDetail) => mutate<KnowledgeDetail>(`/knowledge/${current.id}/withdraw`, { object_version: current.version }, true),
    restrict: (current: KnowledgeDetail, ids: string[]) => mutate<KnowledgeDetail>(`/knowledge/${current.id}/restrict`, { object_version: current.version, scope: 'members', member_ids: ids }, true),
    answer: (question: string, useModel = false, signal?: AbortSignal) => request<KnowledgeAnswer>('/knowledge/answers', 'POST', { question, use_model: useModel }, undefined, useModel ? 65000 : 20000, signal),
  }
}
