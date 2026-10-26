import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  defaultAssistantCatalog,
  normalizeAssistantCatalog,
  normalizeAssistantIcon,
  resolveAssistantCatalog,
  slashEntriesFromCatalog,
} from './assistantCatalog'

describe('assistant catalog', () => {
  it('uses cadre talent business skills as the built-in default catalog', () => {
    expect(defaultAssistantCatalog.skills.map((skill) => ({
      name: skill.name,
      label: skill.label,
      category: skill.category,
      icon: skill.icon,
    }))).toEqual([
      { name: 'leadership-team-analysis', label: '班子分析', category: '分析', icon: 'chart' },
      { name: 'personnel-comparison', label: '人员对比', category: '对比', icon: 'checklist' },
      { name: 'role-fit-analysis', label: '人岗匹配', category: '研判', icon: 'target' },
      { name: 'policy-research', label: '政策研究', category: '研究', icon: 'file-text' },
      { name: 'advanced-talent-search', label: '高级检索', category: '检索', icon: 'target' },
      { name: 'text-proofreading', label: '文字校对', category: '工具', icon: 'pen' },
    ])
  })

  it('keeps the public demo catalog skill names aligned with built-in defaults', () => {
    const publicCatalog = JSON.parse(readFileSync(resolve(__dirname, '../../../public/cc-agent-home-catalog.json'), 'utf8'))

    expect(publicCatalog.skills.map((skill: { name: string }) => skill.name)).toEqual(
      defaultAssistantCatalog.skills.map((skill) => skill.name),
    )
  })

  it('normalizes skills, commands, and suggested questions from host config', () => {
    const catalog = normalizeAssistantCatalog({
      skills: [
        {
          name: 'meeting-notes',
          label: '会议纪要',
          description: '整理会议记录',
          category: '办公',
        },
      ],
      commands: [
        {
          name: 'compact',
          label: '压缩上下文',
          description: '压缩当前会话上下文',
        },
      ],
      suggestedQuestions: ['今天星期几？'],
    })

    expect(catalog.skills).toEqual([
      expect.objectContaining({
        kind: 'skill',
        name: 'meeting-notes',
        label: '会议纪要',
        description: '整理会议记录',
        category: '办公',
      }),
    ])
    expect(catalog.commands).toEqual([
      expect.objectContaining({
        kind: 'command',
        name: 'compact',
        message: '/compact',
      }),
    ])
    expect(catalog.suggestedQuestions).toEqual([
      expect.objectContaining({
        title: '今天星期几？',
        message: '今天星期几？',
      }),
    ])
  })

  it('keeps homepage skills separate while slash entries include commands and skills', () => {
    const homeSkillNames = defaultAssistantCatalog.skills.map((skill) => skill.name)
    const slashEntries = slashEntriesFromCatalog(defaultAssistantCatalog)

    expect(homeSkillNames).toContain('leadership-team-analysis')
    expect(defaultAssistantCatalog.commands.map((command) => command.name)).toContain('compact')
    expect(slashEntries.map((entry) => `${entry.kind}:${entry.name}`)).toEqual(
      expect.arrayContaining([
        'command:compact',
        'skill:leadership-team-analysis',
      ]),
    )
  })

  it('defaults to production-oriented homepage suggested questions without the old test pills', () => {
    const catalog = normalizeAssistantCatalog({
      skills: [
        {
          name: 'email-drafter',
          label: 'Email',
          description: 'Draft email',
          category: 'Communication',
          icon: 'mail',
        },
      ],
    })

    expect(catalog.skills[0]).toEqual(expect.objectContaining({ icon: 'mail' }))
    expect(defaultAssistantCatalog.suggestedQuestions.length).toBeGreaterThan(0)
    expect(defaultAssistantCatalog.suggestedQuestions.map((question) => question.title).join('\n')).not.toMatch(/帮我把这段会议记录整理成纪要和待办|根据这周工作内容生成一版周报|帮我起草一封客户跟进邮件/)
  })

  it('falls back to the default skill icon for missing or unknown icon names', () => {
    const catalog = normalizeAssistantCatalog({
      skills: [
        { name: 'known', icon: 'target' },
        { name: 'missing' },
        { name: 'unknown', icon: 'custom-company-logo' },
      ],
    })

    expect(catalog.skills.map((skill) => skill.icon)).toEqual(['target', 'skill', 'skill'])
    expect(normalizeAssistantIcon('chart')).toBe('chart')
    expect(normalizeAssistantIcon('bad icon')).toBe('skill')
  })

  it('resolves partial host catalog with default commands while preserving explicit empty questions', () => {
    const catalog = resolveAssistantCatalog({
      skills: [{ name: 'meeting-notes', label: '会议纪要' }],
      suggestedQuestions: [],
    })

    expect(catalog.commands.map((command) => command.name)).toEqual(['help', 'status', 'context', 'compact', 'reset'])
    expect(catalog.skills).toEqual([
      expect.objectContaining({
        kind: 'skill',
        name: 'meeting-notes',
        label: '会议纪要',
        category: '技能',
        icon: 'skill',
      }),
    ])
    expect(catalog.suggestedQuestions).toEqual([])
  })
})
