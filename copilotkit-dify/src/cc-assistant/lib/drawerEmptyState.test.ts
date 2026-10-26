import { describe, expect, it } from 'vitest'
import { drawerEmptyStateSections } from './drawerEmptyState'

describe('drawerEmptyStateSections', () => {
  it('exposes business skills for non-sidebar empty surfaces', () => {
    expect(drawerEmptyStateSections.length).toBe(1)
    expect(drawerEmptyStateSections.map((section) => section.title)).toEqual([
      '常用技能',
    ])

    for (const section of drawerEmptyStateSections) {
      expect(section.items.length).toBeGreaterThan(0)
      for (const item of section.items) {
        expect(item.title.trim()).not.toBe('')
        expect(item.description.trim()).not.toBe('')
        expect(item.message.trim()).not.toBe('')
      }
    }

    const messages = drawerEmptyStateSections.flatMap((section) => (
      section.items.map((item) => item.message)
    ))
    expect(messages.join('\n')).not.toMatch(/帮我把这段会议记录整理成纪要和待办|根据这周工作内容生成一版周报|帮我起草一封客户跟进邮件/)
  })

  it('does not expose slash commands or debug entries on the home surface', () => {
    const messages = drawerEmptyStateSections.flatMap((section) => (
      section.items.map((item) => item.message)
    ))

    expect(messages).not.toContain('/help')
    expect(messages).not.toContain('/status')
    expect(messages).not.toContain('/compact')
    expect(messages.some((message) => message.startsWith('/meeting-notes'))).toBe(false)
    expect(messages.some((message) => message.startsWith('/weekly-report'))).toBe(false)
  })
})
