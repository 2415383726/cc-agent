<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ReasoningEntry } from '../projection/transcript'
import MarkdownContent from './MarkdownContent.vue'
import TextShimmer from './TextShimmer.vue'
import { iconSvg } from './icons'
import { STRINGS } from './strings'
import rowCss from '../vendor/dsh/ui-chat/src/client/chat/ReasoningRow.module.css'
import disclosureCss from '../vendor/dsh/ui-primitives/src/DisclosureRow.module.css'

/*
 * 思考折叠行。DOM 蓝图：ui-chat ReasoningRow.tsx + ui-primitives
 * DisclosureRow.tsx（MIT）的 expandOnRowClick 形态（本应用唯一披露行用例，
 * 故内联 DOM 而非抽象组件）——
 * div.root[data-variant=think][data-state][data-expanded][data-preview] >
 *   div.header[data-disclosure-header] >
 *     div.row[role=button][aria-expanded][data-expandable]（整行点击/Enter 切换）>
 *       span.leading（思考图标；展开后 chevron-up；收起 hover 换 chevron-down）
 *       + span.title 思考 + collapsedContent =
 *         span.separator + span.summary[data-streaming] > span.summaryText > TextShimmer
 *   展开时随后渲染 div.thinkBody > MarkdownText variant=compact。
 * 摘要规则平移上游：静态取首行；流式取最近完成段落首行；去 ** 标记。
 * 偏离：usePresentation 预览策略省略——本应用始终展示摘要预览。
 */
const props = defineProps<{ entry: ReasoningEntry }>()

const expanded = ref(false)
// 切换场景重建条目时收起新的思考行（id 变化即视为新行）。
watch(
  () => props.entry.id,
  () => {
    expanded.value = false
  },
)

function firstLine(text: string): string {
  const newline = text.indexOf('\n')
  return newline === -1 ? text : text.slice(0, newline)
}

function latestCompletedParagraphFirstLine(text: string): string {
  let summary = ''
  let paragraphStart = 0
  const separator = /\r?\n(?:[\t ]*\r?\n)+/g
  while (true) {
    const nextParagraph = separator.exec(text)
    const paragraphEnd =
      nextParagraph === null ? text.length : nextParagraph.index + nextParagraph[0].indexOf('\n')
    const newline = text.indexOf('\n', paragraphStart)
    if (newline !== -1 && newline <= paragraphEnd) {
      const candidate = text.slice(paragraphStart, newline).trim()
      if (candidate !== '') summary = candidate
    }
    if (nextParagraph === null) return summary
    paragraphStart = nextParagraph.index + nextParagraph[0].length
  }
}

const summaryText = computed(() =>
  props.entry.streaming
    ? latestCompletedParagraphFirstLine(props.entry.text)
    : firstLine(props.entry.text),
)
const summary = computed(() => summaryText.value.replaceAll('**', ''))
const hasSummary = computed(() => summary.value !== '')
const thinkIcon = iconSvg('think')
const chevronDown = iconSvg('chevron-down')
const chevronUp = iconSvg('chevron-up')

function onToggle(): void {
  expanded.value = !expanded.value
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  onToggle()
}
</script>

<template>
  <div
    :class="rowCss.root"
    data-variant="think"
    :data-state="entry.streaming ? 'running' : 'ok'"
    :data-expanded="expanded ? '' : undefined"
    :data-preview="hasSummary ? '' : undefined"
  >
    <div :class="disclosureCss.header" data-disclosure-header>
      <div
        :class="disclosureCss.row"
        data-disclosure-row
        data-expandable
        role="button"
        tabindex="0"
        :aria-expanded="expanded"
        data-testid="reasoning-toggle"
        @click="onToggle"
        @keydown="onKeydown"
      >
        <span :class="disclosureCss.leading">
          <template v-if="!expanded">
            <span :class="disclosureCss.iconIdle" v-html="thinkIcon" />
            <span :class="disclosureCss.chevronHover" v-html="chevronDown" />
          </template>
          <template v-else>
            <span v-html="chevronUp" />
          </template>
        </span>
        <span :class="disclosureCss.title">{{ STRINGS.think }}</span>
        <span :class="rowCss.separator" data-shimmer-decoration aria-hidden="true" />
        <span :class="rowCss.summary" :data-streaming="entry.streaming ? '' : undefined" data-testid="reasoning-summary">
          <span :class="rowCss.summaryText">
            <TextShimmer :text="summary" :active="entry.streaming" />
          </span>
        </span>
      </div>
    </div>
    <div v-if="expanded" :class="rowCss.thinkBody" data-testid="reasoning-body">
      <MarkdownContent :text="entry.text" :compact="true" />
    </div>
  </div>
</template>
