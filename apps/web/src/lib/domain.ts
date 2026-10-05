import type { Invitation, StanceKind, Utterance } from './types'
export const stanceLabels: Record<StanceKind, string> = { support: '支持', conditional: '有条件支持', reservation: '保留意见', oppose: '反对', need_info: '需要更多信息' }
export const invitationLabels: Record<Invitation['status'], string> = { pending: '等待回应', accepted: '已接受', declined: '已拒绝', negotiating: '协商条件中' }
export const roleLabels = { admin: '社区管理员', facilitator: '议题主持人', member: '社区成员' }
export function isConfirmed(item: Utterance): boolean { return item.confirmed_version === item.version && item.confirmed_at !== null }
export function validStance(stance: StanceKind, condition: string): boolean { return stance !== 'conditional' || condition.trim().length > 0 }
export function dateText(value?: string | null): string {
  if (!value) return '未设置'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(new Date(value))
}
