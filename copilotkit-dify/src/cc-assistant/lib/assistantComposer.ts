import type { AssistantSkill, AssistantSlashEntry } from './assistantCatalog'

export interface SelectedSkillDeleteState {
  key: string
  hasSelectedSkill: boolean
  value: string
  selectionStart?: number | null
  selectionEnd?: number | null
}

export function isSlashMode(value: string) {
  return String(value || '').startsWith('/')
}

export function filterSlashEntries(entries: AssistantSlashEntry[], value: string) {
  if (!isSlashMode(value)) return []
  const query = String(value || '').slice(1).trim().toLowerCase()
  if (!query) return entries
  return entries.filter((entry) => {
    const haystack = [
      entry.name,
      entry.label,
      entry.description,
      entry.kind === 'skill' ? entry.category : '',
    ].join(' ').toLowerCase()
    return haystack.includes(query)
  })
}

export function buildSubmittedText(text: string, selectedSkill: AssistantSkill | null | undefined) {
  const content = String(text || '').trim()
  if (!selectedSkill) return content
  if (content.startsWith('/')) return content
  return content ? `/${selectedSkill.name} ${content}` : `/${selectedSkill.name}`
}

export function shouldClearSelectedSkillOnDelete(state: SelectedSkillDeleteState) {
  if (!state.hasSelectedSkill) return false
  if (state.key !== 'Backspace' && state.key !== 'Delete') return false

  const value = String(state.value || '')
  const start = typeof state.selectionStart === 'number' ? state.selectionStart : value.length
  const end = typeof state.selectionEnd === 'number' ? state.selectionEnd : start
  if (start !== end) return false
  if (!value) return true

  return state.key === 'Backspace' && start === 0
}
