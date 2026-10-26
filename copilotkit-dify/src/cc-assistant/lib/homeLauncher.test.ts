import { describe, expect, it, vi } from 'vitest'
import { submitLauncherMessage } from './homeLauncher'

describe('submitLauncherMessage', () => {
  it('adds a user message and runs the current agent', async () => {
    const agent = {
      addMessage: vi.fn(),
    }
    const runAgent = vi.fn().mockResolvedValue(undefined)

    const submitted = await submitLauncherMessage({
      text: '今天星期几',
      agent,
      runAgent,
      openDrawer: vi.fn(),
    })

    expect(submitted).toBe(true)
    expect(agent.addMessage).toHaveBeenCalledWith(expect.objectContaining({
      role: 'user',
      content: '今天星期几',
    }))
    expect(runAgent).toHaveBeenCalledWith({ agent })
  })

  it('builds slash skill text when the homepage composer has a selected skill', async () => {
    const agent = {
      addMessage: vi.fn(),
    }
    const runAgent = vi.fn().mockResolvedValue(undefined)

    const submitted = await submitLauncherMessage({
      text: '整理今天例会',
      selectedSkill: {
        kind: 'skill',
        name: 'meeting-notes',
        label: '会议纪要',
        description: '整理会议记录',
        category: '办公',
      },
      agent,
      runAgent,
      openDrawer: vi.fn(),
    })

    expect(submitted).toBe(true)
    expect(agent.addMessage).toHaveBeenCalledWith(expect.objectContaining({
      role: 'user',
      content: '/meeting-notes 整理今天例会',
    }))
  })

  it('opens the drawer before running the agent', async () => {
    const calls: string[] = []
    const agent = {
      addMessage: vi.fn(() => calls.push('addMessage')),
    }
    const runAgent = vi.fn(async () => {
      calls.push('runAgent')
    })
    const openDrawer = vi.fn(() => calls.push('openDrawer'))

    await submitLauncherMessage({
      text: '你好',
      agent,
      runAgent,
      openDrawer,
    })

    expect(calls).toEqual(['openDrawer', 'addMessage', 'runAgent'])
  })

  it('can prepare a fresh conversation before sending from the homepage', async () => {
    const calls: string[] = []
    const freshAgent = {
      addMessage: vi.fn(() => calls.push('fresh.addMessage')),
    }
    const staleAgent = {
      addMessage: vi.fn(() => calls.push('stale.addMessage')),
    }
    const runAgent = vi.fn(async () => {
      calls.push('runAgent')
    })

    const submitted = await submitLauncherMessage({
      text: '总结今天工作',
      agent: staleAgent,
      runAgent,
      openDrawer: () => calls.push('openDrawer'),
      prepareConversation: async () => {
        calls.push('prepareConversation')
        return freshAgent
      },
    })

    expect(submitted).toBe(true)
    expect(staleAgent.addMessage).not.toHaveBeenCalled()
    expect(freshAgent.addMessage).toHaveBeenCalledWith(expect.objectContaining({
      role: 'user',
      content: '总结今天工作',
    }))
    expect(runAgent).toHaveBeenCalledWith({ agent: freshAgent })
    expect(calls).toEqual(['prepareConversation', 'openDrawer', 'fresh.addMessage', 'runAgent'])
  })

  it('does not run empty input or invalid config', async () => {
    const agent = {
      addMessage: vi.fn(),
    }
    const runAgent = vi.fn()
    const openDrawer = vi.fn()

    await expect(submitLauncherMessage({
      text: '   ',
      agent,
      runAgent,
      openDrawer,
    })).resolves.toBe(false)

    await expect(submitLauncherMessage({
      text: 'hello',
      agent,
      runAgent,
      openDrawer,
      disabledReason: 'invalid config',
    })).resolves.toBe(false)

    expect(agent.addMessage).not.toHaveBeenCalled()
    expect(runAgent).not.toHaveBeenCalled()
    expect(openDrawer).not.toHaveBeenCalled()
  })
  it('does not send to an earlier agent if preparing the new conversation was cancelled', async () => {
    const addMessage = vi.fn()
    const runAgent = vi.fn()
    const submitted = await submitLauncherMessage({ text: 'hello', agent: { addMessage }, runAgent,
      openDrawer: vi.fn(), prepareConversation: async () => undefined })
    expect(submitted).toBe(false)
    expect(addMessage).not.toHaveBeenCalled()
    expect(runAgent).not.toHaveBeenCalled()
  })

})
