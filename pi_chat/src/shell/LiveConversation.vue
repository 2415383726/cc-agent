<script setup lang="ts">
import { computed } from 'vue'
import type { WorkbenchController } from '../dify/controller'
import { errorText, formatFileSize, statusText, toolStatusText } from '../projection/labels'
import type {
  ApprovalEntry,
  CompactionEntry,
  MessageEntry,
  NoteEntry,
  QuestionEntry,
  ReasoningEntry,
  SkillEntry,
  TerminalEntry,
  ToolEntry,
  WorkbenchEntry,
} from '../projection/transcript'

/*
 * 实时会话视图（票 07）：占位级时间线渲染（问卷/审批卡属于票 05/06，时间线
 * 重样式属于票 03）。本组件只承担接线可见性：错误、警告、「更早」分页按钮、
 * 恢复的待交互占位与终态，保证会话切换/历史恢复在实时模式下可用。
 */
const props = defineProps<{ controller: WorkbenchController }>()

const view = computed(() => props.controller.view)
const ui = computed(() => props.controller.ui)

function entryLabel(entry: WorkbenchEntry): string {
  switch (entry.kind) {
    case 'message':
      return (entry as MessageEntry).role === 'user' ? '用户' : '助手'
    case 'reasoning':
      return '思考'
    case 'tool':
      return '工具'
    case 'skill':
      return '技能'
    case 'compaction':
      return '上下文压缩'
    case 'question':
      return '问卷'
    case 'approval':
      return '审批'
    case 'terminal':
      return '终态'
    case 'note':
      return '备注'
    default:
      return entry.kind
  }
}

function questionText(entry: QuestionEntry): string {
  const lines = [entry.questionnaire.title || '问卷', statusText(entry.status)]
  for (const question of entry.questionnaire.questions || []) {
    lines.push(`- ${question.question}`)
  }
  return lines.join('\n')
}

function approvalText(entry: ApprovalEntry): string {
  return `${entry.tool} · ${statusText(entry.status)}`
}

function terminalText(entry: TerminalEntry): string {
  const terminal = entry.terminal
  const lines = [statusText(terminal.status)]
  if (terminal.answer) lines.push(terminal.answer)
  if (terminal.error?.message) lines.push(errorText(terminal.error.code, terminal.error.message))
  return lines.join('\n')
}

function compactionText(entry: CompactionEntry): string {
  const parts: string[] = []
  if (typeof entry.tokensBefore === 'number') parts.push(`压缩前 ${entry.tokensBefore} tokens`)
  if (typeof entry.summaryChars === 'number') parts.push(`摘要 ${entry.summaryChars} 字符`)
  return parts.join(' · ') || (entry.phase === 'start' ? '开始压缩' : '压缩完成')
}

function resultText(entry: ToolEntry): string {
  const parts: string[] = []
  if (entry.updates.length) parts.push(entry.updates.join('\n'))
  if (entry.result) parts.push(entry.result)
  return parts.join('\n')
}

function skillText(entry: SkillEntry): string {
  if (entry.action === 'read') {
    return `${entry.skill} · 读取 ${entry.path || ''}`
  }
  return `${entry.skill} · 已激活`
}

function bodyText(entry: WorkbenchEntry): string {
  switch (entry.kind) {
    case 'message':
      return (entry as MessageEntry).text
    case 'reasoning':
      return (entry as ReasoningEntry).text
    case 'skill':
      return skillText(entry as SkillEntry)
    case 'compaction':
      return compactionText(entry as CompactionEntry)
    case 'question':
      return questionText(entry as QuestionEntry)
    case 'approval':
      return approvalText(entry as ApprovalEntry)
    case 'terminal':
      return terminalText(entry as TerminalEntry)
    case 'note':
      return (entry as NoteEntry).text
    default:
      return ''
  }
}
</script>

<template>
  <div class="pi-live">
    <p v-if="ui.error" role="alert" class="pi-live-error">{{ ui.error }}</p>
    <p v-if="ui.stoppedNote" role="status" class="pi-live-error" data-testid="stopped-note">{{ ui.stoppedNote }}</p>
    <ul v-if="view.warnings.length" aria-label="警告" class="pi-live-warnings">
      <li v-for="warning in view.warnings" :key="warning">{{ warning }}</li>
    </ul>

    <button
      v-if="ui.hasMore"
      type="button"
      class="pi-live-earlier"
      data-testid="load-earlier"
      :disabled="ui.loadingHistory"
      @click="controller.loadMore()"
    >
      {{ ui.loadingHistory ? '加载中…' : '更早' }}
    </button>

    <p v-if="!view.entries.length">暂无消息；在下方输入开启对话，或从侧栏选择历史会话。</p>
    <ol v-else aria-label="会话记录" class="pi-live-list">
      <li v-for="entry in view.entries" :key="`${entry.kind}:${entry.id}`">
        <strong>{{ entryLabel(entry) }}<template v-if="entry.kind === 'tool'"> · {{ (entry as ToolEntry).name }}</template></strong>
        <!-- 附件安全元数据（票 08）：只展示名称/类型/大小，不提供内容访问。 -->
        <div
          v-if="entry.kind === 'message' && (entry as MessageEntry).files?.length"
          class="pi-live-files"
        >
          <span
            v-for="file in (entry as MessageEntry).files"
            :key="file.id || file.name"
            class="pi-live-file"
            data-testid="message-file-chip"
          >
            {{ file.name || file.id }} · {{ file.mimeType || file.type || '文件' }} · {{ formatFileSize(file.size) }}
          </span>
        </div>
        <pre v-if="entry.kind === 'tool'">{{ JSON.stringify((entry as ToolEntry).args) }}</pre>
        <span v-if="entry.kind === 'tool'">{{ toolStatusText((entry as ToolEntry).status) }}</span>
        <p>{{ bodyText(entry) }}</p>
      </li>
    </ol>

    <ul v-if="view.outputs.length" aria-label="输出文件" class="pi-live-outputs">
      <li v-for="file in view.outputs" :key="file.id">
        <a v-if="file.url" :href="file.url" target="_blank" rel="noopener">{{ file.name }}</a>
        <span v-else>{{ file.name }}</span>
      </li>
    </ul>
  </div>
</template>

<style>
/* 组件自有（非 vendor）：实时占位时间线的最小排版（票 03 会重做时间线样式）。 */
.pi-live {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.pi-live-error {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--dsw-radius-md);
  background: var(--dsw-alias-interactive-bg-hover);
  color: var(--dsw-alias-state-error-primary);
  font-size: 13px;
  line-height: 20px;
}

.pi-live-warnings {
  margin: 0;
  padding-left: 18px;
  color: var(--dsw-alias-label-secondary);
  font-size: 13px;
  line-height: 20px;
}

.pi-live-earlier {
  align-self: flex-start;
  height: 28px;
  padding: 0 14px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-sm);
  background: transparent;
  color: var(--dsw-alias-label-secondary);
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
}

.pi-live-earlier:disabled {
  cursor: default;
  color: var(--dsw-alias-label-caption);
}

@media (hover: hover) {
  .pi-live-earlier:hover:not(:disabled) {
    background: var(--dsw-alias-interactive-bg-hover);
    color: var(--dsw-alias-label-primary);
  }
}

.pi-live-list {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 14px;
  line-height: 22px;
  color: var(--dsw-alias-label-primary);
}

/* 组件自有（非 vendor）：消息附件安全元数据 chips（名称/类型/大小）。 */
.pi-live-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.pi-live-file {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-sm);
  background: var(--dsw-alias-interactive-bg-hover);
  color: var(--dsw-alias-label-secondary);
  font-size: 12px;
  line-height: 18px;
  overflow-wrap: anywhere;
}

.pi-live-list p {
  margin: 2px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.pi-live-list pre {
  margin: 2px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: var(--ds-font-family-code, monospace);
  font-size: 12px;
  color: var(--dsw-alias-label-secondary);
}

.pi-live-outputs {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 20px;
}

.pi-live-outputs a {
  color: var(--dsw-alias-link);
}
</style>
