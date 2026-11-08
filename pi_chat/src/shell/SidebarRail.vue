<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { WorkbenchController } from '../dify/controller'
import type { DifyConversation } from '../dify/transport'
import { relativeTimeLabel } from '../projection/relativeTime'
import { iconSvg, whaleTailSvg } from '../timeline/icons'
import css from '../vendor/dsh/ui-sidebar/src/client/SidebarRoot.module.css'
import rows from '../vendor/dsh/ui-workspace/src/client/rows/Rows.module.css'

/*
 * DOM 蓝图：ui-sidebar SidebarRoot.tsx 的展开态骨架（logoRow(toggle) →
 * newSession → scrollRegion/scrollArea）+ ui-workspace Rows.tsx 的
 * SessionNodeItem 行结构（slot/title/rowResting/time/rowActions，悬停互换由
 * CSS 完成）。票面裁剪项（品牌区、插件、自动化任务、工作区管理、搜索）不
 * 渲染；logoRow 仅承载折叠开关（panel-left 图标，无品牌徽标位）。
 * 折叠（平移上游 slide + crossfade 相位机）：折叠开始时宽内容冻结在
 * 280px（inline width）并整列淡出（.fading，150ms）；settle 后卸载宽内容、
 * 呈现 56px 导轨（.collapsed：36px 控件、主墨图标）；再展开时宽内容以
 * .wide 淡入。冷折叠渲染（无动画）不走 .railIn。
 */
const props = withDefaults(
  defineProps<{ controller?: WorkbenchController | null; collapsed?: boolean }>(),
  { collapsed: false },
)
const emit = defineEmits<{ toggle: [] }>()

/** 宽内容淡出卸载延时；对齐上游 COLLAPSE_SETTLE_MS 与 150ms 淡出。 */
const COLLAPSE_SETTLE_MS = 150
const SIDEBAR_WIDTH = 280

const conversations = computed(() => props.controller?.ui.conversations ?? [])
const activeId = computed(() => props.controller?.ui.conversationId ?? '')
const conversationsError = computed(() => props.controller?.ui.conversationsError ?? '')
const actionNote = computed(() => props.controller?.ui.actionNote ?? '')

/* ---- 折叠相位（上游 SidebarRoot settled/wide/animateRail 平移） ----
   冷折叠渲染（初始即 collapsed）：settled 直接为真、无 railIn 动画。 */
const settled = ref(props.collapsed)
let settleTimer: number | undefined
const animateRail = ref(!props.collapsed)

watch(
  () => props.collapsed,
  (collapsed) => {
    if (settleTimer !== undefined) window.clearTimeout(settleTimer)
    if (!collapsed) {
      settled.value = false
      animateRail.value = true
      return
    }
    settled.value = false
    settleTimer = window.setTimeout(() => {
      settled.value = true
      animateRail.value = false
    }, COLLAPSE_SETTLE_MS)
  },
)

onBeforeUnmount(() => {
  if (settleTimer !== undefined) window.clearTimeout(settleTimer)
  cancelLinger()
})

/* 宽 = 抽屉展开或折叠淡出未 settle（内容仍挂载、冻结宽度、整列淡出）。 */
const wide = computed(() => !props.collapsed || !settled.value)
const rootClass = computed(() => [
  css.root,
  !wide.value && css.collapsed,
  !wide.value && animateRail.value && css.railIn,
  props.collapsed && wide.value && css.fading,
  /* .quietBars 把滚动条 thumb 重绑为透明：指针不在列内时列表无滚动条，
     进入即现、离开后再驻留 SCROLLBAR_LINGER_MS 才隐（上游 SidebarRoot 同款）。 */
  !pointerInside.value && css.quietBars,
])
const toggleLabel = computed(() => (props.collapsed ? '展开侧栏' : '折叠侧栏'))

/* ---- 滚动条跟随指针（上游 SCROLLBAR_LINGER_MS 语义平移） ---- */
const SCROLLBAR_LINGER_MS = 2000
const pointerInside = ref(false)
let lingerTimer: number | undefined

function armLinger(): void {
  if (lingerTimer !== undefined) return
  lingerTimer = window.setTimeout(() => {
    lingerTimer = undefined
    pointerInside.value = false
  }, SCROLLBAR_LINGER_MS)
}

function cancelLinger(): void {
  if (lingerTimer !== undefined) {
    window.clearTimeout(lingerTimer)
    lingerTimer = undefined
  }
}

/* 相对时间的时钟：30s 步进让「4分钟」这类标签保持新鲜。 */
const now = ref(Date.now())
let clock: number | null = null
onMounted(() => {
  clock = window.setInterval(() => {
    now.value = Date.now()
  }, 30_000)
})
onBeforeUnmount(() => {
  if (clock !== null) window.clearInterval(clock)
})

function timeLabel(item: DifyConversation): string {
  return relativeTimeLabel(item.updatedAt, now.value)
}

function openConversation(item: DifyConversation): void {
  if (editingId.value === item.id || confirmingId.value === item.id) return
  void props.controller?.loadConversation(item.id)
}

/* 行内重命名：Enter/失焦提交（裁剪），Escape 取消；先清 editingId 防止二段提交。 */
const editingId = ref('')
const editingName = ref('')
/* v-for 作用域内的模板 ref 收集为数组（同时只会有一个输入框）。 */
const renameInput = ref<HTMLInputElement[] | null>(null)

async function startRename(item: DifyConversation): Promise<void> {
  confirmingId.value = ''
  editingId.value = item.id
  editingName.value = item.name
  await nextTick()
  const input = Array.isArray(renameInput.value) ? renameInput.value[0] : renameInput.value
  input?.focus()
  input?.select()
}

async function commitRename(): Promise<void> {
  const id = editingId.value
  if (!id) return
  const name = editingName.value.trim()
  const original = conversations.value.find((item) => item.id === id)?.name
  editingId.value = ''
  if (!name || name === original) return
  await props.controller?.renameConversation(id, name)
}

function cancelRename(): void {
  editingId.value = ''
}

/* 删除：行内确认条；确认后交给控制器（含当前会话的陈旧流丢弃）。 */
const confirmingId = ref('')

function askDelete(item: DifyConversation): void {
  editingId.value = ''
  confirmingId.value = item.id
}

async function confirmDelete(): Promise<void> {
  const id = confirmingId.value
  confirmingId.value = ''
  if (!id) return
  await props.controller?.deleteConversation(id)
}

function cancelDelete(): void {
  confirmingId.value = ''
}
</script>

<template>
  <div
    :class="rootClass"
    :style="wide ? { width: `${SIDEBAR_WIDTH}px` } : undefined"
    @pointerenter="cancelLinger(); pointerInside = true"
    @pointerleave="armLinger()"
  >
    <!-- logoRow：票面裁剪品牌区，仅承载折叠开关（展开态右缘、导轨态首位）。
         导轨态静止为鲸尾标（主墨、无悬停圆），悬停换出 panel 图标——展开
         供能提示（vendored .panelIcon/.railMark 互换 CSS 原样生效）。 -->
    <div :class="css.logoRow">
      <button
        type="button"
        :class="[css.iconButton, css.toggle]"
        data-testid="sidebar-toggle"
        :aria-label="toggleLabel"
        :title="toggleLabel"
        :aria-expanded="!collapsed"
        @click="emit('toggle')"
      >
        <span v-if="!wide" :class="css.railMark" aria-hidden="true" v-html="whaleTailSvg()" />
        <span :class="css.panelIcon" aria-hidden="true" v-html="iconSvg('panel-left', wide ? 16 : 18)" />
      </button>
    </div>

    <button
      type="button"
      :class="css.newSession"
      data-testid="new-conversation"
      :aria-label="'新会话'"
      :title="'新会话'"
      :disabled="!controller"
      @click="controller?.newConversation()"
    >
      <span :class="css.newSessionContent">
        <span aria-hidden="true" v-html="iconSvg(wide ? 'new-chat-medium' : 'new-chat', wide ? 14 : 18)" />
        <span v-if="wide" :class="[css.newSessionLabel, css.wide]">新会话</span>
      </span>
    </button>

    <div v-if="wide" :class="css.scrollRegion">
      <div :class="css.scrollArea" aria-label="会话列表">
        <div v-if="!controller" class="pi-list-status" data-testid="replay-notice">
          回放模式：连接 Dify 后展示会话历史。
        </div>
        <template v-else>
          <div
            v-if="conversationsError"
            class="pi-list-status"
            role="alert"
            data-testid="conversations-error"
          >
            <span>会话列表加载失败</span>
            <span class="pi-list-error">{{ conversationsError }}</span>
            <button
              type="button"
              class="pi-list-retry"
              data-testid="conversations-retry"
              @click="controller?.refreshConversations()"
            >
              重试
            </button>
          </div>
          <p v-else-if="!conversations.length" class="pi-list-status">暂无历史会话</p>
          <div
            v-else
            :class="['pi-session-list', rows.list, rows.flatList]"
            data-testid="conversation-list"
          >
            <div
              v-for="item in conversations"
              :key="item.id"
              :class="[rows.sessionRow, item.id === activeId && rows.selected]"
              role="treeitem"
              :aria-selected="item.id === activeId"
              tabindex="0"
              data-testid="conversation-item"
              @click="openConversation(item)"
              @keydown.enter.prevent="openConversation(item)"
              @keydown.space.prevent="openConversation(item)"
            >
              <input
                v-if="editingId === item.id"
                ref="renameInput"
                v-model="editingName"
                :class="rows.renameInput"
                data-testid="rename-input"
                aria-label="会话名称"
                @click.stop
                @keydown.enter.prevent="commitRename"
                @keydown.esc.prevent="cancelRename"
                @blur="commitRename"
              />
              <span
                v-else
                :class="rows.title"
                @dblclick.stop="startRename(item)"
              >{{ item.name }}</span>
              <span
                v-if="confirmingId !== item.id"
                :class="rows.rowResting"
              >
                <span :class="[rows.time, rows.timestamp]">{{ timeLabel(item) }}</span>
              </span>
              <span :class="rows.rowActions" @click.stop @dblclick.stop>
                <template v-if="confirmingId === item.id">
                  <span class="pi-confirm-text" data-testid="confirm-delete">删除该会话？</span>
                  <button
                    type="button"
                    class="pi-confirm-yes"
                    data-testid="confirm-delete-yes"
                    @click="confirmDelete"
                  >
                    删除
                  </button>
                  <button
                    type="button"
                    class="pi-confirm-no"
                    data-testid="confirm-delete-no"
                    @click="cancelDelete"
                  >
                    取消
                  </button>
                </template>
                <template v-else>
                  <button
                    type="button"
                    :class="rows.iconButton"
                    data-testid="rename-button"
                    aria-label="重命名会话"
                    title="重命名"
                    @click="startRename(item)"
                  >
                    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
                      <path
                        d="M11.3 1.7a1.7 1.7 0 0 1 2.4 2.4l-8.2 8.2-3 1 1-3 8.2-8.2z"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.2"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    :class="rows.iconButton"
                    data-testid="delete-button"
                    aria-label="删除会话"
                    title="删除"
                    @click="askDelete(item)"
                  >
                    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
                      <path
                        d="M2.5 4h11M6.5 4V2.8c0-.4.3-.8.8-.8h1.4c.5 0 .8.4.8.8V4M4 4l.6 9a1 1 0 0 0 1 .9h4.8a1 1 0 0 0 1-.9L12 4M6.5 7v4.5M9.5 7v4.5"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.2"
                        stroke-linecap="round"
                      />
                    </svg>
                  </button>
                </template>
              </span>
            </div>
          </div>
          <p
            v-if="actionNote"
            class="pi-action-note"
            role="alert"
            data-testid="action-note"
          >
            {{ actionNote }}
          </p>
        </template>
      </div>
      <!-- 列表底部渐隐（vendored .scrollFade；collapsed 态由 CSS 隐藏）。 -->
      <span :class="css.scrollFade" aria-hidden="true" />
    </div>
  </div>
</template>

<style>
/* 组件自有（非 vendor）：列表状态行（回放提示/空态/加载失败重试）与操作兜底
   提示，令牌着色；几何对齐 ui-workspace 的 searchStatus（10px 12px 12px 字）。 */
.pi-list-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  grid-column: 2;
  grid-row: 2;
  margin-top: 8px;
  padding: 10px 12px;
  color: var(--dsw-alias-label-tertiary);
  font-size: 12px;
  line-height: 18px;
}

.pi-list-error {
  overflow-wrap: anywhere;
  color: var(--dsw-alias-state-error-primary);
}

.pi-list-retry {
  flex: none;
  height: 24px;
  padding: 0 10px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-sm);
  background: transparent;
  color: var(--dsw-alias-label-secondary);
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
}

@media (hover: hover) {
  .pi-list-retry:hover {
    background: var(--dsw-alias-interactive-bg-hover);
    color: var(--dsw-alias-label-primary);
  }
}

/* 会话列表在 .scrollArea 的 grid 中占位（列 2 / 行 2），行间 2px 节奏对齐
   ui-workspace 的 .flatList；底部 16px 清出 shell 的渐隐遮罩。 */
.pi-session-list {
  grid-column: 2;
  grid-row: 2;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.pi-action-note {
  grid-column: 2;
  grid-row: 4;
  margin: 8px 0 0;
  padding: 10px 12px;
  color: var(--dsw-alias-state-error-primary);
  font-size: 12px;
  line-height: 18px;
  overflow-wrap: anywhere;
}

/* 行内删除确认条：替换悬停操作按钮的位置。 */
.pi-confirm-text {
  font-size: 12px;
  line-height: 20px;
  color: var(--dsw-alias-label-secondary);
  white-space: nowrap;
}

.pi-confirm-yes,
.pi-confirm-no {
  flex: none;
  height: 24px;
  padding: 0 10px;
  border: none;
  border-radius: var(--dsw-radius-sm);
  background: transparent;
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
  color: var(--dsw-alias-label-secondary);
}

.pi-confirm-yes {
  color: var(--dsw-alias-state-error-primary);
}

@media (hover: hover) {
  .pi-confirm-yes:hover,
  .pi-confirm-no:hover {
    background: var(--dsw-alias-interactive-bg-hover);
  }
}
</style>
