/**
 * Status tone mapping derived from Leyline lib/tool-activity.js
 * (spmurrayzzz/leyline@a368c8b7590b88bb138c024b7dd8414b3dcc2a73, Apache-2.0).
 * Modified for the Pi display contract: statuses are the finite Pi tool states.
 */
import type { ToolStatus } from './transcript'
import { toolStatusText } from './labels'

export type ToolTone = 'running' | 'completed' | 'error' | 'stopped' | 'unknown'

export function toolStatusTone(status: ToolStatus): ToolTone {
  if (status === 'running' || status === 'awaiting_user' || status === 'awaiting_approval') {
    return 'running'
  }
  if (status === 'stopped') return 'stopped'
  if (status === 'unknown') return 'unknown'
  if (status === 'error') return 'error'
  if (status === 'not_executed') return 'stopped'
  return 'completed'
}

export function toolStatusLabel(status: ToolStatus): string {
  return toolStatusText(status)
}
