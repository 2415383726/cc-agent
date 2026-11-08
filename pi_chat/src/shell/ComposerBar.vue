<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { FileRef } from '../projection/transcript'
import { formatFileSize } from '../projection/labels'
import css from '../vendor/dsh/ui-conversation/src/client/skeleton/InputBar.module.css'

/*
 * DOM 蓝图：ui-conversation skeleton/InputBar.tsx 的 .root > .card
 * （data-composer-card）> .scroll（data-input-scroll）> .grow > 文本面 +
 * .placeholder（data-composer-placeholder），随后 .row > .tools/.trailing。
 * Lexical 属取材黑名单：文本面用原生 <textarea> 承接同一组 .input 类；
 * textarea 特有判定（block、去边框、去 resize）在组件自有 .pi-composer-textarea。
 *
 * 交互（票 08，语义对齐 pi_workbench WorkbenchComposer 的平移）：
 * - Enter 发送（IME 组词期不发送，Shift+Enter 换行）；发送后清空草稿与附件。
 * - 附件：「+」激活真实文件选择 → upload prop（controller.upload → local_file
 *   传输）→ 待发送 chips 只展示安全元数据（名称/类型/大小），可移除；上传中
 *   禁止再次选择与发送；失败由控制器写 actionNote，chip 不加入。
 * - busy：发送路径禁用且发送按钮被停止按钮替换（stopping 时禁用显示「停止中…」）；
 *   停止按钮只在运行/停止中（stoppable）渲染。
 */
const props = withDefaults(
  defineProps<{
    interactive?: boolean
    busy?: boolean
    /** 运行或停止请求进行中：发送按钮让位给停止按钮。 */
    stoppable?: boolean
    /** 停止请求已发出但流未结束：停止按钮禁用并显示「停止中…」。 */
    stopping?: boolean
    /** 上传单个附件；缺省时「+」保持禁用占位（未连接）。 */
    upload?: (file: File) => Promise<FileRef | null>
  }>(),
  { interactive: false, busy: false, stoppable: false, stopping: false },
)
const emit = defineEmits<{ send: [text: string, files: FileRef[]]; stop: [] }>()
const draft = defineModel<string>({ default: '' })
/* P3-1：占位文案不宣传超出本应用范围的特性（无指令/文件提及语法）。 */
const placeholder = '发消息'

const composing = ref(false)
const textArea = ref<HTMLTextAreaElement | null>(null)
const pendingFiles = ref<FileRef[]>([])
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const canPick = computed(() => props.interactive && !props.busy && !props.stoppable && !uploading.value)
const canSend = computed(() => props.interactive && !props.busy && !props.stoppable && !uploading.value)

function pickFiles(): void {
  if (!canPick.value || !props.upload) return
  fileInput.value?.click()
}

async function onPick(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files || [])
  input.value = ''
  if (!selected.length || !props.upload) return
  uploading.value = true
  try {
    for (const file of selected) {
      const uploaded = await props.upload(file)
      if (uploaded?.id) pendingFiles.value.push(uploaded)
    }
  } finally {
    uploading.value = false
  }
}

function removeFile(index: number): void {
  pendingFiles.value.splice(index, 1)
}

/* composing 只门控键盘路径：点发送是一次明确的提交，不可能是 IME 组词的一部分，
   若沿用该标志，一次丢失的 compositionend（组词期切走焦点等）会让发送永久静默失效。 */
function trySend(force = false): void {
  if (!canSend.value) return
  if (!force && composing.value) return
  const text = draft.value.trim()
  // 控制器要求非空 query（纯附件会被静默丢弃），这里同样要求有文本。
  if (!text) return
  emit('send', text, pendingFiles.value.slice())
  draft.value = ''
  pendingFiles.value = []
}

function onSendClick(): void {
  composing.value = false
  trySend(true)
}

/* 修饰键加速发送（上游 keymap 的 Ctrl/Cmd+Enter → accelerated submit）。 */
function onKeydown(event: KeyboardEvent): void {
  /* IME 组词期的 Enter 属于输入法确认，不拦截也不发送。 */
  if (event.isComposing || composing.value) return
  /* 按住 Enter 连发由 event.repeat 拦截（上游 input/editor keymap 同款守卫）。 */
  if (event.repeat) return
  /* key 大小写不敏感（真实内核 'Enter'，合成事件可能 'enter'）。 */
  const key = event.key.toLowerCase()
  if ((event.metaKey || event.ctrlKey) && key === 'enter') {
    event.preventDefault()
    trySend()
    return
  }
  if (key === 'enter' && !event.shiftKey) {
    event.preventDefault()
    trySend()
  }
}

function onStop(): void {
  emit('stop')
}

/* 近似 Harness 草稿面的自动增高：随内容抬升，滚动上限交给 .scroll 的 14 行帽。 */
function autoGrow(): void {
  const el = textArea.value
  if (el === null) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}
onMounted(autoGrow)
watch(draft, () => nextTick(autoGrow))
</script>

<template>
  <div :class="css.root">
    <div :class="css.card" data-composer-card>
      <!-- 待发送附件：仅安全元数据（名称/类型/大小），无内容访问。 -->
      <div v-if="pendingFiles.length || uploading" class="pi-composer-files" data-testid="composer-files">
        <span
          v-for="(file, index) in pendingFiles"
          :key="file.id || index"
          class="pi-composer-file"
          data-testid="composer-file-chip"
        >
          <span class="pi-composer-file-name">{{ file.name || file.id }}</span>
          <span class="pi-composer-file-meta">
            {{ file.mimeType || file.type || '文件' }} · {{ formatFileSize(file.size) }}
          </span>
          <button
            type="button"
            class="pi-composer-file-remove"
            data-testid="chip-remove"
            :aria-label="`移除 ${file.name || '附件'}`"
            @click="removeFile(index)"
          >
            ×
          </button>
        </span>
        <span v-if="uploading" class="pi-composer-file pi-composer-file-uploading" data-testid="composer-uploading">
          上传中…
        </span>
      </div>
      <div :class="css.scroll" data-input-scroll>
        <div :class="css.grow">
          <textarea
            ref="textArea"
            v-model="draft"
            rows="1"
            :class="[css.input, 'pi-composer-textarea']"
            :data-phase="'inert'"
            aria-label="消息输入"
            :aria-disabled="false"
            @compositionstart="composing = true"
            @compositionend="composing = false"
            @blur="composing = false"
            @keydown="onKeydown"
          />
          <!-- 上游以 CSS 在 IME 组词期隐藏占位（.input[data-composer-composing] +
               .placeholder）；此处在组词期直接不渲染，可观察行为一致。 -->
          <div
            v-if="draft === '' && !composing"
            aria-hidden
            :class="css.placeholder"
            data-composer-placeholder
          >
            {{ placeholder }}
          </div>
        </div>
      </div>
      <div :class="css.row">
        <div :class="css.tools">
          <button
            type="button"
            :class="css.add"
            data-testid="composer-add"
            :aria-label="upload ? '添加附件' : '附件（不可用）'"
            :title="upload ? '添加附件' : '附件（不可用）'"
            :disabled="!canPick"
            @click="pickFiles"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
              <path d="M8 2.75v10.5M2.75 8h10.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>
          <!-- 隐藏 file input 只在交互态渲染；未连接时连 DOM 都不存在。 -->
          <input
            v-if="upload"
            ref="fileInput"
            type="file"
            multiple
            hidden
            data-testid="composer-file-input"
            @change="onPick"
          />
        </div>
        <div :class="css.trailing">
          <button
            v-if="stoppable"
            type="button"
            :class="[css.primary, 'pi-composer-stop']"
            data-testid="composer-stop"
            :aria-label="stopping ? '停止中' : '停止'"
            :title="stopping ? '停止中…' : '停止'"
            :disabled="stopping"
            @click="onStop"
          >
            <!-- 蓝色圆形停止钮内是 16px 圆角方块字形（上游 InputBar.tsx 同款），
                 文案只进 aria-label/title，避免塞满 34px 圆。 -->
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden>
              <rect x="3.5" y="3.5" width="9" height="9" rx="2" fill="currentColor" />
            </svg>
          </button>
          <button
            v-else
            type="button"
            :class="css.primary"
            data-testid="composer-send"
            :aria-label="interactive ? '发送' : '发送（不可用）'"
            :title="interactive ? '发送（Enter）' : '发送（不可用）'"
            :disabled="!canSend"
            @click="onSendClick"
          >
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden>
              <path d="M8.3125 0.980183C8.66767 1.0531 8.97902 1.20418 9.2627 1.43233C9.48724 1.61297 9.73029 1.85793 9.97949 2.10714L14.707 6.83468L13.293 8.24874L9 3.95577V15.0417H7V3.95577L2.70703 8.24874L1.29297 6.83468L6.02051 2.10714C6.26971 1.85793 6.51277 1.61297 6.7373 1.43233C6.97662 1.23986 7.28445 1.04402 7.6875 0.980183C7.8973 0.947006 8.1031 0.95516 8.3125 0.980183Z" fill="currentColor" />
            </svg>
          </button>
        </div>
      </div>
    </div>
    <!-- 上游 .dock 预留一行统计读数（22px），卡片底距由此产生；
         tok/s 等统计不在本票范围，仅保留占位行。 -->
    <div :class="css.dock" data-composer-dock />
  </div>
</template>

<style>
/* 组件自有（非 vendor）：textarea 是替换 Lexical 的文本面，补齐其作为表单控件
   的默认判定，使其贴合 .input 类所描述的块级草稿面。 */
.pi-composer-textarea {
  display: block;
  width: 100%;
  border: none;
  resize: none;
  background: transparent;
  overflow: hidden;
}

/* 组件自有（非 vendor）：待发送附件 chips（安全元数据：名称/类型/大小）。 */
.pi-composer-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px 0;
}

.pi-composer-file {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 3px 8px;
  border: 0.5px solid var(--dsw-alias-border-l3);
  border-radius: var(--dsw-radius-sm);
  background: var(--dsw-alias-interactive-bg-hover);
  font-size: 12px;
  line-height: 18px;
  color: var(--dsw-alias-label-secondary);
}

.pi-composer-file-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dsw-alias-label-primary);
}

.pi-composer-file-meta {
  white-space: nowrap;
}

.pi-composer-file-remove {
  flex: none;
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--dsw-alias-label-tertiary);
  font-size: 12px;
  line-height: 16px;
  cursor: pointer;
}

@media (hover: hover) {
  .pi-composer-file-remove:hover {
    background: var(--dsw-alias-interactive-bg-hover);
    color: var(--dsw-alias-label-primary);
  }
}

/* 停止按钮沿用发送按钮的几何（.primary 类），字形为 16px 圆角方块（同上游）。 */
.pi-composer-stop svg {
  pointer-events: none;
}
</style>
