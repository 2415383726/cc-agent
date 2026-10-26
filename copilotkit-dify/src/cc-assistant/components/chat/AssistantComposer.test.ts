import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import AssistantComposer from './AssistantComposer.vue'
import { normalizeAssistantCatalog } from '../../lib/assistantCatalog'

describe('AssistantComposer', () => {
  it('renders a selected skill as an inline input prefix with a remove affordance', async () => {
    const catalog = normalizeAssistantCatalog({
      skills: [{ name: 'brainstorming', label: 'Brainstorming', description: 'Explore ideas' }],
    })
    const app = createSSRApp(AssistantComposer, {
      modelValue: 'Draft the outline',
      selectedSkill: catalog.skills[0],
      catalog,
      placeholder: 'Type a question',
    })

    const html = await renderToString(app)

    expect(html).toContain('Brainstorming')
    expect(html).toContain('Draft the outline')
    expect(html).toContain('assistant-composer__skill-prefix')
    expect(html).toContain('assistant-composer__skill-remove')
    expect(html).toContain('has-skill assistant-composer__box')
    expect(html).toContain('aria-label="移除已选择技能"')
  })

  it('renders command and skill entries in the slash menu when input starts with slash', async () => {
    const catalog = normalizeAssistantCatalog({
      commands: [{ name: 'compact', label: 'Compact context', description: 'Compress history' }],
      skills: [{ name: 'meeting-notes', label: 'Meeting notes', description: 'Summarize meeting notes' }],
    })
    const app = createSSRApp(AssistantComposer, {
      modelValue: '/',
      selectedSkill: null,
      catalog,
      placeholder: 'Type a question',
    })

    const html = await renderToString(app)

    expect(html).toContain('命令')
    expect(html).toContain('Compact context')
    expect(html).toContain('技能')
    expect(html).toContain('Meeting notes')
    expect(html).toContain('data-kind="command"')
    expect(html).toContain('data-kind="skill"')
    expect(html).toContain('assistant-composer__slash-icon')
    expect(html).toContain('assistant-composer__slash-title')
    expect(html).toContain('assistant-composer__slash-description')
    expect(html).toContain('data-icon="command-compact"')
    expect(html).toContain('data-icon="skill"')
  })
})
