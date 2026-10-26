import { describe, expect, it } from 'vitest'
import {
  buildSubmittedText,
  filterSlashEntries,
  isSlashMode,
  shouldClearSelectedSkillOnDelete,
} from './assistantComposer'
import { normalizeAssistantCatalog, slashEntriesFromCatalog } from './assistantCatalog'

const catalog = normalizeAssistantCatalog({
  skills: [
    { name: 'meeting-notes', label: '会议纪要', description: '整理会议记录' },
    { name: 'weekly-report', label: '周报生成', description: '生成周报' },
  ],
  commands: [
    { name: 'compact', label: '压缩上下文', description: '压缩历史' },
    { name: 'status', label: '会话状态', description: '查看状态' },
  ],
})

describe('assistant composer helpers', () => {
  it('detects slash mode only at the start of the input', () => {
    expect(isSlashMode('/')).toBe(true)
    expect(isSlashMode('/com')).toBe(true)
    expect(isSlashMode('请执行 /compact')).toBe(false)
  })

  it('filters slash entries across commands and skills', () => {
    const entries = slashEntriesFromCatalog(catalog)

    expect(filterSlashEntries(entries, '/comp').map((entry) => entry.name)).toEqual(['compact'])
    expect(filterSlashEntries(entries, '/周').map((entry) => entry.name)).toEqual(['weekly-report'])
    expect(filterSlashEntries(entries, '/').map((entry) => `${entry.kind}:${entry.name}`)).toEqual([
      'command:compact',
      'command:status',
      'skill:meeting-notes',
      'skill:weekly-report',
    ])
  })

  it('hides skill tags by converting them to slash skill messages on submit', () => {
    const skill = catalog.skills[0]

    expect(buildSubmittedText('整理 3/24 项目周会', skill)).toBe('/meeting-notes 整理 3/24 项目周会')
    expect(buildSubmittedText('   ', skill)).toBe('/meeting-notes')
    expect(buildSubmittedText('/compact', skill)).toBe('/compact')
    expect(buildSubmittedText('你好', null)).toBe('你好')
  })

  it('clears the selected skill with Backspace only when text deletion has nothing to handle', () => {
    expect(shouldClearSelectedSkillOnDelete({
      key: 'Backspace',
      hasSelectedSkill: true,
      value: '',
      selectionStart: 0,
      selectionEnd: 0,
    })).toBe(true)
    expect(shouldClearSelectedSkillOnDelete({
      key: 'Delete',
      hasSelectedSkill: true,
      value: '',
      selectionStart: 0,
      selectionEnd: 0,
    })).toBe(true)
    expect(shouldClearSelectedSkillOnDelete({
      key: 'Backspace',
      hasSelectedSkill: true,
      value: 'hello',
      selectionStart: 5,
      selectionEnd: 5,
    })).toBe(false)
    expect(shouldClearSelectedSkillOnDelete({
      key: 'Backspace',
      hasSelectedSkill: false,
      value: '',
      selectionStart: 0,
      selectionEnd: 0,
    })).toBe(false)
  })
})
