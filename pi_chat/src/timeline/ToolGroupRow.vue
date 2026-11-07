<script setup lang="ts">
import { ref } from 'vue'
import { iconSvg } from './icons'
import TextShimmer from './TextShimmer.vue'
import css from '../vendor/dsh/ui-chat/src/client/chat/ChatGroupSeat.module.css'

/*
 * 工具活动分组（「已调用工具并执行了命令」组头行）。DOM 蓝图：ui-chat
 * ChatGroupSeat.tsx 的 ProcessGroupHeader + body（MIT），类名零改动引用
 * vendored ChatGroupSeat.module.css。
 * 偏离：上游组策略（turnProcessOpen 存储、fold 时钟、useProcessScroll 滚动
 * 渐隐 mask、组员 NodeSeat 装配）不在本票据契约内——本组件是纯展示折叠组，
 * 默认展开（对齐视觉锚点截图），折叠态隐藏组体；body 保留 400px 滚动帽与
 * 稳定滚动条槽，渐隐边缘 mask 省略（无滚动边检测）。
 * 标题与 running 由调用方按 grouping.ts 的类别计数/拼装给出；上游嵌套
 * TextShimmer(TextShimmer(label)) 的写法简化为单层（文本型 shimmer）。
 */
const props = defineProps<{
  /** 组头标题（groupTitle 拼装结果，含 live 词）。 */
  label: string
  /** 上游 data-process-activity 的类别（组头 leading glyph 随类别切换）。 */
  activity: string
  /** 组内仍有运行中工具：组头 shimmer 指示。 */
  running: boolean
}>()

const expanded = ref(true)

const PROCESS_ICONS: Record<string, string> = {
  read: iconSvg('browse'),
  readImage: iconSvg('browse'),
  search: iconSvg('search'),
  edit: iconSvg('edit'),
  write: iconSvg('edit'),
  commands: iconSvg('api'),
  code: iconSvg('code'),
  webSearch: iconSvg('search'),
  webFetch: iconSvg('browse'),
  plan: iconSvg('edit'),
  questions: iconSvg('skill'),
  tools: iconSvg('sparkle'),
  thinking: iconSvg('think'),
}

const activityIcon = PROCESS_ICONS[props.activity] ?? PROCESS_ICONS.tools
const chevronDown = iconSvg('chevron-down')
const chevronUp = iconSvg('chevron-up')

function onToggle(): void {
  expanded.value = !expanded.value
}
</script>

<template>
  <div :class="css.root" data-step-process>
    <button
      type="button"
      :class="css.title"
      data-testid="tool-group-header"
      :aria-expanded="expanded"
      :data-process-activity="activity"
      @click="onToggle"
    >
      <span :class="css.leading" aria-hidden="true">
        <span :class="css.activityIcon" data-testid="tool-group-activity" :data-activity="activity" v-html="activityIcon" />
        <span :class="css.chevron" data-step-process-chevron>
          <span v-if="expanded" v-html="chevronUp" />
          <span v-else v-html="chevronDown" />
        </span>
      </span>
      <TextShimmer :text="label" :active="running" />
    </button>
    <div v-if="expanded" :class="css.body" data-step-process-body>
      <div :class="css.content">
        <slot />
      </div>
    </div>
  </div>
</template>
