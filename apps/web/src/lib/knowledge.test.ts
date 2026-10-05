import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearSession, setSession } from './api'
import { copyKnowledgeInput, createKnowledgeApi, decodeKnowledgeFile, emptyKnowledgeInput, expiryInstant, splitSourceLines, validateKnowledgeInput } from './knowledge'
import type { KnowledgeDetail, KnowledgeRevision, Session } from './types'

const session: Session = { user: { id: 'author', username: 'a', display_name: '作者', role: 'member', active: true }, csrf_token: 'test-private-page-proof' }
const revision: KnowledgeRevision = { ...emptyKnowledgeInput(), id: 'revision-1', document_id: 'doc-1', number: 1, created_at: '2026-10-05T00:00:00Z', title: '标题', category: '参与', body: '只有明确接受才承担任务。', source: '本人记录', rights: '合成授权，仅开发', purpose: '开发核对', maintainer: '合成维护人', requested_scope: 'members', requested_member_ids: ['listener'] }
const detail: KnowledgeDetail = { id: 'doc-1', version: 2, owner_id: 'author', owner_name: '作者', latest: revision, submitted: null, published: null, reviewer_id: null, access_epoch: 0, withdrawn_at: null, reviews: [], publication_active: false, audience: null }
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
beforeEach(() => { clearSession(); setSession(session); vi.stubGlobal('fetch', vi.fn()) })
afterEach(() => { clearSession(); vi.unstubAllGlobals() })

describe('private text intake', () => {
  it('reads UTF-8 Chinese and preserves Markdown as literal text', () => {
    const text = '# 授权\n<script>本行只是一段文字</script>'
    expect(decodeKnowledgeFile('记录.MD', new TextEncoder().encode(text).buffer)).toBe(text)
  })
  it('rejects another format, invalid UTF-8, and binary NUL without changing the current body', () => {
    expect(() => decodeKnowledgeFile('secret.docx', new ArrayBuffer(1))).toThrow('仅支持')
    expect(() => decodeKnowledgeFile('bad.txt', new Uint8Array([0xc3, 0x28]).buffer)).toThrow('UTF-8')
    expect(() => decodeKnowledgeFile('binary.txt', new Uint8Array([0]).buffer)).toThrow('空字符')
  })
  it('checks the 20000-character intake limit independently of bytes', () => {
    expect(() => decodeKnowledgeFile('long.txt', new TextEncoder().encode('壤'.repeat(20001)).buffer)).toThrow('20000')
    expect(() => decodeKnowledgeFile('large.txt', new ArrayBuffer(80001))).toThrow('文件过大')
  })
  it('copies only editable fields and an independent explicit member list', () => {
    const input = copyKnowledgeInput(revision)
    input.requested_member_ids.push('new-member')
    expect(revision.requested_member_ids).toEqual(['listener'])
    expect(input).not.toHaveProperty('id')
    expect(input).not.toHaveProperty('owner_id')
    expect(validateKnowledgeInput({ ...input, requested_member_ids: [] })).toContain('固定名单')
    expect(validateKnowledgeInput({ ...input, rights: ' ' })).toContain('授权依据')
    expect(expiryInstant('')).toBeNull()
    expect(() => expiryInstant('invalid-date')).toThrow('有效')
  })
  it('locates citations across CRLF, CR, LF, NEL and Unicode paragraph boundaries like Python splitlines', () => {
    const lines = splitSourceLines('第一行\r\n第二行\r第三行\n第四行\u0085第五行\u2028第六行\u2029第七行\n')
    expect(lines).toEqual(['第一行', '第二行', '第三行', '第四行', '第五行', '第六行', '第七行'])
    expect(lines.slice(4, 6).join('\n')).toBe('第五行\n第六行')
    expect(splitSourceLines('')).toEqual([])
    expect(splitSourceLines('\n\n')).toEqual(['', ''])
    expect(splitSourceLines('甲\v乙\f丙\x1c丁\x1d戊\x1e己')).toEqual(['甲', '乙', '丙', '丁', '戊', '己'])
    expect(splitSourceLines('最后一行')).toEqual(['最后一行'])
  })
})

describe('knowledge requests', () => {
  it('defaults to extract mode and includes proof for private reads and exact source revisions', async () => {
    const api = createKnowledgeApi()
    vi.mocked(fetch).mockResolvedValue(response({ mode: 'extract' }))
    await api.answer('怎么参加？')
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.body).toBe('{"question":"怎么参加？","use_model":false}')
    await api.source('private/doc', 'rev 2')
    expect(fetch).toHaveBeenLastCalledWith('/api/v1/documents/private%2Fdoc?revision_id=rev%202', expect.objectContaining({ method: 'GET', headers: expect.objectContaining({ 'X-CSRF-Token': session.csrf_token }) }))
  })
  it('submits the exact latest version with separate author consent, never a blanket approval', async () => {
    const api = createKnowledgeApi()
    vi.mocked(fetch).mockResolvedValue(response(detail))
    await api.submit(detail, 'another-reviewer')
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0]?.[1]?.body as string)).toEqual({ object_version: 2, revision_id: 'revision-1', reviewer_id: 'another-reviewer', consent: true })
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).toHaveProperty('Idempotency-Key')
  })
  it('reuses the exact mutation key after a network failure and clears it after a conflict', async () => {
    const api = createKnowledgeApi()
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(response({ detail: '版本变化' }, 409)).mockResolvedValueOnce(response(detail))
    await expect(api.restrict(detail, [])).rejects.toMatchObject({ status: 0 })
    await expect(api.restrict(detail, [])).rejects.toMatchObject({ status: 409 })
    await api.restrict(detail, [])
    const options = vi.mocked(fetch).mock.calls.map(call => call[1])
    expect((options[0]?.headers as Record<string, string>)['Idempotency-Key']).toBe((options[1]?.headers as Record<string, string>)['Idempotency-Key'])
    expect((options[1]?.headers as Record<string, string>)['Idempotency-Key']).not.toBe((options[2]?.headers as Record<string, string>)['Idempotency-Key'])
    expect(JSON.parse(options[2]?.body as string)).toEqual({ object_version: 2, scope: 'members', member_ids: [] })
  })
  it('revokes just the pending submission with a distinct endpoint and version', async () => {
    const api = createKnowledgeApi()
    vi.mocked(fetch).mockResolvedValue(response(detail))
    await api.cancelSubmission(detail)
    expect(fetch).toHaveBeenCalledWith('/api/v1/knowledge/doc-1/cancel-submission', expect.objectContaining({ body: '{"object_version":2}', headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }))
  })
})
