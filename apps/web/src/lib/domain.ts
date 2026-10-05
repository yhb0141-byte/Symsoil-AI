import type { Candidate, CandidateKind, ExpressionDetail, Invitation, RephraseChoice, StanceKind, UnderstandingStatus, Utterance } from './types'
export const stanceLabels: Record<StanceKind, string> = { support: '支持', conditional: '有条件支持', reservation: '保留意见', oppose: '反对', need_info: '需要更多信息' }
export const invitationLabels: Record<Invitation['status'], string> = { pending: '等待回应', accepted: '已接受', declined: '已拒绝', negotiating: '协商条件中' }
export const roleLabels = { admin: '社区管理员', facilitator: '议题主持人', member: '社区成员' }
export function isConfirmed(item: Utterance): boolean { return item.confirmed_version === item.version && item.confirmed_at !== null }
export function validStance(stance: StanceKind, condition: string): boolean { return stance !== 'conditional' || condition.trim().length > 0 }
export function dateText(value?: string | null): string {
  if (!value) return '未设置'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(new Date(value))
}

export const candidateLabels: Record<CandidateKind, string> = { everyday: '日常表达', discussion: '本次讨论表达' }
export const choiceLabels: Record<RephraseChoice, string> = { candidate: '使用本人确认的候选', original_only: '只用我的原话', no_rephrase: '拒绝现有转述' }
export const understandingLabels: Record<UnderstandingStatus, string> = { pending: '等待表达者核对', accurate: '表达者确认听懂', needs_correction: '表达者提出修正', prefer_in_person: '表达者希望当面交流' }
export function confirmedCandidate(detail: ExpressionDetail | null): Candidate | null {
  const choice = detail?.choice
  if (!detail || choice?.choice !== 'candidate' || choice.utterance_version !== detail.utterance.version) return null
  return detail.candidates.find(candidate => candidate.id === choice.candidate_id && candidate.utterance_version === detail.utterance.version && candidate.version === choice.candidate_version && candidate.confirmed_version === candidate.version && candidate.confirmed_at !== null) ?? null
}
