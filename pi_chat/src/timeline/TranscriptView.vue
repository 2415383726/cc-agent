<script setup lang="ts">
import { computed } from 'vue'
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
import { groupTimeline, groupTitle } from './grouping'
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

/* 连续 tool/skill/compaction 折入可折叠组（票据 04）；分组与组头标题拼装是纯函数。 */
const segments = computed(() => groupTimeline(props.entries, props.running === true))
const groupActivity = (segment: Extract<typeof segments.value[number], { kind: 'tool-group' }>): string =>
  segment.running ? segment.counts[0]?.kind ?? 'tools' : segment.counts[0]?.kind ?? 'thinking'

const firstEntryTs = computed(() => props.entries[0]?.ts)

/* 输出文件链接（P3-3）：绑定前校验协议（http/https/相对引用），拒绝的退化为纯文本。 */
const outputLinks = computed(() =>
  (props.outputs ?? []).map((file) => ({ file, href: safeOutputHref(file.url) })),
)
</script>

<template>
  <ol class="pi-timeline" aria-label="会话记录">
    <template v-for="segment in segments" :key="segment.kind === 'tool-group' ? segment.id : `${segment.entry.kind}:${segment.entry.id}`">
      <li v-if="segment.kind === 'single'">
        <UserMessage v-if="isUser(segment.entry)" :entry="segment.entry as MessageEntry" />

        <AssistantMessage v-else-if="isAssistant(segment.entry)" :entry="segment.entry as MessageEntry" />

        <ReasoningRow v-else-if="segment.entry.kind === 'reasoning'" :entry="segment.entry as ReasoningEntry" />

        <TerminalRow
          v-else-if="segment.entry.kind === 'terminal'"
          :entry="segment.entry as TerminalEntry"
          :start-ts="firstEntryTs"
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
