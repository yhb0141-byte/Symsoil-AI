import { describe, expect, it } from 'vitest'
import { dateText, isConfirmed, validStance } from './domain'
import type { Utterance } from './types'
const original: Utterance = { id: 'u', title: '我的原话', text: '我不能接受此安排。', version: 2, confirmed_version: 1, confirmed_at: '2026-10-05T00:00:00Z', shared_topic_id: null, created_at: '2026-10-05T00:00:00Z', updated_at: '2026-10-05T00:00:00Z' }
describe('explicit versioned confirmation', () => {
  it('does not inherit confirmation after editing the original text', () => { expect(isConfirmed(original)).toBe(false); expect(isConfirmed({ ...original, confirmed_version: 2 })).toBe(true) })
  it('does not treat a version number without confirmation time as a confirmation', () => { expect(isConfirmed({ ...original, confirmed_version: 2, confirmed_at: null })).toBe(false) })
  it('requires meaningful conditions for conditional support', () => { expect(validStance('conditional', '  ')).toBe(false); expect(validStance('conditional', '必须有人承担清理')).toBe(true); expect(validStance('oppose', '')).toBe(true) })
  it('shows explicitly absent deadlines without inventing dates', () => { expect(dateText(null)).toBe('未设置') })
})
