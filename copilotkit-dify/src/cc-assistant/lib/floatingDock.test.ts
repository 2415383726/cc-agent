import { describe, expect, it } from 'vitest'
import {
  clampFloatingDockY,
  floatingDockFromPointer,
  floatingDockStorageKey,
  isFloatingDockDrag,
  loadFloatingDock,
  saveFloatingDock,
} from './floatingDock'

function createMemoryStorage(initial: Record<string, string> = {}): Storage {
  const values = new Map(Object.entries(initial))
  return {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    removeItem: (key: string) => values.delete(key),
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
  }
}

describe('floating dock', () => {
  it('generates the persisted key from a storage prefix', () => {
    expect(floatingDockStorageKey('cadre-system-assistant')).toBe('cadre-system-assistant:floating-dock')
    expect(floatingDockStorageKey('')).toBe('cc-dify-assistant:floating-dock')
  })

  it('distinguishes click and drag with a 6px movement threshold', () => {
    expect(isFloatingDockDrag({ x: 100, y: 100 }, { x: 104, y: 104 })).toBe(false)
    expect(isFloatingDockDrag({ x: 100, y: 100 }, { x: 107, y: 100 })).toBe(true)
  })

  it('clamps y inside the viewport and docks to the closest horizontal side', () => {
    expect(clampFloatingDockY(-20, 600)).toBe(16)
    expect(clampFloatingDockY(700, 600)).toBe(538)
    expect(floatingDockFromPointer({ x: 100, y: 220, viewportWidth: 1000, viewportHeight: 600 })).toEqual({
      side: 'left',
      y: 197,
    })
    expect(floatingDockFromPointer({ x: 900, y: 220, viewportWidth: 1000, viewportHeight: 600 })).toEqual({
      side: 'right',
      y: 197,
    })
  })

  it('restores and saves the dock position from localStorage-compatible storage', () => {
    const storage = createMemoryStorage()
    const key = floatingDockStorageKey('demo')

    saveFloatingDock(storage, key, { side: 'left', y: 780 }, 600)
    expect(storage.getItem(key)).toBe(JSON.stringify({ side: 'left', y: 538 }))
    expect(loadFloatingDock(storage, key, 600)).toEqual({ side: 'left', y: 538 })
  })

  it('falls back to a right-side default when storage data is invalid', () => {
    const storage = createMemoryStorage({ [floatingDockStorageKey('bad')]: '{bad json' })

    expect(loadFloatingDock(storage, floatingDockStorageKey('bad'), 600)).toEqual({
      side: 'right',
      y: 538,
    })
  })
})
