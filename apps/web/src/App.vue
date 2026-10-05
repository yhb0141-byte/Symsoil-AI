<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import Icon from './components/Icon.vue'
import Modal from './components/Modal.vue'
import { ApiError, clearSession, endSession, errorText, mutationKey, onUnauthorized, request, setSession } from './lib/api'
import { dateText, invitationLabels, isConfirmed, roleLabels, stanceLabels, validStance } from './lib/domain'
import type { AuditEvent, Dashboard, Document, Invitation, InvitationResponse, Member, Option, Session, SessionStatus, StanceKind, Topic, TopicDetail, User, Utterance } from './lib/types'

type Page = 'home' | 'documents' | 'expressions' | 'topics' | 'tasks' | 'memory' | 'permissions' | 'admin'
type Dialog = 'document' | 'expression' | 'share' | 'revoke' | 'topic' | 'participants' | 'option' | 'stance' | 'invitation' | 'response' | 'help' | 'admin-invite' | 'freeze' | null
const entries: { id: Page; title: string; subtitle: string; icon: string }[] = [
  { id: 'documents', title: '查资料', subtitle: '找到来源，也找到下一步', icon: 'book' },
  { id: 'expressions', title: '说想法', subtitle: '先写给自己，再选择分享', icon: 'pen' },
  { id: 'topics', title: '看议题', subtitle: '看见差异，一起比较方案', icon: 'discuss' },
  { id: 'tasks', title: '做事情', subtitle: '核对条件，由本人接下邀请', icon: 'task' },
  { id: 'memory', title: '共同记忆', subtitle: '经验与感谢，等待授权后沉淀', icon: 'memory' },
  { id: 'permissions', title: '我的权限', subtitle: '知道谁能看到，随时核对', icon: 'shield' },
]
const user = ref<User | null>(null)
const page = ref<Page>('home')
const authLoading = ref(true)
const loading = ref(false)
const busy = ref(false)
const logoutPending = ref(false)
const pageError = ref('')
const formError = ref('')
const authError = ref('')
const notice = ref('')
const dialog = ref<Dialog>(null)
const loginMode = ref<'login' | 'register'>('login')
const login = ref({ username: '', password: '', token: '' })
const dashboard = ref<Dashboard | null>(null)
const documents = ref<Document[]>([])
const expressions = ref<Utterance[]>([])
const topics = ref<Topic[]>([])
const invitations = ref<Invitation[]>([])
const members = ref<Member[]>([])
const adminMembers = ref<User[]>([])
const audits = ref<AuditEvent[]>([])
const sessions = ref<SessionStatus[]>([])
const selectedDocument = ref<Document | null>(null)
const selectedExpression = ref<Utterance | null>(null)
const selectedTopic = ref<TopicDetail | null>(null)
const selectedOption = ref<Option | null>(null)
const selectedInvitation = ref<Invitation | null>(null)
const freezeUser = ref<User | null>(null)
const query = ref('')
const expressionForm = ref({ title: '', text: '' })
const topicForm = ref({ title: '', description: '', scope: '' })
const optionForm = ref({ title: '', description: '', cost: '', labor: '', risks: '' })
const invitationForm = ref({ invitee_id: '', title: '', description: '', completion_criteria: '', resources: '', compensation: '', due_date: '' })
const responseForm = ref<{ response: InvitationResponse; note: string }>({ response: 'accepted', note: '' })
const stanceForm = ref<{ stance: StanceKind; condition: string }>({ stance: 'need_info', condition: '' })
const adminForm = ref<{ username: string; display_name: string; role: User['role'] }>({ username: '', display_name: '', role: 'member' })
const shareTopicId = ref('')
const shareConsent = ref(false)
const participantId = ref('')
const inviteResult = ref<{ token: string; expires_at: string } | null>(null)
const helpSubject = ref('参与与人工协助')
const mutationKeys = new Map<string, string>()
let activityAt = Date.now()
let idleTimer: ReturnType<typeof setInterval> | undefined
let noticeTimer: ReturnType<typeof setTimeout> | undefined
let heartbeatTimer: ReturnType<typeof setInterval> | undefined
let heartbeatBusy = false
const canCreateTopic = computed(() => user.value?.role === 'admin' || user.value?.role === 'facilitator')
const pageTitle = computed(() => page.value === 'home' ? '社区工作台' : page.value === 'admin' ? '账号管理' : entries.find(entry => entry.id === page.value)?.title ?? '社区工作台')
const myPending = computed(() => invitations.value.filter(item => item.invitee_id === user.value?.id && ['pending', 'negotiating'].includes(item.status)))
const participantCandidates = computed(() => members.value.filter(member => !selectedTopic.value?.participants.includes(member.id)))
const shareTarget = computed(() => topics.value.find(topic => topic.id === shareTopicId.value))
const currentStance = computed(() => selectedOption.value?.stances.find(item => item.member_id === user.value?.id))

function showNotice(message: string) {
  notice.value = message
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => { notice.value = '' }, 6500)
}
function resetPrivateMemory(reason = '') {
  clearSession()
  user.value = null
  dashboard.value = null
  documents.value = []; expressions.value = []; topics.value = []; invitations.value = []
  members.value = []; adminMembers.value = []; audits.value = []; sessions.value = []
  selectedDocument.value = null; selectedExpression.value = null; selectedTopic.value = null
  selectedOption.value = null; selectedInvitation.value = null; freezeUser.value = null
  expressionForm.value = { title: '', text: '' }; topicForm.value = { title: '', description: '', scope: '' }
  optionForm.value = { title: '', description: '', cost: '', labor: '', risks: '' }
  invitationForm.value = { invitee_id: '', title: '', description: '', completion_criteria: '', resources: '', compensation: '', due_date: '' }
  responseForm.value = { response: 'accepted', note: '' }; stanceForm.value = { stance: 'need_info', condition: '' }
  adminForm.value = { username: '', display_name: '', role: 'member' }; login.value = { username: '', password: '', token: '' }
  inviteResult.value = null; shareTopicId.value = ''; shareConsent.value = false; query.value = ''; participantId.value = ''; helpSubject.value = '参与与人工协助'
  mutationKeys.clear(); dialog.value = null; pageError.value = ''; formError.value = ''; notice.value = ''
  page.value = 'home'; authError.value = reason
  document.title = '共壤 · 社区工作台'
}
onUnauthorized(() => resetPrivateMemory('会话已结束。请重新登录，未提交的内容已从页面清除。'))
function closeDialog() {
  if (busy.value) return
  dialog.value = null; formError.value = ''; inviteResult.value = null
  expressionForm.value = { title: '', text: '' }
  selectedExpression.value = null; selectedInvitation.value = null; selectedOption.value = null
  shareConsent.value = false
}
function openHelp(subject = '参与与人工协助') { helpSubject.value = subject; dialog.value = 'help'; formError.value = '' }
function openDialog(name: Dialog) { formError.value = ''; dialog.value = name }
async function authenticate() {
  if (busy.value || logoutPending.value) return
  busy.value = true; authError.value = ''
  try {
    if (loginMode.value === 'register') {
      await request<User>('/auth/register', 'POST', { token: login.value.token.trim(), password: login.value.password })
      login.value = { username: '', password: '', token: '' }; loginMode.value = 'login'
      authError.value = '账号已建立。请使用邀请中的用户名与新密码登录。'
      return
    }
    const session = await request<Session>('/auth/login', 'POST', { username: login.value.username.trim(), password: login.value.password })
    setSession(session); user.value = session.user; activityAt = Date.now(); login.value.password = ''
    await loadPage('home')
  } catch (error) { authError.value = errorText(error) }
  finally { busy.value = false }
}
async function logout(idle = false) {
  if (logoutPending.value) return
  logoutPending.value = true
  const ending = endSession()
  resetPrivateMemory(idle ? '已闲置 5 分钟，已立即清除页面私人内容。正在请求服务器撤销会话。' : '已立即清除页面私人内容。正在请求服务器撤销会话。')
  try {
    await ending
    if (!user.value) authError.value = idle ? '闲置会话已退出。未提交内容已清除，请重新登录。' : '服务器已确认退出。请重新登录后使用。'
  } catch {
    if (!user.value) authError.value = '页面私人内容已清除，但服务器尚未确认注销。请恢复连接后重新登录；刷新或新开页面不会自动恢复前一个账号。'
  } finally { logoutPending.value = false }
}
function activity() { activityAt = Date.now() }
async function loadPage(target = page.value) {
  if (!user.value) return
  page.value = target; loading.value = true; pageError.value = ''; selectedTopic.value = null
  document.title = `${pageTitle.value} · 共壤`
  try {
    if (target === 'home') dashboard.value = await request<Dashboard>('/dashboard')
    else if (target === 'documents') documents.value = await request<Document[]>(`/documents${query.value.trim() ? `?q=${encodeURIComponent(query.value.trim())}` : ''}`)
    else if (target === 'expressions') {
      const results = await Promise.all([request<Utterance[]>('/utterances'), request<Topic[]>('/topics')])
      expressions.value = results[0]; topics.value = results[1]
    } else if (target === 'topics') topics.value = await request<Topic[]>('/topics')
    else if (target === 'tasks') invitations.value = await request<Invitation[]>('/invitations')
    else if (target === 'permissions') {
      const results = await Promise.all([request<Utterance[]>('/utterances'), request<AuditEvent[]>('/audit'), request<SessionStatus[]>('/auth/sessions')])
      expressions.value = results[0]; audits.value = results[1]; sessions.value = results[2]
    } else if (target === 'admin') adminMembers.value = await request<User[]>('/admin/members')
  } catch (error) { pageError.value = errorText(error) }
  finally { loading.value = false; await nextTick(); document.querySelector<HTMLElement>('#page-title')?.focus() }
}
async function loadTopic(id: string) {
  loading.value = true; pageError.value = ''; page.value = 'topics'; document.title = '议题详情 · 共壤'
  try { selectedTopic.value = await request<TopicDetail>(`/topics/${id}`); members.value = await request<Member[]>('/members') }
  catch (error) { pageError.value = errorText(error); selectedTopic.value = null }
  finally { loading.value = false }
}
async function mutate<T>(path: string, body?: unknown, method = 'POST', keyed = false): Promise<T> {
  const signature = `${method}:${path}:${JSON.stringify(body ?? {})}`
  const key = keyed ? mutationKeys.get(signature) ?? mutationKey() : undefined
  if (key) mutationKeys.set(signature, key)
  try {
    const result = await request<T>(path, method, body, key)
    mutationKeys.delete(signature)
    return result
  } catch (error) {
    if (error instanceof ApiError && error.status !== 0) mutationKeys.delete(signature)
    throw error
  }
}
async function perform(action: () => Promise<void>, success: string) {
  if (busy.value) return
  busy.value = true; formError.value = ''; pageError.value = ''
  try { await action(); dialog.value = null; showNotice(success) }
  catch (error) { if (dialog.value) formError.value = errorText(error); else pageError.value = errorText(error) }
  finally { busy.value = false }
}
function editExpression(item?: Utterance) {
  selectedExpression.value = item ?? null
  expressionForm.value = { title: item?.title ?? '', text: item?.text ?? '' }
  openDialog('expression')
}
async function saveExpression() {
  await perform(async () => {
    const item = selectedExpression.value
    await mutate<Utterance>(item ? `/utterances/${item.id}` : '/utterances', { ...expressionForm.value, ...(item ? { object_version: item.version } : {}) }, item ? 'PATCH' : 'POST')
    expressions.value = await request<Utterance[]>('/utterances'); expressionForm.value = { title: '', text: '' }; selectedExpression.value = null
  }, '私稿已保存。此次保存没有分享给任何人；新版需要本人重新确认。')
}
async function confirmExpression(item: Utterance) {
  await perform(async () => {
    await mutate(`/utterances/${item.id}/confirmations`, { object_version: item.version }, 'POST', true)
    expressions.value = await request<Utterance[]>('/utterances')
  }, `已确认第 ${item.version} 版原话准确。尚未因此增加分享权限。`)
}
function prepareShare(item: Utterance) { selectedExpression.value = item; shareTopicId.value = ''; shareConsent.value = false; openDialog('share') }
async function shareExpression() {
  if (!selectedExpression.value || !shareTarget.value || !shareConsent.value) return
  const item = selectedExpression.value
  await perform(async () => {
    await mutate(`/utterances/${item.id}/share`, { object_version: item.version, topic_id: shareTopicId.value }, 'POST', true)
    expressions.value = await request<Utterance[]>('/utterances'); selectedExpression.value = null; shareConsent.value = false
  }, '已按预览将这一版原话分享给指定议题参与者。可在“我的权限”撤回。')
}
function prepareRevoke(item: Utterance) { selectedExpression.value = item; openDialog('revoke') }
async function revokeExpression() {
  if (!selectedExpression.value) return
  const item = selectedExpression.value
  await perform(async () => {
    await mutate(`/utterances/${item.id}/revoke`, { object_version: item.version })
    expressions.value = await request<Utterance[]>('/utterances'); selectedExpression.value = null
    if (page.value === 'permissions') audits.value = await request<AuditEvent[]>('/audit')
  }, '分享已撤回，当前议题视图已停止展示。已经被他人看到的内容无法从记忆中撤除。')
}
function newTopic() { if (!canCreateTopic.value) { openHelp('发起议题需由已授权主持人或管理员办理'); return }; topicForm.value = { title: '', description: '', scope: '' }; openDialog('topic') }
async function saveTopic() {
  await perform(async () => { const topic = await mutate<Topic>('/topics', topicForm.value); await loadTopic(topic.id) }, '合成测试议题已建立。只有受邀参与者可以访问。')
}
function prepareParticipants() { participantId.value = ''; openDialog('participants') }
async function addParticipant() {
  if (!selectedTopic.value || !participantId.value) return
  const topic = selectedTopic.value
  await perform(async () => { selectedTopic.value = await mutate<TopicDetail>(`/topics/${topic.id}/participants`, { member_id: participantId.value, object_version: topic.version }) }, '参与者已加入此议题可见范围。请按实际议事程序进行线下告知。')
}
function newOption() { optionForm.value = { title: '', description: '', cost: '', labor: '', risks: '' }; openDialog('option') }
async function saveOption() {
  if (!selectedTopic.value) return
  const topic = selectedTopic.value
  await perform(async () => { selectedTopic.value = await mutate<TopicDetail>(`/topics/${topic.id}/options`, { ...optionForm.value, object_version: topic.version }) }, '备选方案已加入，等待参与者比较和表达立场。')
}
function prepareStance(option: Option) {
  selectedOption.value = option
  const previous = option.stances.find(stance => stance.member_id === user.value?.id)
  stanceForm.value = { stance: previous?.stance ?? 'need_info', condition: previous?.condition ?? '' }
  openDialog('stance')
}
async function saveStance() {
  if (!selectedTopic.value || !selectedOption.value) return
  if (!validStance(stanceForm.value.stance, stanceForm.value.condition)) { formError.value = '请写明有条件支持的具体条件。'; return }
  const topic = selectedTopic.value, option = selectedOption.value
  await perform(async () => { selectedTopic.value = await mutate<TopicDetail>(`/topics/${topic.id}/stances`, { option_id: option.id, option_version: option.version, ...stanceForm.value }, 'POST', true) }, '立场已保存并绑定本次方案版本。表达立场不构成正式批准。')
}
function newInvitation() {
  invitationForm.value = { invitee_id: '', title: '', description: '', completion_criteria: '', resources: '', compensation: '', due_date: '' }
  openDialog('invitation')
}
async function saveInvitation() {
  if (!selectedTopic.value) return
  const topicId = selectedTopic.value.id
  await perform(async () => {
    await mutate<Invitation>(`/topics/${topicId}/invitations`, { ...invitationForm.value, due_date: invitationForm.value.due_date ? new Date(`${invitationForm.value.due_date}T23:59:00+08:00`).toISOString() : null })
    selectedTopic.value = await request<TopicDetail>(`/topics/${topicId}`)
  }, '合成任务邀请已发出。只有被邀请者本人回应后才改变状态。')
}
function prepareResponse(item: Invitation) { selectedInvitation.value = item; responseForm.value = { response: 'accepted', note: '' }; openDialog('response') }
async function saveResponse() {
  if (!selectedInvitation.value) return
  const item = selectedInvitation.value
  await perform(async () => {
    await mutate<Invitation>(`/invitations/${item.id}/response`, { object_version: item.version, ...responseForm.value }, 'POST', true)
    if (page.value === 'home') dashboard.value = await request<Dashboard>('/dashboard')
    else if (selectedTopic.value) selectedTopic.value = await request<TopicDetail>(`/topics/${selectedTopic.value.id}`)
    else invitations.value = await request<Invitation[]>('/invitations')
    selectedInvitation.value = null
  }, '本人回应已保存。本轮属于合成测试，不构成真实项目执行授权。')
}
function newAdminInvite() { adminForm.value = { username: '', display_name: '', role: 'member' }; inviteResult.value = null; openDialog('admin-invite') }
async function saveAdminInvite() {
  if (busy.value) return
  busy.value = true; formError.value = ''
  try { inviteResult.value = await mutate('/admin/invites', adminForm.value); showNotice('一次性邀请已建立，请通过已约定的人工渠道交给指定成员。') }
  catch (error) { formError.value = errorText(error) }
  finally { busy.value = false }
}
async function copyInvite() {
  if (!inviteResult.value) return
  try { await navigator.clipboard.writeText(inviteResult.value.token); showNotice('邀请口令已复制，请仅交给指定成员。') }
  catch { formError.value = '当前环境不支持自动复制，请选中口令手动复制。' }
}
function prepareFreeze(item: User) { freezeUser.value = item; openDialog('freeze') }
async function freezeMember() {
  if (!freezeUser.value) return
  const id = freezeUser.value.id
  await perform(async () => { await mutate(`/admin/members/${id}/freeze`); adminMembers.value = await request<User[]>('/admin/members') }, '账号已冻结，服务器已使其现有会话失效。')
}
function memberName(id: string) { return members.value.find(member => member.id === id)?.display_name ?? '议题参与者' }
function auditLabel(action: string): string {
  const labels: Record<string, string> = { 'auth.login': '账号登录', 'auth.logout': '退出账号', 'auth.register': '建立账号', 'registration.invite': '建立加入邀请', 'member.freeze': '冻结账号', 'utterance.create': '保存私稿', 'utterance.edit': '修改私稿', 'utterance.confirm': '确认表达准确', 'utterance.share': '分享表达', 'utterance.revoke': '撤回分享', 'topic.create': '建立议题', 'topic.participant.add': '添加议题参与者', 'topic.option.add': '补充备选方案', 'topic.stance': '保存方案立场', 'task.invite': '发出任务邀请', 'task.accepted': '本人接受任务邀请', 'task.declined': '本人拒绝任务邀请', 'task.negotiating': '本人提出协商条件' }
  return labels[action] ?? action
}
onMounted(async () => {
  document.addEventListener('pointerdown', activity); document.addEventListener('keydown', activity); document.addEventListener('input', activity)
  idleTimer = setInterval(() => { if (user.value && Date.now() - activityAt >= 5 * 60 * 1000) { activityAt = Date.now(); void logout(true) } }, 1000)
  // Public/shared terminals require explicit sign-in on every reload and new tab.
  // A cookie left by an interrupted logout never restores private UI automatically.
  authLoading.value = false
  heartbeatTimer = setInterval(async () => {
    if (!user.value || heartbeatBusy || Date.now() - activityAt > 60000) return
    heartbeatBusy = true
    try { await request<Session>('/auth/me') }
    catch (error) { if (error instanceof ApiError && error.status === 0 && user.value) showNotice('暂时无法续期会话，请检查与社区服务器的连接。未提交内容仍在当前页面中。') }
    finally { heartbeatBusy = false }
  }, 45000)
})
onUnmounted(() => { if (idleTimer) clearInterval(idleTimer); if (noticeTimer) clearTimeout(noticeTimer); if (heartbeatTimer) clearInterval(heartbeatTimer); document.removeEventListener('pointerdown', activity); document.removeEventListener('keydown', activity); document.removeEventListener('input', activity); clearSession() })
</script>

<template>
  <div v-if="authLoading" class="login-shell"><div class="loading-state" role="status"><Icon name="leaf" :size="34" /><p>正在连接社区工作台…</p></div></div>
  <div v-else-if="!user" class="login-shell">
    <section class="login-aside">
      <div class="brand"><Icon name="leaf" :size="34" /><span>共壤 <small>SYMSOIL</small></span></div>
      <div><p class="eyebrow">一片共同生长的土壤</p><h1>把想法说清楚，<br />把事情一起做好。</h1><p>在差异中互相理解，在真实行动中建立信任。<br />属于社区自己的数字工作台。</p></div>
      <p class="muted">社区掌握 · 本地协作 · 本人确认</p>
    </section>
    <main class="login-card">
      <div class="badge warning">R0 · 合成数据开发版</div>
      <h2>{{ loginMode === 'login' ? '回到社区工作台' : '使用一次性邀请加入' }}</h2>
      <p class="muted">本轮仅供开发测试。议题、回应与任务均不代表真实社区决定；AI 推理尚未上线。</p>
      <div v-if="authError" class="notice info" role="alert">{{ authError }}</div>
      <form @submit.prevent="authenticate">
        <label v-if="loginMode === 'login'" class="form-field">用户名<input v-model="login.username" autocomplete="username" required maxlength="64" placeholder="输入本地账号用户名" /></label>
        <label v-else class="form-field">一次性邀请口令<input v-model="login.token" autocomplete="off" required minlength="20" maxlength="128" placeholder="由社区管理员提供" /></label>
        <label class="form-field">{{ loginMode === 'login' ? '密码' : '设置密码' }}<input v-model="login.password" type="password" :autocomplete="loginMode === 'login' ? 'current-password' : 'new-password'" required :minlength="loginMode === 'register' ? 12 : 1" maxlength="128" placeholder="输入个人密码" /></label>
        <p v-if="loginMode === 'register'" class="muted">使用至少 12 位密码。注册成功后，使用邀请时约定的用户名登录。</p>
        <button class="button primary full-width" type="submit" :disabled="busy || logoutPending">{{ logoutPending ? '正在结束前一会话…' : busy ? '正在处理…' : loginMode === 'login' ? '进入工作台' : '建立本地账号' }}<Icon name="arrow" /></button>
      </form>
      <div class="inline-actions"><button class="button ghost" :disabled="busy || logoutPending" @click="loginMode = loginMode === 'login' ? 'register' : 'login'; authError = ''; login.password = ''">{{ loginMode === 'login' ? '我有加入邀请' : '返回账号登录' }}</button><button class="button ghost" @click="openHelp('账号登录与邀请')">需要帮助</button></div>
      <p class="muted login-note">公用设备闲置 5 分钟会自动退出。私人内容与凭据不会保存到浏览器本地存储；每次刷新或打开新页面均须显式登录。</p>
    </main>
  </div>
  <div v-else class="app-shell">
    <aside class="sidebar">
      <button class="brand brand-button" @click="loadPage('home')" aria-label="共壤首页"><Icon name="leaf" :size="32" /><span>共壤 <small>SYMSOIL</small></span></button>
      <p class="eyebrow sidebar-caption">社区工作台</p>
      <nav aria-label="主要功能"><button class="nav-item" :class="{ active: page === 'home' }" @click="loadPage('home')"><Icon name="home" />首页</button><button v-for="entry in entries" :key="entry.id" class="nav-item" :class="{ active: page === entry.id }" @click="loadPage(entry.id)"><Icon :name="entry.icon" />{{ entry.title }}<span v-if="entry.id === 'memory'" class="nav-hint">待上线</span></button><button v-if="user.role === 'admin'" class="nav-item" :class="{ active: page === 'admin' }" @click="loadPage('admin')"><Icon name="person" />账号管理</button></nav>
      <div class="sidebar-footer"><div class="notice info"><Icon name="leaf" /><p>这里的每一次分享、立场与承诺，都由你自己决定。</p></div><button class="button ghost" @click="openHelp()">求助与人工路径<Icon name="arrow" :size="16" /></button></div>
    </aside>
    <div class="workspace">
      <header class="topbar"><div><span class="desktop-only muted">共壤 / </span><span>{{ pageTitle }}</span></div><div class="inline-actions"><span class="badge">本地工作台</span><span class="user-name">{{ user.display_name }}</span><button class="button ghost icon-button" aria-label="退出账号" @click="logout()"><Icon name="logout" /></button></div></header>
      <div class="synthetic-banner"><span><strong>R0 合成测试</strong> · 当前记录不构成真实社区决定或项目授权。</span><span>AI 推理未上线</span></div>
      <main class="main-content">
        <div v-if="notice" class="notice success" role="status">{{ notice }}</div>
        <div v-if="pageError" class="notice error" role="alert"><p>{{ pageError }}</p><button class="button secondary" :disabled="loading" @click="selectedTopic ? loadTopic(selectedTopic.id) : loadPage()">重新载入</button></div>
        <div v-if="loading" class="loading-state" role="status"><span class="spinner"></span><p>正在读取你有权访问的记录…</p></div>
        <template v-else>
          <template v-if="page === 'home'">
            <section class="hero hero-card"><div><p class="eyebrow">共同生活，共同行动</p><h1 id="page-title" tabindex="-1">你好，{{ user.display_name }}。</h1><p>从一个想法、一句回应、一件可以一起做的事开始。</p><div class="inline-actions"><button class="button primary" @click="editExpression()">写下我的想法<Icon name="pen" /></button><button class="button secondary" @click="loadPage('topics')">去看议题<Icon name="arrow" /></button></div></div><div class="hero-art" aria-hidden="true"><div class="sun"></div><Icon name="leaf" :size="140" /><span>让关系慢慢生长</span></div></section>
            <section class="section-heading"><div><h2>需要我回应</h2><p class="muted">每一项都需要你的明确选择。没有回应，不会被当成同意。</p></div><button class="button ghost" @click="loadPage('tasks')">查看全部<Icon name="arrow" :size="18" /></button></section>
            <section class="card">
              <template v-if="dashboard?.pending.length"><article v-for="item in dashboard.pending" :key="item.id" class="list-row"><div class="avatar"><Icon name="task" /></div><div class="row-content"><div class="inline-actions"><h3>{{ item.title }}</h3><span class="badge warning">等待本人回应</span></div><p class="muted">{{ item.topic_title }} · 任务条款第 {{ item.version }} 版 · 截止 {{ dateText(item.due_date) }}</p></div><button class="button secondary" @click="prepareResponse(item)">核对与回应</button></article></template>
              <div v-else class="empty-state compact"><Icon name="check" :size="28" /><h3>暂时没有待回应事项</h3><p>你可以看看议题，或先保存一个私人想法。</p></div>
            </section>
            <div class="section-heading"><div><h2>从这里开始</h2><p class="muted">六个入口，承接社区里不同的事情。</p></div></div>
            <section class="entry-grid"><button v-for="entry in entries" :key="entry.id" class="entry-card" @click="loadPage(entry.id)"><div class="entry-icon"><Icon :name="entry.icon" :size="25" /></div><h3>{{ entry.title }}<span v-if="entry.id === 'memory'" class="badge quiet">下一阶段</span></h3><p>{{ entry.subtitle }}</p><Icon class="entry-arrow" name="arrow" :size="18" /></button></section>
            <section class="stats-row"><div class="stat"><strong>{{ dashboard?.counts.documents ?? 0 }}</strong><span>可查资料</span></div><div class="stat"><strong>{{ dashboard?.counts.topics ?? 0 }}</strong><span>可见议题</span></div><div class="stat"><strong>{{ dashboard?.counts.utterances ?? 0 }}</strong><span>我的私稿</span></div><div class="stat"><strong>{{ dashboard?.counts.open_invitations ?? 0 }}</strong><span>未完成回应</span></div></section>
            <div class="section-heading"><h2>最近的议题</h2><button v-if="canCreateTopic" class="button ghost" @click="newTopic()"><Icon name="plus" />发起议题</button></div>
            <section class="card"><article v-for="topic in dashboard?.topics ?? []" :key="topic.id" class="list-row"><div class="row-content"><h3>{{ topic.title }}</h3><p class="muted">{{ topic.scope }}</p></div><span class="badge">讨论中</span><button class="button ghost" @click="loadTopic(topic.id)">进入<Icon name="arrow" :size="17" /></button></article><div v-if="!dashboard?.topics.length" class="empty-state compact"><p>暂无可见议题。请联系已授权主持人发起或邀请参与。</p></div></section>
          </template>
          <template v-else-if="page === 'documents'">
            <div class="page-heading"><div><p class="eyebrow">有来源的社区知识</p><h1 id="page-title" tabindex="-1">查资料</h1><p class="muted">R0 提供关键词查询和原文阅读。所有资料均为合成测试内容。</p></div><button class="button secondary" @click="openHelp('资料纠错与查找负责人')">资料有疑问</button></div>
            <form class="toolbar search-form" @submit.prevent="loadPage('documents')"><label class="search-input"><Icon name="search" /><input v-model="query" aria-label="搜索社区资料" placeholder="搜索规则、场地或参与方法…" maxlength="200" /></label><button class="button primary" type="submit">查找资料</button><button v-if="query" class="button ghost" type="button" @click="query = ''; loadPage('documents')">清除</button></form>
            <div class="notice info">AI 问答尚未启用。当前搜索直接匹配已有资料，不会生成答案；找不到时可走人工路径。</div>
            <section v-if="documents.length" class="card-grid"><article v-for="doc in documents" :key="doc.id" class="card"><span class="badge">{{ doc.category }}</span><h2>{{ doc.title }}</h2><p class="line-clamp">{{ doc.body }}</p><div class="source-meta">第 {{ doc.version }} 版 · {{ dateText(doc.updated_at) }}</div><button class="button ghost" @click="selectedDocument = doc; openDialog('document')">查看原文与来源<Icon name="arrow" :size="17" /></button></article></section>
            <div v-else class="card empty-state"><Icon name="book" :size="34" /><h2>没有找到匹配资料</h2><p>试试更短的关键词，或请社区人员帮助查找。</p><button class="button secondary" @click="openHelp('找不到需要的资料')">转人工查找</button></div>
          </template>
          <template v-else-if="page === 'expressions'">
            <div class="page-heading"><div><p class="eyebrow">先表达，再决定谁能看见</p><h1 id="page-title" tabindex="-1">说想法</h1><p class="muted">你的原话默认只对本人可见。确认准确和允许分享是两次不同操作。</p></div><button class="button primary" @click="editExpression()"><Icon name="plus" />写一个私稿</button></div>
            <div class="notice info">R0 只处理你亲自填写的原话，尚无 AI 转述或理解核对。可以先线下交流，再自行修订。</div>
            <div v-if="!expressions.length" class="card empty-state"><Icon name="pen" :size="34" /><h2>这里还没有你的私稿</h2><p>写下你的想法、担忧或希望。保存后，再决定是否分享。</p><button class="button primary" @click="editExpression()">开始写想法</button></div>
            <section v-else class="stack"><article v-for="item in expressions" :key="item.id" class="card"><div class="section-heading"><div><p class="eyebrow">我的原话 · 第 {{ item.version }} 版</p><h2>{{ item.title }}</h2></div><span class="badge" :class="isConfirmed(item) ? 'success' : 'warning'">{{ isConfirmed(item) ? '本人已确认准确' : '待本人核对' }}</span></div><p class="preserve-text">{{ item.text }}</p><div class="divider"></div><p class="muted">{{ item.shared_topic_id ? '已分享给指定议题参与者' : '尚未分享 · 仅本人可见' }} · 更新 {{ dateText(item.updated_at) }}</p><div class="inline-actions"><button class="button secondary" :disabled="busy" @click="editExpression(item)">编辑原话</button><button v-if="!isConfirmed(item)" class="button secondary" :disabled="busy" @click="confirmExpression(item)">本人确认这版准确</button><button v-if="isConfirmed(item) && !item.shared_topic_id" class="button primary" :disabled="busy" @click="prepareShare(item)">预览并选择分享</button><button v-if="item.shared_topic_id" class="button danger" :disabled="busy" @click="prepareRevoke(item)">撤回分享</button></div></article></section>
          </template>
          <template v-else-if="page === 'topics' && !selectedTopic">
            <div class="page-heading"><div><p class="eyebrow">让差异有地方被看见</p><h1 id="page-title" tabindex="-1">看议题</h1><p class="muted">只展示你受邀参与的合成议题。表达立场不等于批准决定。</p></div><button v-if="canCreateTopic" class="button primary" @click="newTopic()"><Icon name="plus" />发起议题</button></div>
            <section v-if="topics.length" class="card-grid"><article v-for="topic in topics" :key="topic.id" class="card"><div class="inline-actions"><span class="badge">讨论中</span><span class="badge quiet">合成测试</span></div><h2>{{ topic.title }}</h2><p class="line-clamp">{{ topic.description }}</p><div class="source-meta">{{ topic.participants.length }} 位参与者 · 第 {{ topic.version }} 版</div><p class="muted">讨论范围：{{ topic.scope }}</p><button class="button ghost" @click="loadTopic(topic.id)">查看观点与方案<Icon name="arrow" :size="18" /></button></article></section>
            <div v-else class="card empty-state"><Icon name="discuss" :size="34" /><h2>暂无你可参与的议题</h2><p>请联系发起人邀请你。已授权的主持人和管理员可以创建合成测试议题。</p><button v-if="canCreateTopic" class="button primary" @click="newTopic()">发起议题</button></div>
          </template>
          <template v-else-if="page === 'topics' && selectedTopic">
            <button class="button ghost back-button" @click="loadPage('topics')">← 返回议题列表</button>
            <div class="detail-header"><div class="inline-actions"><span class="badge">讨论中</span><span class="badge quiet">合成测试 · v{{ selectedTopic.version }}</span></div><h1 id="page-title" tabindex="-1">{{ selectedTopic.title }}</h1><p class="preserve-text">{{ selectedTopic.description }}</p><div class="key-value"><span>讨论范围</span><strong>{{ selectedTopic.scope }}</strong></div><div class="inline-actions"><button class="button secondary" @click="loadTopic(selectedTopic.id)">刷新版本</button><button class="button ghost" @click="openHelp(`议题协商：${selectedTopic.title}`)">请求人工协助</button></div></div>
            <div class="topic-layout"><div class="stack">
              <section class="card"><div class="section-heading"><div><h2>已授权分享的观点</h2><p class="muted">只展示本人确认并显式分享的原话版本。</p></div><button class="button ghost" @click="loadPage('expressions')">分享我的想法<Icon name="arrow" :size="16" /></button></div><article v-for="view in selectedTopic.viewpoints" :key="view.id" class="viewpoint"><div class="inline-actions"><div class="avatar small">{{ view.author_name.slice(0, 1) }}</div><strong>{{ view.author_name }}</strong><span class="muted">原话 v{{ view.utterance_version }}</span></div><p class="preserve-text">{{ view.text }}</p><small class="muted">本人确认：{{ dateText(view.confirmed_at) }}</small></article><div v-if="!selectedTopic.viewpoints.length" class="empty-state compact"><p>暂时没有共享观点。未分享的私人原话不会出现在这里。</p></div></section>
              <section><div class="section-heading"><div><h2>比较备选方案</h2><p class="muted">保留支持、条件、异议与待核实的信息。</p></div><button class="button secondary" @click="newOption()"><Icon name="plus" />补充方案</button></div><div v-if="!selectedTopic.options.length" class="card empty-state compact"><p>还没有备选方案。可以先写清楚成本、劳动与风险。</p></div><article v-for="option in selectedTopic.options" :key="option.id" class="card option-card"><div class="section-heading"><h3>{{ option.title }}</h3><span class="badge quiet">方案 v{{ option.version }}</span></div><p class="preserve-text">{{ option.description }}</p><dl class="comparison-grid"><div><dt>费用与资源</dt><dd>{{ option.cost || '待补充' }}</dd></div><div><dt>劳动与承担</dt><dd>{{ option.labor || '待补充' }}</dd></div><div><dt>风险与未核实项</dt><dd>{{ option.risks || '待补充' }}</dd></div></dl><div class="divider"></div><h4>参与者的明确立场</h4><ul v-if="option.stances.length" class="stance-list"><li v-for="stance in option.stances" :key="stance.member_id"><span>{{ stance.member_name }}</span><span class="badge">{{ stanceLabels[stance.stance] }}</span><p v-if="stance.condition" class="preserve-text muted">{{ stance.condition }}</p></li></ul><p v-else class="muted">暂无明确立场。没有回应不会计入支持。</p><p class="muted">尚未表达：{{ Math.max(0, selectedTopic.participants.length - option.stances.length) }} 人。R0 不计算共识或正式批准。</p><button class="button primary" @click="prepareStance(option)">{{ option.stances.some(stance => stance.member_id === user?.id) ? '重新核对我的立场' : '表达我的立场' }}</button></article></section>
              <section class="card"><div class="section-heading"><h2>相关任务邀请</h2><button v-if="selectedTopic.owner_id === user.id" class="button secondary" @click="newInvitation()"><Icon name="plus" />邀请承担任务</button></div><article v-for="item in selectedTopic.invitations" :key="item.id" class="list-row"><div class="row-content"><h3>{{ item.title }}</h3><p class="muted">{{ item.invitee_name }} · {{ invitationLabels[item.status] }}</p></div><button class="button ghost" @click="prepareResponse(item)">{{ item.invitee_id === user.id && ['pending', 'negotiating'].includes(item.status) ? '核对与回应' : '查看条款' }}</button></article><p v-if="!selectedTopic.invitations.length" class="muted">没有你可见的任务条款。条款仅发起人与被邀请者可读。</p></section>
            </div><aside class="stack">
              <section class="card"><div class="section-heading"><h2>议题参与者</h2><button v-if="selectedTopic.owner_id === user.id" class="button ghost icon-button" aria-label="添加议题参与者" @click="prepareParticipants()"><Icon name="plus" /></button></div><ul class="participant-list"><li v-for="id in selectedTopic.participants" :key="id"><div class="avatar small">{{ memberName(id).slice(0, 1) }}</div><span>{{ memberName(id) }}</span><span v-if="id === selectedTopic.owner_id" class="badge quiet">发起人</span></li></ul><p class="muted">新增参与者会扩大已共享观点的议题可见范围。</p></section>
              <section class="card stage-card"><span class="badge warning">下一阶段 · R1</span><h3>正式决定与公共屏</h3><p>R0 尚未实现批准流程、理解核对、公共屏或自动摘要。请由主持人按约定程序组织线下协商，另行核对记录。</p><button class="button secondary" @click="openHelp('正式议事与公共屏替代路径')">查看人工议事路径</button></section>
            </aside></div>
          </template>
          <template v-else-if="page === 'tasks'">
            <div class="page-heading"><div><p class="eyebrow">邀请不等于分配</p><h1 id="page-title" tabindex="-1">做事情</h1><p class="muted">先核对范围、资源和条件，再由本人接受、拒绝或协商。{{ myPending.length }} 项需要你回应。</p></div><button class="button secondary" @click="openHelp('任务协商与行动协调')">需要调整或帮助</button></div>
            <div class="notice warning">R0 任务邀请均为独立的合成测试记录。接受只记录本人回应，不构成真实项目开始、付款或责任授权。</div>
            <section v-if="invitations.length" class="stack"><article v-for="item in invitations" :key="item.id" class="card"><div class="section-heading"><div><p class="eyebrow">{{ item.topic_title }} · 第 {{ item.version }} 版</p><h2>{{ item.title }}</h2></div><span class="badge" :class="item.status === 'pending' ? 'warning' : ''">{{ invitationLabels[item.status] }}</span></div><p class="preserve-text">{{ item.description }}</p><dl class="comparison-grid"><div><dt>被邀请者</dt><dd>{{ item.invitee_name }}{{ item.invitee_id === user.id ? '（我）' : '' }}</dd></div><div><dt>完成标准</dt><dd>{{ item.completion_criteria }}</dd></div><div><dt>资源支持</dt><dd>{{ item.resources || '未说明，接受前请核对' }}</dd></div><div><dt>报酬或自愿性质</dt><dd>{{ item.compensation || '未说明，接受前请核对' }}</dd></div><div><dt>截止时间</dt><dd>{{ dateText(item.due_date) }}</dd></div></dl><p v-if="item.note" class="notice info preserve-text">本人回应：{{ item.note }}</p><button class="button secondary" @click="prepareResponse(item)">{{ item.invitee_id === user.id && ['pending', 'negotiating'].includes(item.status) ? '核对条款并回应' : '查看完整条款' }}</button></article></section>
            <div v-else class="card empty-state"><Icon name="task" :size="34" /><h2>暂无你可见的任务邀请</h2><p>任务发起人与被邀请者可查看条款。你可以进入议题看看正在讨论的事情。</p><button class="button secondary" @click="loadPage('topics')">查看议题</button></div>
            <section class="card stage-card"><span class="badge quiet">下一阶段</span><h3>行动核验与共同复盘</h3><p>任务执行、结果核验、条件变更和复盘记录将在后续阶段接入。当前请联系协调人，使用纸面或线下记录。</p><button class="button ghost" @click="openHelp('行动核验与复盘')">查看人工复盘路径<Icon name="arrow" :size="17" /></button></section>
          </template>
          <template v-else-if="page === 'memory'">
            <div class="page-heading"><div><p class="eyebrow">让共同经历，有合适的归处</p><h1 id="page-title" tabindex="-1">共同记忆</h1><p class="muted">记录经验、故事和具体的感谢，需要相关人的授权与审阅。</p></div><span class="badge warning">R1 规划 · 尚未上线</span></div>
            <section class="card memory-intro"><Icon name="memory" :size="48" /><h2>共同记忆正在准备中</h2><p>R0 尚未提供故事发布、感谢墙、经验复盘或记忆授权。这里没有可发布的真实故事，也不会自动保存你的私稿作为共同记忆。</p><div class="card-grid"><div><h3>经验</h3><p class="muted">事情怎样发生，哪些方法可复用，以及适用边界。</p></div><div><h3>故事</h3><p class="muted">共同经历与地方记忆，由相关人审阅后选择分享。</p></div><div><h3>感谢</h3><p class="muted">对具体行动与照料的感谢，受众由表达者选择。</p></div></div><button class="button primary" @click="openHelp('共同记忆与线下授权')">查看人工记录与授权路径</button></section>
          </template>
          <template v-else-if="page === 'permissions'">
            <div class="page-heading"><div><p class="eyebrow">看见自己的授权与操作</p><h1 id="page-title" tabindex="-1">我的权限</h1><p class="muted">分享范围、会话和审计，只展示当前账号有权访问的记录。</p></div><button class="button secondary" @click="logout()"><Icon name="logout" />安全退出</button></div>
            <section class="card"><div class="section-heading"><div class="inline-actions"><div class="avatar">{{ user.display_name.slice(0, 1) }}</div><div><h2>{{ user.display_name }}</h2><p class="muted">{{ user.username }}</p></div></div><span class="badge">{{ roleLabels[user.role] }}</span></div><p>账号角色由已授权管理员配置。账号管理员不会因角色自动读到成员未分享的原话。</p><p class="muted">本地部署的系统维护人员仍有底层运维能力，使用应遵守社区的运维访问程序。</p><button v-if="user.role === 'admin'" class="button ghost" @click="loadPage('admin')">进入账号管理<Icon name="arrow" :size="17" /></button></section>
            <div class="section-heading"><h2>我分享的原话</h2><button class="button ghost" @click="loadPage('expressions')">管理我的私稿<Icon name="arrow" :size="17" /></button></div>
            <section class="card"><article v-for="item in expressions.filter(item => item.shared_topic_id)" :key="item.id" class="list-row"><div class="row-content"><h3>{{ item.title }}</h3><p class="muted">第 {{ item.version }} 版 · 可见范围：指定议题的参与者</p></div><button class="button danger" @click="prepareRevoke(item)">撤回分享</button></article><div v-if="!expressions.some(item => item.shared_topic_id)" class="empty-state compact"><p>当前没有共享中的原话。</p></div></section>
            <div class="section-heading"><h2>账号会话</h2></div><section class="card"><p>{{ sessions.length }} 条账号会话记录（含历史）。公用终端闲置 5 分钟自动退出；退出同时清除当前页面内存。</p><article v-for="(session, index) in sessions" :key="session.id ?? index" class="list-row"><div class="row-content"><h3>{{ session.current ? '当前会话' : session.revoked ? '已撤销的历史会话' : '其他账号会话记录' }}</h3><p class="muted">建立 {{ dateText(session.created_at) }} · 到期 {{ dateText(session.expires_at) }}</p></div><span v-if="session.current" class="badge">当前</span></article></section>
            <div class="section-heading"><h2>我的操作留痕</h2><button class="button ghost" @click="loadPage('permissions')">刷新</button></div><section class="card audit-list"><article v-for="(audit, index) in audits" :key="audit.id ?? index" class="list-row"><Icon name="clock" /><div class="row-content"><h3>{{ auditLabel(audit.action) }}</h3><p class="muted">{{ audit.object_type ?? '操作记录' }}{{ audit.object_id ? ` · ${audit.object_id.slice(0, 8)}` : '' }}</p></div><time>{{ dateText(audit.created_at ?? audit.timestamp) }}</time></article><div v-if="!audits.length" class="empty-state compact"><p>暂无当前账号的操作记录。</p></div></section>
            <section class="card stage-card"><h3>更正、导出与退出社区</h3><p>R0 尚未提供自动导出、数据删除和求助工单。请向社区指定受理人提出申请，先核对范围，再由人工办理并留存记录。</p><button class="button secondary" @click="openHelp('个人资料更正、导出或退出社区')">查看人工办理路径</button></section>
          </template>
          <template v-else-if="page === 'admin' && user.role === 'admin'">
            <div class="page-heading"><div><p class="eyebrow">账号管理与最小授权</p><h1 id="page-title" tabindex="-1">账号管理</h1><p class="muted">此处管理本地账号，不提供成员私稿读取权。</p></div><button class="button primary" @click="newAdminInvite()"><Icon name="plus" />建立加入邀请</button></div><section class="card"><article v-for="member in adminMembers" :key="member.id" class="list-row"><div class="avatar">{{ member.display_name.slice(0, 1) }}</div><div class="row-content"><h3>{{ member.display_name }}{{ member.id === user.id ? '（我）' : '' }}</h3><p class="muted">{{ member.username }} · {{ roleLabels[member.role] }}</p></div><span class="badge" :class="member.active ? 'success' : 'warning'">{{ member.active ? '可用' : '已冻结' }}</span><button v-if="member.active && member.id !== user.id" class="button danger" @click="prepareFreeze(member)">冻结账号</button></article><div v-if="!adminMembers.length" class="empty-state compact"><p>暂无账号记录。</p></div></section>
          </template>
        </template>
      </main>
    </div>
    <nav class="mobile-nav" aria-label="手机快捷导航"><button :class="{ active: page === 'home' }" @click="loadPage('home')"><Icon name="home" /><span>首页</span></button><button :class="{ active: page === 'tasks' }" @click="loadPage('tasks')"><Icon name="task" /><span>待回应</span></button><button :class="{ active: page === 'permissions' || page === 'admin' }" @click="loadPage('permissions')"><Icon name="person" /><span>我的</span></button></nav>
  </div>

  <Modal v-if="dialog" :title="dialog === 'help' ? '求助与人工路径' : dialog === 'document' ? '资料原文' : dialog === 'expression' ? selectedExpression ? '编辑我的原话' : '写下我的想法' : dialog === 'share' ? '预览本次原话分享' : dialog === 'revoke' ? '撤回原话分享' : dialog === 'topic' ? '发起合成测试议题' : dialog === 'participants' ? '添加议题参与者' : dialog === 'option' ? '补充备选方案' : dialog === 'stance' ? '核对并表达我的立场' : dialog === 'invitation' ? '邀请本人承担任务' : dialog === 'response' ? '核对任务条款' : dialog === 'admin-invite' ? '建立一次性加入邀请' : '冻结本地账号'" @close="closeDialog">
    <div v-if="formError" class="notice error" role="alert"><p>{{ formError }}</p><button v-if="formError.includes('版本')" class="button secondary" @click="closeDialog(); selectedTopic ? loadTopic(selectedTopic.id) : loadPage()">关闭并重新载入</button></div>
    <template v-if="dialog === 'help'"><span class="badge">人工协助 · 不会自动发送</span><h3>{{ helpSubject }}</h3><p>请联系你所在社区已约定的值班人员、议题主持人或独立请求受理人。R0 尚未配置真实联系人，也不自动发送消息。</p><ol class="manual-steps"><li>先说明你希望得到什么帮助，可以不讲述敏感经历。</li><li>当面或通过已约定渠道核对接收人，并说明哪些内容仅供对方阅读。</li><li>涉及观点、任务或授权，请一起核对具体版本和本人意愿。</li><li>共同记忆须先让相关人审阅，记录受众和期限；不同意或没有回应时不发布。</li></ol><div class="notice info">如为程序异议或涉及主持人本人，请寻找另一位独立受理人。未上线的功能可先采用纸面记录与本人签认。</div><button class="button primary" @click="closeDialog()">已了解人工路径</button></template>
    <template v-else-if="dialog === 'document' && selectedDocument"><span class="badge">{{ selectedDocument.category }} · 合成资料</span><h3>{{ selectedDocument.title }}</h3><p class="preserve-text document-body">{{ selectedDocument.body }}</p><div class="divider"></div><dl class="key-values"><div><dt>来源</dt><dd>{{ selectedDocument.source }}</dd></div><div><dt>版本</dt><dd>第 {{ selectedDocument.version }} 版</dd></div><div><dt>更新</dt><dd>{{ dateText(selectedDocument.updated_at) }}</dd></div></dl><button class="button secondary" @click="openHelp('资料来源与内容纠错')">请求人工核对</button></template>
    <form v-else-if="dialog === 'expression'" @submit.prevent="saveExpression"><div class="notice info">默认仅本人可见。{{ selectedExpression ? '修改会产生新版本，并移除当前议题中的旧共享文本。新版须重新确认和分享。' : '保存只建立私稿；不会自动分享。' }}</div><label class="form-field">想法标题<input v-model="expressionForm.title" required maxlength="160" placeholder="用一句话描述你想谈的事" /></label><label class="form-field">我的原话<textarea v-model="expressionForm.text" required maxlength="10000" rows="9" placeholder="可以说出担忧、拒绝、条件与不确定性，不必写得很完美。"></textarea></label><p class="muted">本轮没有 AI 转述，系统会完整保存你提交的原话。</p><div class="inline-actions"><button class="button primary" type="submit" :disabled="busy">{{ busy ? '保存中…' : '保存私人原话' }}</button><button class="button secondary" type="button" :disabled="busy" @click="closeDialog()">取消</button></div></form>
    <form v-else-if="dialog === 'share' && selectedExpression" @submit.prevent="shareExpression"><div class="notice warning">本次将分享本人确认的原话第 {{ selectedExpression.version }} 版。R0 不生成转述，请确认这段原话适合所选受众。</div><h3>{{ selectedExpression.title }}</h3><div class="share-preview preserve-text">{{ selectedExpression.text }}</div><label class="form-field">分享到哪个议题<select v-model="shareTopicId" required><option value="" disabled>选择你有权参与的议题</option><option v-for="topic in topics" :key="topic.id" :value="topic.id">{{ topic.title }}</option></select></label><div v-if="shareTarget" class="notice info"><strong>本次受众：{{ shareTarget.title }} 的 {{ shareTarget.participants.length }} 位参与者</strong><p>议题后续新增的参与者也会看到当前共享内容。只分享上述原话版本与作者信息，私人草稿不会因此全部开放。</p></div><p v-if="!topics.length" class="notice warning">目前没有可分享的议题。请先请发起人邀请你，或建立议题。</p><label class="checkbox-field"><input v-model="shareConsent" type="checkbox" required />我已核对这段原话、具体版本与议题受众，同意本次分享。</label><div class="inline-actions"><button class="button primary" type="submit" :disabled="busy || !shareConsent || !shareTopicId">{{ busy ? '分享中…' : '分享这版原话到所选议题' }}</button><button class="button secondary" type="button" :disabled="busy" @click="closeDialog()">继续保留私稿</button></div></form>
    <template v-else-if="dialog === 'revoke' && selectedExpression"><h3>{{ selectedExpression.title }}</h3><div class="notice warning">撤回后，当前议题视图会立即停止展示这份原话。已经被看到或另行记录的内容无法自动收回。</div><p>原话继续保留在你的私稿中。撤回分享不会自动改变你已表达的立场或任务回应。</p><div class="inline-actions"><button class="button danger" :disabled="busy" @click="revokeExpression()">{{ busy ? '撤回中…' : '撤回此原话的分享' }}</button><button class="button secondary" :disabled="busy" @click="closeDialog()">保留现有分享</button></div></template>
    <form v-else-if="dialog === 'topic'" @submit.prevent="saveTopic"><div class="notice warning">本轮仅建立合成测试议题，由你负责邀请参与者。此操作不启动正式决定程序。</div><label class="form-field">议题标题<input v-model="topicForm.title" required maxlength="160" placeholder="我们需要一起讨论什么？" /></label><label class="form-field">背景与问题<textarea v-model="topicForm.description" required maxlength="10000" rows="5" placeholder="说明为什么提出，以及需要核实的事实。"></textarea></label><label class="form-field">讨论范围与边界<textarea v-model="topicForm.scope" required maxlength="3000" rows="3" placeholder="这次讨论影响什么、暂不涉及什么、谁需要参与？"></textarea></label><button class="button primary" type="submit" :disabled="busy">{{ busy ? '建立中…' : '建立测试议题' }}</button></form>
    <form v-else-if="dialog === 'participants' && selectedTopic" @submit.prevent="addParticipant"><div class="notice warning">新增参与者会获得此议题及当前共享观点的读取权。请先按约定程序征得对方参与意愿。</div><label class="form-field">选择成员<select v-model="participantId" required><option value="" disabled>请选择成员</option><option v-for="member in participantCandidates" :key="member.id" :value="member.id">{{ member.display_name }}</option></select></label><p v-if="!participantCandidates.length" class="muted">合成成员目录中的所有成员已经在本议题中。</p><button class="button primary" type="submit" :disabled="busy || !participantId">确认加入此议题可见范围</button></form>
    <form v-else-if="dialog === 'option'" @submit.prevent="saveOption"><label class="form-field">方案名称<input v-model="optionForm.title" required maxlength="160" /></label><label class="form-field">方案内容<textarea v-model="optionForm.description" required rows="4" maxlength="10000"></textarea></label><label class="form-field">费用与资源<textarea v-model="optionForm.cost" rows="2" maxlength="3000" placeholder="已确认和待确认的资源分别写清楚"></textarea></label><label class="form-field">劳动与承担<textarea v-model="optionForm.labor" rows="2" maxlength="3000" placeholder="需要谁投入什么；尚未有人接受的任务请标明"></textarea></label><label class="form-field">风险与未核实项<textarea v-model="optionForm.risks" rows="2" maxlength="3000"></textarea></label><button class="button primary" type="submit" :disabled="busy">{{ busy ? '保存中…' : '加入备选方案' }}</button></form>
    <form v-else-if="dialog === 'stance' && selectedOption" @submit.prevent="saveStance"><p class="eyebrow">{{ selectedOption.title }} · 方案 v{{ selectedOption.version }}</p><div class="notice info">本次只记录你对这一版方案的立场，不构成正式批准或接受劳动。此前立场：{{ currentStance ? stanceLabels[currentStance.stance] : '尚未表达' }}。</div><fieldset class="stance-grid"><legend>我的明确立场</legend><label v-for="(label, value) in stanceLabels" :key="value" class="stance-button" :class="{ selected: stanceForm.stance === value }"><input v-model="stanceForm.stance" type="radio" :value="value" />{{ label }}</label></fieldset><label class="form-field">{{ stanceForm.stance === 'conditional' ? '支持的必要条件（必填）' : '具体意见、异议或待补充信息' }}<textarea v-model="stanceForm.condition" :required="stanceForm.stance === 'conditional'" maxlength="5000" rows="4" placeholder="写明你需要保留的条件或差异"></textarea></label><button class="button primary" type="submit" :disabled="busy">{{ busy ? '保存中…' : '保存我对这一版的立场' }}</button></form>
    <form v-else-if="dialog === 'invitation' && selectedTopic" @submit.prevent="saveInvitation"><div class="notice info">邀请只有对方本人回应后才改变状态。任务条款仅发起人与受邀者可读。</div><label class="form-field">邀请谁<select v-model="invitationForm.invitee_id" required><option value="" disabled>选择议题参与者</option><option v-for="id in selectedTopic.participants" :key="id" :value="id">{{ memberName(id) }}{{ id === user?.id ? '（我）' : '' }}</option></select></label><label class="form-field">任务名称<input v-model="invitationForm.title" required maxlength="160" /></label><label class="form-field">具体范围<textarea v-model="invitationForm.description" required rows="3" maxlength="10000"></textarea></label><label class="form-field">完成标准<textarea v-model="invitationForm.completion_criteria" required rows="2" maxlength="3000"></textarea></label><div class="form-grid"><label class="form-field">提供的资源<input v-model="invitationForm.resources" required maxlength="3000" placeholder="工具、支持或明确写无" /></label><label class="form-field">报酬或自愿性质<input v-model="invitationForm.compensation" required maxlength="3000" placeholder="需明确写清，不用默认自愿" /></label></div><label class="form-field">截止日期（可选，按北京时间）<input v-model="invitationForm.due_date" type="date" /></label><button class="button primary" type="submit" :disabled="busy">{{ busy ? '发出中…' : '发出合成测试邀请' }}</button></form>
    <form v-else-if="dialog === 'response' && selectedInvitation" @submit.prevent="saveResponse"><span class="badge warning">合成任务 · 第 {{ selectedInvitation.version }} 版</span><h3>{{ selectedInvitation.title }}</h3><p class="preserve-text">{{ selectedInvitation.description }}</p><dl class="key-values"><div><dt>议题</dt><dd>{{ selectedInvitation.topic_title }}</dd></div><div><dt>被邀请者</dt><dd>{{ selectedInvitation.invitee_name }}</dd></div><div><dt>完成标准</dt><dd>{{ selectedInvitation.completion_criteria }}</dd></div><div><dt>资源</dt><dd>{{ selectedInvitation.resources || '未说明' }}</dd></div><div><dt>报酬或自愿性质</dt><dd>{{ selectedInvitation.compensation || '未说明' }}</dd></div><div><dt>截止</dt><dd>{{ dateText(selectedInvitation.due_date) }}</dd></div><div><dt>当前回应</dt><dd>{{ invitationLabels[selectedInvitation.status] }}</dd></div></dl><p v-if="selectedInvitation.note" class="notice info preserve-text">{{ selectedInvitation.note }}</p><template v-if="selectedInvitation.invitee_id === user?.id && ['pending', 'negotiating'].includes(selectedInvitation.status)"><fieldset class="stance-grid"><legend>由我本人回应</legend><label class="stance-button" :class="{ selected: responseForm.response === 'accepted' }"><input v-model="responseForm.response" type="radio" value="accepted" />我接受这些条款</label><label class="stance-button" :class="{ selected: responseForm.response === 'negotiating' }"><input v-model="responseForm.response" type="radio" value="negotiating" />我想协商条件</label><label class="stance-button" :class="{ selected: responseForm.response === 'declined' }"><input v-model="responseForm.response" type="radio" value="declined" />我拒绝这次邀请</label></fieldset><label class="form-field">我的补充说明<textarea v-model="responseForm.note" rows="3" maxlength="5000" placeholder="拒绝不需要证明理由；协商时请写明希望修改的条件。"></textarea></label><div class="notice warning">接受只记录本轮合成测试回应。拒绝只关闭这次邀请，不影响社区参与资格。</div><button class="button primary" type="submit" :disabled="busy">{{ busy ? '提交中…' : '保存本人回应' }}</button></template><button v-else class="button secondary" type="button" @click="closeDialog()">关闭条款</button></form>
    <form v-else-if="dialog === 'admin-invite' && !inviteResult" @submit.prevent="saveAdminInvite"><label class="form-field">用户名<input v-model="adminForm.username" required maxlength="64" pattern="[a-zA-Z0-9_\-]{1,64}" placeholder="1–64位英文字母、数字、下划线或连字符" /></label><label class="form-field">显示称呼<input v-model="adminForm.display_name" required maxlength="80" /></label><label class="form-field">授权角色<select v-model="adminForm.role"><option value="member">社区成员</option><option value="facilitator">议题主持人</option><option value="admin">社区管理员</option></select></label><div class="notice warning">请按社区已确认的授权范围分配角色。邀请口令只交给指定对象，本界面不会代发消息。</div><button class="button primary" type="submit" :disabled="busy">{{ busy ? '建立中…' : '生成一次性加入邀请' }}</button></form>
    <template v-else-if="dialog === 'admin-invite' && inviteResult"><div class="notice success">邀请已建立，仅在有效期内可使用一次。</div><dl class="key-values"><div><dt>用户名</dt><dd>{{ adminForm.username }}</dd></div><div><dt>有效期至</dt><dd>{{ dateText(inviteResult.expires_at) }}</dd></div></dl><label class="form-field">一次性邀请口令<textarea class="mono" readonly :value="inviteResult.token" rows="3" aria-label="一次性邀请口令"></textarea></label><p class="muted">将口令与用户名通过已约定的人工渠道交给指定成员。关闭窗口后，口令会从当前页面清除。</p><div class="inline-actions"><button class="button secondary" @click="copyInvite()">复制邀请口令</button><button class="button primary" @click="closeDialog()">已交付，清除页面口令</button></div></template>
    <template v-else-if="dialog === 'freeze' && freezeUser"><h3>冻结 {{ freezeUser.display_name }} 的账号？</h3><div class="notice warning">冻结后，该账号不能继续登录，既有会话立即失效。不会因此自动删除业务记录或取消任务，请另行协调交接。</div><div class="inline-actions"><button class="button danger" :disabled="busy" @click="freezeMember()">{{ busy ? '冻结中…' : '确认冻结账号' }}</button><button class="button secondary" :disabled="busy" @click="closeDialog()">取消</button></div></template>
  </Modal>
</template>
