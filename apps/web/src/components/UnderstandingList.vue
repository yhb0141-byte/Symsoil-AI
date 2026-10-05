<script setup lang="ts">
import type { Understanding, UnderstandingStatus } from '../lib/types'
import { dateText, understandingLabels } from '../lib/domain'
import Icon from './Icon.vue'

withDefaults(defineProps<{
  items: Understanding[]
  currentUserId: string
  busy?: boolean
}>(), { busy: false })

const emit = defineEmits<{ open: [item: Understanding] }>()

function reviewClass(status: UnderstandingStatus): string {
  if (status === 'accurate') return 'confirmed'
  if (status === 'prefer_in_person') return 'draft'
  return 'pending'
}

const responseHints: Record<UnderstandingStatus, string> = {
  pending: '表达者还没有核对这次复述。',
  accurate: '表达者已确认，这次复述准确表达了自己的意思。',
  needs_correction: '表达者提出了修正，可以据此继续确认彼此的理解。',
  prefer_in_person: '表达者希望当面交流，可以由双方约定合适的时间。',
}
</script>

<template>
  <section class="stack" aria-label="双方理解核对" :aria-busy="busy">
    <template v-if="items.length">
      <div class="notice info">
        <strong>双方私密的理解核对</strong>
        <p>复述与核对回应仅向听者和原表达者开放。这次核对确认彼此理解的意思，是否同意观点仍需另外表达。</p>
      </div>

      <article
        v-for="item in items"
        :key="item.id"
        :class="['understanding-card', reviewClass(item.status)]"
        :data-state="reviewClass(item.status)"
      >
        <header class="candidate-header">
          <div>
            <span class="eyebrow">听者向表达者核对</span>
            <h3>
              {{ item.requester_name }}
              <span aria-hidden="true"> → </span>
              <span class="sr-only">请</span>
              {{ item.author_name }}
            </h3>
          </div>
          <span :class="['understanding-status', reviewClass(item.status)]">
            {{ understandingLabels[item.status] }}
          </span>
        </header>

        <div class="source-meta">
          <span>原话 V{{ item.utterance_version }}</span>
          <span v-if="item.representation === 'candidate'">基于候选转述 V{{ item.candidate_version }}</span>
          <span v-else>基于原话</span>
          <span>本次复述 V{{ item.version }}</span>
        </div>

        <div class="divider" />
        <p class="eyebrow">听者亲手填写的复述</p>
        <p class="preserve-text">{{ item.text }}</p>

        <div class="divider" />
        <p class="eyebrow">表达者的核对回应</p>
        <p v-if="item.correction" class="preserve-text">{{ item.correction }}</p>
        <p v-else class="muted">{{ responseHints[item.status] }}</p>

        <div class="source-meta">
          <span>发起于 <time :datetime="item.created_at">{{ dateText(item.created_at) }}</time></span>
          <span v-if="item.updated_at !== item.created_at">更新于 <time :datetime="item.updated_at">{{ dateText(item.updated_at) }}</time></span>
        </div>

        <footer class="candidate-actions">
          <button
            type="button"
            :class="['button', currentUserId === item.author_id && item.status === 'pending' ? 'primary' : 'secondary']"
            :disabled="busy"
            @click="emit('open', item)"
          >
            {{ currentUserId === item.author_id && item.status === 'pending' ? '本人核对这次复述' : '查看双方核对' }}
          </button>
          <span class="muted">这份记录仅双方可见。</span>
        </footer>
      </article>
    </template>

    <div v-else class="card empty-state">
      <Icon name="discuss" :size="32" />
      <h3>还没有双方理解核对</h3>
      <p>从已共享的原话或候选转述发起，亲手写下“我理解的意思”，再请表达者核对。</p>
      <p class="muted">复述与核对回应仅向双方开放。</p>
    </div>
  </section>
</template>
