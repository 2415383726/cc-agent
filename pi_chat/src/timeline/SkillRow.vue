<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { SkillEntry } from '../projection/transcript'
import { SKILL_STRINGS } from './strings'
import { iconSvg } from './icons'
import css from '../vendor/dsh/ui-skill/src/client/SkillRow.module.css'

/*
 * 加载技能行。DOM 蓝图：ui-skill SkillRow.tsx（MIT）的 StartedSkillRow 形态，
 * 类名零改动引用 vendored SkillRow.module.css。折叠行 = skill glyph + 加载技能
 * · 技能名；展开为说明卡（instructionsCard：说明头 + 内容）。
 * 偏离：上游说明卡展示技能指令文本（工具结果）；本契约的 skill.activate/read
 * 事件不携带指令正文（指令进入模型上下文，不经 display 通道），展开体呈现
 * 投影保留的元数据（来源/激活方/资料路径/字符数）。open 态 chevron 朝下为上游
 * 原样行为（与 DisclosureRow 的朝上不同），逐字保留。
 */
const props = defineProps<{ entry: SkillEntry }>()

const expanded = ref(false)
// 切换场景重建条目时收起新的行。
watch(
  () => props.entry.id,
  () => {
    expanded.value = false
  },
)

/** 展开体（元数据行，空行过滤）。上游 expandable = output !== null 的对应物。 */
const detailsText = computed(() => {
  const lines: string[] = []
  if (props.entry.action === 'activate') {
    if (props.entry.source) lines.push(`来源 ${props.entry.source}`)
    if (props.entry.activatedBy) lines.push(`激活 ${props.entry.activatedBy}`)
  } else {
    if (props.entry.path) lines.push(props.entry.path)
    if (typeof props.entry.offset === 'number') lines.push(`起始 ${props.entry.offset}`)
    if (typeof props.entry.totalChars === 'number') lines.push(`共 ${props.entry.totalChars} 字符`)
    if (props.entry.nextOffset !== undefined && props.entry.nextOffset !== null) {
      lines.push(`续读 ${props.entry.nextOffset}`)
    }
  }
  return lines.join('\n')
})

const expandable = computed(() => detailsText.value !== '')
const open = computed(() => expanded.value && expandable.value)

/** 折叠摘要：技能名；读取条目追加资料路径以区分激活/读取两行。 */
const summaryText = computed(() =>
  props.entry.action === 'read' && props.entry.path
    ? `${props.entry.skill} · ${props.entry.path}`
    : props.entry.skill,
)

const skillIcon = iconSvg('skill')
const chevronDown = iconSvg('chevron-down')

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
  <div :class="css.card" data-tool="skill" data-state="ok">
    <div
      :class="css.row"
      :data-expandable="expandable ? '' : undefined"
      :role="expandable ? 'button' : undefined"
      :tabindex="expandable ? 0 : undefined"
      :aria-expanded="expandable ? open : undefined"
      data-testid="skill-toggle"
      @click="onToggle"
      @keydown="onKeydown"
    >
      <span :class="css.leading">
        <template v-if="!open">
          <span :class="css.iconIdle" v-html="skillIcon" />
          <span :class="css.chevronHover" v-html="chevronDown" />
        </template>
        <template v-else>
          <span :class="css.chevron" v-html="chevronDown" />
        </template>
      </span>
      <span :class="css.title">{{ SKILL_STRINGS.title }}</span>
      <span :class="css.separator" data-shimmer-decoration aria-hidden="true" />
      <span :class="css.summary" data-testid="skill-summary">{{ summaryText }}</span>
    </div>
    <div v-if="open" :class="css.bodyWrap" data-testid="skill-body">
      <section :class="css.instructionsCard" :aria-label="SKILL_STRINGS.instructions">
        <div :class="css.instructionsHeader">{{ SKILL_STRINGS.instructions }}</div>
        <pre :class="css.instructions">{{ detailsText }}</pre>
      </section>
    </div>
  </div>
</template>
