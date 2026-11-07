<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CardFrame from './CardFrame.vue'
import DshButton from './DshButton.vue'
import DshSegmented, { type SegmentedOption } from './DshSegmented.vue'
import DshStateDot from './DshStateDot.vue'
import composerCss from '../vendor/dsh/ui-user-questions/src/client/QuestionComposer.module.css'
import reviewCss from '../vendor/dsh/ui-user-questions/src/client/PlanReviewPanel.module.css'
import toolCss from '../vendor/dsh/ui-tool/src/client/tool/components/ToolRow.module.css'
import { APPROVAL_STRINGS, approvalString } from './approvalStrings'
import { classifyTool, formatToolBody } from '../timeline/toolModel'
import { statusText } from '../projection/labels'
import type { ApprovalEntry } from '../projection/transcript'

/*
 * 审批卡（票据 06 主目标）：与问卷同卡片体系（CardFrame + QuestionComposer
 * module.css 卡面），但语义严格分离——这是工具授权，不是问卷作答。DOM 蓝图：
 * 上游 ui-user-questions PlanReviewPanel.tsx（MIT，计划评审/审批接管面）的
 * warn strip（状态点 + 阻断提示）+ summary（标题/说明）+ footer（反馈 + 动作），
 * 类名零改动引用逐字 vendor 的 PlanReviewPanel.module.css；参数载荷块借用
 * ui-tool ToolRow 的 IN/OUT ioCard（时间线同族）；授权范围用 ui-primitives
 * SegmentedControl 的 Vue 重写（DshSegmented）。
 *
 * 语义边界（票据 DoD）：
 * - 审批是独立于问卷的待交互类型：阻断优先（waiting 时 warn strip 常驻），
 *   提交中全卡禁用；
 * - 决定只有批准/拒绝两条路，走 controller.submitApproval 的
 *   inputs.interaction 协议（回放本地闭环）；卡面没有第三条关闭/放弃通道
 *   （CardFrame closable=false）——误触关闭不能代替一次明确决定；
 * - 决策后只读回显：rejected/cancelled 是「未执行」非执行态；
 * - 保存态恢复的 waiting 卡直接可操作：恢复 ≠ 授权，授权只来自本卡按钮。
 */
const props = defineProps<{ entry: ApprovalEntry }>()

const emit = defineEmits<{
  submit: [decision: 'approve' | 'reject', scope: 'once' | 'session']
}>()

const waiting = computed(() => props.entry.status === 'waiting')
const busy = computed(() => props.entry.submitting === true)

/* 授权范围候选来自 approval.requested 的 scope_options（保存态恢复同款）；
   缺失或为空回退为 once + session 两项。 */
const SCOPE_VALUES = ['once', 'session'] as const
const scopeOptions = computed<SegmentedOption<'once' | 'session'>[]>(() => {
  const listed = (props.entry.scopeOptions ?? []).filter((value): value is 'once' | 'session' =>
    (SCOPE_VALUES as readonly string[]).includes(value),
  )
  return (listed.length ? listed : [...SCOPE_VALUES]).map((value) => ({
    value,
    label: value === 'once' ? APPROVAL_STRINGS.scopeOnce : APPROVAL_STRINGS.scopeSession,
  }))
})

const scope = ref<'once' | 'session'>('once')
/* 候选变化时若当前选中不在候选内（如保存态只给 session），回落到首个候选；
   默认 once（票据 DoD）。 */
watch(
  scopeOptions,
  (options) => {
    if (!options.some((option) => option.value === scope.value)) scope.value = options[0]!.value
  },
  { immediate: true },
)

/* 参数格式化沿用 timeline/toolModel 的展开体（对象 → 2 空格缩进 JSON），
   与工具卡展开的参数视图一致。 */
const argumentsText = computed(() => formatToolBody(classifyTool(props.entry.tool), props.entry.arguments))

const scopeEcho = computed(() =>
  props.entry.scope === 'session' ? APPROVAL_STRINGS.echoScopeSession : APPROVAL_STRINGS.echoScopeOnce,
)

/* 决策后只读回显文案与状态点：rejected/cancelled 都是「未执行」非执行态。 */
const echoText = computed(() => {
  switch (props.entry.status) {
    case 'approved':
      return approvalString('echoApproved', { scope: scopeEcho.value })
    case 'rejected':
      return APPROVAL_STRINGS.echoRejected
    case 'cancelled':
      return APPROVAL_STRINGS.echoCancelled
    default:
      return ''
  }
})
const echoState = computed<'done' | 'error' | 'idle'>(() => {
  switch (props.entry.status) {
    case 'approved':
      return 'done'
    case 'rejected':
      return 'error'
    default:
      return 'idle'
  }
})

function decide(decision: 'approve' | 'reject'): void {
  if (!waiting.value || busy.value) return
  emit('submit', decision, scope.value)
}
</script>

<template>
  <CardFrame
    :eyebrow="APPROVAL_STRINGS.eyebrow"
    :title="entry.tool"
    :labelledby="`approval-${entry.pendingId}`"
    :busy="busy"
    :closable="false"
    data-testid="approval-card"
  >
    <template #header-extra>
      <!-- 等待审批用 awaiting_approval 的词汇表（与工具卡「等待审批」徽标同源）。 -->
      <span v-if="waiting" :class="composerCss.waitStatus" data-testid="approval-wait">{{ statusText('awaiting_approval') }}</span>
      <span v-else :class="composerCss.waitStatus" data-testid="approval-review-status">{{ statusText(entry.status) }}</span>
    </template>

    <div :class="composerCss.body">
      <!-- 阻断提示行（票据 06）：审批等待中运行被阻断，warn 常驻醒目；提交中转 ongoing。 -->
      <div v-if="waiting" :class="reviewCss.strip" data-testid="approval-blocked">
        <DshStateDot :state="busy ? 'ongoing' : 'warning'" />
        {{ APPROVAL_STRINGS.blocked }}
      </div>

      <!-- 授权语义块（PlanReviewPanel summary 蓝图）：标题指向工具，说明钉死语义边界。 -->
      <div :class="reviewCss.summary">
        <h2 :id="`approval-${entry.pendingId}`" :class="reviewCss.title">{{ approvalString('title', { tool: entry.tool }) }}</h2>
        <p :class="reviewCss.description">{{ APPROVAL_STRINGS.authorization }}</p>
      </div>

      <div :class="[toolCss.ioCard, 'pi-approval-args']">
        <div :class="toolCss.ioSection">
          <span :class="toolCss.ioLabel">{{ APPROVAL_STRINGS.argsLabel }}</span>
          <span :class="toolCss.ioText" data-testid="approval-args">{{ argumentsText }}</span>
        </div>
      </div>

      <!-- 静默元信息行：来源与调用 ID（旧卡 dl 元数据基线的紧凑化）。 -->
      <p :class="'pi-approval-row'">
        <span>{{ APPROVAL_STRINGS.sourceLabel }} {{ entry.source || 'Dify' }}</span>
        <span>{{ APPROVAL_STRINGS.callLabel }} {{ entry.toolCallId }}</span>
      </p>

      <!-- 授权范围（waiting 专属）：SegmentedControl 重写，radio 语义见 DshSegmented 注释。 -->
      <div v-if="waiting" :class="'pi-approval-scope'">
        <span :class="composerCss.eyebrow">{{ APPROVAL_STRINGS.scopeLabel }}</span>
        <DshSegmented
          :value="scope"
          :options="scopeOptions"
          :label="APPROVAL_STRINGS.scopeLabel"
          :disabled="busy"
          test-id-prefix="approval-scope"
          @change="(next) => (scope = next as 'once' | 'session')"
        />
        <p :class="'pi-approval-hint'">{{ APPROVAL_STRINGS.scopeHint }}</p>
      </div>
    </div>

    <template #footer>
      <footer :class="composerCss.footer">
        <!-- 提交失败反馈（旧卡 error 位）；决策后该位换成只读回显行。 -->
        <div v-if="waiting" :class="composerCss.feedback" role="alert" data-testid="approval-feedback">{{ entry.error || '' }}</div>
        <p v-else :class="'pi-approval-echo'" data-testid="approval-echo">
          <DshStateDot :state="echoState" />
          {{ echoText }}
        </p>
        <div v-if="waiting" :class="composerCss.footerActions">
          <!-- 拒绝为次要视觉（outline），批准为主（primary）。 -->
          <DshButton variant="outline" :disabled="busy" data-testid="approval-reject" @click="decide('reject')">
            {{ APPROVAL_STRINGS.reject }}
          </DshButton>
          <DshButton variant="primary" :disabled="busy" data-testid="approval-approve" @click="decide('approve')">
            {{ busy ? APPROVAL_STRINGS.submitting : APPROVAL_STRINGS.approve }}
          </DshButton>
        </div>
      </footer>
    </template>
  </CardFrame>
</template>

<style>
/* 组件自有（非 vendor）：审批卡体各区的外距与静默行。侧距对齐上游
   PlanReviewPanel .summary 的 16px（同一卡族）；载荷块借用 ui-tool ioCard，
   外距归本层。 */
.pi-approval-args {
  margin: 12px 16px 0;
}

.pi-approval-row {
  display: flex;
  gap: 16px;
  margin: 8px 16px 0;
  color: var(--dsw-alias-label-tertiary);
  font-size: 12px;
  line-height: 18px;
}

.pi-approval-scope {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  margin: 12px 16px 4px;
}

.pi-approval-hint {
  margin: 0;
  color: var(--dsw-alias-label-tertiary);
  font-size: 12px;
  line-height: 18px;
}

/* 决策后只读回显行：状态点 + 明确文案（footer 的 feedback 位换场）。 */
.pi-approval-echo {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--dsw-alias-label-secondary);
  font-size: 14px;
  line-height: 24px;
}
</style>
