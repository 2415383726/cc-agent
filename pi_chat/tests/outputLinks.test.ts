import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TranscriptView from '../src/timeline/TranscriptView.vue'
import { safeOutputHref } from '../src/timeline/links'

/*
 * P3-3：输出文件链接的协议护栏。输出 URL 来自 Dify 平台消息与远端 MCP 产物，
 * 属不可信输入——TranscriptView 渲染 <a> 前必须过 safeOutputHref，
 * 拒绝的（javascript:/data:/...）退化为纯文本文件名。
 */
describe('safeOutputHref 输出链接协议护栏', () => {
  it('放行 http/https 绝对地址与站内相对引用', () => {
    expect(safeOutputHref('https://files.test/report.pdf')).toBe('https://files.test/report.pdf')
    expect(safeOutputHref('http://files.test/report.pdf')).toBe('http://files.test/report.pdf')
    expect(safeOutputHref('/files/report.pdf')).toBe('/files/report.pdf')
    expect(safeOutputHref('./files/report.pdf')).toBe('./files/report.pdf')
    expect(safeOutputHref('files/report.pdf')).toBe('files/report.pdf')
    expect(safeOutputHref('#report')).toBe('#report')
    expect(safeOutputHref('//files.test/report.pdf')).toBe('//files.test/report.pdf')
  })

  it('拒绝 javascript:/data:/vbscript:/ftp: 等非常规协议与空值', () => {
    expect(safeOutputHref('javascript:alert(1)')).toBeNull()
    expect(safeOutputHref('JaVaScRiPt:alert(1)')).toBeNull()
    expect(safeOutputHref('data:text/html,<b>x</b>')).toBeNull()
    expect(safeOutputHref('vbscript:msgbox')).toBeNull()
    expect(safeOutputHref('ftp://files.test/report.pdf')).toBeNull()
    expect(safeOutputHref('')).toBeNull()
    expect(safeOutputHref(undefined)).toBeNull()
  })

  it('TranscriptView 输出文件渲染：javascript: URL 退化为纯文本文件名（不渲染 <a>）', () => {
    const wrapper = mount(TranscriptView, {
      props: {
        entries: [],
        outputs: [
          { id: 'f1', name: '安全报告.pdf', url: 'https://files.test/report.pdf' },
          { id: 'f2', name: '恶意.pdf', url: 'javascript:alert(1)' },
        ],
      },
    })
    const list = wrapper.find('[aria-label="输出文件"]')
    expect(list.exists()).toBe(true)
    const links = list.findAll('a')
    expect(links).toHaveLength(1)
    expect(links[0].attributes('href')).toBe('https://files.test/report.pdf')
    // 被拒链接只保留文件名文本，无任何可点击通道
    expect(list.text()).toContain('恶意.pdf')
    expect(list.html()).not.toContain('javascript:')
  })
})
