import { shallowRef } from 'vue'

/** Current-only private records: invalidate first, and ignore older in-flight reads. */
export function createCurrentRecords<T>(load: () => Promise<T[]>) {
  const items = shallowRef<T[]>([])
  let revision = 0
  function clear() { revision += 1; items.value = [] }
  async function refresh(clearBeforeRead = false): Promise<void> {
    const readRevision = ++revision
    if (clearBeforeRead) items.value = []
    try {
      const current = await load()
      if (revision === readRevision) items.value = current
    } catch (error) {
      if (revision === readRevision) throw error
    }
  }
  return { items, clear, refresh }
}
