<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
const paths: Record<string, string> = {
  home: 'M3 10 12 3l9 7M5 9v11h14V9M9 20v-7h6v7',
  book: 'M4 3h6c2 0 2 1 2 2v16c0-2-2-3-4-3H4zM20 3h-6c-2 0-2 1-2 2v16c0-2 2-3 4-3h4z',
  pen: 'm16 3 5 5-12 12-6 1 1-6zM13 6l5 5',
  discuss: 'M4 4h16v12H9l-5 5zM8 8h8M8 12h5',
  task: 'M8 5H4v16h16V5h-4M8 3h8v4H8zM8 13l3 3 5-6',
  memory: 'M12 20s-9-5-9-11a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6-9 11-9 11z',
  shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  plus: 'M12 4v16M4 12h16',
  search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m5 12 6 6',
  close: 'm5 5 14 14M19 5 5 19',
  logout: 'M9 4H4v16h5M9 12h12m-5-5 5 5-5 5',
  person: 'M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M4 21v-3a8 8 0 0 1 16 0v3',
  check: 'm5 12 4 4L19 6',
  leaf: 'M5 19 19 5M4 14C4 6 12 3 21 3c0 9-3 17-11 17-3 0-6-3-6-6',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2',
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] ?? paths.leaf" /></svg></template>
