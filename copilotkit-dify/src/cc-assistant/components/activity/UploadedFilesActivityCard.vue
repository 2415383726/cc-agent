<template>
  <div v-if="files.length" class="uploaded-files-container">
    <div class="uploaded-files-header">
      <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path
          d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48" />
      </svg>
      <span>附件 ({{ files.length }})</span>
    </div>

    <div class="uploaded-files-list">
      <div v-for="file in files" :key="file.key" class="file-item">
        <!-- 左侧精美的文件图标 -->
        <div class="file-icon-wrapper">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M7 18H17V16H7V18Z" fill="currentColor" fill-opacity="0.5" />
            <path d="M7 14H13V12H7V14Z" fill="currentColor" fill-opacity="0.5" />
            <path
              d="M14 2H6C4.89543 2 4 2.89543 4 4V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V8L14 2Z"
              stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M14 2V8H20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"
              stroke-linejoin="round" />
          </svg>
        </div>

        <!-- 中间文件信息 -->
        <div class="file-main">
          <span class="file-name" :title="file.name">{{ file.name }}</span>
          <span class="file-meta">
            {{ formatFileType(file.type || file.mimeType) }}
            <span class="dot-divider">·</span>
            {{ formatFileSize(file) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, unref } from 'vue'
import { normalizeFileView } from '../../lib/fileView'

const props = defineProps<{
  content?: any
}>()

const difyBaseUrl = inject<any>('difyBaseUrl', '')
const files = computed(() => {
  const rawFiles = Array.isArray(props.content?.files) ? props.content.files : []
  return rawFiles.map((file: any, index: number) => normalizeFileView(file, index, String(unref(difyBaseUrl) || '')))
})

// 辅助方法：美化文件类型显示
const formatFileType = (type: string) => {
  if (!type || type === 'file') return 'File'
  if (type.includes('word') || type.includes('document')) return 'Document'
  if (type.includes('pdf')) return 'PDF'
  if (type.includes('image')) return 'Image'
  if (type.includes('spreadsheet') || type.includes('excel')) return 'Spreadsheet'
  return type.split('/')[1]?.toUpperCase() || 'File'
}

// 辅助方法：更强健的文件大小转换（修复 bytes 显示问题）
const formatFileSize = (file: any) => {
  let numBytes = Number(file.size)

  // 如果 file.size 不存在，尝试从 "393326 bytes" 这种 sizeLabel 字符串中提取数字
  if (isNaN(numBytes) || numBytes === 0) {
    if (typeof file.sizeLabel === 'string') {
      const match = file.sizeLabel.match(/\d+/)
      if (match) numBytes = Number(match[0])
    }
  }

  // 如果实在提取不到，返回原始标签或 0 B
  if (isNaN(numBytes) || numBytes === 0) return file.sizeLabel || '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(numBytes) / Math.log(k))
  return parseFloat((numBytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}
</script>

<style scoped>
/* 核心修改：靠右对齐的容器 */
.uploaded-files-container {
  margin-top: 8px;
  margin-bottom: 8px;

  /* ---- 让容器靠右的魔法 ---- */
  margin-left: auto;
  /* 块级元素靠右 */
  align-self: flex-end;
  /* 兼容父级是 Flex 的情况 */
  width: fit-content;
  /* 宽度包裹内容，不占满全屏 */
  min-width: 280px;
  /* 设置最小宽度，防止文件名太短时卡片过窄 */
  max-width: 85%;
  /* 设置最大宽度（给左侧留出空白，像聊天气泡一样） */
  /* -------------------------- */
}

/* 顶部标题区 */
.uploaded-files-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 8px;
  padding-left: 2px;
}

.header-icon {
  width: 14px;
  height: 14px;
}

.uploaded-files-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 单个文件卡片 */
.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  transition: border-color 0.2s ease, background-color 0.2s ease, color 0.2s ease;
  cursor: pointer;
  /* 加上手指指针，暗示可点击 */
}

.file-item:hover {
  background: #ffffff;
  border-color: #cbd5e1;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}

/* 图标容器 */
.file-icon-wrapper {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: #eff6ff;
  color: #3b82f6;
  border-radius: 8px;
}

.file-icon-wrapper svg {
  width: 20px;
  height: 20px;
}

/* 中间文字区 */
.file-main {
  flex: 1;
  min-width: 0;
  /* 必须保留，保证长文本能正确出现省略号 */
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}

/* 文件名：单行截断 */
.file-name {
  font-size: 13.5px;
  font-weight: 500;
  color: #0f172a;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Meta信息 */
.file-meta {
  font-size: 11.5px;
  color: #64748b;
  line-height: 1.2;
  display: flex;
  align-items: center;
  gap: 4px;
}

.dot-divider {
  font-size: 14px;
  opacity: 0.5;
}
</style>