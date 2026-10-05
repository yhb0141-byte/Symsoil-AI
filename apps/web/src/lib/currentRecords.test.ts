import { describe, expect, it, vi } from 'vitest'
import { createCurrentRecords } from './currentRecords'

describe('current-only understanding records', () => {
  it('removes obsolete records before the replacement read finishes', async () => {
    let finish: (items: string[]) => void = () => {}
    const load = vi.fn<() => Promise<string[]>>().mockResolvedValueOnce(['old-understanding']).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const current = createCurrentRecords(load)
    await current.refresh()
    const afterSourceChange = current.refresh(true)
    expect(current.items.value).toEqual([])
    finish([])
    await afterSourceChange
    expect(current.items.value).toEqual([])
  })
  it('keeps invalidated records cleared when the follow-up server read fails', async () => {
    const load = vi.fn<() => Promise<string[]>>().mockResolvedValueOnce(['old-understanding']).mockRejectedValueOnce(new Error('offline'))
    const current = createCurrentRecords(load)
    await current.refresh()
    await expect(current.refresh(true)).rejects.toThrow('offline')
    expect(current.items.value).toEqual([])
  })
  it('prevents an older in-flight list from reviving withdrawn source records', async () => {
    let finishOldRead: (items: string[]) => void = () => {}
    const load = vi.fn<() => Promise<string[]>>().mockImplementationOnce(() => new Promise(resolve => { finishOldRead = resolve })).mockResolvedValueOnce([])
    const current = createCurrentRecords(load)
    const oldRead = current.refresh()
    await current.refresh(true)
    finishOldRead(['withdrawn-understanding'])
    await oldRead
    expect(current.items.value).toEqual([])
  })
})
