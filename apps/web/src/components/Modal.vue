<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import Icon from './Icon.vue'
defineProps<{ title: string }>()
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement>()
let returnFocus: HTMLElement | null = null
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); emit('close'); return }
  if (event.key !== 'Tab') return
  const items = Array.from(panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]') ?? [])
  const first = items[0], last = items[items.length - 1]
  if (!first) { event.preventDefault(); panel.value?.focus(); return }
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
onMounted(async () => { returnFocus = document.activeElement as HTMLElement; document.body.style.overflow = 'hidden'; await nextTick(); panel.value?.querySelector<HTMLElement>('input, textarea, select, button')?.focus(); document.addEventListener('keydown', keydown) })
onUnmounted(() => { document.body.style.overflow = ''; document.removeEventListener('keydown', keydown); returnFocus?.focus() })
</script>
<template><Teleport to="body"><div class="modal-backdrop" @click.self="emit('close')"><section ref="panel" class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabindex="-1"><div class="section-heading"><h2 id="modal-title">{{ title }}</h2><button class="button ghost icon-button" aria-label="关闭窗口" @click="emit('close')"><Icon name="close" /></button></div><slot /></section></div></Teleport></template>
