import { describe, expect, it } from 'vitest'
import { confirmedCandidate, dateText, isConfirmed, validStance } from './domain'
import type { Candidate, ExpressionDetail, Utterance } from './types'
const original: Utterance = { id: 'u', title: '我的原话', text: '我不能接受此安排。', version: 2, confirmed_version: 1, confirmed_at: '2026-10-05T00:00:00Z', shared_topic_id: null, created_at: '2026-10-05T00:00:00Z', updated_at: '2026-10-05T00:00:00Z' }
describe('explicit versioned confirmation', () => {
  it('does not inherit confirmation after editing the original text', () => { expect(isConfirmed(original)).toBe(false); expect(isConfirmed({ ...original, confirmed_version: 2 })).toBe(true) })
  it('does not treat a version number without confirmation time as a confirmation', () => { expect(isConfirmed({ ...original, confirmed_version: 2, confirmed_at: null })).toBe(false) })
  it('requires meaningful conditions for conditional support', () => { expect(validStance('conditional', '  ')).toBe(false); expect(validStance('conditional', '必须有人承担清理')).toBe(true); expect(validStance('oppose', '')).toBe(true) })
  it('shows explicitly absent deadlines without inventing dates', () => { expect(dateText(null)).toBe('未设置') })
})

const candidate: Candidate = { id: 'c', utterance_id: 'u', utterance_version: 2, kind: 'discussion', text: '我无法接受此次安排，请保留我的异议。', context: '私人背景', target_context: '本次会议', purpose: '保留异议', version: 1, origin: 'manual', confirmed_version: 1, confirmed_at: '2026-10-05T00:00:00Z', created_at: '2026-10-05T00:00:00Z', updated_at: '2026-10-05T00:00:00Z' }
const detail: ExpressionDetail = { utterance: original, candidates: [candidate], choice: { utterance_id: 'u', utterance_version: 2, version: 1, choice: 'candidate', candidate_id: 'c', candidate_version: 1, confirmed_at: '2026-10-05T00:00:00Z', updated_at: '2026-10-05T00:00:00Z' }, share: null }
describe('candidate choice is distinct from original confirmation and sharing', () => {
  it('finds only the currently chosen and confirmed candidate version', () => { expect(confirmedCandidate(detail)?.id).toBe('c'); expect(isConfirmed(detail.utterance)).toBe(false); expect(detail.share).toBeNull() })
  it('rejects an edited candidate even if the old choice remains in a stale client snapshot', () => { expect(confirmedCandidate({ ...detail, candidates: [{ ...candidate, version: 2 }] })).toBeNull() })
  it('rejects a candidate bound to an older original text version', () => { expect(confirmedCandidate({ ...detail, utterance: { ...original, version: 3 } })).toBeNull() })
  it('does not publish a candidate after the author chooses original only or rejects rephrasing', () => { expect(confirmedCandidate({ ...detail, choice: { ...detail.choice!, choice: 'original_only', candidate_id: null, candidate_version: null } })).toBeNull(); expect(confirmedCandidate({ ...detail, choice: { ...detail.choice!, choice: 'no_rephrase', candidate_id: null, candidate_version: null } })).toBeNull() })
})
