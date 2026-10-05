import { shallowRef } from 'vue'
import type { KnowledgeAnswer, KnowledgeCitation, PublishedDocument } from './types'

/** Quotes and answers are ephemeral. Source changes, logout and older reads cannot revive them. */
export function createKnowledgeReading(api: {
  source: (id: string, revision: string) => Promise<PublishedDocument>
  answer: (question: string, useModel: boolean, signal: AbortSignal) => Promise<KnowledgeAnswer>
}) {
  const source = shallowRef<PublishedDocument | null>(null)
  const answer = shallowRef<KnowledgeAnswer | null>(null)
  const citation = shallowRef<KnowledgeCitation | null>(null)
  let sourceRead = 0, answerRead = 0, disposed = false
  let controller: AbortController | null = null
  function clearSource() { sourceRead += 1; source.value = null; citation.value = null }
  function clear() { clearSource(); answerRead += 1; answer.value = null; controller?.abort(); controller = null }
  async function open(id: string, revision: string, reference?: KnowledgeCitation): Promise<boolean> {
    clearSource()
    const current = sourceRead
    try {
      const result = await api.source(id, revision)
      if (disposed || current !== sourceRead) return false
      if (reference && (result.revision_id !== reference.revision_id || result.access_epoch !== reference.access_epoch || result.version !== reference.document_version)) {
        throw new Error('引用所依赖的发布版本或访问范围已变化。请重新检索当前资料。')
      }
      source.value = result; citation.value = reference ?? null
      return true
    } catch (error) {
      if (disposed || current !== sourceRead) return false
      clear(); throw error
    }
  }
  async function ask(question: string, useModel = false): Promise<boolean> {
    clear()
    const current = answerRead
    controller = new AbortController()
    try {
      const result = await api.answer(question, useModel, controller.signal)
      if (disposed || current !== answerRead) return false
      answer.value = result
      return true
    } catch (error) { if (!disposed && current === answerRead) throw error; return false }
    finally { if (current === answerRead) controller = null }
  }
  return { source, answer, citation, open, ask, clear, clearSource, dispose: () => { disposed = true; clear() } }
}
