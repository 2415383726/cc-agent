import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import yaml from 'highlight.js/lib/languages/yaml'

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('python', python)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('yaml', yaml)

const md = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: true,
  highlight(source, language) {
    const lang = String(language || '').trim().toLowerCase()
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(source, { language: lang, ignoreIllegals: true }).value
      } catch {
        /* fall through */
      }
    }
    return escapeHtml(source)
  },
})

const defaultLinkOpen =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  token.attrSet('target', '_blank')
  token.attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(source: string): string {
  return md.render(String(source || ''))
}

export function escapeHtml(value: string): string {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function renderJson(value: unknown): string {
  try {
    return escapeHtml(JSON.stringify(value, null, 2))
  } catch {
    return escapeHtml(String(value))
  }
}

/** Shared Markdown parser for assistant content; HTML stays disabled. */
export function markdownTokens(source: string) {
  return md.parse(source, {})
}
