<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ToolEntry } from '../projection/transcript'
import { toolStatusLabel, toolStatusTone } from '../projection/toolStatus'
import { classifyTool, formatToolBody, toolRowState, toolSummary } from './toolModel'
import { TOOL_STRINGS } from './strings'
import { iconSvg } from './icons'
import TextShimmer from './TextShimmer.vue'
import css from '../vendor/dsh/ui-tool/src/client/tool/components/ToolRow.module.css'
import disclosureCss from '../vendor/dsh/ui-primitives/src/DisclosureRow.module.css'
import tagCss from '../vendor/dsh/ui-primitives/src/Tag.module.css'

/*
 * 工具折叠卡。DOM 蓝图：ui-tool GenericToolCard → ToolRow.tsx（MIT）+
 * ui-primitives DisclosureRow.tsx 的 expandOnRowClick 形态（与思考行同构，
 * 故内联 DOM）。类名零改动引用 vendored ToolRow.module.css / DisclosureRow.module.css /
 * Tag.module.css。
 * 偏离（契约外省略，均有注释）：上游 file/web/diff/search/terminal/image 专用卡
 * 不在本契约事件面内，展开体统一走 generic IN/OUT（ioCard）卡；文件链接/打开、
 * inspect 跳转、context menu 省略；useDisclosure 语义用本地 Vue state；
 * 「状态徽标」为本票据新增（上游以 shimmer/颜色表意）——复用 ExitCodeBadge 的
 * neutral 胶囊 + 着色点语言，tone 映射取 projection/toolStatus 的 toolStatusTone；
 * header shimmer 仅包住摘要文本（ReasoningRow 同款），行级转态由徽标运行点承担。
 */
const props = defineProps<{ entry: ToolEntry }>()

/* 内部工具由问卷卡与技能行承载（projection 已隐藏；组件侧再守一道）。 */
const INTERNAL_TOOL_NAMES = new Set(['ask_user', 'activate_skill', 'read_skill_resource'])
const isInternal = computed(() => INTERNAL_TOOL_NAMES.has(props.entry.name))

const expanded = ref(false)
// 切换场景重建条目时收起新的卡片（id 变化即视为新行）。
watch(
  () => props.entry.id,
  () => {
    expanded.value = false
  },
)

const variant = computed(() => classifyTool(props.entry.name))
const title = computed(() => {
  const titles: Record<string, string> = {
    search: TOOL_STRINGS.titleSearch,
    read: TOOL_STRINGS.titleRead,
    bash: TOOL_STRINGS.titleBash,
    write: TOOL_STRINGS.titleWrite,
    edit: TOOL_STRINGS.titleEdit,
    code: TOOL_STRINGS.titleCode,
    others: TOOL_STRINGS.titleGeneric,
  }
  return titles[variant.value]
})
const state = computed(() => toolRowState(props.entry.status))

/** 结果文本：进度（tool.update）行在前，合成/真实结果在后（配对不变量的呈现侧）。 */
const outputText = computed(() => {
  const parts: string[] = []
  if (props.entry.updates.length) parts.push(props.entry.updates.join('\n'))
  if (props.entry.result) parts.push(props.entry.result)
  return parts.join('\n')
})

const hasArgsBody = computed(
  () => props.entry.args !== undefined && props.entry.args !== null && props.entry.args !== '',
)
const expandable = computed(() => hasArgsBody.value || outputText.value !== '')
const open = computed(() => expanded.value && expandable.value)

const inputText = computed(() =>
  open.value && hasArgsBody.value ? formatToolBody(variant.value, props.entry.args) : null,
)

/** 折叠摘要：失败行取结果首行（上游 errorSummary 语义），否则参数摘要。 */
const summaryText = computed(() => {
  if (state.value === 'error' && outputText.value !== '') {
    const newline = outputText.value.indexOf('\n')
    return newline === -1 ? outputText.value : outputText.value.slice(0, newline)
  }
  return toolSummary(props.entry)
})

const badgeLabel = computed(() => toolStatusLabel(props.entry.status))
const badgeTone = computed(() => toolStatusTone(props.entry.status))
const running = computed(() => state.value === 'running')

/** 上游 GenericToolCard VARIANT_ICONS：变体 → leading glyph。 */
const variantIcon = computed(() => {
  const icons: Record<string, string> = {
    search: iconSvg('search'),
    read: iconSvg('browse'),
    bash: iconSvg('api'),
    write: iconSvg('edit'),
    edit: iconSvg('edit'),
    code: iconSvg('code'),
    others: iconSvg('sparkle'),
  }
  return icons[variant.value]
})
const chevronDown = iconSvg('chevron-down')
const chevronUp = iconSvg('chevron-up')

/** 上游 stateStatus：给读屏的运行/失败/中断态文案。 */
const statusAnnouncement = computed(() => {
  if (running.value) return TOOL_STRINGS.rowRunning
  if (state.value === 'error') return TOOL_STRINGS.rowFailed
  if (state.value === 'stopped') return TOOL_STRINGS.rowStopped
  return null
})

function onToggle(): void {
  if (!expandable.value) return
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
    v-if="!isInternal"
    :class="css.root"
    :data-variant="variant"
    :data-tool="entry.name"
    :data-state="state"
    data-testid="tool-card"
  >
    <span v-if="statusAnnouncement" :class="css.visuallyHidden">{{ statusAnnouncement }}</span>
    <div :class="disclosureCss.header" data-disclosure-header>
      <div
        :class="disclosureCss.row"
        data-disclosure-row
        data-expandable
        role="button"
        tabindex="0"
        :aria-expanded="expandable ? expanded : undefined"
        data-testid="tool-toggle"
        @click="onToggle"
        @keydown="onKeydown"
      >
        <span :class="[disclosureCss.leading, css.leading]">
          <template v-if="!expanded">
            <span :class="disclosureCss.iconIdle" v-html="variantIcon" />
            <span :class="disclosureCss.chevronHover" v-html="chevronDown" />
          </template>
          <template v-else>
            <span v-html="chevronUp" />
          </template>
        </span>
        <span :class="css.title">{{ title }}</span>
        <template v-if="summaryText !== ''">
          <span :class="css.sep" data-shimmer-decoration aria-hidden="true" />
          <span
            :class="[css.summary, state === 'error' ? css.errorSummary : '', state === 'stopped' ? css.stoppedSummary : '']"
            data-testid="tool-summary"
          >
            <TextShimmer :text="summaryText" :active="running" />
          </span>
        </template>
        <!-- 状态徽标（票据新增）：neutral 胶囊 + tone 着色点；运行点带脉冲（自有 CSS）。 -->
        <span :class="[tagCss.tag, 'pi-tool-status']" data-tone="neutral" data-testid="tool-status">
          <span class="pi-tool-status-dot" :data-tone="badgeTone" aria-hidden="true" />
          {{ badgeLabel }}
        </span>
      </div>
    </div>
    <div v-if="open" :class="css.bodyWrap" data-testid="tool-body">
      <div :class="css.ioCard">
        <div v-if="inputText !== null" :class="css.ioSection">
          <span :class="css.ioLabel">{{ TOOL_STRINGS.input }}</span>
          <span :class="css.ioText" data-testid="tool-input">{{ inputText }}</span>
        </div>
        <span v-if="inputText !== null && outputText !== ''" :class="css.ioDivider" aria-hidden="true" />
        <div v-if="outputText !== ''" :class="css.ioSection">
          <span :class="css.ioLabel">{{ TOOL_STRINGS.output }}</span>
          <span
            :class="css.ioText"
            :data-error="state === 'error' ? '' : undefined"
            data-testid="tool-output"
          >{{ outputText }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
/* 组件自有（非 vendor）：状态徽标点。颜色取上游 state alias 令牌；running 点
   脉冲为本票据新增（上游运行态以 shimmer 表意，徽标是补充的可读状态）。 */
.pi-tool-status {
  flex: none;
  margin-left: 8px;
  gap: 5px;
}

.pi-tool-status-dot {
  flex: none;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  corner-shape: round;
}

.pi-tool-status-dot[data-tone='running'] {
  background: var(--dsw-alias-state-business-primary, #4c82fb);
  animation: pi-tool-dot-pulse 1.2s ease-in-out infinite;
}

.pi-tool-status-dot[data-tone='completed'] {
  background: var(--dsw-alias-state-success-primary, #23a55a);
}

.pi-tool-status-dot[data-tone='error'] {
  background: var(--dsw-alias-state-error-primary, #e5484d);
}

.pi-tool-status-dot[data-tone='stopped'],
.pi-tool-status-dot[data-tone='unknown'] {
  background: var(--dsw-alias-state-warn-label, #b47609);
}

@keyframes pi-tool-dot-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .pi-tool-status-dot[data-tone='running'] {
    animation: none;
  }
}
</style>
