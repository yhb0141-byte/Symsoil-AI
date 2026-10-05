import { describe, expect, it, vi } from 'vitest'
import { createKnowledgeReading } from './knowledgeReading'
import type { KnowledgeAnswer, KnowledgeCitation, PublishedDocument } from './types'

const source: PublishedDocument = { id: 'd', title: '可读资料', category: '合成', body: '第一行\n只在本人明确接受后承担', version: 1, source: '合成来源', updated_at: '2026-10-05T00:00:00Z', revision_id: 'r1', owner_name: '作者', maintainer: '合成维护人', purpose: '开发核对', effective_until: null, scope: 'members', access_epoch: 1, snippets: [] }
const citation: KnowledgeCitation = { citation_id: 'c1', document_id: 'd', revision_id: 'r1', document_version: 1, title: source.title, source: source.source, quote: '只在本人明确接受后承担', start_line: 2, end_line: 2, access_epoch: 1 }
const answer: KnowledgeAnswer = { mode: 'extract', answer: '资料摘录，非模型回答', citations: [citation], provider: null, model: null }
function deferred<T>() { let resolve: (value: T) => void = () => {}; const promise = new Promise<T>(finish => { resolve = finish }); return { promise, resolve } }

describe('ephemeral current-source reading', () => {
  it('clears quotes and answers before a source mutation can finish', async () => {
    const reading = createKnowledgeReading({ source: vi.fn().mockResolvedValue(source), answer: vi.fn().mockResolvedValue(answer) })
    await reading.ask('问题', false); await reading.open('d', 'r1', citation)
    expect(reading.source.value).toEqual(source)
    reading.clear()
    expect(reading.answer.value).toBeNull(); expect(reading.source.value).toBeNull(); expect(reading.citation.value).toBeNull()
  })
  it('rejects a quote when its access epoch changed even if the source revision remains readable', async () => {
    const reading = createKnowledgeReading({ source: vi.fn().mockResolvedValue({ ...source, access_epoch: 2 }), answer: vi.fn().mockResolvedValue(answer) })
    await reading.ask('问题', false)
    await expect(reading.open('d', 'r1', citation)).rejects.toThrow('访问范围已变化')
    expect(reading.answer.value).toBeNull(); expect(reading.source.value).toBeNull()
  })
  it('clears the old answer when the exact cited source returns 404', async () => {
    const reading = createKnowledgeReading({ source: vi.fn().mockRejectedValue(new Error('404')), answer: vi.fn().mockResolvedValue(answer) })
    await reading.ask('问题', false)
    await expect(reading.open('d', 'r1', citation)).rejects.toThrow('404')
    expect(reading.answer.value).toBeNull()
  })
  it('never revives an old quote after clearing it or selecting a newer source', async () => {
    const old = deferred<PublishedDocument>()
    const read = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce({ ...source, revision_id: 'r2', version: 2 })
    const reading = createKnowledgeReading({ source: read, answer: vi.fn().mockResolvedValue(answer) })
    const pending = reading.open('d', 'r1')
    await reading.open('d', 'r2')
    old.resolve(source)
    expect(await pending).toBe(false)
    expect(reading.source.value?.revision_id).toBe('r2')
  })
  it('aborts waiting inference and does not render a late result in a new query', async () => {
    const old = deferred<KnowledgeAnswer>()
    let oldSignal: AbortSignal | undefined
    const infer = vi.fn().mockImplementationOnce((_question, _useModel, signal) => { oldSignal = signal; return old.promise }).mockResolvedValueOnce({ ...answer, answer: '新的资料摘录' })
    const reading = createKnowledgeReading({ source: vi.fn().mockResolvedValue(source), answer: infer })
    const pending = reading.ask('旧问题', true)
    reading.clear()
    expect(oldSignal?.aborted).toBe(true)
    await reading.ask('新问题', false)
    old.resolve(answer)
    expect(await pending).toBe(false)
    expect(reading.answer.value?.answer).toBe('新的资料摘录')
  })
  it('cannot repopulate a disposed workspace after logout or navigation', async () => {
    const oldSource = deferred<PublishedDocument>(), oldAnswer = deferred<KnowledgeAnswer>()
    const reading = createKnowledgeReading({ source: () => oldSource.promise, answer: () => oldAnswer.promise })
    const question = reading.ask('问题', true), original = reading.open('d', 'r1')
    reading.dispose()
    oldSource.resolve(source); oldAnswer.resolve(answer)
    expect(await question).toBe(false); expect(await original).toBe(false)
    expect(reading.source.value).toBeNull(); expect(reading.answer.value).toBeNull()
  })
})
