import { describe, expect, it } from 'vitest'
import type { Message } from '@ag-ui/core'
import { buildRunProcessGroups } from './runProcess'

const userMessage = (id: string, content = '请分析这个项目') => ({
  id,
  role: 'user',
  content,
}) as Message

const assistantMessage = (id: string, content: string, extra: Record<string, unknown> = {}) => ({
  id,
  role: 'assistant',
  content,
  ...extra,
}) as Message

const reasoningMessage = (id: string, content: string) => ({
  id,
  role: 'reasoning',
  content,
}) as Message

const activityMessage = (id: string, activityType: string, content: any, extra: Record<string, unknown> = {}) => ({
  id,
  role: 'activity',
  activityType,
  content,
  ...extra,
}) as Message

const toolCallMessage = (id: string, toolCallId: string, name = 'read_file', extra: Record<string, unknown> = {}) => ({
  id,
  role: 'assistant',
  content: '',
  toolCalls: [
    {
      id: toolCallId,
      type: 'function',
      function: {
        name,
        arguments: '{"path":"README.md"}',
      },
    },
  ],
  ...extra,
}) as Message

const toolResultMessage = (id: string, toolCallId: string, content = '读取完成', extra: Record<string, unknown> = {}) => ({
  id,
  role: 'tool',
  toolCallId,
  content,
  ...extra,
}) as Message

describe('buildRunProcessGroups', () => {
  it('keeps active run process messages in their original visible order', () => {
    const groups = buildRunProcessGroups([
      userMessage('u1'),
      reasoningMessage('r1', 'checking files'),
      assistantMessage('a1', '我先检查项目结构。'),
      toolCallMessage('tc1', 'call_1', 'read_file'),
      toolResultMessage('tr1', 'call_1', 'README 内容'),
      activityMessage('skill1', 'cc_agent.skill_apply', { skillName: 'Docs' }),
    ], true, null)

    expect(groups).toHaveLength(1)
    expect(groups[0].processDisplay).toBe('expanded')
    expect(groups[0].defaultExpanded).toBe(true)
    expect(groups[0].processMessages.map((message) => message.id)).toEqual(['r1', 'a1', 'tc1', 'skill1'])
    expect(groups[0].toolResultMessages.map((message) => message.id)).toEqual(['tr1'])
    expect(groups[0].finalAssistantMessages).toEqual([])
    expect(groups[0].summary).toBe('处理中 · 调用 1 个工具 · 4 步')
  })

  it('separates completed process messages from the final assistant answer', () => {
    const groups = buildRunProcessGroups([
      userMessage('u1'),
      reasoningMessage('r1', 'internal analysis remains in the process stream'),
      assistantMessage('a1', '我先说明中间判断。'),
      toolCallMessage('tc1', 'call_1', 'weekday'),
      toolResultMessage('tr1', 'call_1', 'June 27, 2026 is Saturday.'),
      assistantMessage('a2', '最终建议如下'),
    ], false, null)

    expect(groups).toHaveLength(1)
    expect(groups[0].processDisplay).toBe('collapsed')
    expect(groups[0].defaultExpanded).toBe(false)
    expect(groups[0].processMessages.map((message) => message.id)).toEqual(['r1', 'a1', 'tc1'])
    expect(groups[0].finalAssistantMessages.map((message) => message.id)).toEqual(['a2'])
    expect(groups[0].toolResultMessages.map((message) => message.id)).toEqual(['tr1'])
  })

  it('summarizes completed runs with tool, file, step, and duration counts', () => {
    const groups = buildRunProcessGroups([
      userMessage('u1'),
      toolCallMessage('tc1', 'call_1', 'read_file', { createdAt: 1000 }),
      toolResultMessage('tr1', 'call_1', '读取完成', { createdAt: 6000 }),
      activityMessage('file1', 'cc_agent.skill_artifact', {
        files: [
          { name: 'report.md', status: 'attached' },
          { name: 'chart.png', status: 'attached' },
        ],
      }),
      assistantMessage('a1', '完成'),
    ], false, null)

    expect(groups[0].summary).toBe('已处理 5s · 调用 1 个工具 · 生成 2 个文件 · 2 步')
  })

  it('uses a runtime duration fallback when messages do not carry timestamps', () => {
    const groups = buildRunProcessGroups([
      userMessage('u1'),
      toolCallMessage('tc1', 'call_1', 'read_file'),
      toolResultMessage('tr1', 'call_1', '读取完成'),
      assistantMessage('a1', '完成'),
    ], false, null, {
      durationMsByGroupId: {
        'run:u1': 4200,
      },
    })

    expect(groups[0].summary).toBe('已处理 4s · 调用 1 个工具 · 1 步')
  })

  it('adds a waiting permission interrupt to the visible process stream', () => {
    const groups = buildRunProcessGroups([
      userMessage('u1'),
    ], false, {
      result: {
        id: 'call_1',
        fields: [],
        purpose: 'permission',
        question: 'Allow this operation to run?\nTool: run_python',
        options: [
          { label: 'Allow once', value: 'allow_once' },
          { label: 'Always allow', value: 'allow_conversation' },
          { label: 'Deny', value: 'deny' },
        ],
        allowCustomInput: false,
        multiSelect: false,
      },
      resolve: () => undefined,
    })

    expect(groups).toHaveLength(1)
    expect(groups[0].processDisplay).toBe('expanded')
    expect(groups[0].defaultExpanded).toBe(true)
    expect(groups[0].hasActiveInterrupt).toBe(true)
    expect(groups[0].summary).toBe('处理中 · 1 步')
  })

  it('separates multiple conversation turns without cross-grouping process messages', () => {
    const groups = buildRunProcessGroups([
      userMessage('u1', '第一轮'),
      reasoningMessage('r1', 'thinking one'),
      assistantMessage('a1', '第一轮回答'),
      userMessage('u2', '第二轮'),
      activityMessage('skill2', 'cc_agent.skill_apply', { skillName: 'Docs' }),
      assistantMessage('a2', '第二轮回答'),
    ], false, null)

    expect(groups).toHaveLength(2)
    expect(groups[0].userMessages.map((message) => message.id)).toEqual(['u1'])
    expect(groups[0].processMessages.map((message) => message.id)).toEqual(['r1'])
    expect(groups[0].finalAssistantMessages.map((message) => message.id)).toEqual(['a1'])
    expect(groups[0].processDisplay).toBe('collapsed')
    expect(groups[1].userMessages.map((message) => message.id)).toEqual(['u2'])
    expect(groups[1].processMessages.map((message) => message.id)).toEqual(['skill2'])
    expect(groups[1].finalAssistantMessages.map((message) => message.id)).toEqual(['a2'])
    expect(groups[1].processDisplay).toBe('collapsed')
  })
  it('collapses process messages as soon as the streaming final answer starts', () => {
    const groups = buildRunProcessGroups([
      userMessage('u1'),
      reasoningMessage('r1', 'working'),
      assistantMessage('mid1', 'I will inspect the data first.'),
      toolCallMessage('tc1', 'call_1', 'read_file'),
      toolResultMessage('tr1', 'call_1', 'done'),
      assistantMessage('final1', 'The final answer has started'),
    ], true, null)

    expect(groups[0].isRunning).toBe(true)
    expect(groups[0].isComplete).toBe(true)
    expect(groups[0].processDisplay).toBe('collapsed')
    expect(groups[0].defaultExpanded).toBe(false)
    expect(groups[0].processMessages.map((message) => message.id)).toEqual(['r1', 'mid1', 'tc1'])
    expect(groups[0].finalAssistantMessages.map((message) => message.id)).toEqual(['final1'])
  })
})
