/**
 * 时间线 markdown 渲染：在 projection/markdown.ts 的统一配置（html:false +
 * highlight.js）之上，为代码块与表格补上 dsh 的 DOM 包装，使
 * vendored CodeBlock.module.css / MarkdownText.module.css 原样生效。
 *
 * DOM 蓝图（上游 ui-primitives markdown/render.tsx + CodeBlock.tsx，MIT）：
 * - 代码块 → div.md-code-block > div.bannerWrap > div.banner[data-code-block-banner]
 *   （div.infostring 语言标注 + div.action > button 复制）+ div.content > pre/code
 * - 表格   → div.tableScroll（≥4 列加全局钩子 md-table-wide，否则 tableFill）
 * 类名经 CSS Modules 哈希注入；`md-table-wide`、`data-code-block-banner`、
 * `data-code-copy` 是上游既定的全局钩子，保持原名。
 * 偏离：上游用 shiki 高亮，本应用规格固定 highlight.js（spec 取材黑名单），
 * pre/code 结构与 vendored CSS 的 `:where(pre)` 规则兼容。
 */
import type MarkdownIt from 'markdown-it'
import type Token from 'markdown-it/lib/token.mjs'
import { createTranscriptMarkdown, escapeHtml } from '../projection/markdown'
import codeBlockCss from '../vendor/dsh/ui-primitives/src/markdown/CodeBlock.module.css'
import markdownCss from '../vendor/dsh/ui-primitives/src/markdown/MarkdownText.module.css'
import { STRINGS } from './strings'

const md: MarkdownIt = createTranscriptMarkdown()

const defaultFence =
  md.renderer.rules.fence ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.fence = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const lang = String(token.info || '').trim().split(/\s+/)[0] || ''
  const content = String(token.content || '')
  // 上游对空围栏保留原生 <pre>；有内容的围栏包 CodeBlock 横幅 DOM。
  if (!content.trim()) return defaultFence(tokens, idx, options, env, self)
  const language = escapeHtml(lang)
  const inner = options.highlight
    ? options.highlight(content, lang, '') // highlight 已转义
    : escapeHtml(content)
  return (
    `<div class="${codeBlockCss.block} md-code-block" data-testid="md-code-block">` +
    `<div class="${codeBlockCss.bannerWrap}">` +
    `<div class="${codeBlockCss.banner}" data-code-block-banner>` +
    `<div class="${codeBlockCss.infostring}">${language}</div>` +
    `<div class="${codeBlockCss.action}">` +
    `<button type="button" class="${codeBlockCss.copyButton}" data-code-copy>${STRINGS.codeCopy}</button>` +
    '</div></div></div>' +
    `<div class="${codeBlockCss.content}" data-code-block-content>` +
    `<pre><code${lang ? ` class="language-${language}"` : ''}>${inner}</code></pre>` +
    '</div></div>'
  )
}

function countColumns(tokens: Token[], tableIndex: number): number {
  for (let i = tableIndex + 1; i < tokens.length; i++) {
    if (tokens[i].type === 'thead_close') break
    if (tokens[i].type === 'tr_close') {
      // 数第一行表头单元格数。
      let columns = 0
      for (let j = tableIndex + 1; j < i; j++) {
        if (tokens[j].type === 'th_open') columns++
      }
      return columns
    }
  }
  return 0
}

const defaultTableOpen =
  md.renderer.rules.table_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.table_open = (tokens, idx, options, env, self) => {
  const wide = countColumns(tokens, idx) >= 4
  const wrapClass = wide ? `${markdownCss.tableScroll} md-table-wide` : `${markdownCss.tableScroll} ${markdownCss.tableFill}`
  return `<div class="${wrapClass}" data-testid="md-table">` + defaultTableOpen(tokens, idx, options, env, self)
}

const defaultTableClose =
  md.renderer.rules.table_close ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.table_close = (tokens, idx, options, env, self) => {
  return defaultTableClose(tokens, idx, options, env, self) + '</div>'
}

export function renderTranscriptMarkdown(source: string): string {
  return md.render(String(source || ''))
}
