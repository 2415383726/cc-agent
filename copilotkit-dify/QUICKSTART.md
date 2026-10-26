# CcDifyAssistant 快速接入

把 `CcDifyAssistant` 放进已有 Vue 3 系统后，宿主只传 Dify 连接参数即可。默认首页能力已内置，不传 `catalog`。

## 1. 复制文件

保持目录结构复制到宿主 `src/`：

```text
src/cc-assistant/components/
src/cc-assistant/lib/
src/cc-assistant/styles/
src/cc-assistant/charts/
```

不要复制 demo 的 `src/style.css`，它会污染宿主的 `body/#app/button/input` 样式。

## 2. 安装依赖

版本必须精确 pin：

```bash
npm install @copilotkit/vue@1.57.4 @ag-ui/client@0.0.53 @ag-ui/core@0.0.53 rxjs@7.8.1 zod@3.25.76 echarts mermaid
```

如果宿主还没装 Vue：

```bash
npm install vue@3.5.12
```

## 3. 引入样式

在入口文件导入：

```ts
import '@copilotkit/vue/styles.css'
import './cc-assistant/styles/assistant-vars.css'
import './cc-assistant/styles/assistant.css'
```

如果宿主配置了 `@` 指向 `src`，也可以写成：

```ts
import '@/cc-assistant/styles/assistant-vars.css'
import '@/cc-assistant/styles/assistant.css'
```

没有 `@` 别名就用相对路径：

```ts
import './cc-assistant/styles/assistant-vars.css'
import './cc-assistant/styles/assistant.css'
```

`assistant-vars.css` 管 `--cc-agent-*` 变量，改主题色、边框色、文字色优先改这里。

`assistant.css` 管助手 class 样式，改抽屉、侧边栏、输入框、卡片布局改这里。

## 4. 挂载组件

```vue
<script setup lang="ts">
import { ref } from 'vue'
import CcDifyAssistant from './cc-assistant/components/CcDifyAssistant.vue'

const assistantRef = ref<InstanceType<typeof CcDifyAssistant> | null>(null)

async function askAssistant(text: string) {
  await assistantRef.value?.launchWithMessage(text)
}
</script>

<template>
  <CcDifyAssistant
    ref="assistantRef"
    :dify="{
      baseUrl: 'https://your-dify.example/v1',
      apiKey: 'app-xxx',
      user: 'user-001',
      token: 'agent-token'
    }"
    title="系统助手"
    storage-key-prefix="cadre-system-assistant"
    :ui="{ drawerWidth: '72vw', drawerMaxWidth: '1180px', defaultSidebarCollapsed: true }"
  />
</template>
```

JavaScript 项目把类型标注去掉：`lang="ts"`、`InstanceType<...>`、`: string`、`import type ...` 都不要复制。

## 5. 接宿主输入框

宿主自己的输入框回车时调用：

```ts
await assistantRef.value?.launchWithMessage(inputText)
```

组件会自动打开抽屉、创建新会话并发送消息。用户不需要在抽屉里二次输入。

## 6. 结构化回答和 UserPrompt 已自动接入

复制整个 `src/cc-assistant/` 后，不需要在宿主项目额外注册 renderer 或解析特殊标记：

- assistant Markdown 中的 `cc-record`、`cc-table`、`cc-compare`、`cc-timeline` fenced JSON 会自动渲染为业务结果面；
- `cc-chart` 与 Mermaid 继续按现有协议渲染；
- AG-UI `UserPrompt` interrupt 会自动显示选择器或富表单，并在提交后继续当前 agent；
- 旧 `cc-ui` fence 不兼容，会作为普通代码显示。

确保复制时包含 `components/generated-ui/`、`components/chat/InterruptCard.vue`、`lib/structuredContent.ts` 和 `lib/question.ts`；它们已经位于上述目录结构内，不需要单独配置。

后端输出约定：普通说明优先使用 Markdown；单一对象用 `cc-record`，同构列表用 `cc-table`，2–4 个对象比较用 `cc-compare`，真实时间事件用 `cc-timeline`。需要用户补充多个相关字段时使用 `UserPrompt.fields`，不要在 Markdown 中模拟表单。

流式生成结构化卡片时，前端会在 fence 闭合前显示轻量占位，并在闭合后一次性校验和渲染卡片；已完成卡片不会因后续 token 重复解析。建议每张卡片独立输出一个完整 fence，避免把大批量原始数据直接塞入消息。

更多配置见 [README.md](./README.md)。
