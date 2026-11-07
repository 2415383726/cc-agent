<script setup lang="ts">
import { computed, reactive } from 'vue'
import AssistantMessage from './AssistantMessage.vue'
import CompactionRow from './CompactionRow.vue'
import NoteRow from './NoteRow.vue'
import ReasoningRow from './ReasoningRow.vue'
import SkillRow from './SkillRow.vue'
import TerminalRow from './TerminalRow.vue'
import ToolCard from './ToolCard.vue'
import ToolGroupRow from './ToolGroupRow.vue'
import UserMessage from './UserMessage.vue'
import QuestionCard from '../cards/QuestionCard.vue'
import ApprovalCard from '../cards/ApprovalCard.vue'
import { groupTimeline, groupTitle, turnViews, type TurnView } from './grouping'
import { safeOutputHref } from './links'
import type {
  ApprovalEntry,
  FileRef,
  MessageEntry,
  NoteEntry,
  QuestionEntry,
  ReasoningEntry,
  TerminalEntry,
  WorkbenchEntry,
} from '../projection/transcript'

/*
 * 共享时间线渲染器（ADR-0010「回放必须用同一契约与组件，不做第二个渲染器」）：
 * 回放分支与实时分支都渲染本组件。纯展示——只接收投影视图模型
 * （entries/running/outputs）与交互回调 props，不持有任何控制器：
 * 回放传 ReplayController 的本地闭环回调，实时传 DifyController 的
 * inputs.interaction 通道（问卷作答/审批授权从此在 live 模式可交互）。
 *
 * 回合折叠（对齐 DeepSeek Harness 完成态行为）：回合闭合后过程行
 * （思考/工具组）默认折叠进「已完成，用时 X 秒」头，文本原位可见；
 * 头部点击展开还原原始穿插顺序；进行中/等待交互的回合不折叠。
 */
const props = defineProps<{
  entries: WorkbenchEntry[]
  running?: boolean
  outputs?: FileRef[]
  onQuestionSubmit?: (entry: QuestionEntry, answers: Record<string, string | string[]>) => void
  onQuestionCancel?: (entry: QuestionEntry) => void
  onApprovalSubmit?: (entry: ApprovalEntry, decision: 'approve' | 'reject', scope: 'once' | 'session') => void
}>()

const isUser = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'message' && (entry as MessageEntry).role === 'user'
const isAssistant = (entry: WorkbenchEntry): boolean =>
  entry.kind === 'message' && (entry as MessageEntry).role === 'assistant'

const turns = computed(() => turnViews(props.entries, props.running === true))

/* 折叠态：默认收起；用户展开的回合记录在案（回合 id → 是否展开）。 */
const expandedTurns = reactive(new Set<string>())
const isExpanded = (turn: TurnView): boolean => expandedTurns.has(turn.id)
const toggleFold = (turn: TurnView): void => {
  if (expandedTurns.has(turn.id)) expandedTurns.delete(turn.id)
  else expandedTurns.add(turn.id)
}

/* 折叠时隐藏过程段（思考/工具组）；文本/卡片/备注/非提升终态保持原位。 */
const visibleSegments = (turn: TurnView) =>
  !turn.closed || isExpanded(turn)
    ? turn.segments
    : turn.segments.filter((segment) => {
        if (segment.kind === 'tool-group') return false
        return !(segment.kind === 'single' && segment.entry.kind === 'reasoning')
      })

/* 连续 tool/skill/compaction 折入可折叠组（票据 04）；分组与组头标题拼装是纯函数。 */
const groupActivity = (segment: { kind: 'tool-group'; running: boolean; counts: { kind: string }[] }): string =>
  segment.running ? segment.counts[0]?.kind ?? 'tools' : segment.counts[0]?.kind ?? 'thinking'

/* 输出文件链接（P3-3）：绑定前校验协议（http/https/相对引用），拒绝的退化为纯文本。 */
const outputLinks = computed(() =>
  (props.outputs ?? []).map((file) => ({ file, href: safeOutputHref(file.url) })),
)
</script>

<template>
  <ol class="pi-timeline" aria-label="会话记录">
    <template v-for="turn in turns" :key="turn.id">
      <!-- 回合开头的用户消息（折叠头之前，始终可见） -->
      <template v-for="segment in turn.lead" :key="`lead:${segment.entry.kind}:${segment.entry.id}`">
        <li>
          <UserMessage :entry="segment.entry as MessageEntry" />
        </li>
      </template>

      <!-- 闭合回合：终态头渲染在用户消息之后，点击折叠/展开过程行 -->
      <li v-if="turn.header">
        <TerminalRow
          :entry="turn.header"
          :start-ts="turn.startTs"
          collapsible
          :expanded="isExpanded(turn)"
          @toggle="toggleFold(turn)"
        />
      </li>

      <template v-for="segment in visibleSegments(turn)" :key="segment.kind === 'tool-group' ? segment.id : `${segment.entry.kind}:${segment.entry.id}`">
        <li v-if="segment.kind === 'single'">
          <UserMessage v-if="isUser(segment.entry)" :entry="segment.entry as MessageEntry" />

          <AssistantMessage v-else-if="isAssistant(segment.entry)" :entry="segment.entry as MessageEntry" />

          <ReasoningRow v-else-if="segment.entry.kind === 'reasoning'" :entry="segment.entry as ReasoningEntry" />

          <!-- 未提升的终态（等待交互/同回合更早终态）：平铺渲染，不可折叠 -->
          <TerminalRow
            v-else-if="segment.entry.kind === 'terminal'"
            :entry="segment.entry as TerminalEntry"
            :start-ts="turn.startTs"
          />

          <NoteRow v-else-if="segment.entry.kind === 'note'" :entry="segment.entry as NoteEntry" />

          <!-- 问卷卡（票据 05）：作答/跳过/取消经回调交回所属控制器。 -->
          <QuestionCard
            v-else-if="segment.entry.kind === 'question'"
            :entry="segment.entry as QuestionEntry"
            @submit="(answers) => onQuestionSubmit?.(segment.entry as QuestionEntry, answers)"
            @cancel="onQuestionCancel?.(segment.entry as QuestionEntry)"
          />

          <!-- 审批卡（票据 06）：批准/拒绝（含 scope）经回调交回所属控制器。 -->
          <ApprovalCard
            v-else-if="segment.entry.kind === 'approval'"
            :entry="segment.entry as ApprovalEntry"
            @submit="(decision, scope) => onApprovalSubmit?.(segment.entry as ApprovalEntry, decision, scope)"
          />

          <template v-else>
            <strong>{{ segment.entry.kind }}</strong>
          </template>
        </li>

        <!-- 工具活动组（票据 04）：连续 tool/skill/compaction 折入同一折叠组。 -->
        <li v-else>
          <ToolGroupRow
            :label="groupTitle(segment.counts, segment.running)"
            :activity="groupActivity(segment)"
            :running="segment.running"
          >
            <template v-for="member in segment.entries" :key="`${member.kind}:${member.id}`">
              <ToolCard v-if="member.kind === 'tool'" :entry="member" />
              <SkillRow v-else-if="member.kind === 'skill'" :entry="member" />
              <CompactionRow v-else-if="member.kind === 'compaction'" :entry="member" />
            </template>
          </ToolGroupRow>
        </li>
      </template>
    </template>
  </ol>

  <ul v-if="outputLinks.length" aria-label="输出文件" class="pi-transcript-outputs">
    <li v-for="{ file, href } in outputLinks" :key="file.id || file.url || file.name">
      <a v-if="href" :href="href" target="_blank" rel="noopener">{{ file.name }}</a>
      <span v-else>{{ file.name }}</span>
    </li>
  </ul>
</template>

<style>
/* 组件自有（非 vendor）：时间线列表。上游 ChatView 的 flow 列（容器查询轴 +
   行间 16px）在本应用由该列表承担；宽度对齐 --dsh-chat-content-width，
   使 vendored 的 .md-table-wide 断行 CSS 在同一宽度轴上生效。 */
.pi-timeline {
  list-style: none;
  margin: 0 auto;
  padding: 24px 16px 16px;
  width: 100%;
  max-width: var(--dsh-chat-content-width, min(100% - 32px, 920px));
  container-type: inline-size;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pi-timeline > li {
  min-width: 0;
}

/* 组件自有（非 vendor）：输出文件列表（回放无输出时不渲染；链接经协议护栏）。 */
.pi-transcript-outputs {
  list-style: none;
  margin: 0 auto;
  padding: 0 16px 16px;
  width: 100%;
  max-width: var(--dsh-chat-content-width, min(100% - 32px, 920px));
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  line-height: 20px;
}

.pi-transcript-outputs a {
  color: var(--dsw-alias-link);
}
</style>
