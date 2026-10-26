import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function readStyle(name: string) {
  return readFileSync(resolve(__dirname, name), 'utf8')
}

describe('assistant packaged styles', () => {
  it('keeps assistant.css free of host-level reset selectors', () => {
    const css = readStyle('assistant.css')

    expect(css).not.toMatch(/(^|\n)\s*body\s*\{/)
    expect(css).not.toMatch(/(^|\n)\s*#app\s*\{/)
    expect(css).not.toMatch(/(^|\n)\s*\*\s*\{/)
    expect(css).not.toMatch(/button,\s*\n\s*textarea,\s*\n\s*input\s*\{/)
    expect(css).not.toMatch(/(^|\n)\s*:root\s*\{[^}]*\b(?:color|background|font-family)\s*:/)
  })

  it('keeps assistant-vars.css limited to custom properties', () => {
    const css = readStyle('assistant-vars.css')

    expect(css).toContain('--cc-agent-primary')
    expect(css).toContain('--cc-agent-font-family')
    expect(css).not.toMatch(/(^|[;}])\s*font-family\s*:/)
    expect(css).not.toContain('background:')
    expect(css).not.toContain('color:')
  })

  it('uses a visible home composer border with a primary focus state', () => {
    const css = readStyle('assistant.css')

    expect(css).toMatch(/\.drawer-home-composer \.assistant-composer \.assistant-composer__box[^{]*\{[^}]*border-color:\s*var\(--cc-agent-line\)/s)
    expect(css).toMatch(/\.drawer-home-composer \.assistant-composer \.assistant-composer__box:focus-within[^{]*\{[^}]*border-color:\s*var\(--cc-agent-focus\)/s)
  })
})
