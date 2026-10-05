<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import Modal from './Modal.vue'
import { ApiError, errorText } from '../lib/api'
import { dateText } from '../lib/domain'
import { correctionLabels, createCorrectionReadGate, createCorrectionsApi } from '../lib/corrections'
import type { Correction, CorrectionContext, CorrectionListing, CorrectionSource, CorrectionTarget } from '../lib/corrections'

const props = defineProps<{ currentUserId: string; initialTarget: CorrectionTarget | null }>()
const emit = defineEmits<{ source: [source: CorrectionSource]; manage: [id: string]; started: [] }>()
const api = createCorrectionsApi(), gate = createCorrectionReadGate()
const listing = ref<CorrectionListing>({ items: [], counts: { sent: 0, incoming: 0, pending_incoming: 0 } })
const busy = ref(false), error = ref(''), notice = ref('')
const modal = ref<'create' | 'detail' | 'withdraw' | null>(null)
const preview = ref<CorrectionContext | null>(null), selected = ref<Correction | null>(null)
const issue = ref(''), response = ref(''), consent = ref(false)
function close() { if (busy.value) return; gate.clear(); modal.value = null; preview.value = null; selected.value = null; issue.value = ''; response.value = ''; consent.value = false }
let disposed = false
async function run(action: (ticket: number) => Promise<void>) {
  if (busy.value || disposed) return
  const ticket = gate.start()
  busy.value = true; error.value = ''; notice.value = ''
  try { await action(ticket) }
  catch (failure) {
    if (gate.current(ticket)) {
      error.value = errorText(failure)
      if (failure instanceof ApiError && [401, 404, 409].includes(failure.status)) { selected.value = null; preview.value = null; listing.value = { items: [], counts: { sent: 0, incoming: 0, pending_incoming: 0 } }; consent.value = false }
    }
  } finally { if (gate.current(ticket)) busy.value = false }
}
async function refresh() {
  await run(async ticket => {
    selected.value = null; preview.value = null; modal.value = null
    const data = await api.list(); if (gate.current(ticket)) listing.value = data
  })
}
async function compose(target: CorrectionTarget) {
  await run(async ticket => {
    preview.value = null; selected.value = null; consent.value = false; issue.value = ''; modal.value = 'create'
    const data = await api.preview(target); if (gate.current(ticket)) preview.value = data
  })
}
async function open(item: Correction) {
  await run(async ticket => {
    selected.value = null; preview.value = null; response.value = ''; consent.value = false; modal.value = 'detail'
    const data = await api.detail(item.id); if (gate.current(ticket)) selected.value = data
  })
}
async function save(kind: 'create' | 'respond' | 'withdraw') {
  if (kind !== 'withdraw' && (!consent.value || !(kind === 'create' ? issue.value : response.value).trim())) { error.value = '请填写问题或回应，并明确确认双方范围。'; return }
  if (kind === 'create' && !preview.value || kind !== 'create' && !selected.value) return
  const source = preview.value, item = selected.value
  await run(async ticket => {
    const result = kind === 'create' ? await api.create(source!, issue.value) : kind === 'respond' ? await api.respond(item!, response.value) : await api.withdraw(item!)
    if (!gate.current(ticket)) return
    selected.value = result; preview.value = null; modal.value = 'detail'; consent.value = false; issue.value = ''; response.value = ''
    notice.value = kind === 'create' ? '纠错请求已按预览仅发给资料录入者。' : kind === 'respond' ? '本人的回应已发给请求者。资料内容没有因此修改或发布。' : '纠错共享已撤回，对方不再能通过此请求读取正文；本人历史保留。'
    const data = await api.list(); if (gate.current(ticket)) listing.value = data
  })
}
function viewSource(item: Correction) { if (!item.source) return; const source = item.source; close(); emit('source', source) }
function manage(item: Correction) { const id = item.document_id; close(); emit('manage', id) }
onMounted(async () => { const target = props.initialTarget; emit('started'); await refresh(); if (!disposed && target) await compose(target) })
onUnmounted(() => { disposed = true; gate.dispose(); api.clear(); listing.value = { items: [], counts: { sent: 0, incoming: 0, pending_incoming: 0 } }; selected.value = null; preview.value = null; issue.value = ''; response.value = '' })
</script>

<template>
  <section class="corrections-workspace">
    <div class="section-heading"><div><h2>我的资料纠错</h2><p class="muted">本人提出，明确交给资料录入者。双方私下交流与资料发布分别授权。</p></div><button class="button secondary" :disabled="busy" @click="refresh">刷新纠错请求</button></div>
    <p class="notice info">已回应只表示对方给出说明。需要修改资料时，由录入者另存完整新版本并重新送审。通用投诉、改派和多人交流尚未开放。</p>
    <p class="muted">本人已发 {{ listing.counts.sent }} 条 · 收到 {{ listing.counts.incoming }} 条 · 待本人回应 {{ listing.counts.pending_incoming }} 条</p>
    <div v-if="notice" class="notice success" role="status">{{ notice }}</div>
    <div v-if="error && !modal" class="notice error" role="alert">{{ error }}</div>
    <p v-if="busy" role="status">正在核对本人可见的纠错记录…</p>
    <div class="stack"><article v-for="item in listing.items" :key="item.id" class="card correction-card"><div class="section-heading"><h3>{{ item.source?.title ?? '关联版本当前不可查阅' }}</h3><span class="badge" :class="item.status === 'submitted' ? 'warning' : 'quiet'">{{ correctionLabels[item.status] }}</span></div><p class="muted">针对资料第 {{ item.document_version }} 版 · {{ item.requester_id === props.currentUserId ? `我发给 ${item.recipient_name}` : `${item.requester_name} 发给我` }} · {{ dateText(item.updated_at) }}</p><p class="line-clamp preserve-text">{{ item.text }}</p><button class="button secondary" :disabled="busy" @click="open(item)">查看双方纠错记录</button></article></div>
    <div v-if="!busy && !listing.items.length" class="card empty-state"><h3>当前没有本人可见的纠错请求</h3><p>打开获准资料的精确原文，选择“提出资料纠错”，核对版本和接收人后再发送。</p></div>
  </section>
  <Modal v-if="modal" :title="modal === 'create' ? '预览资料纠错 · 仅发给录入者' : modal === 'withdraw' ? '撤回纠错共享' : '双方私有的资料纠错'" wide @close="close">
    <div v-if="error" class="notice error" role="alert"><p>{{ error }}</p><p v-if="!selected && !preview">当前预览或记录不可继续使用。请关闭窗口，刷新后重新核对；问题不会自动重发。</p></div>
    <form v-if="modal === 'create'" @submit.prevent="save('create')">
      <template v-if="preview"><h3>{{ preview.title }}</h3><dl class="key-values"><div><dt>精确资料</dt><dd>第 {{ preview.document_version }} 版</dd></div><div><dt>实际接收人</dt><dd>{{ preview.recipient.display_name }} · 资料录入者</dd></div><div><dt>原维护说明</dt><dd>{{ preview.maintainer }}</dd></div></dl></template>
      <p class="notice info">只分享你下面主动填写的问题，不附带整篇资料或其他私稿。源资料后来撤下或变更，不会自动撤回这次双方交流；你可另行撤回共享。</p>
      <label class="form-field">我发现的问题<textarea v-model="issue" required maxlength="2000" rows="6" :disabled="busy" placeholder="说明哪一处需要核对，不必填写私人经历。"></textarea></label>
      <label class="checkbox-field"><input v-model="consent" type="checkbox" required :disabled="busy || !preview" />我已核对版本和接收人，同意仅把上面的问题发给资料录入者，接收其本人回应。</label>
      <button class="button primary" type="submit" :disabled="busy || !preview || !consent">确认发送这条私人纠错</button>
    </form>
    <template v-else-if="selected">
      <h3>{{ selected.source?.title ?? '关联版本当前不可查阅' }}</h3><p class="muted">针对资料第 {{ selected.document_version }} 版 · {{ correctionLabels[selected.status] }}</p>
      <p v-if="!selected.source" class="notice info">此记录仍指向原提交版本。现有权限或发布版本发生变化，原文不能从这里读取；下方仅保留双方主动分享的交流。</p>
      <section class="card"><h4>{{ selected.requester_name }} 提出的问题</h4><p class="preserve-text">{{ selected.text }}</p><small>{{ dateText(selected.created_at) }}</small></section>
      <section v-if="selected.response" class="card"><h4>{{ selected.recipient_name }} 的本人回应</h4><p class="preserve-text">{{ selected.response }}</p><small>已回应不等于资料已修正 · {{ dateText(selected.responded_at ?? selected.updated_at) }}</small></section>
      <template v-if="modal === 'withdraw'"><p class="notice warning">撤回后，对方无法再通过此请求读取问题与回应。本人保留历史，已经看到或另存的副本无法追回。</p><button class="button danger" :disabled="busy" @click="save('withdraw')">确认撤回这次纠错共享</button></template>
      <template v-else>
        <div class="inline-actions"><button v-if="selected.source" class="button secondary" :disabled="busy" @click="viewSource(selected)">重新核对关联原文</button><button v-if="selected.recipient_id === props.currentUserId" class="button secondary" :disabled="busy" @click="manage(selected)">打开我的资料管理</button><button v-if="selected.requester_id === props.currentUserId && selected.status !== 'withdrawn'" class="button danger" :disabled="busy" @click="modal = 'withdraw'">撤回这次纠错共享</button></div>
        <form v-if="selected.recipient_id === props.currentUserId && selected.status === 'submitted'" @submit.prevent="save('respond')"><label class="form-field">我的核对与回应<textarea v-model="response" required maxlength="2000" rows="5" :disabled="busy" placeholder="说明核查结果或下一步。若需改稿，请另存新版本送审。"></textarea></label><label class="checkbox-field"><input v-model="consent" type="checkbox" required :disabled="busy" />我确认只把这段本人回应发给请求者；这不会自动修改或发布资料。</label><button class="button primary" type="submit" :disabled="busy || !consent">发送本人的回应</button></form>
        <p v-if="selected.status === 'responded'" class="notice info">此轮已回应。进一步的问题可从当前获准原文重新发起；原请求不会被改成另一个版本。</p>
      </template>
    </template>
  </Modal>
</template>
