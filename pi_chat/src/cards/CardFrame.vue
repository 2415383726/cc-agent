<script setup lang="ts">
import { computed, ref } from 'vue'
import composerCss from '../vendor/dsh/ui-user-questions/src/client/QuestionComposer.module.css'
import { iconSvg } from '../timeline/icons'

/*
 * 卡片体系共享卡框（票据 05 原语，票据 06 审批卡复用）。
 *
 * DOM/类名蓝图：ui-user-questions QuestionComposer.tsx 的卡面骨架（MIT）——
 * section.card[data-minimized] >
 *   header.header > div.headingBlock(.eyebrow + 收起时的 .title)
 *                 + div.headerActions（slot="header-extra" 状态文案 + 收起/关闭 24px 圆形图标钮）
 *   + slot 默认（卡体）
 *   + slot="footer"（页脚：翻页器/反馈/动作）。
 * 样式类来自逐字 vendor 的 QuestionComposer.module.css（card/header/eyebrow/
 * headerActions/iconButton/cardMinimized/footer），类名零改动；票据 06 直接
 * 复用本组件与同一 CSS module，不复制第二份卡面样式。
 *
 * 收起（minimize）是卡框内部状态（上游同为组件内 state）：收起后只留头部
 * 条，标题进 headingBlock。关闭语义由宿主决定（问卷等待中=放弃整组，
 * 审批=拒绝语义归票据 06），卡框只 emit。
 */
const props = withDefaults(
  defineProps<{
    /** 头部眉题（问卷：question.header ?? questionnaire.title）。 */
    eyebrow?: string
    /** 收起时显示在头部的标题（问卷：当前题干）。 */
    title?: string
    /** 卡体标题元素 id（展开态 aria-labelledby 指向它，上游 body 题干同款）。 */
    labelledby?: string
    /** 提交中冻结头部件。 */
    busy?: boolean
    /** 关闭按钮的可访问名（等待中问卷为「放弃整组问题」）。 */
    closeLabel?: string
    /** 只读回显卡没有可返回的座位，隐藏关闭钮（偏离上游：上游工具行可重开）。 */
    closable?: boolean
  }>(),
  { eyebrow: '', title: '', labelledby: '', busy: false, closeLabel: '', closable: true },
)

const emit = defineEmits<{ close: [] }>()

const minimized = ref(false)
/* glyph 尺寸取上游调用点默认：chevron 14、close 16。 */
const chevronDown = iconSvg('chevron-down', 14)
const chevronUp = iconSvg('chevron-up', 14)
const closeIcon = iconSvg('close', 16)

const rootClasses = computed(() => [composerCss.card, minimized.value ? composerCss.cardMinimized : ''])
const headingId = computed(() => `card-heading-${props.eyebrow || 'card'}-${Math.abs(hash(props.title))}`)

function hash(text: string): number {
  let value = 0
  for (let index = 0; index < text.length; index += 1) {
    value = (value * 31 + text.charCodeAt(index)) | 0
  }
  return value
}
</script>

<template>
  <section
    :class="rootClasses"
    :aria-labelledby="minimized ? (title ? headingId : undefined) : labelledby || undefined"
    data-testid="card-frame"
  >
    <header :class="composerCss.header">
      <div v-if="eyebrow || (minimized && title)" :class="composerCss.headingBlock">
        <div v-if="eyebrow" :class="composerCss.eyebrow">{{ eyebrow }}</div>
        <h2 v-if="minimized && title" :id="headingId" :class="composerCss.title">{{ title }}</h2>
      </div>
      <div :class="composerCss.headerActions">
        <!-- 等待状态/倒计时/慢答按钮等宿主状态插槽（上游 waitStatus/waitButton 位）。 -->
        <slot name="header-extra" />
        <button
          type="button"
          :class="composerCss.iconButton"
          :aria-label="minimized ? '展开问题卡片' : '收起问题卡片'"
          :title="minimized ? '展开问题卡片' : '收起问题卡片'"
          :aria-expanded="!minimized"
          :disabled="busy"
          data-testid="card-minimize"
          @click="minimized = !minimized"
        >
          <span v-if="minimized" v-html="chevronUp" />
          <span v-else v-html="chevronDown" />
        </button>
        <button
          v-if="closable"
          type="button"
          :class="composerCss.iconButton"
          :aria-label="closeLabel || '关闭'"
          :title="closeLabel || '关闭'"
          :disabled="busy"
          data-testid="card-close"
          @click="emit('close')"
        >
          <span v-html="closeIcon" />
        </button>
      </div>
    </header>

    <template v-if="!minimized">
      <slot />
      <slot name="footer" />
    </template>
  </section>
</template>
