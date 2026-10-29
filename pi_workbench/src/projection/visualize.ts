import { markdownTokens, renderMarkdown } from './markdown'

export interface VisualizeBlock {
  index: number
  digest: string
  source: string
  title: string
  description: string
  libraries: string[]
  error: string
}

export type AnswerSegment = { kind: 'markdown'; html: string } | { kind: 'visualize'; block: VisualizeBlock }

/** Recognize only dedicated fenced blocks, using the same parser as ordinary Markdown. */
export function answerSegments(source: string): AnswerSegment[] {
  const lines = source.split('\n')
  const segments: AnswerSegment[] = []
  let cursor = 0
  let index = 0
  let totalBytes = 0
  const markdown = (start: number, end: number) => {
    const text = lines.slice(start, end).join('\n')
    if (text.trim()) segments.push({ kind: 'markdown', html: renderMarkdown(text) })
  }
  for (const token of markdownTokens(source)) {
    if (token.type !== 'fence' || token.info.trim() !== 'pi-visualize' || !token.map) continue
    const [start, end] = token.map
    markdown(cursor, start)
    const raw = token.content.replace(/\n$/, '')
    const bytes = new TextEncoder().encode(raw).byteLength
    totalBytes += bytes
    const budgetError = index >= 2 ? '每条回答最多展示两幅作品。'
      : bytes > 65536 ? '作品超过 64 KiB 上限，未执行。'
      : totalBytes > 131072 ? '此回答的作品总量超过 128 KiB，未执行。' : ''
    // A detached template is inert, including resource elements. Resource parsing must stay outside an active document.
    const template = document.createElement('template')
    if (!budgetError) template.innerHTML = raw
    const root = template.content.firstElementChild
    const closing = (lines[end - 1] || '').replace(/\r$/, '')
    const closed = new RegExp(`^ {0,3}${token.markup[0]}{${token.markup.length},}[ \\t]*$`).test(closing)
    const error = budgetError || (!closed ? '作品尚未生成完整。' : validateFragment(raw, template.content, root))
    segments.push({ kind: 'visualize', block: {
      index: index++, digest: contentFingerprint(raw), source: raw,
      title: [...(root?.getAttribute('data-title') || '交互作品')].slice(0, 120).join(''),
      description: [...(root?.getAttribute('data-description') || '')].slice(0, 500).join(''),
      libraries: (root?.getAttribute('data-libraries') || '').split(/[ ,]+/).filter(Boolean), error,
    } })
    cursor = end
  }
  markdown(cursor, lines.length)
  return segments
}

/** Format preflight only. Browser isolation, not this check, enforces script capabilities. */
function validateFragment(source: string, content: DocumentFragment, root: Element | null): string {
  const nodes = [...content.childNodes].filter((node) => node.nodeType !== 8 &&
    !(node.nodeType === 3 && !node.textContent?.trim()))
  if (!root || nodes.length !== 1 || nodes[0] !== root) return '作品需要一个根元素。'
  if (/<\s*!doctype|<\s*\/?\s*(?:html|head|body)\b/i.test(source)) return '作品只能提供内容片段。'
  if (root.getAttribute('data-pi-visualize') !== '1' || root.getAttribute('data-kit-version') !== '1') {
    return '此作品的协议或套件版本暂不受支持。'
  }
  const title = root.getAttribute('data-title') || ''
  const description = root.getAttribute('data-description') || ''
  if (!title.trim() || !description.trim()) return '作品缺少标题或文字说明。'
  if ([...title].length > 120 || [...description].length > 500) return '作品的标题或文字说明过长。'
  if ((root.getAttribute('data-libraries') || '').trim()) return '此版本尚不支持声明的本地库。'
  for (const element of fragmentElements(root)) {
    if (['BASE', 'META', 'LINK', 'IFRAME', 'OBJECT', 'EMBED'].includes(element.tagName.toUpperCase())) {
      return '作品包含不支持的文档或资源元素。'
    }
    if (element.tagName.toUpperCase() === 'SCRIPT' &&
      !['', 'text/javascript', 'application/javascript'].includes((element.getAttribute('type') || '').trim().toLowerCase())) {
      return '作品仅支持经典本地脚本。'
    }
    for (const attr of [...element.attributes]) {
      const name = attr.name.toLowerCase()
      if (['src', 'href', 'xlink:href', 'action', 'formaction', 'poster', 'data', 'ping', 'srcset', 'srcdoc'].includes(name)) {
        if (!attr.value.startsWith('#') && !/^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(attr.value)) {
          return '作品不支持外部资源或跳转。'
        }
      }
      if (name === 'style' && externalCss(attr.value)) return '作品不支持外部样式资源。'
    }
    if (element.tagName.toUpperCase() === 'STYLE' && externalCss(element.textContent || '')) {
      return '作品不支持外部样式资源。'
    }
  }
  return ''
}

function* fragmentElements(root: Element): Generator<Element> {
  const pending = [root]
  while (pending.length) {
    const element = pending.pop()!
    yield element
    pending.push(...element.children)
    if (element.tagName.toUpperCase() === 'TEMPLATE' && 'content' in element) {
      pending.push(...(element as HTMLTemplateElement).content.children)
    }
  }
}

function externalCss(css: string): boolean {
  // Normalize CSS escapes before format checks. CSP independently rejects network resource loads.
  const plain = css.replace(/\\([0-9a-f]{1,6})\s?/gi, (_, hex) => String.fromCodePoint(Math.min(0x10ffff, parseInt(hex, 16))))
    .replace(/\\(.)/g, '$1').replace(/\/\*[\s\S]*?\*\//g, '')
  return /@import\b/i.test(plain) || [...plain.matchAll(/url\(([^)]*)\)/gi)].some((match) => {
    const target = match[1].trim().replace(/^['"]|['"]$/g, '')
    return !target.startsWith('#')
  })
}

/** Content fingerprint for instance identity; never an authorization token. */
function contentFingerprint(source: string): string {
  let hash = 14695981039346656037n
  for (const byte of new TextEncoder().encode(source)) {
    hash = BigInt.asUintN(64, (hash ^ BigInt(byte)) * 1099511628211n)
  }
  return hash.toString(16).padStart(16, '0')
}
