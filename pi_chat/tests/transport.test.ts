import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { deleteConversation, listConversations, renameConversation } from '../src/dify/transport'

const config = {
  baseUrl: '/v1/',
  apiKey: 'app-test',
  user: 'u1',
  inputs: {},
}

const fetchSpy = vi.fn()

beforeEach(() => {
  fetchSpy.mockReset()
  vi.stubGlobal('fetch', fetchSpy)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
    json: async () => body,
  } as unknown as Response
}

describe('conversation rename/delete transport', () => {
  it('重命名调用 Dify conversations name 端点并携带 user/name/auto_generate', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ id: 'conv_1', name: '新名字' }))
    const updated = await renameConversation(config, 'conv_1', '新名字')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/v1/conversations/conv_1/name')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer app-test')
    expect(JSON.parse(String(init.body))).toEqual({
      user: 'u1',
      name: '新名字',
      auto_generate: false,
    })
    expect(updated).toMatchObject({ id: 'conv_1', name: '新名字' })
  })

  it('删除调用 Dify conversations DELETE 端点并携带 user', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ result: 'success' }))
    await deleteConversation(config, 'conv_1')
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/v1/conversations/conv_1')
    expect(init.method).toBe('DELETE')
    expect(JSON.parse(String(init.body))).toEqual({ user: 'u1' })
  })

  it('重命名失败时抛出 Dify 返回的错误消息', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ message: 'Conversation Not Exists' }, 404),
    )
    await expect(renameConversation(config, 'missing', 'x')).rejects.toThrow(
      'Conversation Not Exists',
    )
  })

  it('删除失败时抛出带状态码的错误', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({}, 500))
    await expect(deleteConversation(config, 'conv_1')).rejects.toThrow('500')
  })

  it('会话时间戳按 Unix 秒换算为毫秒（列表与重命名一致）', async () => {
    fetchSpy
      .mockResolvedValueOnce(
        jsonResponse({ data: [{ id: 'conv_1', name: '问候', updated_at: 1_800_000_000 }], has_more: false }),
      )
      .mockResolvedValueOnce(jsonResponse({ id: 'conv_1', name: '新名字', updated_at: 1_800_000_001 }))
    const list = await listConversations(config)
    expect(list[0].updatedAt).toBe(1_800_000_000_000)
    const renamed = await renameConversation(config, 'conv_1', '新名字')
    expect(renamed.updatedAt).toBe(1_800_000_001_000)
  })

  it('已是毫秒的时间戳保持不变', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse({ data: [{ id: 'conv_1', name: '问候', updated_at: 1_800_000_000_000 }], has_more: false }),
    )
    const list = await listConversations(config)
    expect(list[0].updatedAt).toBe(1_800_000_000_000)
  })
})
