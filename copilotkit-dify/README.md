# copilotkit-dify

`copilotkit-dify` 是一个 Vue 3 侧边栏系统助手组件。它把 Dify `/chat-messages` SSE 输出包装成 CopilotKit/AG-UI 前端体验，并提供可复制接入的 `CcDifyAssistant`。

只想接入请先看：[QUICKSTART.md](./QUICKSTART.md)。

## 它负责什么

- 悬浮按钮和抽屉侧边栏
- 抽屉内首页默认能力卡片和 `/` 命令面板
- Dify 会话历史、多会话 thread、运行中状态
- 工具调用、技能、权限确认、文件产物等 AG-UI activity 渲染
- `launchWithMessage()`，让宿主业务输入框一键打开抽屉并发起对话

它不包含宿主业务首页，也不要求宿主页面使用本仓库 demo 的布局。

## 推荐文件结构

宿主项目建议保持本仓库目录结构，把封装代码整体放在 `src/cc-assistant/` 下，避免 `ActivityCard.vue`、`ConversationSidebar.vue` 这类通用文件名和业务组件重名：

```text
src/cc-assistant/components/
src/cc-assistant/lib/
src/cc-assistant/styles/
src/cc-assistant/charts/
```

`src/style.css` 是本仓库 demo 专用样式，不属于组件接入清单。

## Public API

```vue
<CcDifyAssistant
  ref="assistantRef"
  :dify="{
    baseUrl: 'https://your-dify.example/v1',
    apiKey: 'app-xxx',
    user: currentUserId,
    token: agentAuthToken,
    inputs: {
      tenantId: currentTenantId
    }
  }"
  title="系统助手"
  storage-key-prefix="cadre-system-assistant"
/>
```

### Props

```ts
interface CcDifyAssistantProps {
  dify: {
    baseUrl: string
    apiKey: string
    user: string
    token?: string
    inputs?: Record<string, unknown>
  }
  catalog?: AssistantCatalog
  title?: string
  storageKeyPrefix?: string
  ui?: {
    drawerWidth?: string
    drawerMaxWidth?: string
    defaultSidebarCollapsed?: boolean
  }
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `dify.baseUrl` | 是 | Dify API 地址，例如 `https://your-dify.example/v1` |
| `dify.apiKey` | 是 | Dify App API Key，当前方案是前端直连 Dify |
| `dify.user` | 是 | Dify user 标识，建议用业务系统当前用户 ID |
| `dify.token` | 否 | agent 鉴权信息，会作为 `inputs.token` 传给后端 |
| `dify.inputs` | 否 | 宿主业务字段，原样透传给 Dify `inputs` |
| `catalog` | 否 | 自定义首页能力、推荐问题、slash 面板；不传则使用内置默认能力 |
| `title` | 否 | 抽屉标题，默认 `系统助手` |
| `storageKeyPrefix` | 否 | 悬浮按钮位置 localStorage 前缀 |
| `ui` | 否 | 仅控制抽屉宽度、最大宽度和历史栏默认折叠状态 |

宿主视角只需要关心：连哪里 `baseUrl`，你是谁 `apiKey + user`，agent 鉴权 `token`，以及可选的业务字段 `inputs`。

不要把 `show_tool_calls`、`capability_mode`、`app_skills_yaml`、`state_id` 暴露给宿主业务系统；这些属于后端 CC Agent/Dify 应用内部配置。

### 暴露方法

```ts
type LaunchWithMessage = (
  text: string,
  options?: {
    files?: File[]
    selectedSkill?: AssistantSkill | null
  }
) => Promise<boolean>
```

宿主输入框回车时：

```ts
await assistantRef.value?.launchWithMessage(inputText)
```

组件内部会打开抽屉、创建新 draft thread、挂载文件、追加用户消息并运行 agent。

## 默认能力

不传 `catalog` 时，组件使用干部人才场景默认能力：

| name | label |
| --- | --- |
| `leadership-team-analysis` | 班子分析 |
| `personnel-comparison` | 人员对比 |
| `role-fit-analysis` | 人岗匹配 |
| `policy-research` | 政策研究 |
| `advanced-talent-search` | 高级检索 |
| `text-proofreading` | 文字校对 |

这些 `name` 会用于 slash query，例如：

```text
/role-fit-analysis 帮我判断这名干部适合哪些岗位
```

前端 catalog 只负责展示和拼接 slash 文本，不会自动安装后端 skill。后端必须已经能识别对应 skill。

## 自定义 Catalog

```ts
interface AssistantCatalog {
  commands?: AssistantCommand[]
  skills?: AssistantSkill[]
  suggestedQuestions?: Array<string | SuggestedQuestion>
}

interface AssistantSkill {
  kind?: 'skill'
  name: string
  label?: string
  description?: string
  category?: string
  icon?: AssistantIconName
}
```

规则：

- `skills[].name` 必填，必须和后端 CC Agent skill 名称一致。
- `label` 缺省时使用 `name`。
- `description` 可为空。
- `category` 缺省为 `技能`。
- `icon` 缺省或未知时 fallback 到 `skill`。
- `commands` 不传时默认保留 `/help /status /context /compact /reset`。
- `suggestedQuestions` 可以是字符串，也可以是 `{ title, message }`。

当前内置图标：

```text
file-text
chart
mail
pen
target
feedback
checklist
skill
```

## 样式边界

宿主只导入：

```ts
import '@copilotkit/vue/styles.css'
import './cc-assistant/styles/assistant-vars.css'
import './cc-assistant/styles/assistant.css'
```

如果宿主配置了 `@` 指向 `src`，可以改成 `@/cc-assistant/styles/...`。如果没有配置 `@`，必须使用相对路径或宿主自己的别名。

`assistant-vars.css` 只放 `--cc-agent-*` CSS 变量。变量冲突或想换主题色时，优先改这个文件。

`assistant.css` 只放助手组件 class 样式，例如 `.ai-drawer`、`.drawer-*`、`.conversation-sidebar-*`、`.assistant-composer-*`、`.home-catalog-*`。组件布局、边框、间距在这里改。

不要把 demo 的 `src/style.css` 导入宿主项目。它包含 `body`、`#app`、按钮、输入框和调试配置面板样式，会污染宿主。

## 文件上传

```ts
await assistantRef.value?.launchWithMessage('总结这些附件', {
  files: selectedFiles,
})
```

组件会通过当前 Dify agent 上传文件，再把 Dify 文件引用附到用户消息上。

## 结构化回答与用户补充信息

普通结论、摘要、建议和操作说明仍使用 Markdown。只有结构化内容确实更易读时，assistant 消息才可混排以下 fenced JSON 协议：

| 内容形态 | 协议 | 适用场景 |
| --- | --- | --- |
| 单个业务对象 | `cc-record` | 人员、项目、订单、政策、事项等分组字段 |
| 同构结果集合 | `cc-table` | 共享列定义的名单、检索结果、统计明细 |
| 少量对象横向研判 | `cc-compare` | 2–4 个对象按相同维度比较 |
| 真实时间事件 | `cc-timeline` | 审批记录、履历、政策沿革、项目里程碑 |
| 定量趋势 | `cc-chart` | 图表协议保持现有行为 |
| 图形关系 | `mermaid` | Mermaid 协议保持现有行为 |

前端会严格校验 `cc-record`、`cc-table`、`cc-compare`、`cc-timeline` 的 version 1 JSON。未知字段、非法 JSON 和已移除的 `cc-ui` 协议都会作为普通代码块保留显示，不会静默丢失回答内容。

需要用户补充信息、选择、确认或审批时，后端应发出 AG-UI `UserPrompt` interrupt，而不是在最终回答中伪造表单卡片。组件会自动渲染：

- 简单单选、多选与自定义输入；
- 分组的业务表单字段：文本、长文本、下拉、多选、单选、日期、日期范围、日期时间、数字、邮箱、电话和确认框；
- 必填、默认值、选项说明、数值范围、单位前后缀与提交校验。

提交后会在当前会话恢复 agent，恢复 payload 同时包含结构化 `values` 与便于模型理解的可读 `answer`。表单本身不会直接调用业务 API；业务写入仍必须经过 agent 工具权限或审批流程。

### 流式生成性能

当回答连续生成多张结构化卡片时，组件会缓存已完成卡片的已校验结果，并跳过稳定内容的重复渲染。未闭合的 `cc-record`、`cc-table`、`cc-compare`、`cc-timeline` fence 会显示轻量占位，不会把持续增长的 JSON 交给 Markdown 渲染器；收到结束 fence 后才进行一次正式解析和渲染。

因此接入方应让每张结构化卡片输出完整、独立的 fenced JSON。不要把超大 JSON、HTML、回调、URL 或业务操作指令塞进结构化协议；大批量数据宜先收窄查询范围或使用摘要与后续检索。

相关实现位于：

- `src/cc-assistant/lib/structuredContent.ts`
- `src/cc-assistant/components/generated-ui/GeneratedUiAssistantMessage.vue`
- `src/cc-assistant/components/chat/InterruptCard.vue`

## 悬浮按钮

- 点击打开抽屉。
- 拖动后只吸附到浏览器窗口左侧或右侧。
- 移动小于 `6px` 视为点击；达到阈值后视为拖动。
- 位置持久化到 `${storageKeyPrefix}:floating-dock`。

每个业务系统建议使用自己的 `storage-key-prefix`。

## 会话与运行态

组件内部维护：

- `activeThreadKey`
- `conversationThreadKeys`
- `loadedConversationsByThreadKey`
- `runningThreadKeys`
- `pendingHistoryLoad`

关键行为：

- 新会话使用本地 `draft:<uuid>` thread。
- 已有 Dify 会话使用 `conversation:<conversationId>` thread。
- Dify 首次返回真实 `conversation_id` 后，只建立映射，不中途切 thread。
- 切换会话不会把 B 会话历史灌进 A thread。
- 历史列表里当前页面内正在回复的会话会显示 spinner。
- 刷新页面后默认仍是首页，不自动打开最近会话。

运行态只表示当前浏览器页面生命周期内的前端运行状态，不是 Dify 服务端全局任务状态。

## Dify / 后端要求

- `/chat-messages` 可用。
- `apiKey` 对应 App 能处理当前 query。
- 如果使用 CC Agent AG-UI 输出，后端需要输出前端能识别的 AG-UI activity。
- `catalog.skills[].name` 对应的 skill 已在后端可用。
- `token` 如果传入，会作为 `inputs.token` 给后端鉴权逻辑使用。
- `inputs` 里的业务字段由后端自行解释，例如 `tenantId`、`module`、`orgId`。

## TypeScript 和 JavaScript 宿主

本仓库源码用 TypeScript。TypeScript 宿主可直接使用示例中的 `InstanceType<typeof CcDifyAssistant>` 和 `AssistantSkill` 类型。

JavaScript 宿主删除类型标注即可：

```js
const assistantRef = ref(null)
await assistantRef.value?.launchWithMessage(text)
```

不要复制 `import type ...`、`KeyboardEvent`、`File[]`、`InstanceType<...>` 这类 TS 写法到纯 JS 文件里。

## 常见问题

### apiKey 放前端安全吗？

当前方案是前端直连 Dify，所以 `apiKey` 会在浏览器侧可见。如果业务要求更严格，应在宿主系统后面加一层代理，由代理持有 Dify API Key。

### report/chart 是什么？

report/chart 是标准渲染能力，随 `src/cc-assistant/` 一起复制。`AssistantReportMessage.vue`、`InlineFigure.vue`、`lib/chartMarkdown.ts` 和 `charts/chartTemplates.ts` 用于渲染报告里的内联图表。

当前图表模板是轻量实现，支持 `line/bar/pie/table`，不依赖 ECharts 或 Chart.js。

### 升级 CopilotKit 后 tool renderer 类型报错怎么办？

当前代码按 `@copilotkit/vue@1.57.4` 验证。`DrawerExperience.vue` 在注册 `useRenderTool/useDefaultRenderTool` 时已经对 tool card render 做了 `as any` 兼容处理，避免 CopilotKit minor 版本中的 status 类型差异影响宿主编译。

如果宿主自行升级 CopilotKit，需要重新跑类型检查和构建；优先保持 `@copilotkit/vue`、`@ag-ui/*`、`rxjs`、`zod` 与 [QUICKSTART.md](./QUICKSTART.md) 的依赖版本一致。

## Demo 调试

本仓库 [src/App.vue](./src/App.vue) 只是 demo 壳：

- 显示连接配置面板。
- 读取 `public/cc-agent-home-catalog.json`。
- 挂载 `CcDifyAssistant`。

业务系统接入时，不需要复制这个调试面板。

## 开发验证

```bash
npm run test
npm run build
```
