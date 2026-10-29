import { describe, expect, it } from 'vitest'
import { answerSegments } from '../src/projection/visualize'

const fragment = '<section data-pi-visualize="1" data-kit-version="1" data-title="排队演示" data-description="拖动到达速度观察排队人数。"><svg></svg><script>let n=1</script></section>'
const block = (html = fragment) => `\`\`\`pi-visualize\n${html}\n\`\`\``

describe('assistant answer content', () => {
  it('segments a dedicated closed block while keeping ordinary code inert', () => {
    const parts = answerSegments(`说明\n\n${block()}\n\n\`\`\`html\n<script>bad()</script>\n\`\`\``)
    expect(parts.map((part) => part.kind)).toEqual(['markdown', 'visualize', 'markdown'])
    expect(parts[1]).toMatchObject({ block: { title: '排队演示', description: '拖动到达速度观察排队人数。', source: fragment, error: '' } })
    expect(parts[2]).toMatchObject({ html: expect.stringContaining('&lt;script&gt;') })
  })
})

it('rejects unclosed fences, unsupported versions and malformed fragment roots without executing partial content', () => {
  for (const source of [
    `\`\`\`pi-visualize\n${fragment}`,
    block(fragment.replace('data-kit-version="1"', 'data-kit-version="2"')),
    block(fragment.replace('data-pi-visualize="1"', 'data-pi-visualize="2"')),
    block(fragment.replace('data-title="排队演示"', 'data-title=""')),
    block(fragment.replace('data-description="拖动到达速度观察排队人数。"', '')),
    block(`${fragment}<script>bad()</script>`),
    block(`<!doctype html><html><body>${fragment}</body></html>`),
    block(fragment.replace('<svg>', '<meta http-equiv="Content-Security-Policy" content="default-src *"><svg>')),
    block(fragment.replace('<svg>', '<script type="module">import "x"</script><svg>')),
    block(fragment.replace('<svg>', '<img src="https://remote.invalid/pixel"><svg>')),
    block(fragment.replace('<svg>', '<template><template><img src="https://remote.invalid/pixel"></template></template><svg>')),
    block(fragment.replace('<svg>', '<style>@import "https://remote.invalid/a.css";</style><svg>')),
    block(fragment.replace('<svg>', '<svg><image href="https://remote.invalid/x.svg"/></svg><svg>')),
    block(fragment.replace('data-kit-version="1"', 'data-kit-version="1" data-libraries="d3"')),
  ]) {
    const artifact = answerSegments(source).find((part) => part.kind === 'visualize') as any
    expect(artifact?.block.error, source).toBeTruthy()
  }
})

it('enforces UTF-8 byte budgets and Unicode field limits on entire blocks', () => {
  const sized = (bytes: number) => {
    const padding = bytes - new TextEncoder().encode(fragment).byteLength - 7
    return fragment.replace('</section>', `<!--${'x'.repeat(padding)}--></section>`)
  }
  expect((answerSegments(block(sized(65536)))[0] as any).block.error).toBe('')
  expect((answerSegments(block(sized(65537)))[0] as any).block.error).toContain('64 KiB')
  const chinese = fragment.replace('<svg>', `<!--${'汉'.repeat(23000)}--><svg>`)
  expect((answerSegments(block(chinese))[0] as any).block.error).toContain('64 KiB')
  const three = answerSegments([block(), block(), block()].join('\n\n')) as any[]
  expect(three[2].block.error).toContain('两幅')
  const field = fragment.replace('data-title="排队演示"', `data-title="${'😀'.repeat(120)}"`)
  expect((answerSegments(block(field))[0] as any).block.error).toBe('')
  expect((answerSegments(block(field.replace('data-title="', 'data-title="😀')))[0] as any).block.error).toBeTruthy()
})

it('supports local SVG paint references and CRLF fences while malformed CSS stays a readable fallback', () => {
  const local = fragment.replace('<svg>', '<svg style="fill:url(\'#paint\')"><defs><linearGradient id="paint"/></defs>')
  expect((answerSegments(block(local).replaceAll('\n', '\r\n'))[0] as any).block.error).toBe('')
  const malformed = fragment.replace('<svg>', '<style>.a{color:\\ffffff}</style><svg>')
  expect(() => answerSegments(block(malformed))).not.toThrow()
})
