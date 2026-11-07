import { describe, expect, it } from 'vitest'
// 接缝：scanText(text) —— 纯函数扫描器（check:static 的模式层）。
// 只验证外显行为：给定产物文本，断言违例清单；文件遍历/哈希/报告落盘归 CLI 脚本。
import { FORBIDDEN, scanText } from '../scripts/static-scan.mjs'

interface Violation {
  pattern: string
  match: string
}

function matchesFor(text: string): string[] {
  return scanText(text).map((violation: Violation) => violation.match)
}

describe('check:static 扫描器', () => {
  it('放行干净产物：相对引用、data: URI、无外网端点', () => {
    const clean = [
      '<script src="./assets/index-abc.js"></script>',
      '<link href="./assets/index-abc.css" rel="stylesheet">',
      '.font { src: url(./montserrat-light.woff2) }',
      "background: url('/assets/icon.svg')",
      "const res = await fetch(baseUrl + '/v1/chat-messages')",
      "const mod = await import('./vendor/chunk.js')",
      '<img src="data:image/svg+xml;base64,PHN2Zz4=">',
      '连接 Dify 服务地址由用户在表单填写',
    ].join('\n')
    expect(scanText(clean)).toEqual([])
  })

  it('拦截硬编码外链：src/href/url()/fetch()/import() 的 http(s) 引用', () => {
    expect(matchesFor('<img src="https://cdn.example.com/a.png">')).toEqual(['src="https:'])
    expect(matchesFor('<a href="https://example.com">x</a>')).toEqual(['href="https:'])
    expect(matchesFor('.x { background: url(https://img.example.com/a.png) }')).toEqual(['url(https:'])
    expect(matchesFor("fetch('https://api.example.com/v1')")).toEqual(["fetch('https:"])
    expect(matchesFor('import("https://cdn.example.com/mod.js")')).toEqual(['import("https:'])
  })

  it('拦截 ws:// 与 wss:// 明文套接字', () => {
    expect(matchesFor("new WebSocket('ws://host/socket')")).toEqual(['ws://'])
    expect(matchesFor("new WebSocket('wss://host/socket')")).toEqual(['wss://'])
  })

  it('拦截追踪器与公共 CDN 主机', () => {
    expect(matchesFor('https://fonts.googleapis.com/css2?family=x')).toEqual(['fonts.googleapis.com'])
    expect(matchesFor('https://cdn.jsdelivr.net/npm/vue')).toEqual(['cdn.jsdelivr.net'])
    expect(matchesFor('https://unpkg.com/vue@3')).toEqual(['unpkg.com'])
    expect(matchesFor('https://www.google-analytics.com/collect')).toEqual(['google-analytics'])
  })

  it('拦截 Pi Agent SDK 与旧后端 API 残留', () => {
    expect(matchesFor("import { Agent } from 'pi-coding-agent'")).toEqual(['pi-coding-agent'])
    expect(matchesFor("from '@earendil-works/harness'")).toEqual(['@earendil-works'])
    expect(matchesFor("fetch('/api/pi/conversation')")).toEqual(['/api/pi/'])
  })

  it('每个违例都携带来源模式与命中片段（报告可读）', () => {
    const violations = scanText('<img src="https://x.example/a.png">')
    expect(violations).toHaveLength(1)
    expect(violations[0].pattern).toContain('https?:')
    expect(violations[0].match).toContain('https:')
  })

  it('模式清单与移植源一致（机制照搬）', () => {
    expect(FORBIDDEN).toHaveLength(13)
  })
})
