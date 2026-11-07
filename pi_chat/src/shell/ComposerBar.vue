<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import css from '../vendor/dsh/ui-conversation/src/client/skeleton/InputBar.module.css'

/*
 * DOM 蓝图：ui-conversation skeleton/InputBar.tsx 的 .root > .card
 * （data-composer-card）> .scroll（data-input-scroll）> .grow > 文本面 +
 * .placeholder（data-composer-placeholder），随后 .row > .tools/.trailing。
 * Lexical 属取材黑名单：文本面用原生 <textarea> 承接同一组 .input 类；
 * textarea 特有判定（block、去边框、去 resize）在组件自有 .pi-composer-textarea。
 * 发送按钮与附件「+」均为视觉占位：发送禁用（逻辑留待后续票据），附件不接逻辑。
 */
const draft = defineModel<string>({ default: '' })
const placeholder = '发消息或创建任务，/ 调用指令，@ 文件或对话'

const composing = ref(false)
const textArea = ref<HTMLTextAreaElement | null>(null)

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
            aria-label="附件与指令（后续票据启用）"
          >
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
              <path d="M8 2.75v10.5M2.75 8h10.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            </svg>
          </button>
        </div>
        <div :class="css.trailing">
          <button
            type="button"
            :class="css.primary"
            data-testid="composer-send"
            aria-label="发送（回放模式占位）"
            disabled
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
</style>
