import { ApiError, mutationKey, request } from './api'

export type CorrectionSource = { document_id: string; revision_id: string; document_version: number; access_epoch: number; title: string }
export type CorrectionContext = CorrectionSource & { maintainer: string; recipient: { id: string; display_name: string } }
export type Correction = { id: string; document_id: string; revision_id: string; document_version: number; source_access_epoch: number; requester_id: string; requester_name: string; recipient_id: string; recipient_name: string; text: string; response: string | null; status: 'submitted' | 'responded' | 'withdrawn'; version: number; created_at: string; updated_at: string; responded_at: string | null; withdrawn_at: string | null; source: CorrectionSource | null }
export type CorrectionListing = { items: Correction[]; counts: { sent: number; incoming: number; pending_incoming: number } }
export type CorrectionTarget = { id: string; revision_id: string; access_epoch: number }
export const correctionLabels = { submitted: '等待录入者回应', responded: '录入者已回应', withdrawn: '本人已撤回共享' }

export function createCorrectionsApi() {
  const keys = new Map<string, string>()
  async function mutate(path: string, body: unknown): Promise<Correction> {
    const signature = JSON.stringify([path, body]), key = keys.get(signature) ?? mutationKey()
    keys.set(signature, key)
    try { const result = await request<Correction>(path, 'POST', body, key); keys.delete(signature); return result }
    catch (error) { if (error instanceof ApiError && error.status !== 0) keys.delete(signature); throw error }
  }
  return {
    clear: () => keys.clear(),
    list: () => request<CorrectionListing>('/knowledge-corrections'),
    detail: (id: string) => request<Correction>(`/knowledge-corrections/${encodeURIComponent(id)}`),
    preview: (target: CorrectionTarget) => request<CorrectionContext>(`/documents/${encodeURIComponent(target.id)}/correction-context?revision_id=${encodeURIComponent(target.revision_id)}&access_epoch=${target.access_epoch}`),
    create: (source: CorrectionContext, text: string) => mutate('/knowledge-corrections', { document_id: source.document_id, revision_id: source.revision_id, access_epoch: source.access_epoch, expected_recipient_id: source.recipient.id, text, consent: true }),
    respond: (item: Correction, text: string) => mutate(`/knowledge-corrections/${encodeURIComponent(item.id)}/respond`, { object_version: item.version, text, consent: true }),
    withdraw: (item: Correction) => mutate(`/knowledge-corrections/${encodeURIComponent(item.id)}/withdraw`, { object_version: item.version }),
  }
}

/** A closed view or changed account cannot receive an older private read. */
export function createCorrectionReadGate() {
  let generation = 0, alive = true
  return {
    start: () => ++generation,
    current: (ticket: number) => alive && ticket === generation,
    clear: () => { generation += 1 },
    dispose: () => { alive = false; generation += 1 },
  }
}
