import {
  DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX,
  assistantFloatingDockStorageKey,
} from './assistantConfig'

export type FloatingDockSide = 'left' | 'right'

export interface FloatingDockPosition {
  side: FloatingDockSide
  y: number
}

export interface FloatingDockPoint {
  x: number
  y: number
}

export interface FloatingDockPointerInput extends FloatingDockPoint {
  viewportWidth: number
  viewportHeight: number
  buttonSize?: number
  margin?: number
}

export const FLOATING_DOCK_CLICK_THRESHOLD = 6
export const FLOATING_DOCK_BUTTON_SIZE = 46
export const FLOATING_DOCK_MARGIN = 16

export function floatingDockStorageKey(prefix?: string) {
  return assistantFloatingDockStorageKey(prefix || DEFAULT_ASSISTANT_STORAGE_KEY_PREFIX)
}

export function clampFloatingDockY(
  y: number,
  viewportHeight: number,
  buttonSize = FLOATING_DOCK_BUTTON_SIZE,
  margin = FLOATING_DOCK_MARGIN,
) {
  const max = Math.max(margin, Number(viewportHeight || 0) - buttonSize - margin)
  return Math.min(max, Math.max(margin, Math.round(Number(y || 0))))
}

export function floatingDockFromPointer({
  x,
  y,
  viewportWidth,
  viewportHeight,
  buttonSize = FLOATING_DOCK_BUTTON_SIZE,
  margin = FLOATING_DOCK_MARGIN,
}: FloatingDockPointerInput): FloatingDockPosition {
  return {
    side: Number(x || 0) < Number(viewportWidth || 0) / 2 ? 'left' : 'right',
    y: clampFloatingDockY(Number(y || 0) - buttonSize / 2, viewportHeight, buttonSize, margin),
  }
}

export function isFloatingDockDrag(
  start: FloatingDockPoint,
  current: FloatingDockPoint,
  threshold = FLOATING_DOCK_CLICK_THRESHOLD,
) {
  const dx = Number(current.x || 0) - Number(start.x || 0)
  const dy = Number(current.y || 0) - Number(start.y || 0)
  return Math.sqrt(dx * dx + dy * dy) >= threshold
}

export function defaultFloatingDock(viewportHeight = 0): FloatingDockPosition {
  return {
    side: 'right',
    y: clampFloatingDockY(Number(viewportHeight || 0) - FLOATING_DOCK_BUTTON_SIZE - FLOATING_DOCK_MARGIN, viewportHeight),
  }
}

export function loadFloatingDock(
  storage: Pick<Storage, 'getItem'> | null | undefined,
  key: string,
  viewportHeight = 0,
) {
  try {
    const raw = storage?.getItem(key)
    const parsed = raw ? JSON.parse(raw) : null
    const side = parsed?.side === 'left' ? 'left' : parsed?.side === 'right' ? 'right' : defaultFloatingDock(viewportHeight).side
    const y = typeof parsed?.y === 'number'
      ? clampFloatingDockY(parsed.y, viewportHeight)
      : defaultFloatingDock(viewportHeight).y
    return { side, y }
  } catch (_) {
    return defaultFloatingDock(viewportHeight)
  }
}

export function saveFloatingDock(
  storage: Pick<Storage, 'setItem'> | null | undefined,
  key: string,
  dock: FloatingDockPosition,
  viewportHeight = 0,
) {
  try {
    storage?.setItem(key, JSON.stringify({
      side: dock.side === 'left' ? 'left' : 'right',
      y: clampFloatingDockY(dock.y, viewportHeight),
    }))
  } catch (_) {
    // Ignore unavailable or blocked storage.
  }
}
