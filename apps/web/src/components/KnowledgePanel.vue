<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import Icon from './Icon.vue'
import Modal from './Modal.vue'
import CorrectionsPanel from './CorrectionsPanel.vue'
import type { CorrectionSource, CorrectionTarget } from '../lib/corrections'
import { ApiError, errorText } from '../lib/api'
import { dateText } from '../lib/domain'
import { copyKnowledgeInput, createKnowledgeApi, decodeKnowledgeFile, emptyKnowledgeInput, expiryInstant, localDateInput, splitSourceLines, validateKnowledgeInput } from '../lib/knowledge'
import { createKnowledgeReading } from '../lib/knowledgeReading'
import type { AiStatus, KnowledgeCitation, KnowledgeDetail, KnowledgeRevision, KnowledgeReviewItem, KnowledgeRevisionInput, Member, PublishedDocument } from '../lib/types'

const props = defineProps<{ currentUserId: string; aiStatus: AiStatus | null }>()
const emit = defineEmits<{ help: [subject: string] }>()
const api = createKnowledgeApi()
const reading = createKnowledgeReading(api)
const source = reading.source, answer = reading.answer, activeCitation = reading.citation
const tab = ref<'catalog' | 'mine' | 'reviews' | 'answer' | 'corrections'>('catalog')
const catalog = ref<PublishedDocument[]>([]), mine = ref<KnowledgeDetail[]>([]), queue = ref<KnowledgeReviewItem[]>([])
const members = ref<Member[]>([]), reviewers = ref<Member[]>([])
const loading = ref(false), busy = ref(false), answering = ref(false)
const error = ref(''), formError = ref(''), notice = ref(''), query = ref(''), question = ref(''), useModel = ref(false)
const modal = ref<'source' | 'edit' | 'manage' | 'submit' | 'review' | 'withdraw' | 'restrict' | null>(null)
const correctionTarget = ref<CorrectionTarget | null>(null)
const selected = ref<KnowledgeDetail | null>(null), selectedReview = ref<KnowledgeReviewItem | null>(null)
const form = ref<KnowledgeRevisionInput>(emptyKnowledgeInput())
const expiry = ref(''), reviewerId = ref(''), consent = ref(false)
const reviewDecision = ref<'approve' | 'changes_requested'>('changes_requested'), reviewReason = ref('')
const restrictedIds = ref<string[]>([])
let alive = true, workspaceRead = 0, fileRead = 0, answerOperation = 0
const modalTitle = computed(() => ({ source: '资料原文与精确来源', edit: selected.value ? '保存新的私人资料版本' : '新增私人文字资料', manage: '我的资料 · 私人版本与发布版本', submit: '送审预览 · 授权指定审核人', review: '核对指定送审版本', withdraw: '撤下当前发布资料', restrict: '收紧当前发布受众' }[modal.value ?? 'source']))
const canReview = computed(() => !!queue.value.length)
const selectedReviewer = computed(() => reviewers.value.find(item => item.id === reviewerId.value))
const canSubmitSelected = computed(() => !!selected.value && selected.value.latest.id !== selected.value.published?.id && !selected.value.reviews.some(record => record.revision_id === selected.value?.latest.id && record.decision === 'approve'))
const restrictCandidates = computed(() => selected.value?.audience?.scope === 'members' ? members.value.filter(item => selected.value?.audience?.member_ids.includes(item.id)) : members.value)
const sourceLines = computed(() => source.value ? splitSourceLines(source.value.body) : [])
watch(() => props.aiStatus?.available, available => { if (!available) useModel.value = false })

function memberName(id: string): string { return members.value.find(item => item.id === id)?.display_name ?? id }
function scopeText(revision: KnowledgeRevision): string { return revision.requested_scope === 'community' ? '当前有效的社区登录成员' : `固定名单：${revision.requested_member_ids.map(memberName).join('、')}` }
function publishedText(item: KnowledgeDetail): string {
  if (!item.published) return '从未发布，当前没有发布版'
  if (!item.publication_active) return `最后发布第 ${item.published.number} 版已停止访问（撤下或有效期已到），仅保留本人历史`
  return `当前发布第 ${item.published.number} 版 · ${item.audience?.scope === 'community' ? '社区成员可见' : item.audience ? `仅作者与 ${item.audience.member_ids.length} 位固定名单成员可见` : '当前范围待重新核对'}`
}
function clearPublicViews() { reading.clear(); catalog.value = [] }
function requestHelp(subject: string) { close(); emit('help', subject) }
function open(name: typeof modal.value) { fileRead += 1; formError.value = ''; modal.value = name }
function close() { if (busy.value) return; fileRead += 1; modal.value = null; selectedReview.value = null; selected.value = null; form.value = emptyKnowledgeInput(); consent.value = false; reviewerId.value = ''; reading.clearSource(); formError.value = '' }
function selectTab(next: typeof tab.value) { correctionTarget.value = null; if (busy.value || answering.value) return; tab.value = next; error.value = ''; reading.clear(); if (next === 'catalog') void search(); else if (next === 'mine' || next === 'reviews') void refreshWorkspace() }

async function refreshWorkspace() {
  const generation = ++workspaceRead
  loading.value = true; error.value = ''; clearPublicViews()
  try {
    const result = await Promise.all([api.catalog(query.value), api.mine(), api.reviewQueue(), api.members(), api.reviewers()])
    if (!alive || generation !== workspaceRead) return
    ;[catalog.value, mine.value, queue.value, members.value, reviewers.value] = result
  } catch (failure) { if (alive && generation === workspaceRead) error.value = errorText(failure) }
  finally { if (alive && generation === workspaceRead) loading.value = false }
}
async function search() {
  const generation = ++workspaceRead
  loading.value = true; error.value = ''; clearPublicViews()
  try { const result = await api.catalog(query.value); if (alive && generation === workspaceRead) catalog.value = result }
  catch (failure) { if (alive && generation === workspaceRead) error.value = errorText(failure) }
  finally { if (alive && generation === workspaceRead) loading.value = false }
}
function startCorrection() {
  if (!source.value || busy.value) return
  const item = source.value
  close(); correctionTarget.value = { id: item.id, revision_id: item.revision_id, access_epoch: item.access_epoch }; tab.value = 'corrections'
}
async function viewCorrectionSource(item: CorrectionSource) {
  try { const opened = await reading.open(item.document_id, item.revision_id); if (alive && opened) open('source') }
  catch (failure) { if (alive) error.value = errorText(failure) }
}
async function viewSource(item: PublishedDocument | KnowledgeCitation) {
  error.value = ''; formError.value = ''
  try {
    const isCitation = 'document_id' in item
    const opened = await reading.open(isCitation ? item.document_id : item.id, item.revision_id, isCitation ? item : undefined)
    if (alive && opened) {
      open('source')
      if (isCitation) { await nextTick(); if (alive && modal.value === 'source') document.querySelector<HTMLElement>('.knowledge-source-lines .highlighted')?.scrollIntoView({ block: 'nearest' }) }
    }
  } catch (failure) { if (alive) { catalog.value = []; error.value = `当前来源暂时不可读取；旧摘录与回答已清除。${errorText(failure)}` } }
}
async function manage(item: Pick<KnowledgeDetail, 'id'>) {
  if (busy.value) return
  const generation = ++workspaceRead
  busy.value = true; error.value = ''; selected.value = null
  try { const result = await api.detail(item.id); if (alive && generation === workspaceRead) { selected.value = result; open('manage') } }
  catch (failure) { if (alive && generation === workspaceRead) error.value = errorText(failure) }
  finally { if (alive && generation === workspaceRead) busy.value = false }
}
function edit(item?: KnowledgeDetail) { selected.value = item ?? null; form.value = item ? copyKnowledgeInput(item.latest) : emptyKnowledgeInput(); expiry.value = localDateInput(form.value.effective_until); open('edit') }
async function readFile(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0], current = ++fileRead
  if (!file) return
  formError.value = ''
  try { const text = decodeKnowledgeFile(file.name, await file.arrayBuffer()); if (alive && current === fileRead && modal.value === 'edit') { form.value.body = text; notice.value = '已在此页面读取本地文字。尚未上传或保存，请核对来源和授权后自行保存。' } }
  catch (failure) { if (alive && current === fileRead) formError.value = errorText(failure) }
  finally { input.value = '' }
}
async function runMutation(action: () => Promise<KnowledgeDetail | void>, message: string) {
  if (busy.value) return
  busy.value = true; formError.value = ''; error.value = ''; notice.value = ''; clearPublicViews(); workspaceRead += 1
  try {
    const result = await action()
    if (!alive) return
    selected.value = result ?? null; modal.value = result ? 'manage' : null; consent.value = false
    notice.value = message
    await refreshWorkspace()
  } catch (failure) { if (alive) { formError.value = errorText(failure); if (failure instanceof ApiError && failure.status === 409) notice.value = '请重新载入此资料，核对当前精确版本后再主动提交。' } }
  finally { if (alive) busy.value = false }
}
async function save() {
  try { form.value.effective_until = expiryInstant(expiry.value) }
  catch (failure) { formError.value = errorText(failure); return }
  const input = copyKnowledgeInput(form.value)
  if (input.requested_scope === 'community') input.requested_member_ids = []
  const invalid = validateKnowledgeInput(input)
  if (invalid) { formError.value = invalid; return }
  const current = selected.value
  await runMutation(() => api.save(input, current), current ? '新的私人版本已保存，旧送审停止。上次有效发布版仍按原授权提供，新的内容尚未发布。' : '私人资料已保存。当前仅本人可见，尚未送审或进入目录。')
}
function prepareSubmit() { if (!canSubmitSelected.value) return; reviewerId.value = ''; consent.value = false; open('submit') }
async function submit() {
  if (!canSubmitSelected.value) { formError.value = '此版已经发布过。请先另存完整新版本，重新核对受众后再送审。'; return }
  if (!selected.value || !reviewerId.value || !consent.value) { formError.value = '请明确选择另一个审核人，并确认本次送审授权。'; return }
  const current = selected.value
  await runMutation(() => api.submit(current, reviewerId.value), '仅此精确版本已授权给指定审核人。作者私稿和其他版本不会随之开放；尚未通过审核发布。')
}
async function cancelSubmission() { if (!selected.value) return; const current = selected.value; await runMutation(() => api.cancelSubmission(current), '本次送审授权已经撤回。指定审核人不再获得此送审版读取，当前获准发布版保持原授权。') }
async function prepareReview(item: KnowledgeReviewItem) {
  if (busy.value) return
  const generation = ++workspaceRead
  busy.value = true; selectedReview.value = null; selected.value = null; error.value = ''
  try {
    const current = await api.reviewQueue()
    if (!alive || generation !== workspaceRead) return
    queue.value = current
    const precise = current.find(record => record.id === item.id && record.revision.id === item.revision.id && record.version === item.version)
    if (!precise) throw new Error('本次送审已撤回或版本已变化。旧送审内容已清除，请核对当前待审列表。')
    selectedReview.value = precise; reviewDecision.value = 'changes_requested'; reviewReason.value = ''; open('review')
  } catch (failure) { if (alive && generation === workspaceRead) { queue.value = []; error.value = errorText(failure) } }
  finally { if (alive && generation === workspaceRead) busy.value = false }
}
async function review() {
  if (!selectedReview.value) return
  if (reviewDecision.value === 'changes_requested' && !reviewReason.value.trim()) { formError.value = '退回请说明需要补充或修正的内容。'; return }
  const item = selectedReview.value, decision = reviewDecision.value
  await runMutation(async () => { await api.review(item, decision, reviewReason.value); selectedReview.value = null }, decision === 'approve' ? '此精确版本已经通过资料审核并按预览受众发布。这不批准正文中的社区决定、支出或任务。' : '此精确版本已退回。旧的有效发布版仍按原授权提供，新稿不会发布。')
}
function prepareRestrict() { restrictedIds.value = [...(selected.value?.audience?.member_ids ?? [])].filter(id => members.value.some(member => member.id === id)); open('restrict') }
async function restrict() { if (!selected.value) return; const current = selected.value; await runMutation(() => api.restrict(current, [...restrictedIds.value]), '当前发布资料的受众已经收紧，旧摘录与回答已从页面清除。已看见或自行保存的副本无法追回。') }
async function withdraw() { if (!selected.value) return; const current = selected.value; await runMutation(() => api.withdraw(current), '当前发布版已经撤下，不再进入目录、引用与模型上下文。私人版本保留，已经被看见的内容无法追回。') }
async function ask() {
  if (answering.value || busy.value || !question.value.trim()) return
  const operation = ++answerOperation
  answering.value = true; error.value = ''; notice.value = ''
  try { await reading.ask(question.value.trim(), useModel.value) }
  catch (failure) { if (alive && operation === answerOperation) error.value = errorText(failure) }
  finally { if (alive && operation === answerOperation) answering.value = false }
}
function cancelAnswer() { answerOperation += 1; reading.clear(); answering.value = false; notice.value = '已放弃接收本次结果。可以继续目录与关键词查找；没有自动保存回答。' }
function activeLine(number: number): boolean { return !!activeCitation.value && number >= activeCitation.value.start_line && number <= activeCitation.value.end_line }
function expireVisibleSources() {
  const expired = catalog.value.some(item => !!item.effective_until && Date.parse(item.effective_until) <= Date.now()) || !!source.value?.effective_until && Date.parse(source.value.effective_until) <= Date.now()
  if (expired) { clearPublicViews(); if (modal.value === 'source') modal.value = null; notice.value = '资料已到显示的有效期，请重新读取当前目录。' }
}
let expiryTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => { void refreshWorkspace(); expiryTimer = setInterval(expireVisibleSources, 15000) })
onUnmounted(() => { alive = false; workspaceRead += 1; fileRead += 1; api.clear(); reading.dispose(); if (expiryTimer) clearInterval(expiryTimer) })
</script>

<template>
  <section class="knowledge-workspace">
    <div class="page-heading"><div><p class="eyebrow">有来源、有权限的社区知识</p><h1 id="page-title" tabindex="-1">查资料</h1><p class="muted">先查当前获准资料，再看原文。本人录入、指定审核和正式入库分别操作。</p></div><button class="button secondary" @click="requestHelp('资料纠错、来源核实与负责人')">资料有疑问</button></div>
    <div class="notice info">R0.3 合成开发 · 只支持文字资料与关键词检索。资料审核不批准正文中的决定或责任；本地模型关闭时所有人工流程可用。</div>
    <nav class="knowledge-tabs" aria-label="资料功能"><button class="button" :class="tab === 'catalog' ? 'primary' : 'secondary'" :aria-pressed="tab === 'catalog'" :disabled="busy || answering" @click="selectTab('catalog')">当前资料目录</button><button class="button" :class="tab === 'mine' ? 'primary' : 'secondary'" :aria-pressed="tab === 'mine'" :disabled="busy || answering" @click="selectTab('mine')">我的私人资料</button><button class="button" :class="tab === 'reviews' ? 'primary' : 'secondary'" :aria-pressed="tab === 'reviews'" :disabled="busy || answering" @click="selectTab('reviews')">指定给我的审核<span v-if="canReview" class="knowledge-count">{{ queue.length }}</span></button><button class="button" :class="tab === 'answer' ? 'primary' : 'secondary'" :aria-pressed="tab === 'answer'" :disabled="busy || answering" @click="selectTab('answer')">有来源问答</button><button class="button" :class="tab === 'corrections' ? 'primary' : 'secondary'" :aria-pressed="tab === 'corrections'" :disabled="busy || answering" @click="selectTab('corrections')">纠错请求</button></nav>
    <div v-if="notice" class="notice success" role="status">{{ notice }}</div>
    <div v-if="error" class="notice error" role="alert"><p>{{ error }}</p><button class="button secondary" :disabled="loading || busy || answering" @click="refreshWorkspace">重新读取当前资料</button></div>
    <div v-if="loading" class="loading-state" role="status"><span class="spinner"></span><p>正在读取你有权访问的资料…</p></div>
    <template v-else>
      <template v-if="tab === 'catalog'">
        <form class="toolbar search-form" @submit.prevent="search"><label class="search-input"><Icon name="search" /><input v-model="query" aria-label="搜索社区资料" placeholder="搜索标题与正文关键词…" maxlength="200" /></label><button class="button primary" type="submit" :disabled="busy">查找资料</button><button v-if="query" class="button ghost" type="button" @click="query = ''; search()">清除</button></form>
        <p class="muted knowledge-count-line">当前可读匹配资料 {{ catalog.length }} 份。只统计已获准、未过期的当前发布版。</p>
        <section v-if="catalog.length" class="card-grid"><article v-for="item in catalog" :key="`${item.id}:${item.revision_id}:${item.access_epoch}`" class="card knowledge-document"><div class="inline-actions"><span class="badge">{{ item.category }}</span><span class="badge quiet">{{ item.scope === 'community' ? '社区成员可见' : '固定名单可见' }}</span></div><h2>{{ item.title }}</h2><p class="source-meta">发布第 {{ item.version }} 版 · 维护人 {{ item.maintainer }} · {{ item.effective_until ? `有效至 ${dateText(item.effective_until)}` : '未设置截止时间' }}</p><blockquote v-for="snippet in item.snippets" :key="snippet.citation_id" class="knowledge-quote"><p class="preserve-text">{{ snippet.quote }}</p><small>原文第 {{ snippet.start_line }}–{{ snippet.end_line }} 行</small></blockquote><p v-if="!item.snippets.length" class="line-clamp">{{ item.body }}</p><p class="source-meta">来源：{{ item.source }}</p><button class="button ghost" @click="viewSource(item)">查看原文与来源<Icon name="arrow" :size="17" /></button></article></section>
        <div v-else class="card empty-state"><Icon name="book" :size="34" /><h2>没有找到当前可读资料</h2><p>试试更短的关键词，或请维护人核实资料是否已经审核和授权。</p><button class="button secondary" @click="requestHelp('找不到当前获准资料')">转人工查找</button></div>
      </template>
      <template v-else-if="tab === 'mine'">
        <div class="section-heading"><div><h2>我的资料版本</h2><p class="muted">只有本人能看完整私稿。新稿不会覆盖上一份有效发布版。</p></div><button class="button primary" :disabled="busy" @click="edit()"><Icon name="plus" />新增私人文字资料</button></div>
        <section v-if="mine.length" class="stack"><article v-for="item in mine" :key="item.id" class="card knowledge-own"><div class="section-heading"><div><p class="eyebrow">本人最新保存第 {{ item.latest.number }} 版</p><h2>{{ item.latest.title }}</h2></div><span class="badge" :class="item.submitted ? 'warning' : 'quiet'">{{ item.submitted ? `第 ${item.submitted.number} 版待指定审核` : '最新版本未在送审' }}</span></div><p class="muted">{{ publishedText(item) }}</p><p v-if="item.publication_active && item.published && item.latest.id !== item.published.id" class="notice info">最新私人第 {{ item.latest.number }} 版与发布第 {{ item.published.number }} 版是不同内容。公开目录仍使用获准发布版。</p><div class="inline-actions"><button class="button secondary" :disabled="busy" @click="manage(item)">核对版本与管理</button><button class="button ghost" :disabled="busy" @click="edit(item)">另存新的私人版本</button></div></article></section>
        <div v-else class="card empty-state"><h3>还没有本人录入的资料</h3><p>从一份来源和授权清楚的文字开始。保存私稿不会自动分享。</p></div>
      </template>
      <template v-else-if="tab === 'reviews'">
        <div class="section-heading"><div><h2>指定给我的资料审核</h2><p class="muted">这里只显示当前明确授权给你的精确送审版，不开放作者其他私稿。</p></div><button class="button secondary" :disabled="busy" @click="refreshWorkspace">刷新待审</button></div>
        <section v-if="queue.length" class="stack"><article v-for="item in queue" :key="`${item.id}:${item.revision.id}`" class="card knowledge-review"><span class="badge warning">资料第 {{ item.revision.number }} 版 · 等待审核</span><h2>{{ item.revision.title }}</h2><p class="muted">录入者 {{ item.owner_name }} · 申请 {{ scopeText(item.revision) }}</p><button class="button secondary" :disabled="busy" @click="prepareReview(item)">核对精确送审版</button></article></section>
        <div v-else class="card empty-state"><Icon name="check" :size="28" /><h3>当前没有指定给你的待审资料</h3><p>审核人资格不会使你获得所有作者私稿的读取权。</p></div>
      </template>
      <CorrectionsPanel v-else-if="tab === 'corrections'" :current-user-id="props.currentUserId" :initial-target="correctionTarget" @started="correctionTarget = null" @source="viewCorrectionSource" @manage="id => manage({ id })" />
      <template v-else>
        <section class="card knowledge-answer"><h2>从当前资料找依据</h2><p class="muted">回答只使用你当前可读的获准片段。业务任务、成员权限与正式决定仍需查看对应当前记录。</p><form @submit.prevent="ask"><label class="form-field">我的问题<input v-model="question" required maxlength="200" placeholder="例如：参加活动前需要核对哪些条件？" :disabled="answering" /></label><label class="checkbox-field"><input v-model="useModel" type="checkbox" :disabled="answering || !props.aiStatus?.available" />我主动使用已就绪的本地模型，根据获准片段生成回答</label><p class="muted">{{ props.aiStatus?.available ? `本地模型 ${props.aiStatus.model} 已就绪。仍需核对原文与引用。` : '本地模型未就绪；默认使用资料摘录，可继续手工查找。' }}回答仅显示在本页，不自动保存或发布。</p><div class="inline-actions"><button class="button primary" type="submit" :disabled="answering || busy">{{ answering ? '正在检索与核对来源…' : useModel ? '依据资料请求本地回答' : '查找可核对的资料摘录' }}</button><button v-if="answering" class="button secondary" type="button" @click="cancelAnswer">放弃等待，返回人工</button><button v-else class="button ghost" type="button" @click="reading.clear()">清除本页摘录与回答</button></div></form></section>
        <section v-if="answer" class="card knowledge-answer-result" aria-label="当前有来源结果"><span class="badge" :class="answer.mode === 'insufficient' ? 'warning' : 'success'">{{ answer.mode === 'extract' ? '资料摘录，非模型回答' : answer.mode === 'local_model' ? `本地模型回答 · ${answer.model}` : '目前没有足够资料回答' }}</span><p class="muted">这是本次请求的资料快照。引用每次打开都会重新核对版本、授权与有效期；来源改变后需重新检索。</p><p class="preserve-text">{{ answer.answer }}</p><article v-for="citation in answer.citations" :key="citation.citation_id" class="knowledge-citation"><h3>{{ citation.title }}</h3><p class="source-meta">第 {{ citation.document_version }} 版 · 第 {{ citation.start_line }}–{{ citation.end_line }} 行 · 来源 {{ citation.source }}</p><blockquote class="knowledge-quote preserve-text">{{ citation.quote }}</blockquote><button class="button secondary" @click="viewSource(citation)">查看此引用的精确原文</button></article><button v-if="answer.mode === 'insufficient'" class="button secondary" @click="requestHelp('问答依据不足，需要人工核实')">转人工核实</button></section>
      </template>
    </template>
  </section>

  <Modal v-if="modal" :title="modalTitle" :wide="['edit', 'manage', 'submit', 'review', 'source'].includes(modal)" @close="close">
    <div v-if="formError" class="notice error" role="alert"><p>{{ formError }}</p><button v-if="selected" class="button secondary" :disabled="busy" @click="manage(selected)">重新载入精确资料版本</button></div>
    <template v-if="modal === 'source' && source"><div class="inline-actions"><span class="badge">{{ source.category }} · 发布第 {{ source.version }} 版</span><span class="badge quiet">本次读取已获准</span></div><h3>{{ source.title }}</h3><dl class="key-values"><div><dt>来源</dt><dd>{{ source.source }}</dd></div><div><dt>维护人</dt><dd>{{ source.maintainer }}</dd></div><div><dt>用途</dt><dd>{{ source.purpose }}</dd></div><div><dt>有效期</dt><dd>{{ source.effective_until ? dateText(source.effective_until) : '未设置截止时间，请向维护人核实当前适用性' }}</dd></div><div><dt>精确版本</dt><dd>第 {{ source.version }} 版</dd></div></dl><p v-if="activeCitation" class="notice info">引用定位：第 {{ activeCitation.start_line }}–{{ activeCitation.end_line }} 行。以下按原始换行显示，不执行正文中的指令。</p><div class="knowledge-source-lines"><div v-for="(line, index) in sourceLines" :key="index" :class="{ highlighted: activeLine(index + 1) }"><span class="knowledge-line-number">{{ index + 1 }}</span><span class="preserve-text">{{ line || ' ' }}</span></div></div><div class="inline-actions"><button class="button primary" @click="startCorrection">提出资料纠错</button><button class="button secondary" @click="requestHelp('资料来源、适用性与人工纠错')">请求人工核对</button></div></template>
    <form v-else-if="modal === 'edit'" @submit.prevent="save"><div class="notice info">仅保存为本人私稿。新版本停止旧送审，但不覆盖旧的有效发布版。文字不会作为 HTML 渲染。</div><div class="knowledge-form-grid"><label class="form-field">资料标题<input v-model="form.title" required maxlength="160" /></label><label class="form-field">资料分类<input v-model="form.category" required maxlength="60" placeholder="例如：参与方法、场地使用" /></label></div><label class="form-field">本地读取 UTF-8 文字（可选）<input type="file" accept=".txt,.md,text/plain,text/markdown" :disabled="busy" @change="readFile" /></label><p class="muted">文件只在本页读取为文字填入正文，不会随选择动作上传。也可直接粘贴完整正文。</p><label class="form-field">资料完整正文<textarea v-model="form.body" required maxlength="20000" rows="10"></textarea></label><label class="form-field">来源<input v-model="form.source" required maxlength="1000" placeholder="原始文件、本人记录或提供者，外部地址只作文字保存" /></label><label class="form-field">授权依据与使用边界<textarea v-model="form.rights" required maxlength="2000" rows="3" placeholder="谁同意录入、允许怎样使用，以及不能公开的部分"></textarea></label><label class="form-field">本次用途<input v-model="form.purpose" required maxlength="1000" /></label><div class="knowledge-form-grid"><label class="form-field">维护人或人工联系路径<input v-model="form.maintainer" required maxlength="500" /></label><label class="form-field">有效至（设备本地时间，可留空）<input v-model="expiry" type="datetime-local" /></label></div><fieldset class="knowledge-audience"><legend>通过审核后申请发布给谁</legend><label class="sharing-mode-choice"><input v-model="form.requested_scope" type="radio" value="community" /><span>社区当前有效登录成员<small>未来加入的有效成员也可读取，撤下或收紧前持续有效。</small></span></label><label class="sharing-mode-choice"><input v-model="form.requested_scope" type="radio" value="members" /><span>明确选择的固定名单<small>不按角色推定，不随新成员加入自动扩大。</small></span></label><div v-if="form.requested_scope === 'members'" class="knowledge-members"><label v-for="member in members" :key="member.id" class="checkbox-field"><input v-model="form.requested_member_ids" type="checkbox" :value="member.id" />{{ member.display_name }}{{ member.id === props.currentUserId ? '（本人）' : '' }}</label></div></fieldset><button class="button primary" type="submit" :disabled="busy">{{ busy ? '正在保存…' : selected ? '保存新的私人版本' : '保存私人文字资料' }}</button></form>
    <template v-else-if="modal === 'manage' && selected"><p class="notice info">{{ publishedText(selected) }}。最新私人内容、指定送审和当前发布是独立状态。</p><div class="knowledge-version-grid"><section class="card"><p class="eyebrow">本人最新保存第 {{ selected.latest.number }} 版{{ selected.publication_active && selected.latest.id === selected.published?.id ? ' · 同时为当前发布版' : ' · 未作为当前发布版' }}</p><h3>{{ selected.latest.title }}</h3><p class="preserve-text">{{ selected.latest.body }}</p><dl class="key-values"><div><dt>来源</dt><dd>{{ selected.latest.source }}</dd></div><div><dt>授权边界</dt><dd>{{ selected.latest.rights }}</dd></div><div><dt>申请受众</dt><dd>{{ scopeText(selected.latest) }}</dd></div></dl></section><section class="card"><h3>送审与发布</h3><p>{{ selected.submitted ? `送审第 ${selected.submitted.number} 版，等待 ${memberName(selected.reviewer_id ?? '')} 核对。` : '当前没有送审版本。' }}</p><p>{{ publishedText(selected) }}</p><p v-if="selected.audience?.scope === 'members'" class="muted">当前固定名单：{{ selected.audience.member_ids.length ? selected.audience.member_ids.map(memberName).join('、') : '仅作者' }}</p><details v-if="selected.published"><summary>{{ selected.publication_active ? '核对当前发布内容' : '核对最后发布的私人历史（已停止访问）' }}（第 {{ selected.published.number }} 版）</summary><h4>{{ selected.published.title }}</h4><p class="preserve-text">{{ selected.published.body }}</p></details><div v-for="record in selected.reviews" :key="record.id" class="knowledge-review-record"><p><strong>{{ record.decision === 'approve' ? '资料审核通过' : '需要修改' }}</strong> · {{ record.reviewer_name }} · {{ dateText(record.created_at) }}</p><p class="preserve-text">{{ record.reason || '未补充理由' }}</p></div></section></div><div class="inline-actions"><button class="button secondary" :disabled="busy" @click="edit(selected)">另存新的私人版本</button><button class="button primary" :disabled="busy || !reviewers.length || !canSubmitSelected" @click="prepareSubmit">预览并指定审核人</button><button v-if="selected.submitted" class="button secondary" :disabled="busy" @click="cancelSubmission">撤回本次送审</button><button v-if="selected.published && selected.publication_active" class="button secondary" :disabled="busy" @click="prepareRestrict">收紧当前发布受众</button><button v-if="selected.published && selected.publication_active" class="button danger" :disabled="busy" @click="open('withdraw')">撤下当前发布资料</button></div><p v-if="!canSubmitSelected" class="notice info">此版已经发布过。请先另存完整新版本，重新核对内容与受众，再送审。</p><p v-if="!reviewers.length" class="notice warning">没有另一个有效审核人，请通过人工程序配置后再送审。本人不能审核自己的资料。</p></template>
    <form v-else-if="modal === 'submit' && selected" @submit.prevent="submit"><p class="notice info">本次只授权最新私人第 {{ selected.latest.number }} 版给明确指定的另一个审核人。审核通过会按以下申请受众发布，旧版本私稿不会开放。</p><h3>{{ selected.latest.title }}</h3><p class="share-preview preserve-text">{{ selected.latest.body }}</p><dl class="key-values"><div><dt>来源</dt><dd>{{ selected.latest.source }}</dd></div><div><dt>授权边界</dt><dd>{{ selected.latest.rights }}</dd></div><div><dt>用途</dt><dd>{{ selected.latest.purpose }}</dd></div><div><dt>维护人</dt><dd>{{ selected.latest.maintainer }}</dd></div><div><dt>有效至</dt><dd>{{ selected.latest.effective_until ? dateText(selected.latest.effective_until) : '未设置截止时间' }}</dd></div><div><dt>获准发布受众</dt><dd>{{ scopeText(selected.latest) }}</dd></div></dl><label class="form-field">指定另一个审核人<select v-model="reviewerId" aria-label="指定另一个审核人" required><option value="">请选择明确的审核人</option><option v-for="member in reviewers" :key="member.id" :value="member.id">{{ member.display_name }}</option></select></label><label class="checkbox-field"><input v-model="consent" type="checkbox" required />我已核对精确版本、来源与授权边界，同意仅把此版送给{{ selectedReviewer?.display_name ?? '指定审核人' }}；同意审核通过后按以上受众发布。</label><button class="button primary" type="submit" :disabled="busy || !consent || !reviewerId">确认此次送审授权</button></form>
    <form v-else-if="modal === 'review' && selectedReview" @submit.prevent="review"><div class="notice info">只核对明确送审的第 {{ selectedReview.revision.number }} 版。通过会发布这版资料，但不赋予正文中的社区决定、支出或任务任何批准效力。</div><h3>{{ selectedReview.revision.title }}</h3><p class="preserve-text knowledge-review-body">{{ selectedReview.revision.body }}</p><dl class="key-values"><div><dt>录入者</dt><dd>{{ selectedReview.owner_name }}</dd></div><div><dt>精确版本</dt><dd>第 {{ selectedReview.revision.number }} 版</dd></div><div><dt>来源</dt><dd>{{ selectedReview.revision.source }}</dd></div><div><dt>授权依据</dt><dd>{{ selectedReview.revision.rights }}</dd></div><div><dt>用途</dt><dd>{{ selectedReview.revision.purpose }}</dd></div><div><dt>维护人</dt><dd>{{ selectedReview.revision.maintainer }}</dd></div><div><dt>有效至</dt><dd>{{ selectedReview.revision.effective_until ? dateText(selectedReview.revision.effective_until) : '未设置截止时间' }}</dd></div><div><dt>发布受众</dt><dd>{{ scopeText(selectedReview.revision) }}</dd></div></dl><fieldset class="knowledge-audience"><legend>我对这份资料的审核选择</legend><label class="sharing-mode-choice"><input v-model="reviewDecision" type="radio" value="changes_requested" />需要作者补充或修改，不发布此版</label><label class="sharing-mode-choice"><input v-model="reviewDecision" type="radio" value="approve" />来源与授权可核对，通过并按预览受众发布此版</label></fieldset><label class="form-field">{{ reviewDecision === 'changes_requested' ? '需要修改的理由（必填）' : '审核说明（可选）' }}<textarea v-model="reviewReason" :required="reviewDecision === 'changes_requested'" maxlength="2000" rows="3"></textarea></label><button class="button primary" type="submit" :disabled="busy">{{ reviewDecision === 'approve' ? '确认通过并发布此精确版本' : '确认退回此精确版本' }}</button></form>
    <form v-else-if="modal === 'restrict' && selected" @submit.prevent="restrict"><div class="notice info">只可从社区范围收为固定名单，或删除现名单成员。扩大受众需要另存新版本、重新授权与审核。收紧会同时撤回当前送审，防止旧审核重新开放受众。作者仍保有管理权。</div><h3>{{ selected.published?.title }}</h3><p>{{ publishedText(selected) }}</p><div class="knowledge-members"><label v-for="member in restrictCandidates" :key="member.id" class="checkbox-field"><input v-model="restrictedIds" type="checkbox" :value="member.id" />{{ member.display_name }}</label></div><p class="muted">保留 {{ restrictedIds.length }} 位固定名单成员。全部取消可仅作者读取。已经读过或另存的副本无法追回。</p><button class="button primary" type="submit" :disabled="busy">确认只收紧当前受众</button></form>
    <form v-else-if="modal === 'withdraw' && selected" @submit.prevent="withdraw"><h3>{{ selected.published?.title }}</h3><p class="notice warning">撤下当前发布第 {{ selected.published?.number }} 版，立即停止目录、全文、引用与模型上下文读取。同时撤回当前送审，防止旧审核再次发布。保留本人私人历史；已经看过或另存的内容无法追回。</p><button class="button danger" type="submit" :disabled="busy">确认撤下当前发布版</button></form>
  </Modal>
</template>
