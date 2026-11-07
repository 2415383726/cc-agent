<script setup lang="ts">
import { computed } from 'vue'
import { renderTranscriptMarkdown } from './markdown'
import { writeClipboard } from '../vendor/dsh/ui-primitives/src/clipboard'
import { STRINGS } from './strings'
import markdownCss from '../vendor/dsh/ui-primitives/src/markdown/MarkdownText.module.css'

/*
 * 助手/思考 markdown 正文。DOM 蓝图：ui-primitives MarkdownText.tsx（MIT）——
 * div.markdown（compact 变体加 .compact，思考行用 13px 次级排版）。
 * 内容经 renderTranscriptMarkdown（html:false 安全策略，见 projection/markdown.ts）。
 * 代码块横幅在 v-html 内，复制按钮经根节点事件委托接管（上游 CodeBlock 自持
 * state；此处以 DOM 直改按钮文案呈现一秒反馈，避免重建整段 HTML）。
 */
const props = defineProps<{
  text: string
  compact?: boolean
}>()

const html = computed(() => renderTranscriptMarkdown(props.text))
const rootClass = computed(() =>
  props.compact ? [markdownCss.markdown, markdownCss.compact] : markdownCss.markdown,
)

async function onRootClick(event: MouseEvent): Promise<void> {
  const target = event.target as HTMLElement | null
  const button = target?.closest('[data-code-copy]') as HTMLButtonElement | null
  if (!button) return
  const block = button.closest('.md-code-block')
  const source = block?.querySelector('pre')?.textContent ?? ''
  const accepted = await writeClipboard(source)
  if (!accepted) return
  button.textContent = STRINGS.copied
  window.setTimeout(() => {
    button.textContent = STRINGS.codeCopy
  }, 1000)
}
</script>

<template>
  <div :class="rootClass" data-testid="markdown-content" @click="onRootClick" v-html="html" />
</template>
